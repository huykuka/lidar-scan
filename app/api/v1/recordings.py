"""REST API endpoints for recording management."""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.repositories.recordings_orm import RecordingRepository
from app.services.shared.recorder import get_recorder
from app.services.nodes.instance import node_manager
from app.services.shared.recording import get_recording_info, RecordingReader
from app.services.modules.lidar.io.pcd import save_to_pcd
import tempfile

router = APIRouter()
logger = logging.getLogger(__name__)


class StartRecordingRequest(BaseModel):
    """Request body for starting a recording."""
    node_id: str
    name: str | None = None
    metadata: dict | None = None


class RecordingResponse(BaseModel):
    """Recording information response."""
    id: str
    name: str
    node_id: str
    sensor_id: str | None
    file_path: str
    file_size_bytes: int
    frame_count: int
    duration_seconds: float
    recording_timestamp: str
    metadata: dict
    thumbnail_path: str | None = None
    created_at: str


class ActiveRecordingResponse(BaseModel):
    """Active recording status response."""
    recording_id: str
    node_id: str
    frame_count: int
    duration_seconds: float
    started_at: str
    metadata: dict | None = None


class ListRecordingsResponse(BaseModel):
    """Response for listing recordings."""
    recordings: list[RecordingResponse]
    active_recordings: list[ActiveRecordingResponse]


