"""Recording upload service (strategy pattern).

The storage backend is chosen with ``UPLOAD_BACKEND`` (see ``registry.py``); this facade holds
the backend-independent logic: cached credential status, readable object naming, persisting the
"uploaded" state on the recording and the auto-upload hook.
"""

import asyncio
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

from .base import StorageStatus, StorageStrategy
from .registry import available_backends, get_strategy

__all__ = ["StorageStatus", "StorageStrategy", "get_status", "invalidate_status_cache", "build_key", "upload_recording", "auto_upload_recording"]

logger = get_logger(__name__)

_STATUS_TTL_S = 60.0
_cached: tuple[float, StorageStatus] | None = None


def invalidate_status_cache() -> None:
    """Drop the cached credential check (call after the storage settings change)."""
    global _cached
    _cached = None


def _check_sync() -> StorageStatus:
    strategy = get_strategy()
    if strategy is None:
        return StorageStatus(
            False, False, settings.UPLOAD_BACKEND,
            reason=f"Unknown storage backend (available: {', '.join(available_backends())})",
        )
    return strategy.check()


async def get_status(force: bool = False) -> StorageStatus:
    """Check (with a short cache) whether the configured backend is usable."""
    global _cached
    now = time.monotonic()
    if not force and _cached and now - _cached[0] < _STATUS_TTL_S:
        return _cached[1]
    status = await asyncio.to_thread(_check_sync)
    _cached = (now, status)
    return status


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.\- ]+", "_", name, flags=re.UNICODE).strip(" ._")
    return re.sub(r"\s+", "_", cleaned) or "recording"


async def build_key(recording: dict, strategy: StorageStrategy | None = None) -> str:
    """Readable object key ``<prefix>/<name>_<YYYY-MM-DD>.<ext>``.

    Mirrors the name the UI gives downloaded files. If an object with that key already
    exists, a short id suffix is appended so nothing gets overwritten.
    """
    strategy = strategy or get_strategy()
    prefix = strategy.key_prefix
    ext = Path(recording["file_path"]).suffix or ".mcap"
    date = str(recording.get("created_at") or "")[:10]
    base = _safe_name(str(recording.get("name") or "recording"))
    stem = f"{base}_{date}" if date else base

    def join(s: str) -> str:
        return f"{prefix}/{s}{ext}" if prefix else f"{s}{ext}"

    key = join(stem)
    if await asyncio.to_thread(strategy.exists, key):
        key = join(f"{stem}_{str(recording['id'])[:8]}")
    return key




class UploadCancelled(Exception):
    """Raised inside a transfer when the user cancelled the upload."""


#: recording_id -> cancel flag of its current upload job (shared with the transfer thread)
_cancel_events: dict[str, threading.Event] = {}


def _set_upload_state_sync(recording_id: str, state: dict | None) -> None:
    """Persist the upload state in the recording's metadata (``blob_upload``); None clears it."""
    from app.db.models import get_db
    from app.repositories.recordings_orm import RecordingRepository

    db = next(get_db())
    try:
        repo = RecordingRepository(db)
        current = repo.get_by_id(recording_id)
        if not current:
            return
        metadata = dict(current.get("metadata") or {})
        existing = metadata.get("blob_upload") or {}
        if state and state.get("progress") is not None and existing.get("status") != "uploading":
            return  # late progress tick after the upload finished, failed or was cancelled
        if state is None:
            metadata.pop("blob_upload", None)
        else:
            metadata["blob_upload"] = state
        repo.update(recording_id, {"metadata": metadata})
    finally:
        db.close()


async def _emit(recording_id: str, state: dict | None, reliable: bool) -> None:
    """Push an upload state to connected clients over the system_status WebSocket."""
    try:
        from app.services.websocket.manager import manager

        await manager.broadcast(
            "system_status",
            {"recording_upload": {"recording_id": recording_id, "blob_upload": state}},
            reliable=reliable,
        )
    except Exception as exc:  # a missed push is recoverable on next load
        logger.warning("Could not emit upload event for %s: %s", recording_id, exc)


async def _persist_and_emit(recording_id: str, state: dict | None) -> None:
    """Save the upload state, then push it (reliably) to clients."""
    await asyncio.to_thread(_set_upload_state_sync, recording_id, state)
    await _emit(recording_id, state, reliable=True)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _timeout_s() -> int:
    """Age after which a queued/uploading state counts as abandoned."""
    return settings.UPLOAD_TIMEOUT_MINUTES * 60


def is_upload_in_progress(recording: dict) -> bool:
    """True if a fresh 'uploading' state is recorded (guards against duplicate jobs)."""
    from datetime import datetime, timezone

    state = (recording.get("metadata") or {}).get("blob_upload") or {}
    if state.get("status") not in ("queued", "uploading"):
        return False
    try:
        started = datetime.fromisoformat(state["started_at"])
    except (KeyError, ValueError):
        return False
    return (datetime.now(timezone.utc) - started).total_seconds() < _timeout_s()


async def begin_upload(recording: dict) -> threading.Event:
    """Mark the recording as queued and return its cancel flag (pass it to ``run_upload_job``)."""
    cancel = threading.Event()
    _cancel_events[recording["id"]] = cancel
    strategy = get_strategy()
    state = {"status": "queued", "timeout_s": _timeout_s(), "backend": strategy.name if strategy else None, "started_at": _now()}
    await _persist_and_emit(recording["id"], state)
    return cancel


