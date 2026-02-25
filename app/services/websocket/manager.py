import asyncio
from typing import List, Dict, Any, TYPE_CHECKING

from fastapi import WebSocket




# System topics that should not be listed in the /topics endpoint
SYSTEM_TOPICS = {
    "system_status",  # Real-time node status updates
}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._interceptors: Dict[str, List[asyncio.Future]] = {}

    def register_topic(self, topic: str):
        """Pre-registers a topic so it appears in the topic list even with no active connections."""
        if topic not in self.active_connections:
            self.active_connections[topic] = []

    def unregister_topic(self, topic: str):
        """Removes a topic completely and cleans up any tracking."""
        if topic in self.active_connections:
            del self.active_connections[topic]
        if topic in self._interceptors:
            del self._interceptors[topic]

    def has_subscribers(self, topic: str) -> bool:
        """Returns True if there are active websocket connections OR active interceptors listening to this topic."""
        has_ws = bool(self.active_connections.get(topic))
        has_interceptors = bool(self._interceptors.get(topic))
        
        return has_ws or has_interceptors


    def reset_active_connections(self):
        self.active_connections.clear()
        self._interceptors.clear()

    async def connect(self, websocket: WebSocket, topic: str):
        await websocket.accept()
        if topic not in self.active_connections:
            self.active_connections[topic] = []
        self.active_connections[topic].append(websocket)

    def disconnect(self, websocket: WebSocket, topic: str):
        if topic in self.active_connections:
            try:
                self.active_connections[topic].remove(websocket)
            except ValueError:
                pass

    async def broadcast(self, topic: str, message: Any):
        
        # Handle active websocket connections
        if topic in self.active_connections:
            for connection in self.active_connections[topic]:
                if getattr(connection, '_is_sending', False):
                    # Drop this frame for this specific client to avoid blocking the backend 
                    # and prevent Starlette "Concurrent call to send" RuntimeError.
                    continue
                    
                async def _send(conn=connection, msg=message):
                    conn._is_sending = True
                    try:
                        if isinstance(msg, bytes):
                            await conn.send_bytes(msg)
                        else:
                            await conn.send_json(msg)
                    except Exception:
                        try:
                            self.active_connections[topic].remove(conn)
                        except ValueError:
                            pass
                    finally:
                        conn._is_sending = False
                            
                # Fire and forget instead of awaiting sequentially
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
