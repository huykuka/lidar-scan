import os
from pathlib import Path

from dotenv import load_dotenv

# Load the repo-root .env (real environment variables win). Docker passes env vars itself.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
from importlib.metadata import version, PackageNotFoundError


def _env(name: str, *legacy: str, default: str = "") -> str:
    """Env var ``name``, falling back to legacy names, then ``default``."""
    for key in (name, *legacy):
        value = os.getenv(key)
        if value is not None:
            return value
    return default


def _read_version() -> str:
    """Read the project version from package metadata (set in pyproject.toml).

    Falls back to parsing pyproject.toml directly when the package is not
    installed (e.g. during certain test or Docker build scenarios).
    """
    try:
        return version("lidar-standalone")
    except PackageNotFoundError:
        pass

    # Fallback: parse pyproject.toml relative to this file's repo root
    try:
        import tomllib
        from pathlib import Path

        toml_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
        return data["project"]["version"]
    except Exception:
        return "unknown"


class Settings:
    # API Settings
    PROJECT_NAME: str = "Lidar Studio API"
    VERSION: str = _read_version()
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8005))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    # Logging verbosity: DEBUG, INFO, WARNING or ERROR.
    APP_LOG_LEVEL: str = os.getenv("APP_LOG_LEVEL", "INFO").upper()

    # Passphrase (any string; longer/random is better) used to encrypt secret settings, e.g. the S3
    # keys, before they are stored in the database. Keep it OUT of the database and version control.
    SETTINGS_ENCRYPTION_KEY: str = os.getenv("SETTINGS_ENCRYPTION_KEY", "")

    # Recording upload: which storage strategy to use (see app/services/blob_storage/registry.py).
    # Env vars are named <CATEGORY>_<NAME>; the old STORAGE_* / S3_* names still work as fallbacks.
    UPLOAD_BACKEND: str = _env("UPLOAD_BACKEND", "STORAGE_BACKEND", default="s3")
    # Upload every newly recorded recording automatically (needs a configured, valid backend).
    UPLOAD_AUTO: bool = _env("UPLOAD_AUTO", "STORAGE_AUTO_UPLOAD", "S3_AUTO_UPLOAD", default="false").lower() == "true"

    # How many recordings upload to storage at the same time (the rest wait as 'queued').
    UPLOAD_MAX_CONCURRENT: int = max(1, int(_env("UPLOAD_MAX_CONCURRENT", "STORAGE_MAX_CONCURRENT_UPLOADS", default="2")))

    # An upload still 'queued'/'uploading' after this long is treated as abandoned (e.g. server restart)
    # and can be retried. Raise it for slow links / very large recordings.
    UPLOAD_TIMEOUT_MINUTES: int = max(1, int(_env("UPLOAD_TIMEOUT_MINUTES", "STORAGE_UPLOAD_TIMEOUT_MINUTES", default="120")))

    # S3-compatible backend (AWS S3 / MinIO). Leave unset to disable.
    UPLOAD_S3_ENDPOINT_URL: str = _env("UPLOAD_S3_ENDPOINT_URL", "S3_ENDPOINT_URL")
    UPLOAD_S3_ACCESS_KEY_ID: str = _env("UPLOAD_S3_ACCESS_KEY_ID", "S3_ACCESS_KEY_ID")
    UPLOAD_S3_SECRET_ACCESS_KEY: str = _env("UPLOAD_S3_SECRET_ACCESS_KEY", "S3_SECRET_ACCESS_KEY")
    UPLOAD_S3_BUCKET: str = _env("UPLOAD_S3_BUCKET", "S3_BUCKET")
    UPLOAD_S3_REGION: str = _env("UPLOAD_S3_REGION", "S3_REGION", default="us-east-1")
    UPLOAD_S3_KEY_PREFIX: str = _env("UPLOAD_S3_KEY_PREFIX", "S3_KEY_PREFIX", default="recordings")

    # Data retention: delete recordings older than N days (0 = keep forever).
    RETENTION_RECORDINGS_DAYS: int = int(_env("RETENTION_RECORDINGS_DAYS", "RECORDINGS_RETENTION_DAYS", default="0"))
    # Safety net: only delete recordings that were already uploaded to external storage.
    RETENTION_ONLY_UPLOADED: bool = os.getenv("RETENTION_ONLY_UPLOADED", "true").lower() == "true"
    RECORDINGS_DIR: str = os.getenv("RECORDINGS_DIR", "data/recordings")


settings = Settings()