async def cancel_upload(recording_id: str) -> None:
    """Cancel a queued or running upload and clear its state so the recording can be re-uploaded."""
    event = _cancel_events.get(recording_id)
    if event:
        event.set()  # the transfer thread / queued job notices this and stops
    await _persist_and_emit(recording_id, None)


async def upload_recording(
    recording: dict,
    on_progress: "Callable[[int, int], None] | None" = None,
) -> tuple[str, str]:
    """Upload a recording row's file under a readable name. Returns (bucket, key)."""
    strategy = get_strategy()
    if strategy is None:
        raise RuntimeError(f"Unknown storage backend '{settings.UPLOAD_BACKEND}'")
    key = await build_key(recording, strategy)
    await asyncio.to_thread(strategy.upload, Path(recording["file_path"]), key, on_progress)
    logger.info("Uploaded %s via %s to %s/%s", recording["file_path"], strategy.name, strategy.location, key)
    return strategy.location, key


_PROGRESS_PERSIST_INTERVAL_S = 5.0
_PROGRESS_MIN_INTERVAL_S = 0.5


def _make_progress_reporter(
    recording_id: str, backend: str | None, started_at: str, loop, cancel: threading.Event | None = None
):
    """Throttled thread-safe callback that pushes transfer progress to clients and saves it to the DB."""
    last_emit = 0.0
    last_saved = 0.0
    last_pct = -1

    def report(sent: int, total: int) -> None:
        nonlocal last_emit, last_pct, last_saved
        if cancel is not None and cancel.is_set():
            raise UploadCancelled()  # aborts the transfer (multipart uploads are aborted by the SDK)
        pct = int(sent * 100 / total) if total else 0
        now = time.monotonic()
        if pct == last_pct or (now - last_emit < _PROGRESS_MIN_INTERVAL_S and pct < 100):
            return
        last_emit, last_pct = now, pct
        state = {
            "status": "uploading", "timeout_s": _timeout_s(), "backend": backend, "started_at": started_at,
            "progress": pct, "bytes_sent": sent, "bytes_total": total,
        }
        if now - last_saved >= _PROGRESS_PERSIST_INTERVAL_S:
            last_saved = now
            asyncio.run_coroutine_threadsafe(_persist_and_emit(recording_id, state), loop)
        else:
            asyncio.run_coroutine_threadsafe(_emit(recording_id, state, reliable=False), loop)

    return report


_slots: tuple[int, asyncio.Semaphore] | None = None


def _get_slots() -> asyncio.Semaphore:
    """Limits concurrent uploads to UPLOAD_MAX_CONCURRENT; extra jobs wait as 'queued'.

    The limit is editable at runtime: a new semaphore is used for jobs that start after a change
    (uploads already running finish under the old one).
    """
    global _slots
    limit = settings.UPLOAD_MAX_CONCURRENT
    if _slots is None or _slots[0] != limit:
        _slots = (limit, asyncio.Semaphore(limit))
    return _slots[1]


async def run_upload_job(recording: dict, cancel: threading.Event | None = None) -> None:
    """Background job: wait for a free slot, upload, record the outcome. Never raises."""
    cancel = cancel or threading.Event()
    try:
        async with _get_slots():
            if cancel.is_set():  # cancelled while queued
                return
            await _run_upload(recording, cancel)
    finally:
        if _cancel_events.get(recording["id"]) is cancel:
            _cancel_events.pop(recording["id"], None)


async def _run_upload(recording: dict, cancel: threading.Event) -> None:
    strategy = get_strategy()
    backend = strategy.name if strategy else None
    started_at = _now()
    try:
        await _persist_and_emit(
            recording["id"],
            {"status": "uploading", "timeout_s": _timeout_s(), "backend": backend, "started_at": started_at},
        )
        reporter = _make_progress_reporter(
            recording["id"], backend, started_at, asyncio.get_running_loop(), cancel
        )
        bucket, key = await upload_recording(recording, reporter)
        state = {"status": "uploaded", "backend": backend, "bucket": bucket, "key": key, "uploaded_at": _now()}
    except Exception as exc:
        if cancel.is_set():  # user cancelled: state was already cleared by cancel_upload
            logger.info("Upload of %s cancelled", recording.get("id"))
            return
        logger.error("Blob upload failed for recording %s: %s", recording.get("id"), exc)
        reason = strategy.describe_error(exc) if strategy else str(exc)
        state = {"status": "failed", "backend": backend, "error": reason[:300], "failed_at": _now()}
    if cancel.is_set():
        return
    try:
        await _persist_and_emit(recording["id"], state)
    except Exception as exc:
        logger.error("Could not persist upload state for %s: %s", recording.get("id"), exc)


async def auto_upload_recording(recording: dict) -> None:
    """Fire-and-forget hook for newly created recordings; never raises."""
    if not settings.UPLOAD_AUTO:
        return
    try:
        status = await get_status(force=True)
        if not (status.configured and status.authenticated):
            logger.warning("Auto-upload skipped for %s: %s", recording.get("id"), status.reason)
            return
        cancel = await begin_upload(recording)
        await run_upload_job(recording, cancel)
    except Exception as exc:
        logger.error("Auto-upload failed for recording %s: %s", recording.get("id"), exc)
