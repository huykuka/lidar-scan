"""Recordings business logic services - Pure business logic without routing configuration."""

import asyncio
import json
import logging
import os
import struct
import tempfile
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.modules.lidar.io.pcd import save_to_pcd
from app.repositories.recordings_orm import RecordingRepository
from app.services.nodes.instance import node_manager
from app.services.shared.mcap_recording import McapRecordingReader as RecordingReader
from app.services.shared.mcap_recording import McapRecordingWriter as RecordingWriter
from app.services.shared.recorder import get_recorder
from .dto import (
    StartRecordingRequest, TrimRecordingRequest
)
from .schemas import StreamPauseCommand, StreamSeekCommand, StreamStartCommand

logger = logging.getLogger(__name__)

_MAX_GENERATION = 0xFFFFFFFF


def _stream_error(code: str, message: str) -> dict[str, str]:
    return {"type": "error", "code": code, "message": message}


def _parse_stream_command(raw: str):
    try:
        payload = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, _stream_error("invalid_json", "Message must contain valid JSON.")

    if not isinstance(payload, dict) or payload.get("type") not in {"start", "seek", "pause"}:
        return None, _stream_error("unknown_command", "Command type must be 'start', 'seek', or 'pause'.")

    command_type = payload["type"]
    command_model = {
        "start": StreamStartCommand,
        "seek": StreamSeekCommand,
        "pause": StreamPauseCommand,
    }[command_type]
    try:
        return command_model.model_validate(payload), None
    except ValueError:
        return None, _stream_error("invalid_frame_index", "frameIndex must be a strict integer.")


def _next_generation(generation: int) -> int:
    return generation + 1 if generation < _MAX_GENERATION else 1


def _encode_stream_frame(points, timestamp: float, frame_index: int, generation: int) -> bytes:
    import numpy as np

    array = np.asarray(points, dtype=np.float32)
    if array.ndim != 2 or array.shape[1] < 3:
        raise ValueError("Recording frame must contain at least x, y, z columns")
    array = np.ascontiguousarray(array[:, :3])
    return struct.pack(
        "<4sIIIdI",
        b"LIDR", 2, generation, frame_index, float(timestamp), array.shape[0],
    ) + array.tobytes(order="C")


