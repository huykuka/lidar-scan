"""Point-cloud capture (during a run) and reading/diffing (afterwards) for visual diff.

Frames are appended to one raw float32 file per captured node, so memory stays flat no
matter how long the recording is.  ``index.json`` maps ``node -> frame -> (offset, count)``.
"""
from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree

#: Per-frame cap; larger clouds are decimated with a fixed stride.
MAX_POINTS_PER_FRAME = 250_000
#: Hard cap for all captured clouds of one run (stops capturing, flags ``truncated``).
MAX_RUN_BYTES = 2 * 1024 ** 3
_BYTES_PER_POINT = 12

HEADER_FORMAT = "<IIIIff8x"  # nA, nB, onlyA, onlyB, meanDistA, meanDistB, pad -> 32 bytes
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def clouds_dir(run_dir: Path) -> Path:
    return run_dir / "clouds"


class CloudCapture:
    """Streams the point clouds of selected nodes to disk, one frame at a time."""

    def __init__(self, run_dir: Path, node_ids: Iterable[str], frame_getter):
        self._dir = clouds_dir(run_dir)
        self._ids = list(dict.fromkeys(node_ids))
        self._frame_getter = frame_getter
        self._index: Dict[str, Dict[int, Tuple[int, int]]] = {nid: {} for nid in self._ids}
        self._points_written: Dict[str, int] = {nid: 0 for nid in self._ids}
        self._handles: Dict[str, Any] = {}
        # Latest emission per node, written once its frame is over (a node may emit several
        # times per frame and only the last one is kept, so don't spend disk on the others).
        self._pending: Dict[str, Tuple[int, np.ndarray]] = {}
        self._bytes = 0
        self.truncated = False
        if self._ids:
            self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return bool(self._ids)

    def record(self, node_id: str, payload: Any) -> None:
        if node_id not in self._index or not isinstance(payload, dict):
            return
        points = payload.get("points")
        if points is None:
            return
        arr = np.asarray(points)
        if arr.ndim != 2 or arr.shape[1] < 3 or len(arr) == 0:
            return
        if len(arr) > MAX_POINTS_PER_FRAME:
            arr = arr[np.linspace(0, len(arr) - 1, MAX_POINTS_PER_FRAME).astype(np.int64)]
        xyz = np.array(arr[:, :3], dtype="<f4", order="C", copy=True)  # own the data: it is written later
        frame = int(self._frame_getter())
        pending = self._pending.get(node_id)
        if pending is not None and pending[0] != frame:
            self._flush(node_id)
        self._pending[node_id] = (frame, xyz)

    def _flush(self, node_id: str) -> None:
        frame, xyz = self._pending.pop(node_id)
        if self._bytes + xyz.nbytes > MAX_RUN_BYTES:
            self.truncated = True
            return
        handle = self._handles.get(node_id)
        if handle is None:
            handle = self._handles[node_id] = open(self._dir / f"{node_id}.bin", "ab")
        handle.write(xyz.tobytes())
        self._bytes += xyz.nbytes
        self._index[node_id][frame] = (self._points_written[node_id], len(xyz))
        self._points_written[node_id] += len(xyz)

    def finalize(self, node_names: Dict[str, str]) -> Dict[str, Any]:
        """Close files, write ``index.json`` and return the summary stored on the run."""
        for node_id in list(self._pending):
            self._flush(node_id)
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
        index = {
            nid: {str(f): list(v) for f, v in frames.items()}
            for nid, frames in self._index.items() if frames
        }
        if index:
            (self._dir / "index.json").write_text(json.dumps(index))
        return {
            nid: {
                "name": node_names.get(nid, nid),
                "frames": sorted(int(f) for f in frames),
                "max_points": max(c for _, c in self._index[nid].values()),
                "truncated": self.truncated,
            }
            for nid, frames in self._index.items() if frames
        }

    def discard(self) -> None:
        self._pending.clear()
        for handle in self._handles.values():
            try:
                handle.close()
            except Exception:
                pass
        self._handles.clear()
        shutil.rmtree(self._dir, ignore_errors=True)


def read_cloud(run_dir: Path, node_id: str, frame: int) -> Optional[np.ndarray]:
    """Return the captured (N, 3) float32 cloud for one node/frame, or None."""
    index_path = clouds_dir(run_dir) / "index.json"
    bin_path = clouds_dir(run_dir) / f"{node_id}.bin"
    if not index_path.exists() or not bin_path.exists():
        return None
    entry = json.loads(index_path.read_text()).get(node_id, {}).get(str(frame))
    if entry is None:
        return None
    offset, count = entry
    data = np.fromfile(bin_path, dtype="<f4", count=count * 3, offset=offset * _BYTES_PER_POINT)
    return data.reshape(-1, 3)


def diff_clouds(a: np.ndarray, b: np.ndarray, tol: float) -> Dict[str, Any]:
    """Flag points of each cloud that have no counterpart within ``tol`` in the other."""
    if len(a) == 0 or len(b) == 0:
        return {
            "flags_a": np.ones(len(a), dtype=np.uint8),
            "flags_b": np.ones(len(b), dtype=np.uint8),
            "mean_a": 0.0, "mean_b": 0.0,
        }
    dist_a, _ = cKDTree(b).query(a)
    dist_b, _ = cKDTree(a).query(b)
    return {
        "flags_a": (dist_a > tol).astype(np.uint8),
        "flags_b": (dist_b > tol).astype(np.uint8),
        "mean_a": float(dist_a.mean()),
        "mean_b": float(dist_b.mean()),
    }


def _pad4(n: int) -> bytes:
    return b"\x00" * (-n % 4)


def pack_cloud_diff(a: np.ndarray, b: np.ndarray, diff: Dict[str, Any]) -> bytes:
    """Binary layout (little endian), 4-byte aligned so JS can wrap it in typed arrays::

        header(32): u32 nA, u32 nB, u32 onlyA, u32 onlyB, f32 meanDistA, f32 meanDistB, pad
        f32[nA*3] A xyz | u8[nA] A flags (+pad) | f32[nB*3] B xyz | u8[nB] B flags (+pad)

    A flag of 1 means "no counterpart in the other cloud within tolerance".
    """
    fa, fb = diff["flags_a"], diff["flags_b"]
    header = struct.pack(
        HEADER_FORMAT, len(a), len(b), int(fa.sum()), int(fb.sum()), diff["mean_a"], diff["mean_b"]
    )
    return b"".join([
        header,
        np.ascontiguousarray(a, dtype="<f4").tobytes(),
        fa.tobytes(), _pad4(len(fa)),
        np.ascontiguousarray(b, dtype="<f4").tobytes(),
        fb.tobytes(), _pad4(len(fb)),
    ])


def common_cloud_nodes(summary_a: Dict[str, Any], summary_b: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Nodes captured in both runs with the frames available in both."""
    ca, cb = summary_a.get("clouds") or {}, summary_b.get("clouds") or {}
    out = []
    for node_id in sorted(set(ca) & set(cb)):
        frames = sorted(set(ca[node_id]["frames"]) & set(cb[node_id]["frames"]))
        if frames:
            out.append({
                "node_id": node_id,
                "name": ca[node_id]["name"],
                "frames": frames,
                "truncated": bool(ca[node_id].get("truncated") or cb[node_id].get("truncated")),
            })
    return out
