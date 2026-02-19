from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket.manager import manager

router = APIRouter()

@router.get("/topics")
async def list_topics():
    """Returns available websocket topics"""
    return {
        "topics": list(manager.active_connections.keys()),
        "description": {
            "raw_points": "Stream of raw point cloud data (sub-sampled for performance)",
            "processed_points": "Stream of preprocessed data with algorithm results"
        }
    }

@router.websocket("/ws/{topic}")
async def websocket_endpoint(websocket: WebSocket, topic: str):
    await manager.connect(websocket, topic)
    try:
        while True:
            # Keep connection alive and wait for client messages if any
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, topic)
