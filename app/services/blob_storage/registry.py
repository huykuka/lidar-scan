"""Maps the STORAGE_BACKEND setting to a strategy implementation."""

from app.core.config import settings

from .base import StorageStrategy
from .s3 import S3Strategy

# Register new backends here.
_STRATEGIES: dict[str, type[StorageStrategy]] = {
    S3Strategy.name: S3Strategy,
}

_instances: dict[str, StorageStrategy] = {}


def get_strategy() -> StorageStrategy | None:
    """Strategy selected by ``STORAGE_BACKEND`` (default ``s3``); None if the name is unknown."""
    name = settings.STORAGE_BACKEND.lower()
    cls = _STRATEGIES.get(name)
    if cls is None:
        return None
    if name not in _instances:
        _instances[name] = cls()
    return _instances[name]


def available_backends() -> list[str]:
    return sorted(_STRATEGIES)
