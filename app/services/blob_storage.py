"""S3-compatible blob storage client (AWS S3 / MinIO) for recording uploads.

Credentials come from environment variables (see ``app.core.config.Settings``).
The feature is considered *configured* when bucket + access key + secret are set,
and *authenticated* when the credentials can actually reach the bucket.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_STATUS_TTL_S = 60.0


@dataclass(frozen=True)
class BlobStorageStatus:
    configured: bool
    authenticated: bool
    bucket: str | None = None
    reason: str | None = None


_cached: tuple[float, BlobStorageStatus] | None = None


def is_configured() -> bool:
    return bool(settings.S3_BUCKET and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY)


def _client():
    import boto3  # imported lazily so the app still boots without the dependency

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
    )


def _check_sync() -> BlobStorageStatus:
    if not is_configured():
        return BlobStorageStatus(configured=False, authenticated=False, reason="Not configured")
    try:
        _client().head_bucket(Bucket=settings.S3_BUCKET)
    except Exception as exc:  # botocore ClientError, endpoint/connection errors, missing boto3, ...
        logger.warning("Blob storage credential check failed: %s", exc)
        return BlobStorageStatus(
            configured=True, authenticated=False, bucket=settings.S3_BUCKET, reason="Authentication failed"
        )
    return BlobStorageStatus(configured=True, authenticated=True, bucket=settings.S3_BUCKET)


async def get_status(force: bool = False) -> BlobStorageStatus:
    """Check (with a short cache) whether the configured credentials work."""
    global _cached
    now = time.monotonic()
    if not force and _cached and now - _cached[0] < _STATUS_TTL_S:
        return _cached[1]
    status = await asyncio.to_thread(_check_sync)
    _cached = (now, status)
    return status


def _upload_sync(file_path: Path, key: str) -> None:
    _client().upload_file(str(file_path), settings.S3_BUCKET, key)


async def upload_file(file_path: Path, key: str) -> str:
    """Upload a local file; returns the object key."""
    await asyncio.to_thread(_upload_sync, file_path, key)
    logger.info("Uploaded %s to s3://%s/%s", file_path, settings.S3_BUCKET, key)
    return key


def _exists_sync(key: str) -> bool:
    try:
        _client().head_object(Bucket=settings.S3_BUCKET, Key=key)
        return True
    except Exception:
        return False


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.\- ]+", "_", name, flags=re.UNICODE).strip(" ._")
    return re.sub(r"\s+", "_", cleaned) or "recording"


async def build_key(recording: dict) -> str:
    """Readable object key ``<prefix>/<name>_<YYYY-MM-DD>.<ext>``.

    Mirrors the name the UI gives downloaded files. If an object with that key already
    exists (e.g. two recordings with the same name on the same day), a short id suffix
    is appended so nothing gets overwritten.
    """
    prefix = settings.S3_KEY_PREFIX.strip("/")
    ext = Path(recording["file_path"]).suffix or ".mcap"
    date = str(recording.get("created_at") or "")[:10]
    base = _safe_name(str(recording.get("name") or "recording"))
    stem = f"{base}_{date}" if date else base

    def join(s: str) -> str:
        return f"{prefix}/{s}{ext}" if prefix else f"{s}{ext}"

    key = join(stem)
    if await asyncio.to_thread(_exists_sync, key):
        key = join(f"{stem}_{str(recording['id'])[:8]}")
    return key


def _mark_uploaded_sync(recording_id: str, bucket: str, key: str) -> None:
    """Persist the upload in the recording's metadata so the UI can show it as uploaded."""
    from datetime import datetime, timezone

    from app.db.models import get_db
    from app.repositories.recordings_orm import RecordingRepository

    db = next(get_db())
    try:
        repo = RecordingRepository(db)
        current = repo.get_by_id(recording_id)
        if not current:
            return
        metadata = dict(current.get("metadata") or {})
        metadata["blob_upload"] = {
            "bucket": bucket,
            "key": key,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        repo.update(recording_id, {"metadata": metadata})
    finally:
        db.close()


async def upload_recording(recording: dict) -> tuple[str, str]:
    """Upload a recording row's file under a readable name. Returns (bucket, key)."""
    key = await build_key(recording)
    await upload_file(Path(recording["file_path"]), key)
    await asyncio.to_thread(_mark_uploaded_sync, recording["id"], settings.S3_BUCKET, key)
    return settings.S3_BUCKET, key


async def auto_upload_recording(recording: dict) -> None:
    """Fire-and-forget hook for newly created recordings; never raises."""
    if not settings.S3_AUTO_UPLOAD:
        return
    try:
        status = await get_status(force=True)
        if not (status.configured and status.authenticated):
            logger.warning("Auto-upload skipped for %s: %s", recording.get("id"), status.reason)
            return
        await upload_recording(recording)
    except Exception as exc:
        logger.error("Auto-upload failed for recording %s: %s", recording.get("id"), exc)
