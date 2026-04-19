"""
Spatial IoU-based shape tracker.

Stabilizes shape IDs across frames when noisy point clouds cause DBSCAN
clusters to shift/split/merge, preventing frontend flicker caused by
hash-based ID churn.

Algorithm
---------
Each frame:
1. For every incoming shape, find the best candidate in the previous frame
   using AABB IoU (cubes) or Euclidean distance (labels/planes).
2. Greedily assign the highest-scoring pair first (no double-assignment).
3. Reuse the previous stable ID when the match score exceeds the threshold.
4. Issue a brand-new monotonic ID for unmatched shapes.
5. Store the result as the new "previous frame" for the next cycle.

Threading note: ShapeTracker is intentionally *not* thread-safe.  It is
called from the asyncio event loop in DataRouter.publish_shapes() which
runs single-threaded — no locking required.
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Matching thresholds
# ---------------------------------------------------------------------------

_CUBE_IOU_THRESHOLD: float = 0.3
"""Minimum AABB IoU for two cubes to be considered the same object."""

_DISTANCE_THRESHOLD: float = 2.0
"""Maximum centre-to-centre distance (metres) for labels/planes to match."""


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def aabb_iou(
    c1: List[float],
    s1: List[float],
    c2: List[float],
    s2: List[float],
) -> float:
    """
    Compute IoU between two axis-aligned bounding boxes.

    Args:
        c1: Centre of box 1 as [x, y, z].
        s1: Full extents of box 1 as [sx, sy, sz].
        c2: Centre of box 2 as [x, y, z].
        s2: Full extents of box 2 as [sx, sy, sz].

    Returns:
        IoU in [0, 1].
    """
    overlap: float = 1.0
    for i in range(3):
        min1 = c1[i] - s1[i] / 2
        max1 = c1[i] + s1[i] / 2
        min2 = c2[i] - s2[i] / 2
        max2 = c2[i] + s2[i] / 2
        overlap_dim = max(0.0, min(max1, max2) - max(min1, min2))
        overlap *= overlap_dim

    vol1: float = s1[0] * s1[1] * s1[2]
    vol2: float = s2[0] * s2[1] * s2[2]
    union: float = vol1 + vol2 - overlap
    return overlap / union if union > 0.0 else 0.0


def _euclidean(p1: List[float], p2: List[float]) -> float:
    """Euclidean distance between two 3-D points."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def _shape_center(shape: Dict[str, Any]) -> Optional[List[float]]:
    """Return the representative 3-D point for a shape, or None."""
    t = shape.get("type")
    if t == "cube":
        return shape.get("center")
    if t == "plane":
        return shape.get("center")
    if t == "label":
        return shape.get("position")
    return None


# ---------------------------------------------------------------------------
# ShapeTracker
# ---------------------------------------------------------------------------


class ShapeTracker:
    """
    Stateful tracker that assigns stable IDs to shapes across frames.

    Usage::

        tracker = ShapeTracker()
        # call once per frame after collecting raw shapes from nodes
        stabilized = tracker.stabilize(raw_shapes)
        # stabilized is the same list with "id" fields mutated in-place
    """

    def __init__(self) -> None:
        self._prev: List[Dict[str, Any]] = []
        """Previous frame's shapes with their assigned stable IDs."""

        self._counter: int = 0
        """Monotonic counter for new stable IDs."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stabilize(self, shapes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Match incoming shapes to previous frame and assign stable IDs.

        Args:
            shapes: Raw shape dicts (may have empty or hash-based ``id``
                    fields — they will be overwritten).

        Returns:
            The same list, with ``id`` fields set to stable tracker IDs.
        """
        if not self._prev:
            # First frame — assign fresh IDs to everything
            for shape in shapes:
                shape["id"] = self._new_id()
            self._prev = [dict(s) for s in shapes]
            return shapes

        matched_prev: set[int] = set()  # indices into self._prev already used

        # Build candidate scores: list of (score, incoming_idx, prev_idx)
        # Higher score = better match.  We use IoU for cubes (higher=better)
        # and *negative* distance for labels/planes (higher=better → less negative).
        candidates: List[Tuple[float, int, int]] = []

        for inc_idx, inc in enumerate(shapes):
            inc_type = inc.get("type")
            inc_node = inc.get("node_name")

            for prev_idx, prev in enumerate(self._prev):
                # Must be same type AND same node
                if prev.get("type") != inc_type or prev.get("node_name") != inc_node:
                    continue

                score = self._match_score(inc, prev)
                if score is not None:
                    candidates.append((score, inc_idx, prev_idx))

        # Sort descending (best match first) for greedy assignment
        candidates.sort(key=lambda t: t[0], reverse=True)

        assigned: Dict[int, str] = {}  # incoming_idx → stable_id

        for score, inc_idx, prev_idx in candidates:
            if inc_idx in assigned or prev_idx in matched_prev:
                continue
            assigned[inc_idx] = self._prev[prev_idx]["id"]
            matched_prev.add(prev_idx)

        # Apply IDs
        for idx, shape in enumerate(shapes):
            shape["id"] = assigned.get(idx) or self._new_id()

        self._prev = [dict(s) for s in shapes]
        return shapes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_id(self) -> str:
        """Generate a new monotonically-increasing stable ID."""
        self._counter += 1
        return f"shape_{uuid.uuid4().hex[:12]}_{self._counter}"

    def _match_score(
        self, inc: Dict[str, Any], prev: Dict[str, Any]
    ) -> Optional[float]:
        """
        Compute a match score between an incoming shape and a previous shape.

        Returns:
            A float score where higher means better match, or ``None`` if the
            pair is below the matching threshold (should not be considered).
        """
        t = inc.get("type")

        if t == "cube":
            inc_center = inc.get("center")
            inc_size = inc.get("size")
            prev_center = prev.get("center")
            prev_size = prev.get("size")
            if not (inc_center and inc_size and prev_center and prev_size):
                return None
            iou = aabb_iou(inc_center, inc_size, prev_center, prev_size)
            return iou if iou >= _CUBE_IOU_THRESHOLD else None

        # label / plane — distance-based
        inc_pos = _shape_center(inc)
        prev_pos = _shape_center(prev)
        if inc_pos is None or prev_pos is None:
            return None
        dist = _euclidean(inc_pos, prev_pos)
        if dist >= _DISTANCE_THRESHOLD:
            return None
        # Convert distance to a score where closer → higher
        return _DISTANCE_THRESHOLD - dist
