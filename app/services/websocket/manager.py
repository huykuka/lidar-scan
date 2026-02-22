import asyncio
from typing import List, Dict, Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._interceptors: Dict[str, List[asyncio.Future]] = {}

    def register_topic(self, topic: str):
        """Pre-registers a topic so it appears in the topic list even with no active connections."""
        if topic not in self.active_connections:
            self.active_connections[topic] = []


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
            dead_connections = []
            for connection in self.active_connections[topic]:
                try:
                    if isinstance(message, bytes):
                        await connection.send_bytes(message)
                    else:
                        await connection.send_json(message)
                except Exception:
                    dead_connections.append(connection)

            for dead in dead_connections:
                self.active_connections[topic].remove(dead)

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


manager = ConnectionManager()
