from fastapi import WebSocket, HTTPException
from typing import List, Dict
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "raw_points": [],
            "processed_points": []
        }

    async def connect(self, websocket: WebSocket, topic: str):
        if topic not in self.active_connections:
            raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
        await websocket.accept()
        self.active_connections[topic].append(websocket)

    def disconnect(self, websocket: WebSocket, topic: str):
        if topic in self.active_connections:
            try:
                self.active_connections[topic].remove(websocket)
            except ValueError:
                pass

    async def broadcast(self, topic: str, message: dict):
        if topic in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[topic]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.append(connection)
            
            for dead in dead_connections:
                self.active_connections[topic].remove(dead)

manager = ConnectionManager()
