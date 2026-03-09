"""Logs router configuration and endpoint metadata."""

from fastapi import APIRouter, Query, WebSocket
from typing import Optional
from app.api.v1.schemas.logs import LogEntry
from .handlers import get_logs, download_logs, logs_websocket_endpoint


# Router configuration
router = APIRouter(tags=["Logs"])

# Endpoint configurations
@router.get(
    "/logs",
    response_model=list[LogEntry],
    summary="Get Logs",
    description="Get paginated application log entries with optional filtering.",
)
def logs_get_endpoint(
    level: Optional[str] = Query(None, description="Log level to filter by (INFO, WARNING, ERROR, DEBUG)"),
    search: Optional[str] = Query(None, description="Free text to search for in log message"),
    offset: int = Query(0, description="Starting row (0 is last/latest entry)"),
    limit: int = Query(100, description="Number of entries to return, max 500"),
):
    return get_logs(level, search, offset, limit)


@router.get(
    "/download",
    responses={200: {"content": {"text/plain": {}}}, 404: {"description": "Log file not found"}},
    summary="Download Logs",
    description="Download filtered log entries as a plain-text file.",
)
def logs_download_endpoint(
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    return download_logs(level, search)


@router.websocket("/logs/ws")
async def logs_websocket(websocket: WebSocket, level: Optional[str] = None, search: Optional[str] = None):
    """WebSocket endpoint for real-time log streaming (not in REST documentation)."""
    return await logs_websocket_endpoint(websocket, level, search)