async def stream_recording(websocket: WebSocket, recording: dict) -> None:
    """Serve one bounded, seekable recording stream over one public WebSocket.

    Caller MUST have already called ``await websocket.accept()`` before invoking
    this function (the endpoint does this so the wsproto handshake completes
    immediately, before any blocking DB/file work).
    """
    reader = None
    producer: asyncio.Task | None = None
    receive_task: asyncio.Task | None = None
    generation = 0
    current_frame_index: int | None = None
    paused = True

    try:
        try:
            reader = await asyncio.to_thread(RecordingReader, recording["file_path"])
        except Exception:
            logger.exception(
                "Recording stream reader initialization failed",
                extra={"recording_id": recording.get("id"), "file_path": recording.get("file_path")},
            )
            await websocket.send_json(_stream_error(
                "recording_stream_failed", "Recording stream failed."
            ))
            await websocket.close(code=1011)
            return

        await websocket.send_json({
            "type": "ready", "frameCount": int(reader.frame_count),
            "startFrameIndex": 0, "generation": 0,
        })

        async def produce(start_index: int, stream_generation: int) -> None:
            nonlocal current_frame_index
            if start_index == reader.frame_count:
                await websocket.send_json({
                    "type": "eof", "frameIndex": start_index, "generation": stream_generation,
                })
                return

            # Even-spacing pacing: distribute frames uniformly over recording duration.
            # Per-frame timestamps from MCAP metadata are often coarse (integer seconds)
            # or contain genuine gaps that would cause visible ~0.5–1s stalls.
            # Even-spacing preserves total wall-clock duration while eliminating stalls.
            #
            # interval = duration / (frame_count - 1) so first→last spans `duration` seconds.
            # For a single-frame recording interval is irrelevant (no sleep needed).
            # Seek/resume re-anchors per produce() call: anchor is always local to this run.
            _total_frames = reader.frame_count
            _duration = float(reader.duration) if hasattr(reader, "duration") else 0.0
            if _total_frames > 1 and _duration > 0:
                _interval = _duration / (_total_frames - 1)
            else:
                _interval = 0.0

            anchor_monotonic: float | None = None

            for frame_index in range(start_index, reader.frame_count):
                points, timestamp = await asyncio.to_thread(reader.get_frame, frame_index)

                # Establish pacing anchor on first frame of this produce() run
                if anchor_monotonic is None:
                    anchor_monotonic = asyncio.get_event_loop().time()
                else:
                    # Target wall time = anchor + (offset from start_index) * interval
                    offset = frame_index - start_index
                    target_monotonic = anchor_monotonic + offset * _interval
                    sleep_delta = target_monotonic - asyncio.get_event_loop().time()
                    if sleep_delta > 0:
                        await asyncio.sleep(sleep_delta)

                await websocket.send_bytes(
                    _encode_stream_frame(points, timestamp, frame_index, stream_generation)
                )
                current_frame_index = frame_index + 1

        async def send_frame(frame_index: int, stream_generation: int) -> None:
            nonlocal current_frame_index
            points, timestamp = await asyncio.to_thread(reader.get_frame, frame_index)
            await websocket.send_bytes(
                _encode_stream_frame(points, timestamp, frame_index, stream_generation)
            )
            current_frame_index = frame_index + 1

        while True:
            if receive_task is None:
                receive_task = asyncio.create_task(websocket.receive())
            wait_tasks = {receive_task}
            if producer is not None:
                wait_tasks.add(producer)
            done, _ = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)

            # Process command when receive and producer complete together. A
            # completed producer must not win and discard seek/start command.
            if receive_task in done:
                if producer is not None and producer in done:
                    producer.result()
                    producer = None
                message = receive_task.result()
                receive_task = None
            elif producer is not None and producer in done:
                producer.result()
                producer = None
                continue
            else:
                continue

            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect
            if message.get("type") != "websocket.receive" or message.get("text") is None:
                await websocket.send_json(_stream_error("invalid_json", "Command must be a JSON text message."))
                continue

            command, error = _parse_stream_command(message["text"])
            if error:
                await websocket.send_json(error)
                continue
            if command.type == "pause":
                if producer is None and generation == 0:
                    await websocket.send_json(_stream_error("not_started", "Start stream before pausing."))
                    continue
                if producer is not None:
                    producer.cancel()
                    await asyncio.gather(producer, return_exceptions=True)
                    producer = None
                paused = True
                await websocket.send_json({
                    "type": "paused",
                    "frameIndex": current_frame_index if current_frame_index is not None else 0,
                    "generation": generation,
                })
                paused = True
                continue

            frame_index = command.frameIndex
            if command.type == "start" and frame_index is None:
                if not paused:
                    await websocket.send_json(_stream_error(
                        "invalid_frame_index", "Initial start requires frameIndex."
                    ))
                    continue
                frame_index = current_frame_index if current_frame_index is not None else 0
            if frame_index is None:
                await websocket.send_json(_stream_error("invalid_frame_index", "frameIndex is required."))
                continue
            if frame_index < 0 or frame_index > reader.frame_count:
                await websocket.send_json(_stream_error(
                    "invalid_frame_index", f"frameIndex must be between 0 and {reader.frame_count}."
                ))
                continue
            was_paused = paused
            if producer is not None:
                producer.cancel()
                await asyncio.gather(producer, return_exceptions=True)
                producer = None
            generation = _next_generation(generation)
            await websocket.send_json({
                "type": "seeked", "frameIndex": frame_index, "generation": generation,
            })
            current_frame_index = frame_index
            if frame_index == reader.frame_count:
                await websocket.send_json({
                    "type": "eof", "frameIndex": frame_index, "generation": generation,
                })
                paused = was_paused if command.type == "seek" else True
                continue
            if command.type == "seek":
                await send_frame(frame_index, generation)
                paused = was_paused
                if not was_paused:
                    producer = asyncio.create_task(produce(frame_index + 1, generation))
            else:
                paused = False
                producer = asyncio.create_task(produce(frame_index, generation))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception(
            "Recording stream failed",
            extra={
                "recording_id": recording.get("id"),
                "file_path": recording.get("file_path"),
                "frame_index": current_frame_index,
                "generation": generation,
            },
        )
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.send_json(_stream_error(
                "recording_stream_failed", "Recording stream failed."
            ))
            await websocket.close(code=1011)
    finally:
        if receive_task is not None:
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
        if producer is not None:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
        if reader is not None:
            await asyncio.to_thread(reader.close)


