"""File-based library of reference point clouds used by the matching node.

Layout (one directory per asset)::

    <root>/<id>/cloud.npy   float32 (N, 3) points, metres
    <root>/<id>/meta.json   name, source file, counts, bounding box, timestamps

No DB table is needed: the node only holds an ``asset_id`` and calls
``ReferenceStore.load``.  ``version`` (meta mtime) lets running nodes notice
that an asset was replaced.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

SUPPORTED_EXTENSIONS = (".pcd", ".ply", ".xyz", ".xyzn", ".xyzrgb", ".pts", ".npy")
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_NAME_MAX = 120


class AssetError(ValueError):
    """Raised for invalid uploads (bad format, empty cloud, ...)."""


class AssetNotFound(KeyError):
    pass


def _default_root() -> Path:
    return Path(os.getenv("POINT_CLOUD_ASSETS_DIR", "data/assets/point_clouds"))


def parse_point_cloud_bytes(raw: bytes, filename: str) -> np.ndarray:
    """Decode an uploaded file into an (N, 3) float32 array."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise AssetError(
            f"Unsupported file type '{ext or filename}'. "
            f"Allowed: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    if not raw:
        raise AssetError("Uploaded file is empty")

    if ext == ".npy":
        import io
        try:
            arr = np.load(io.BytesIO(raw), allow_pickle=False)
        except Exception as exc:
            raise AssetError(f"Failed to parse .npy file: {exc}") from exc
        if arr.ndim != 2 or arr.shape[1] < 3:
            raise AssetError("A .npy file must contain an (N, 3+) array")
        points = arr[:, :3]
    else:
        import open3d as o3d  # heavy import — keep lazy
        fd, tmp = tempfile.mkstemp(suffix=ext)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(raw)
            pcd = o3d.io.read_point_cloud(tmp)
        except Exception as exc:
            raise AssetError(f"Failed to parse point cloud: {exc}") from exc
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        points = np.asarray(pcd.points)

    points = np.asarray(points, dtype=np.float32)
    points = points[np.isfinite(points).all(axis=1)]
    if len(points) == 0:
        raise AssetError("Point cloud contains no valid points")
    return points


class ReferenceStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else _default_root()
        self._lock = threading.Lock()

    # ── helpers ────────────────────────────────────────────────────────────

    def _dir(self, asset_id: str) -> Path:
        if not _ID_RE.match(asset_id or ""):
            raise AssetNotFound(asset_id)
        return self.root / asset_id

    def _read_meta(self, asset_id: str) -> Dict[str, Any]:
        path = self._dir(asset_id) / "meta.json"
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            raise AssetNotFound(asset_id) from None

    # ── CRUD ───────────────────────────────────────────────────────────────

    def create(self, name: str, filename: str, points: np.ndarray, size_bytes: int = 0) -> Dict[str, Any]:
        name = (name or "").strip()[:_NAME_MAX] or Path(filename).stem[:_NAME_MAX] or "reference"
        asset_id = uuid.uuid4().hex
        mn, mx = points.min(axis=0), points.max(axis=0)
        meta = {
            "id": asset_id,
            "name": name,
            "filename": os.path.basename(filename),
            "format": Path(filename).suffix.lower().lstrip("."),
            "point_count": int(len(points)),
            "size_bytes": int(size_bytes),
            "bbox_min": [float(v) for v in mn],
            "bbox_max": [float(v) for v in mx],
            "extent": [float(v) for v in (mx - mn)],
            "created_at": time.time(),
        }
        with self._lock:
            d = self._dir(asset_id)
            d.mkdir(parents=True, exist_ok=True)
            np.save(d / "cloud.npy", points.astype(np.float32))
            (d / "meta.json").write_text(json.dumps(meta))
        return meta

    def list(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        items = []
        for d in self.root.iterdir():
            if not d.is_dir() or not _ID_RE.match(d.name):
                continue
            try:
                items.append(json.loads((d / "meta.json").read_text()))
            except (OSError, ValueError):
                continue  # half-written / corrupt asset — ignore
        return sorted(items, key=lambda m: m.get("created_at", 0), reverse=True)

    def get(self, asset_id: str) -> Dict[str, Any]:
        return self._read_meta(asset_id)

    def rename(self, asset_id: str, name: str) -> Dict[str, Any]:
        name = (name or "").strip()[:_NAME_MAX]
        if not name:
            raise AssetError("Name must not be empty")
        with self._lock:
            meta = self._read_meta(asset_id)
            meta["name"] = name
            (self._dir(asset_id) / "meta.json").write_text(json.dumps(meta))
        return meta

    def load(self, asset_id: str) -> np.ndarray:
        try:
            return np.load(self._dir(asset_id) / "cloud.npy")
        except FileNotFoundError:
            raise AssetNotFound(asset_id) from None

    def version(self, asset_id: str) -> Optional[float]:
        """Cheap change token (mtime of the cloud file); None when missing."""
        try:
            return (self._dir(asset_id) / "cloud.npy").stat().st_mtime_ns
        except (FileNotFoundError, AssetNotFound):
            return None

    def delete(self, asset_id: str) -> None:
        d = self._dir(asset_id)
        with self._lock:
            if not d.is_dir():
                raise AssetNotFound(asset_id)
            shutil.rmtree(d)

    def preview(self, asset_id: str, max_points: int = 20000) -> np.ndarray:
        pts = self.load(asset_id)
        if len(pts) > max_points:
            idx = np.linspace(0, len(pts) - 1, max_points).astype(np.int64)
            pts = pts[idx]
        return pts


reference_store = ReferenceStore()
