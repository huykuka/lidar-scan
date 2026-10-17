import os
from pathlib import Path

from dotenv import load_dotenv

# Load the repo-root .env (real environment variables win). Docker passes env vars itself.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
from importlib.metadata import version, PackageNotFoundError


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

    # Passphrase (any string; longer/random is better) used to encrypt secret settings, e.g. the S3
    # keys, before they are stored in the database. Keep it OUT of the database and version control.
    SETTINGS_ENCRYPTION_KEY: str = os.getenv("SETTINGS_ENCRYPTION_KEY", "")

    # Recording upload: which storage strategy to use (see app/services/blob_storage/registry.py)
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "s3")
    # Upload every newly recorded recording automatically (needs a configured, valid backend).
    # S3_AUTO_UPLOAD is accepted as a legacy alias.
    STORAGE_AUTO_UPLOAD: bool = (
        os.getenv("STORAGE_AUTO_UPLOAD", os.getenv("S3_AUTO_UPLOAD", "false")).lower() == "true"
    )

    # How many recordings upload to storage at the same time (the rest wait as 'queued').
    STORAGE_MAX_CONCURRENT_UPLOADS: int = max(1, int(os.getenv("STORAGE_MAX_CONCURRENT_UPLOADS", "2")))

    # S3-compatible backend (AWS S3 / MinIO). Leave unset to disable.
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")
    S3_ACCESS_KEY_ID: str = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY: str = os.getenv("S3_SECRET_ACCESS_KEY", "")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
    S3_KEY_PREFIX: str = os.getenv("S3_KEY_PREFIX", "recordings")

    # Data retention: delete recordings older than N days (0 = keep forever).
    RECORDINGS_RETENTION_DAYS: int = int(os.getenv("RECORDINGS_RETENTION_DAYS", 0))
    # Safety net: only delete recordings that were already uploaded to external storage.
    RETENTION_ONLY_UPLOADED: bool = os.getenv("RETENTION_ONLY_UPLOADED", "true").lower() == "true"


settings = Settings()
