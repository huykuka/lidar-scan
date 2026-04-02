import asyncio
from typing import List, Dict, Any

from fastapi import WebSocket

# System topics that should not be listed in the /topics endpoint
SYSTEM_TOPICS = {
    "output",
    "system_status",  # Real-time node status updates
}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._interceptors: Dict[str, List[asyncio.Future]] = {}
        self._write_locks: Dict[int, asyncio.Lock] = {}

    def register_topic(self, topic: str):
        """Pre-registers a topic so it appears in the topic list even with no active connections."""
        topic = topic.lower()
        if topic not in self.active_connections:
            self.active_connections[topic] = []

    async def unregister_topic(self, topic: str) -> None:
        """
        Fully unregisters a topic:
        - Closes all active WebSocket connections with a 1001 Going Away code.
        - Resolves (cancels) all pending interceptor futures with cancellation.
        - Removes the topic from all tracking dicts.
        - Method is idempotent when called on non-existent topics.
        """
        # 1. Gracefully close all live WebSocket connections
        connections = self.active_connections.pop(topic, [])
        if connections:
            close_coros = []
            for ws in connections:
                async def close_ws(websocket=ws):
                    try:
                        await websocket.close(code=1001)
                    except Exception:
                        # Already closed or errored — ignore
                        pass

                close_coros.append(close_ws())

            # Close all connections in parallel
            await asyncio.gather(*close_coros, return_exceptions=True)

        # 2. Cancel/resolve all pending interceptors for this topic
        futures = self._interceptors.pop(topic, [])
        for future in futures:
            if not future.done():
                future.cancel()  # CancelledError propagates to the awaiter

    def has_subscribers(self, topic: str) -> bool:
        """Returns True if there are active websocket connections OR active interceptors listening to this topic."""
        has_ws = bool(self.active_connections.get(topic))
        has_interceptors = bool(self._interceptors.get(topic))

        return has_ws or has_interceptors

    def reset_active_connections(self):
        self.active_connections.clear()
        self._interceptors.clear()
        self._write_locks.clear()

    async def connect(self, websocket: WebSocket, topic: str):
        await websocket.accept()
        if topic not in self.active_connections:
            self.active_connections[topic] = []
        self.active_connections[topic].append(websocket)
        self._write_locks[id(websocket)] = asyncio.Lock()

    def disconnect(self, websocket: WebSocket, topic: str):
        if topic in self.active_connections:
            try:
                self.active_connections[topic].remove(websocket)
            except ValueError:
                pass
        self._write_locks.pop(id(websocket), None)

    async def broadcast(self, topic: str, message: Any):

        # Handle active websocket connections
        if topic in self.active_connections:
            for connection in self.active_connections[topic]:
                lock = self._write_locks.get(id(connection))
                if lock is None:
                    continue
                if lock.locked():
                    continue

                async def _send(conn=connection, msg=message, wlock=lock):
                    try:
                        async with wlock:
                            if isinstance(msg, bytes):
                                await conn.send_bytes(msg)
                            else:
                                await conn.send_json(msg)
                    except Exception:
                        try:
                            self.active_connections[topic].remove(conn)
                        except (ValueError, KeyError):
                            pass
                        self._write_locks.pop(id(conn), None)

                asyncio.create_task(_send())

        # Handle pending interceptors (for HTTP capture etc)
        if topic in self._interceptors:
            futures = self._interceptors.pop(topic)
            for future in futures:
                if not future.done():
                    future.set_result(message)

    async def wait_for_next(self, topic: str, timeout: float = 5.0) -> Any:
        """Waits for the next message broadcast on a specific topic."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        if topic not in self._interceptors:
            self._interceptors[topic] = []
        self._interceptors[topic].append(future)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            # Cleanup on timeout
            if topic in self._interceptors and future in self._interceptors[topic]:
                self._interceptors[topic].remove(future)
            raise

    def get_public_topics(self) -> List[str]:
        """Returns list of topics excluding system topics."""
        return sorted([
            topic for topic in self.active_connections.keys()
            if topic not in SYSTEM_TOPICS
        ])


manager = ConnectionManager()
