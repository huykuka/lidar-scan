"""WebSocket endpoint handlers - Pure business logic without routing configuration."""

import asyncio
from typing import List, Dict

from fastapi import WebSocket, WebSocketDisconnect, Response, HTTPException
from pydantic import BaseModel

from app.services.websocket.manager import manager


class TopicInfo(BaseModel):
    """A single WebSocket topic with its node category."""
    topic: str
    category: str


class TopicsResponse(BaseModel):
    """Response for listing available WebSocket topics."""
    topics: List[TopicInfo]
    description: Dict[str, str]


async def list_topics():
    """Returns available websocket topics (excluding system topics)"""
    return TopicsResponse(
        topics=[TopicInfo(**t) for t in manager.get_public_topics()],
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


DISCOVERY_TOPIC = "device_discovery"


def _discovery_token_valid(websocket: WebSocket) -> bool:
    """device_discovery requires a valid JWT via ?token= (browsers cannot set WS headers)."""
    from app.api.v1.auth.service import decode_access_token, get_user_by_id

    token = websocket.query_params.get("token")
    if not token:
        return False
    try:
        payload = decode_access_token(token)
        return get_user_by_id(payload["sub"]) is not None
    except Exception:
        return False


async def _send_discovery_snapshot(websocket: WebSocket) -> None:
    from app.api.v1.discovery.service import send_snapshot

    lock = manager._write_locks.get(id(websocket))
    if lock is None:
        return
    async with lock:
        await send_snapshot(websocket)


_PING_INTERVAL = 20  # seconds — must be shorter than any proxy idle timeout


async def websocket_endpoint(websocket: WebSocket, topic: str):
    """WebSocket endpoint for real-time data streaming."""
    if topic == DISCOVERY_TOPIC and not _discovery_token_valid(websocket):
        await websocket.close(code=4401)
        return
    await manager.connect(websocket, topic)
    try:
        if topic == DISCOVERY_TOPIC:
            await _send_discovery_snapshot(websocket)
        while True:
            try:
                # Wait for a client message; time out to send a keepalive ping.
                msg = await asyncio.wait_for(websocket.receive(), timeout=_PING_INTERVAL)
                if msg.get("type") == "websocket.disconnect":
                    break
            except asyncio.TimeoutError:
                # No client activity — send a ping frame to keep the TCP session
                # alive through proxies and NAT gateways.
                await websocket.send_text("ping")
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Starlette raises if receive() is called after disconnect.
        pass
    finally:
        manager.disconnect(websocket, topic)
