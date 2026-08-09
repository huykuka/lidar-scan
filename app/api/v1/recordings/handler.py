"""Recordings router configuration and endpoint metadata."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, WebSocket, status
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.repositories.recordings_orm import RecordingRepository
from .dto import (
    StartRecordingRequest, RecordingResponse, ListRecordingsResponse,
    RenameRecordingRequest, TrimRecordingRequest
)
from .service import (
    start_recording, stop_recording, list_recordings, get_recording,
    delete_recording, download_recording, get_recording_viewer_info,
    get_recording_frame_as_pcd, get_recording_thumbnail, upload_recording,
    rename_recording, stream_recording, trim_recording
)

# Router configuration
router = APIRouter(tags=["Recordings"])


@router.websocket("/recordings/{recording_id}/stream")
async def recordings_stream_endpoint(websocket: WebSocket, recording_id: str):
    # Accept FIRST so the wsproto handshake completes immediately.
    # Blocking DB work before accept() causes a 403 under Docker (slow volume
    # I/O delays accept past wsproto's handshake window).
    await websocket.accept()

    def _lookup():
        db = next(get_db())
        try:
            return RecordingRepository(db).get_by_id(recording_id)
        finally:
            db.close()

    recording = await asyncio.to_thread(_lookup)
    if not recording:
        await websocket.close(code=1008, reason="recording_not_found")
        return
    await stream_recording(websocket, recording)


# Endpoint configurations
@router.post(
    "/recordings/upload",
    response_model=RecordingResponse,
    responses={
        400: {"description": "Invalid or corrupt recording file"},
        500: {"description": "Internal server error"},
    },
    summary="Upload Recording",
    description=(
            "Upload a recording ZIP archive to import it into the library. "
            "The file must be a valid ZIP produced by the recorder (contains metadata.json and frame PCD files). "
            "An optional `name` field overrides the display name."
    ),
)
async def recordings_upload_endpoint(
        background_tasks: BackgroundTasks,
        db: Annotated[Session, Depends(get_db)],
        file: UploadFile = File(..., description="Recording ZIP archive"),
        name: str | None = Form(None, description="Optional display name for the recording"),
):
    return await upload_recording(file, name, background_tasks, db)


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


@router.patch(
    "/recordings/{recording_id}/rename",
    response_model=RecordingResponse,
    responses={
        404: {"description": "Recording not found"},
        500: {"description": "Internal server error"},
    },
    summary="Rename Recording",
    description="Update the display name of a recording.",
)
async def recordings_rename_endpoint(
        recording_id: str,
        request: RenameRecordingRequest,
        db: Annotated[Session, Depends(get_db)]
):
    return await rename_recording(recording_id, request.name, db)


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


@router.post(
    "/recordings/{recording_id}/trim",
    response_model=RecordingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"description": "Invalid frame range"},
        404: {"description": "Recording not found"},
        500: {"description": "Internal server error"},
    },
    summary="Trim Recording",
    description=(
        "Copy a half-open frame range [start_frame, end_frame) from a source recording "
        "into a new recording. The original recording is not modified. "
        "Returns 202 immediately with status='processing'; the copy runs in the background. "
        "Poll GET /recordings/{id} until status='ready' (or 'failed')."
    ),
)
async def recordings_trim_endpoint(
        recording_id: str,
        request: TrimRecordingRequest,
        background_tasks: BackgroundTasks,
        db: Annotated[Session, Depends(get_db)],
):
    return await trim_recording(recording_id, request, background_tasks, db)
