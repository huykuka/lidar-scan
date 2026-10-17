"""Storage strategy interface for recording uploads.

To add a new backend (Azure Blob, GCS, SFTP, ...): subclass :class:`StorageStrategy`,
implement the blocking primitives, and register it in ``registry.py``.
All methods are synchronous; the facade in ``__init__`` runs them in worker threads.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageStatus:
    configured: bool
    authenticated: bool
    backend: str
    #: bucket / container / share the files go to
    bucket: str | None = None
    reason: str | None = None


class StorageStrategy(ABC):
    #: identifier used by the UPLOAD_BACKEND setting
    name: str

    @property
    def key_prefix(self) -> str:
        """Folder-like prefix every uploaded object is placed under (no surrounding slashes)."""
        return ""

    @property
    @abstractmethod
    def location(self) -> str:
        """Human-readable destination (bucket / container name)."""

    @abstractmethod
    def is_configured(self) -> bool:
        """True when all required settings/credentials are present."""

    @abstractmethod
    def check(self) -> StorageStatus:
        """Verify the credentials actually work (blocking network call)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Whether an object with this key already exists."""

    @abstractmethod
    def upload(
        self,
        file_path: Path,
        key: str,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """Upload a local file under ``key``. Raises on failure.

        ``on_progress(bytes_sent, bytes_total)`` may be called from a worker thread; backends
        should call it as data is transferred (it is optional to support).
        """

    def describe_error(self, exc: Exception) -> str:
        """Short, user-facing reason for a failed upload. Backends may override for nicer messages."""
        return f"{type(exc).__name__}: {exc}"
