"""Recordings router configuration and endpoint metadata."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.api.v1.schemas.common import StatusResponse
from .handlers import (
    start_recording, stop_recording, list_recordings, get_recording,
    delete_recording, download_recording, get_recording_viewer_info,
    get_recording_frame_as_pcd, get_recording_thumbnail,
    StartRecordingRequest, RecordingResponse, ListRecordingsResponse
)


# Router configuration
router = APIRouter(tags=["Recordings"])

# Endpoint configurations
@router.post(
    "/recordings/start",
    responses={
        400: {"description": "Invalid request or node already being recorded"},
        404: {"description": "Node not found"},
        500: {"description": "Internal server error"}
    },
    summary="Start Recording",
    description="Start recording a topic.",
)
async def recordings_start_endpoint(
    request: StartRecordingRequest,
    db: Annotated[Session, Depends(get_db)]
):
    return await start_recording(request, db)


@router.post(
    "/recordings/{recording_id}/stop",
    responses={
        400: {"description": "Recording not found or not active"},
        404: {"description": "Recording not found"},
        500: {"description": "Internal server error"}
    },
    summary="Stop Recording",
    description="Stop an active recording.",
)
async def recordings_stop_endpoint(
    recording_id: str,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)]
):
    return await stop_recording(recording_id, background_tasks, db)


@router.get(
    "/recordings",
    response_model=ListRecordingsResponse,
    summary="List Recordings",
    description="List all recordings with optional node filtering.",
)
async def recordings_list_endpoint(
    node_id: Annotated[str | None, Query(description="Filter by node ID")] = None,
    db: Session = Depends(get_db)
):
    return await list_recordings(node_id, db)


@router.get(
    "/recordings/{recording_id}",
    response_model=RecordingResponse,
    responses={
        404: {"description": "Recording not found"}
    },
    summary="Get Recording",
    description="Get detailed information about a specific recording.",
)
async def recordings_get_endpoint(
    recording_id: str,
    db: Annotated[Session, Depends(get_db)]
):
    return await get_recording(recording_id, db)


@router.delete(
    "/recordings/{recording_id}",
    responses={
        404: {"description": "Recording not found"},
        500: {"description": "Internal server error"}
    },
    summary="Delete Recording",
    description="Delete a recording and its associated files.",
)
async def recordings_delete_endpoint(
    recording_id: str,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)]
):
    return await delete_recording(recording_id, background_tasks, db)


@router.get(
    "/recordings/{recording_id}/download",
    responses={
        404: {"description": "Recording not found"},
        500: {"description": "Internal server error"}
    },
    summary="Download Recording",
    description="Download the raw recording file.",
)
async def recordings_download_endpoint(
    recording_id: str,
    db: Annotated[Session, Depends(get_db)]
):
    return await download_recording(recording_id, db)


@router.get(
    "/recordings/{recording_id}/info",
    summary="Get Recording Info",
    description="Get recording information for the viewer.",
)
async def recordings_info_endpoint(
    recording_id: str,
    db: Annotated[Session, Depends(get_db)]
):
    return await get_recording_viewer_info(recording_id, db)


@router.get(
    "/recordings/{recording_id}/frame/{frame_index}",
    responses={
        404: {"description": "Recording or frame not found"},
        500: {"description": "Internal server error"}
    },
    summary="Get Recording Frame",
    description="Get a specific frame from a recording as PCD file.",
)
async def recordings_frame_endpoint(
    recording_id: str,
    frame_index: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)]
):
    return await get_recording_frame_as_pcd(recording_id, frame_index, background_tasks, db)


@router.get(
    "/recordings/{recording_id}/thumbnail",
    responses={
        404: {"description": "Recording not found"},
        500: {"description": "Internal server error"}
    },
    summary="Get Recording Thumbnail",
    description="Get the thumbnail image for a recording.",
)
async def recordings_thumbnail_endpoint(
    recording_id: str,
    db: Annotated[Session, Depends(get_db)]
):
    return await get_recording_thumbnail(recording_id, db)