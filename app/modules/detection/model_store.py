"""
Model store — file-based storage for uploaded detection model checkpoints.

Uploaded ``.pth`` files are persisted under ``models/detection/`` alongside a
lightweight ``models.json`` manifest that records metadata (display name,
model type, upload timestamp, file size).

The store provides a pure-Python API consumed by both:
* The REST endpoint (``/api/v1/detection/models``) for upload/list/delete.
* The registry (``registry.py``) which builds the dynamic checkpoint
  dropdown for the node-definition schema.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

_MODELS_DIR = Path("models") / "detection"
_MANIFEST_FILE = _MODELS_DIR / "models.json"
_ALLOWED_EXTENSIONS = {".pth", ".pt", ".onnx", ".bin"}


@dataclass
class ModelEntry:
    """Metadata for a single uploaded model checkpoint."""

    id: str
    filename: str
    display_name: str
    model_type: str  # e.g. "pointpillars"
    file_size: int = 0
    uploaded_at: float = field(default_factory=time.time)
    description: str = ""

    def to_dict(self, base_dir: Optional[Path] = None) -> Dict[str, object]:
        d = asdict(self)
        d["path"] = str((base_dir or _MODELS_DIR) / self.filename)
        return d


class ModelStore:
    """Thread-safe file-based model checkpoint store."""

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        self._dir = models_dir or _MODELS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self._dir / "models.json"
        self._entries: Dict[str, ModelEntry] = {}
        self._load_manifest()

    # ── Manifest persistence ────────────────────────────────────────────

    def _load_manifest(self) -> None:
        if not self._manifest.exists():
            self._entries = {}
            return
        try:
            raw = json.loads(self._manifest.read_text())
            self._entries = {
                k: ModelEntry(**v) for k, v in raw.items()
            }
        except Exception as exc:
            logger.warning("Failed to load model manifest: %s", exc)
            self._entries = {}

    def _save_manifest(self) -> None:
        data = {k: asdict(v) for k, v in self._entries.items()}
        self._manifest.write_text(json.dumps(data, indent=2))

    # ── Public API ──────────────────────────────────────────────────────

    def list_models(self) -> List[ModelEntry]:
        """Return all registered model entries sorted by upload time."""
        return sorted(self._entries.values(), key=lambda e: e.uploaded_at, reverse=True)

    def get_model(self, model_id: str) -> Optional[ModelEntry]:
        """Look up a model by its ID."""
        return self._entries.get(model_id)

    def get_checkpoint_path(self, model_id: str) -> Optional[str]:
        """Return the absolute checkpoint path for a model ID, or ``None``."""
        entry = self._entries.get(model_id)
        if entry is None:
            return None
        abs_path = (self._dir / entry.filename).resolve()
        if not abs_path.exists():
            return None
        return str(abs_path)

    def add_model(
        self,
        filename: str,
        data: bytes,
        display_name: str = "",
        model_type: str = "pointpillars",
        description: str = "",
    ) -> ModelEntry:
        """
        Persist a checkpoint file and register it in the manifest.

        Args:
            filename: Original upload filename (e.g. ``"kitti_weights.pth"``).
            data: Raw file bytes.
            display_name: Human-readable label shown in the UI dropdown.
            model_type: Which ``DetectionModel`` backend this checkpoint is for.
            description: Optional longer description.

        Returns:
            The newly created :class:`ModelEntry`.

        Raises:
            ValueError: If the file extension is not allowed.
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}"
            )

        model_id = uuid.uuid4().hex[:12]
        safe_name = f"{model_id}_{filename.replace('/', '_').replace(os.sep, '_')}"
        dest = self._dir / safe_name

        dest.write_bytes(data)
        logger.info("Saved model checkpoint: %s (%d bytes)", dest, len(data))

        entry = ModelEntry(
            id=model_id,
            filename=safe_name,
            display_name=display_name or os.path.splitext(filename)[0],
            model_type=model_type,
            file_size=len(data),
            description=description,
        )
        self._entries[model_id] = entry
        self._save_manifest()
        self._notify_schema_update()
        return entry

    def delete_model(self, model_id: str) -> bool:
        """
        Remove a model from the manifest and delete the checkpoint file.

        Returns:
            ``True`` if the model was found and deleted, ``False`` otherwise.
        """
        entry = self._entries.pop(model_id, None)
        if entry is None:
            return False
        try:
            (self._dir / entry.filename).resolve().unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to delete checkpoint file: %s", exc)
        self._save_manifest()
        self._notify_schema_update()
        return True

    def get_checkpoint_options(self) -> List[Dict[str, str]]:
        """
        Return ``[{label, value}]`` list for the node-definition checkpoint
        dropdown.  ``value`` is the model ID (resolved to a path at runtime).
        """
        return [
            {"label": e.display_name, "value": e.id}
            for e in self.list_models()
        ]

    def _entry_path(self, entry: ModelEntry) -> Path:
        """Return the absolute path for an entry's checkpoint file."""
        return (self._dir / entry.filename).resolve()

    @staticmethod
    def _notify_schema_update() -> None:
        """Refresh the node-definition checkpoint dropdown after store changes."""
        try:
            from app.modules.detection.registry import refresh_checkpoint_options
            refresh_checkpoint_options()
        except ImportError:
            pass


# ── Module-level singleton ──────────────────────────────────────────────
_store: Optional[ModelStore] = None


def get_model_store() -> ModelStore:
    """Return the global :class:`ModelStore` singleton."""
    global _store
    if _store is None:
        _store = ModelStore()
    return _store
