"""WebSocket endpoint handlers - Pure business logic without routing configuration."""

import asyncio
from fastapi import WebSocket, WebSocketDisconnect, Response, HTTPException
from typing import List, Dict
from pydantic import BaseModel

from app.services.websocket.manager import manager


class TopicsResponse(BaseModel):
    """Response for listing available WebSocket topics."""
    topics: List[str]
    description: Dict[str, str]


async def list_topics():
    """Returns available websocket topics (excluding system topics)"""
    return TopicsResponse(
        topics=manager.get_public_topics(),
        description={
            "processed_points": "Stream of preprocessed data with algorithm results"
        }
    )


async def capture_frame(topic: str):
    """
    Capture a single frame from a WebSocket topic.
    
    Args:
        topic: WebSocket topic to capture from
    
    Returns:
        Binary frame data as application/octet-stream
    """
    try:
        data = await manager.wait_for_next(topic, timeout=5.0)
        return Response(content=data, media_type="application/octet-stream")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout waiting for frame")
    except asyncio.CancelledError:
        raise HTTPException(status_code=503, detail="Topic was removed while waiting for frame. Please retry.")


async def websocket_endpoint(websocket: WebSocket, topic: str):
    """WebSocket endpoint for real-time data streaming."""
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