async def start_recording(request: StartRecordingRequest, db: Session):
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


async def stop_recording(recording_id: str, background_tasks: BackgroundTasks, db: Session):
    """
    Stop an active recording and save to database.
    Returns immediately with 'stopping' status, finalization happens in background.

    Args:
        recording_id: Recording ID
        background_tasks: FastAPI background tasks
        db: Database session

    Returns:
        Recording information with status='stopping'

    Raises:
        HTTPException: If recording not found
    """
    recorder = get_recorder()

    try:
        # Mark recording as stopping (returns immediately)
        info = await recorder.stop_recording(recording_id)

        # Schedule finalization in background
        async def finalize_and_save():
            try:
                # Finalize the recording (flush, compress, thumbnail)
                final_info = await recorder.finalize_recording(recording_id)

                # Save to database
                recording_data = {
                    "id": final_info["recording_id"],
                    "name": final_info["name"],
                    "node_id": final_info["node_id"],
                    "sensor_id": final_info["metadata"].get("sensor_id"),
                    "file_path": final_info["file_path"],
                    "file_size_bytes": final_info["file_size_bytes"],
                    "frame_count": final_info["frame_count"],
                    "duration_seconds": final_info["duration_seconds"],
                    "recording_timestamp": final_info["metadata"].get("recording_timestamp",
                                                                      datetime.now(timezone.utc).isoformat()),
                    "metadata": final_info["metadata"],
                    "created_at": datetime.now(timezone.utc).isoformat()
                }

                if final_info.get("thumbnail_path"):
                    recording_data["thumbnail_path"] = final_info["thumbnail_path"]

                # Need a new DB session for background task
                from app.db.models import get_db
                db_gen = get_db()
                bg_db = next(db_gen)
                try:
                    bg_repo = RecordingRepository(bg_db)
                    bg_repo.create(recording_data)
                    logger.info(f"Background: Saved recording {recording_id} to database")
                finally:
                    bg_db.close()

            except Exception as e:
                logger.error(f"Background: Error finalizing recording {recording_id}: {e}", exc_info=True)

        background_tasks.add_task(finalize_and_save)

        logger.info(f"Stopping recording {recording_id} (finalization in background)")

        # Return immediate response with stopping status
        return {
            "recording_id": info["recording_id"],
            "node_id": info["node_id"],
            "status": info["status"],
            "frame_count": info["frame_count"],
            "duration_seconds": info["duration_seconds"],
            "message": "Recording is stopping, finalization in progress..."
        }

    except KeyError:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    except Exception as e:
        logger.error(f"Error stopping recording: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")


async def list_recordings(node_id: str | None, db: Session):
    """
    List all recordings, optionally filtered by topic.

    Args:
        node_id: Optional node ID filter
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


async def get_recording(recording_id: str, db: Session):
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


async def rename_recording(recording_id: str, name: str, db: Session):
    """
    Rename a recording.

    Args:
        recording_id: Recording ID
        name: New display name
        db: Database session

    Returns:
        Updated recording information

    Raises:
        HTTPException: If recording not found
    """
    repo = RecordingRepository(db)
    updated = repo.update(recording_id, {"name": name})

    if not updated:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    return updated


async def delete_recording(recording_id: str, background_tasks: BackgroundTasks, db: Session):
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


async def download_recording(recording_id: str, db: Session):
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
    filename = f"{recording['name']}_{recording['created_at'][:10]}.mcap"
    # Sanitize filename
    filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.')).rstrip()

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


async def get_recording_viewer_info(recording_id: str, db: Session):
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


async def get_recording_frame_as_pcd(recording_id: str, frame_index: int, background_tasks: BackgroundTasks,
                                     db: Session):
    """
    Get a specific frame from a recording as PCD file.

    Args:
        recording_id: Recording ID
        frame_index: Frame index (0-based)
        background_tasks: FastAPI background tasks
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


