from typing import List, Dict, Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

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


manager = ConnectionManager()
