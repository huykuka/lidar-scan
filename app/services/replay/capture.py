"""Capture of node outputs during an offline replay run."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

# Payload keys that carry no comparable information.
_SKIP_KEYS = frozenset({
    "points", "pcds", "node_id", "lidar_id", "timestamp", "count", "shapes",
    # PlaybackNode metadata noise
    "frame", "total_frames", "playback_speed", "loopable", "source", "recording_id",
})
_MAX_VALUES_PER_OUTPUT = 64
_MAX_DEPTH = 2

Scalar = Any  # int | float | str | bool | None


def _to_scalar(value: Any) -> Tuple[bool, Scalar]:
    """Return (is_scalar, normalised_value)."""
    if isinstance(value, (bool, np.bool_)):
        return True, bool(value)
    if isinstance(value, (int, np.integer)):
        return True, int(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        return True, (None if math.isnan(f) or math.isinf(f) else f)
    if isinstance(value, str):
        return True, value[:200]
    return False, None


def flatten_values(payload: Dict[str, Any]) -> Dict[str, Scalar]:
    """Flatten scalar fields of a payload (and nested dicts, up to 2 levels)."""
    out: Dict[str, Scalar] = {}

    def walk(obj: Dict[str, Any], prefix: str, depth: int) -> None:
        for key, value in obj.items():
            if len(out) >= _MAX_VALUES_PER_OUTPUT:
                return
            if key in _SKIP_KEYS:
                continue
            name = f"{prefix}{key}"
            ok, scalar = _to_scalar(value)
            if ok:
                out[name] = scalar
            elif isinstance(value, dict) and depth < _MAX_DEPTH:
                walk(value, f"{name}.", depth + 1)

    walk(payload, "", 0)
    return out


def _point_count(payload: Dict[str, Any]) -> Optional[int]:
    points = payload.get("points")
    if points is None:
        return None
    try:
        return int(len(points))
    except TypeError:
        return None


class OutputCapture:
    """Collects, per node, one record for every ``forward_data`` call."""

    def __init__(self, frame_getter: Callable[[], int], node_meta: Dict[str, Dict[str, str]]):
        self._frame_getter = frame_getter
        self._node_meta = node_meta
        self.frames: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.saved_results: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []

    def record_output(self, node_id: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        self.frames[node_id].append({
            "frame": self._frame_getter(),
            "timestamp": _to_scalar(payload.get("timestamp"))[1],
            "points": _point_count(payload),
            "values": flatten_values(payload),
        })

    def record_error(self, source_id: str, target_id: str, exc: BaseException) -> None:
        self.errors.append({
            "frame": self._frame_getter(),
            "source": source_id,
            "node_id": target_id,
            "error": f"{type(exc).__name__}: {exc}",
        })

    def record_saved_result(
        self, node_id: str, metadata: Dict[str, Any], status: str, pcd_labels: List[str]
    ) -> None:
        self.saved_results.append({
            "frame": self._frame_getter(),
            "node_id": node_id,
            "status": status,
            "pcd_labels": pcd_labels,
            "values": flatten_values(metadata if isinstance(metadata, dict) else {}),
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": {
                node_id: {
                    "name": self._node_meta.get(node_id, {}).get("name", node_id),
                    "type": self._node_meta.get(node_id, {}).get("type", ""),
                    "frames": frames,
                }
                for node_id, frames in self.frames.items()
            },
            "saved_results": self.saved_results,
            "errors": self.errors,
        }


class CapturingResultsService:
    """Drop-in for ``ResultsStorageService`` that keeps results in memory.

    Replay nodes reuse the live node IDs, so they must never write to
    ``application_results`` or ``data/results``.
    """

    def __init__(self, capture: OutputCapture):
        self._capture = capture
        self._counter = 0

    async def save_result(self, node_id, pcds, metadata, status="success") -> str:
        self._counter += 1
        labels = [label for label, _ in (pcds or [])]
        self._capture.record_saved_result(node_id, metadata or {}, status, labels)
        return f"replay-result-{self._counter}"


def summarize(capture_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate per-node statistics for run listing and quick inspection."""
    nodes: Dict[str, Any] = {}
    for node_id, info in capture_dict["nodes"].items():
        frames = info["frames"]
        values: Dict[str, Dict[str, Any]] = {}
        for rec in frames:
            for key, val in rec["values"].items():
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    continue
                st = values.setdefault(
                    key, {"count": 0, "min": val, "max": val, "sum": 0.0, "sumsq": 0.0, "last": val}
                )
                st["count"] += 1
                st["min"] = min(st["min"], val)
                st["max"] = max(st["max"], val)
                st["sum"] += val
                st["sumsq"] += val * val
                st["last"] = val
        for st in values.values():
            st["mean"] = st.pop("sum") / st["count"]
            # Population std-dev (how much the value moves across frames); guard fp noise.
            variance = st.pop("sumsq") / st["count"] - st["mean"] ** 2
            st["std"] = math.sqrt(max(variance, 0.0))
        pts = [r["points"] for r in frames if r["points"] is not None]
        nodes[node_id] = {
            "name": info["name"],
            "type": info["type"],
            "emitted": len(frames),
            "points_mean": (sum(pts) / len(pts)) if pts else None,
            "values": values,
        }
    saved: Dict[str, int] = defaultdict(int)
    for rec in capture_dict["saved_results"]:
        saved[rec["node_id"]] += 1
    return {
        "nodes": nodes,
        "saved_results": dict(saved),
        "saved_results_total": len(capture_dict["saved_results"]),
        "errors_total": len(capture_dict["errors"]),
    }
