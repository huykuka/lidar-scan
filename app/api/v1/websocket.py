from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket.manager import manager

router = APIRouter()

@router.get("/topics")
async def list_topics():
    """Returns available websocket topics (excluding system topics)"""
    return {
        "topics": manager.get_public_topics(),
        "description": {
            "raw_points": "Stream of raw point cloud data (sub-sampled for performance)",
            "processed_points": "Stream of preprocessed data with algorithm results"
        }
    }

@router.get("/topics/capture")
async def capture_frame(topic: str):
    import asyncio
    from fastapi import Response, HTTPException
    try:
        data = await manager.wait_for_next(topic, timeout=5.0)
        return Response(content=data, media_type="application/octet-stream")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout waiting for frame")

@router.websocket("/ws/{topic}")
async def websocket_endpoint(websocket: WebSocket, topic: str):
    await manager.connect(websocket, topic)
    try:
        while True:
            # Keep connection open; client may not send messages.
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Starlette raises if receive() is called after disconnect.
        pass
    finally:
        manager.disconnect(websocket, topic)
