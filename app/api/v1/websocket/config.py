"""WebSocket router configuration and endpoint metadata."""

from fastapi import APIRouter, WebSocket
from .handlers import list_topics, capture_frame, websocket_endpoint, TopicsResponse


# Router configuration
router = APIRouter(tags=["Topics"])

# Endpoint configurations
@router.get(
    "/topics",
    response_model=TopicsResponse,
    summary="List Topics",
    description="Returns available WebSocket topics (excluding system topics).",
)
async def topics_list_endpoint():
    return await list_topics()


@router.get(
    "/topics/capture",
    responses={
        200: {"description": "Binary frame data", "content": {"application/octet-stream": {}}},
        503: {"description": "Topic was removed while waiting for frame"},
        504: {"description": "Timeout waiting for frame"}
    },
    summary="Capture Frame",
    description="Capture a single frame from a WebSocket topic as HTTP response.",
)
async def topic_capture_endpoint(topic: str):
    return await capture_frame(topic)


@router.websocket("/ws/{topic}")
async def websocket_topic_endpoint(websocket: WebSocket, topic: str):
    """WebSocket endpoint for real-time data streaming (not in REST documentation)."""
    return await websocket_endpoint(websocket, topic)