async def upload_recording(file: UploadFile, name: str | None, background_tasks: BackgroundTasks, db: Session):
    """
    Upload a recording file (.mcap primary, .zip transitional) and register it in the database.

    Accepts:
    - .mcap files: validated via McapRecordingReader, stored as-is.
    - .zip files: converted to .mcap on ingest; stored always as .mcap.
    - Other / corrupt: rejected 400.

    Path-traversal safety: ZIP member names with ".." or absolute paths → 400.

    Args:
        file: Multipart-uploaded .mcap or .zip file.
        name: Optional display name. Falls back to the filename stem.
        background_tasks: FastAPI background tasks (used for thumbnail generation).
        db: Database session.

    Returns:
        RecordingResponse for the newly created entry (file_path ends .mcap).

    Raises:
        HTTPException 400: Invalid recording file or path-traversal attempt.
        HTTPException 500: If saving fails unexpectedly.
    """
    from app.services.shared.mcap_recording import McapRecordingWriter as _McapWriter

    recordings_dir = Path("data/recordings")
    recordings_dir.mkdir(parents=True, exist_ok=True)

    recording_id = str(uuid.uuid4()).replace("-", "")
    original_name = file.filename or "upload"
    original_stem = Path(original_name).stem
    display_name = name or original_stem

    dest_path = recordings_dir / f"{recording_id}.mcap"
    tmp_path: Path | None = None
    part_path: Path | None = None

    try:
        content = await file.read()

        # Determine upload type from extension (primary signal)
        suffix = Path(original_name).suffix.lower()

        if suffix == ".zip":
            # ---------- .zip transitional: validate + convert to .mcap ----------
            import io as _io

            if not zipfile.is_zipfile(_io.BytesIO(content)):
                raise HTTPException(status_code=400, detail="Uploaded .zip is not a valid ZIP archive.")

            with zipfile.ZipFile(_io.BytesIO(content), "r") as zf:
                names_in_zip = zf.namelist()
                # Path-traversal safety
                for member_name in names_in_zip:
                    if ".." in member_name or member_name.startswith("/"):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unsafe ZIP member name: '{member_name}'. Upload rejected."
                        )
                if "metadata.json" not in names_in_zip:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid recording ZIP: missing metadata.json.",
                    )

            # Convert in-memory ZIP to .mcap via _ZipRecordingReader shim
            part_path = recordings_dir / f"{recording_id}.mcap.part"
            try:
                from app.services.shared.mcap_recording import _ZipRecordingReader as _ZipShim
                # Write zip bytes to a temp file so _ZipShim can open it
                with tempfile.NamedTemporaryFile(
                    dir=str(recordings_dir), suffix=".zip", delete=False
                ) as _tmp_f:
                    tmp_path = Path(_tmp_f.name)
                    _tmp_f.write(content)

                zip_reader = _ZipShim(tmp_path)
                try:
                    meta_from_zip = zip_reader.metadata
                    mcap_writer = _McapWriter(part_path, dict(meta_from_zip))
                    mcap_writer.write_batch(list(zip_reader.iter_frames()))
                    mcap_writer.finalize()
                finally:
                    zip_reader.close()
            except Exception as conv_exc:
                raise HTTPException(status_code=400, detail=f"Invalid recording ZIP: {conv_exc}")

            import os as _os
            _os.replace(str(part_path), str(dest_path))
            part_path = None

        elif suffix == ".mcap":
            # ---------- .mcap primary: write to temp, validate, move ----------
            part_path = recordings_dir / f"{recording_id}.mcap.part"
            with open(str(part_path), "wb") as _pf:
                _pf.write(content)

            # Validate via McapRecordingReader (raises ValueError if invalid)
            try:
                _r = RecordingReader(str(part_path))
                _r.close()
            except (ValueError, FileNotFoundError) as ve:
                raise HTTPException(status_code=400, detail=f"Invalid MCAP recording: {ve}")

            import os as _os
            _os.replace(str(part_path), str(dest_path))
            part_path = None

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{suffix}'. Upload .mcap or .zip files."
            )

        # Read metadata from the final .mcap file
        reader = RecordingReader(dest_path)
        info = reader.get_info()
        meta: dict = reader.metadata
        reader.close()

        recording_timestamp = meta.get(
            "recording_timestamp",
            meta.get("start_timestamp", datetime.now(timezone.utc).isoformat()),
        )
        if isinstance(recording_timestamp, (int, float)):
            recording_timestamp = datetime.fromtimestamp(recording_timestamp, tz=timezone.utc).isoformat()

        recording_data: dict = {
            "id": recording_id,
            "name": display_name,
            "node_id": meta.get("node_id", "uploaded"),
            "sensor_id": meta.get("sensor_id"),
            "file_path": str(dest_path),
            "file_size_bytes": info["file_size_bytes"],
            "frame_count": info["frame_count"],
            "duration_seconds": info["duration_seconds"],
            "recording_timestamp": recording_timestamp,
            "metadata": meta,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        repo = RecordingRepository(db)
        created = repo.create(recording_data)

        # Attempt thumbnail generation in the background
        async def _generate_thumbnail() -> None:
            try:
                from app.services.shared.thumbnail import generate_thumbnail_from_file

                thumbnail_path = dest_path.with_suffix(".png")
                success = await asyncio.to_thread(
                    generate_thumbnail_from_file, dest_path, output_path=thumbnail_path
                )
                if success:
                    from app.db.models import get_db as _get_db

                    bg_db_gen = _get_db()
                    bg_db = next(bg_db_gen)
                    try:
                        RecordingRepository(bg_db).update(
                            recording_id, {"thumbnail_path": str(thumbnail_path)}
                        )
                    finally:
                        bg_db.close()
            except Exception as exc:
                logger.warning(f"Thumbnail generation failed for uploaded recording {recording_id}: {exc}")

        background_tasks.add_task(_generate_thumbnail)

        logger.info(f"Uploaded recording '{display_name}' saved as {recording_id}.mcap")
        return created

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to upload recording: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded recording: {exc}")
    finally:
        for _cleanup in (tmp_path, part_path):
            if _cleanup and _cleanup.exists():
                try:
                    _cleanup.unlink()
                except Exception:
                    pass


async def get_recording_thumbnail(recording_id: str, db: Session):
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


def _perform_trim_copy(
    src_file_path: str,
    dest: Path,
    new_metadata: dict,
    start_frame: int,
    end_frame: int,
) -> dict:
    """Sync helper: copy frame range from src to dest. Runs in a worker thread.

    Returns writer.finalize() dict on success.
    Cleans up partial dest on failure and re-raises.
    """
    reader = RecordingReader(src_file_path)
    try:
        writer = RecordingWriter(dest, new_metadata)
        writer.write_batch(list(reader.iter_frames(start_frame, end_frame)))
        return writer.finalize()
    except Exception:
        for path in (dest, dest.with_suffix(".png")):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        raise
    finally:
        reader.close()


async def trim_recording(
    recording_id: str,
    req: TrimRecordingRequest,
    background_tasks: BackgroundTasks,
    db: Session,
):
    """
    Copy a half-open frame range [start_frame, end_frame) from a source recording
    into a new recording. Original is untouched.

    Returns HTTP 202 immediately with status='processing'. The actual frame copy
    runs in a BackgroundTask; the row is updated to 'ready' (or 'failed') when done.

    Raises:
        HTTPException 404: Source recording not found.
        HTTPException 400: Invalid frame range.
    """
    repo = RecordingRepository(db)
    src = repo.get_by_id(recording_id)
    if src is None:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")

    try:
        reader = RecordingReader(src["file_path"])
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=f"Recording file not found or corrupt: {exc}")

    try:
        source_count = reader.frame_count

        # Validate range (sync, on event loop)
        start_frame = req.start_frame
        end_frame = req.end_frame

        if source_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Source recording has no frames; cannot trim.",
            )
        if not (0 <= start_frame < end_frame <= source_count):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid frame range [{start_frame}, {end_frame}). "
                    f"Allowed: start_frame >= 0, start_frame < end_frame, "
                    f"end_frame <= {source_count} (source frame count)."
                ),
            )

        new_id = uuid.uuid4().hex
        recordings_dir = Path("data/recordings")
        recordings_dir.mkdir(parents=True, exist_ok=True)
        dest = recordings_dir / f"{new_id}.mcap"

        # Strip stale computed fields; writer.finalize recomputes them
        new_metadata = deepcopy(reader.metadata)
        for stale_key in ("frame_count", "timestamps", "start_timestamp", "end_timestamp"):
            new_metadata.pop(stale_key, None)

    finally:
        reader.close()

    # Determine recording_timestamp from source (best-effort before copy)
    src_ts = src.get("recording_timestamp") or src.get("metadata", {}).get("recording_timestamp")
    recording_timestamp = src_ts or datetime.now(timezone.utc).isoformat()
    display_name = req.name or f'{src["name"]} (trim)'

    # Create DB row immediately with status='processing' and placeholder numerics
    recording_data = {
        "id": new_id,
        "name": display_name,
        "node_id": src["node_id"],
        "sensor_id": src.get("sensor_id"),
        "file_path": str(dest),
        "file_size_bytes": 0,
        "frame_count": end_frame - start_frame,
        "duration_seconds": 0.0,
        "recording_timestamp": recording_timestamp,
        "metadata": deepcopy(new_metadata),
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    created = repo.create(recording_data)

    # Background: copy frames, then finalize the row
    async def _bg_trim_and_finalize() -> None:
        from app.db.models import get_db as _get_db

        try:
            info = await asyncio.to_thread(
                _perform_trim_copy, src["file_path"], dest, new_metadata, start_frame, end_frame
            )

            # Derive recording_timestamp from actual written start if source had none
            if not src_ts:
                raw_ts = info.get("start_timestamp")
                if isinstance(raw_ts, (int, float)) and raw_ts:
                    actual_ts = datetime.fromtimestamp(raw_ts, tz=timezone.utc).isoformat()
                else:
                    actual_ts = recording_timestamp
            else:
                actual_ts = recording_timestamp

            # Finalized metadata with real timestamps
            final_metadata = deepcopy(new_metadata)
            final_metadata["start_timestamp"] = info.get("start_timestamp")
            final_metadata["end_timestamp"] = info.get("end_timestamp")

            bg_db_gen = _get_db()
            bg_db = next(bg_db_gen)
            try:
                RecordingRepository(bg_db).update(new_id, {
                    "file_size_bytes": info["file_size_bytes"],
                    "frame_count": info["frame_count"],
                    "duration_seconds": info["duration_seconds"],
                    "recording_timestamp": actual_ts,
                    "metadata": final_metadata,
                    "status": "ready",
                })
            finally:
                bg_db.close()

            logger.info(
                f"trim_recording: {recording_id} [{start_frame},{end_frame}) "
                f"→ {new_id} ({info['frame_count']} frames) ready"
            )

            # Thumbnail generation (best-effort)
            try:
                from app.services.shared.thumbnail import generate_thumbnail_from_file

                thumbnail_path = dest.with_suffix(".png")
                success = await asyncio.to_thread(
                    generate_thumbnail_from_file, dest, output_path=thumbnail_path
                )
                if success:
                    bg_db_gen2 = _get_db()
                    bg_db2 = next(bg_db_gen2)
                    try:
                        RecordingRepository(bg_db2).update(new_id, {"thumbnail_path": str(thumbnail_path)})
                    finally:
                        bg_db2.close()
            except Exception as thumb_exc:
                logger.warning(f"Thumbnail generation failed for trimmed recording {new_id}: {thumb_exc}")

        except Exception as exc:
            logger.error(f"trim_recording background task failed for {new_id}: {exc}", exc_info=True)
            # Clean up partial file
            for path in (dest, dest.with_suffix(".png")):
                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass
            # Mark row failed
            bg_db_gen = _get_db()
            bg_db = next(bg_db_gen)
            try:
                RecordingRepository(bg_db).update(new_id, {"status": "failed"})
            finally:
                bg_db.close()

    background_tasks.add_task(_bg_trim_and_finalize)

    return created