@router.post("/recordings/start")
async def start_recording(
    request: StartRecordingRequest,
    db: Annotated[Session, Depends(get_db)]
):
    """
    Start recording a topic.
    
    Args:
        request: Recording start request with topic and optional name
        db: Database session
    
    Returns:
        Recording ID and file path
    
    Raises:
        HTTPException: If topic is already being recorded or not found
    """
    recorder = get_recorder()
    
    found_node = node_manager.nodes.get(request.node_id)
    
    if not found_node:
        raise HTTPException(status_code=404, detail=f"Node {request.node_id} not found in active graph")
        
    # Prepare metadata - merge with user-provided metadata
    metadata = {
        "node_id": request.node_id,
        "name": request.name or request.node_id,
    }
    
    # Merge user-provided metadata if present
    if request.metadata:
        metadata.update(request.metadata)
    
    # Add node metadata if found (and not already in user metadata)
    if found_node:
        if hasattr(found_node, "mode") and "mode" not in metadata:
            metadata["mode"] = getattr(found_node, "mode", None)
        if hasattr(found_node, "pipeline_name") and "pipeline_name" not in metadata:
            metadata["pipeline_name"] = getattr(found_node, "pipeline_name", None)
        if hasattr(found_node, "pose_params") and "pose" not in metadata:
            metadata["pose"] = getattr(found_node, "pose_params", None)
    
    try:
        recording_id, file_path = await recorder.start_recording(
            node_id=request.node_id,
            name=request.name,
            metadata=metadata
        )
        
        logger.info(f"Started recording {recording_id} for node {request.node_id}")
        
        return {
            "recording_id": recording_id,
            "file_path": file_path,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting recording: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")


@router.post("/recordings/{recording_id}/stop")
async def stop_recording(
    recording_id: str,
    db: Annotated[Session, Depends(get_db)]
):
    """
    Stop an active recording and save to database.
    
    Args:
        recording_id: Recording ID
        db: Database session
    
    Returns:
        Recording information
    
    Raises:
        HTTPException: If recording not found
    """
    recorder = get_recorder()
    repo = RecordingRepository(db)
    
    try:
        # Stop recording and get info
        info = await recorder.stop_recording(recording_id)
        
        recording_data = {
            "id": info["recording_id"],
            "name": info["name"],
            "node_id": info["node_id"],
            "sensor_id": info["metadata"].get("sensor_id"),
            "file_path": info["file_path"],
            "file_size_bytes": info["file_size_bytes"],
            "frame_count": info["frame_count"],
            "duration_seconds": info["duration_seconds"],
            "recording_timestamp": info["metadata"].get("recording_timestamp", datetime.now(timezone.utc).isoformat()),
            "metadata": info["metadata"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if info.get("thumbnail_path"):
            recording_data["thumbnail_path"] = info["thumbnail_path"]
            logger.info(f"Using recorder-generated thumbnail for {recording_id}")
        
        saved = repo.create(recording_data)
        
        logger.info(f"Stopped and saved recording {recording_id}")
        
        return saved
    
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    except Exception as e:
        logger.error(f"Error stopping recording: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")


@router.get("/recordings", response_model=ListRecordingsResponse)
async def list_recordings(
    node_id: str | None = Query(None, description="Filter by node_id"),
    db: Session = Depends(get_db)
):
    """
    List all recordings, optionally filtered by topic.
    
    Args:
        topic: Optional topic filter
        db: Database session
    
    Returns:
        List of recordings and active recordings
    """
    recorder = get_recorder()
    repo = RecordingRepository(db)
    
    # Get saved recordings
    recordings = repo.list(node_id=node_id)
    
    # Get active recordings
    active = recorder.get_active_recordings()
    
    # Filter active recordings by node_id if specified
    if node_id:
        active = [r for r in active if r.get("node_id") == node_id]
    
    return {
        "recordings": recordings,
        "active_recordings": active
    }


@router.get("/recordings/{recording_id}", response_model=RecordingResponse)
async def get_recording(
    recording_id: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a recording.
    
    Args:
        recording_id: Recording ID
        db: Database session
    
    Returns:
        Recording information
    
    Raises:
        HTTPException: If recording not found
    """
    repo = RecordingRepository(db)
    recording = repo.get_by_id(recording_id)
    
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    
    return recording


@router.delete("/recordings/{recording_id}")
async def delete_recording(
    recording_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Delete a recording (removes file and database entry).
    
    Args:
        recording_id: Recording ID
        background_tasks: FastAPI background tasks
        db: Database session
    
    Returns:
        Success message
    
    Raises:
        HTTPException: If recording not found
    """
    repo = RecordingRepository(db)
    recording = repo.get_by_id(recording_id)
    
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    
    file_path = recording["file_path"]
    thumbnail_path = recording.get("thumbnail_path")
    
    # Delete from database
    repo.delete(recording_id)
    
    # Schedule file deletion in background
    def delete_file():
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted recording file: {file_path}")
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                logger.info(f"Deleted thumbnail file: {thumbnail_path}")
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
    
    background_tasks.add_task(delete_file)
    
    return {"message": f"Recording {recording_id} deleted successfully"}


@router.get("/recordings/{recording_id}/download")
async def download_recording(
    recording_id: str,
    db: Session = Depends(get_db)
):
    """
    Download a recording file.
    
    Args:
        recording_id: Recording ID
        db: Database session
    
    Returns:
        FileResponse with the recording file
    
    Raises:
        HTTPException: If recording not found or file doesn't exist
    """
    repo = RecordingRepository(db)
    recording = repo.get_by_id(recording_id)
    
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    
    file_path = recording["file_path"]
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Recording file not found: {file_path}")
    
    # Generate a nice filename
    filename = f"{recording['name']}_{recording['created_at'][:10]}.lidr"
    # Sanitize filename
    filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.')).rstrip()
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.get("/recordings/{recording_id}/info")
async def get_recording_viewer_info(
    recording_id: str,
    db: Annotated[Session, Depends(get_db)]
):
    """
    Get recording information for viewer (frame count, duration, metadata).
    
    Args:
        recording_id: Recording ID
        db: Database session
    
    Returns:
        Recording info including frame_count, duration, metadata
    
    Raises:
        HTTPException: If recording not found or file doesn't exist
    """
    repo = RecordingRepository(db)
    recording = repo.get_by_id(recording_id)
    
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    
    file_path = recording["file_path"]
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Recording file not found: {file_path}")
    
    return {
        "id": recording["id"],
        "name": recording["name"],
        "node_id": recording["node_id"],
        "frame_count": recording["frame_count"],
        "duration_seconds": recording["duration_seconds"],
        "metadata": recording["metadata"],
        "recording_timestamp": recording["recording_timestamp"],
    }


@router.get("/recordings/{recording_id}/frame/{frame_index}")
async def get_recording_frame_as_pcd(
    recording_id: str,
    frame_index: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)]
):
    """
    Get a specific frame from a recording as PCD file.
    
    Args:
        recording_id: Recording ID
        frame_index: Frame index (0-based)
        db: Database session
    
    Returns:
        FileResponse with PCD file
    
    Raises:
        HTTPException: If recording not found, file doesn't exist, or frame index invalid
    """
    repo = RecordingRepository(db)
    recording = repo.get_by_id(recording_id)
    
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    
    file_path = recording["file_path"]
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Recording file not found: {file_path}")
    
    # Open recording and read frame
    try:
        reader = RecordingReader(file_path)
        
        if frame_index < 0 or frame_index >= reader.frame_count:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid frame index {frame_index}. Recording has {reader.frame_count} frames."
            )
        
        points, timestamp = reader.get_frame(frame_index)
        
        # Convert to PCD and save to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pcd', delete=False) as tmp_file:
            temp_path = tmp_file.name
            save_to_pcd(points, temp_path)
        
        def cleanup():
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp PCD file {temp_path}: {e}")

        # Schedule cleanup
        background_tasks.add_task(cleanup)
        
        return FileResponse(
            path=temp_path,
            filename=f"frame_{frame_index}.pcd",
            media_type="application/octet-stream",
            background=background_tasks
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error reading frame {frame_index} from recording {recording_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read frame: {str(e)}")


@router.get("/recordings/{recording_id}/thumbnail")
async def get_recording_thumbnail(
    recording_id: str,
    db: Session = Depends(get_db)
):
    """
    Get thumbnail image for a recording.
    
    Args:
        recording_id: Recording UUID
        db: Database session
    
    Returns:
        PNG thumbnail image or placeholder
    """
    repo = RecordingRepository(db)
    recording = repo.get_by_id(recording_id)
    
    if not recording:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    
    # Check if thumbnail exists
    if recording.get("thumbnail_path") and os.path.exists(recording["thumbnail_path"]):
        return FileResponse(
            path=recording["thumbnail_path"],
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"}  # Cache for 24 hours
        )
    
    # Try to generate thumbnail if missing
    file_path = Path(recording["file_path"])
    if file_path.exists():
        try:
            from app.services.shared.thumbnail import generate_thumbnail_from_file
            
            thumbnail_path = file_path.with_suffix(".png")
            success = await asyncio.to_thread(
                generate_thumbnail_from_file,
                file_path,
                output_path=thumbnail_path
            )
            
            if success:
                # Update database with thumbnail path
                repo.update(recording_id, {"thumbnail_path": str(thumbnail_path)})
                
                return FileResponse(
                    path=str(thumbnail_path),
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"}
                )
        except Exception as e:
            logger.warning(f"Failed to generate thumbnail on-demand: {e}")
    
    # Return 404 if no thumbnail available
    raise HTTPException(status_code=404, detail="Thumbnail not available")
