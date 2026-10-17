"""S3-compatible strategy (AWS S3 / MinIO)."""

import threading
from collections.abc import Callable
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

from .base import StorageStatus, StorageStrategy

logger = get_logger(__name__)


class S3Strategy(StorageStrategy):
    name = "s3"

    @property
    def key_prefix(self) -> str:
        return settings.UPLOAD_S3_KEY_PREFIX.strip("/")

    @property
    def location(self) -> str:
        return settings.UPLOAD_S3_BUCKET

    def is_configured(self) -> bool:
        return bool(settings.UPLOAD_S3_BUCKET and settings.UPLOAD_S3_ACCESS_KEY_ID and settings.UPLOAD_S3_SECRET_ACCESS_KEY)

    def _client(self):
        import boto3  # imported lazily so the app still boots without the dependency

        from botocore.config import Config

        return boto3.client(
            "s3",
            # Generous timeouts + retries so slow or flaky links don't abort big uploads
            config=Config(connect_timeout=30, read_timeout=300, retries={"max_attempts": 10, "mode": "standard"}),
            endpoint_url=settings.UPLOAD_S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.UPLOAD_S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.UPLOAD_S3_SECRET_ACCESS_KEY,
            region_name=settings.UPLOAD_S3_REGION,
        )

    def check(self) -> StorageStatus:
        if not self.is_configured():
            return StorageStatus(False, False, self.name, reason="Not configured")
        try:
            self._client().head_bucket(Bucket=settings.UPLOAD_S3_BUCKET)
        except Exception as exc:  # ClientError, endpoint/connection errors, missing boto3, ...
            logger.warning("S3 credential check failed: %s", exc)
            return StorageStatus(True, False, self.name, settings.UPLOAD_S3_BUCKET, "Authentication failed")
        return StorageStatus(True, True, self.name, settings.UPLOAD_S3_BUCKET)

    def exists(self, key: str) -> bool:
        try:
            self._client().head_object(Bucket=settings.UPLOAD_S3_BUCKET, Key=key)
            return True
        except Exception:
            return False

    def upload(
        self,
        file_path: Path,
        key: str,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        total = file_path.stat().st_size
        sent = 0
        lock = threading.Lock()  # boto3 invokes the callback from several transfer threads

        def _callback(n: int) -> None:
            nonlocal sent
            with lock:
                sent += n
                current = sent
            if on_progress:
                on_progress(min(current, total), total)

        self._client().upload_file(
            str(file_path), settings.UPLOAD_S3_BUCKET, key, Callback=_callback if on_progress else None
        )

    def describe_error(self, exc: Exception) -> str:
        response = getattr(exc, "response", None)  # botocore ClientError
        if isinstance(response, dict):
            err = response.get("Error", {})
            code, msg = err.get("Code"), err.get("Message")
            if code:
                return f"{code}: {msg}" if msg else str(code)
        return super().describe_error(exc)
