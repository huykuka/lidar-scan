import os
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

    # S3-compatible blob storage (AWS S3 / MinIO) used for recording backups.
    # Leave S3_BUCKET / keys unset to disable the feature.
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")
    S3_ACCESS_KEY_ID: str = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY: str = os.getenv("S3_SECRET_ACCESS_KEY", "")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
    S3_KEY_PREFIX: str = os.getenv("S3_KEY_PREFIX", "recordings")
    # Upload every newly recorded recording automatically (needs valid S3 credentials).
    S3_AUTO_UPLOAD: bool = os.getenv("S3_AUTO_UPLOAD", "false").lower() == "true"


settings = Settings()
