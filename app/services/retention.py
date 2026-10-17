"""Recording retention: periodically delete recordings older than RETENTION_RECORDINGS_DAYS."""

import asyncio
import os
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SWEEP_INTERVAL_S = 3600

_task: asyncio.Task | None = None


def _parse(ts: str | None) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def sweep_recordings_sync(now: datetime | None = None) -> int:
    """Delete expired recordings (DB row + files). Returns how many were removed."""
    days = settings.RETENTION_RECORDINGS_DAYS
    if days <= 0:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)

    from app.db.models import get_db
    from app.repositories.recordings_orm import RecordingRepository

    removed = 0
    db = next(get_db())
    try:
        repo = RecordingRepository(db)
        for rec in repo.list():
            created = _parse(rec.get("created_at"))
            if created is None or created >= cutoff or rec.get("status", "ready") != "ready":
                continue
            if settings.RETENTION_ONLY_UPLOADED and not (rec.get("metadata") or {}).get("blob_upload"):
                continue
            repo.delete(rec["id"])
            for path in (rec.get("file_path"), rec.get("thumbnail_path")):
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except OSError as exc:
                    logger.error("Retention: could not delete %s: %s", path, exc)
            removed += 1
            logger.info("Retention: deleted recording %s (%s)", rec["id"], rec.get("name"))
    finally:
        db.close()
    return removed


async def _loop() -> None:
    while True:
        try:
            await asyncio.to_thread(sweep_recordings_sync)
        except Exception as exc:
            logger.error("Retention sweep failed: %s", exc)
        await asyncio.sleep(SWEEP_INTERVAL_S)


def start_retention() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


def stop_retention() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
