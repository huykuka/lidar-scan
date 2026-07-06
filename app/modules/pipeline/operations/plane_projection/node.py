"""
PlaneProjection — Pipeline Operation
=====================================

Projects a 3D point cloud onto one of the three axis-aligned planes by
zeroing out the dropped coordinate.

NUMPY_ONLY: apply() receives and returns a raw (N, M) numpy array.
No Open3D allocation, no thread hop.

    XY plane (axis="z"): drop Z  → projected_z = 0
    XZ plane (axis="y"): drop Y  → projected_y = 0
    YZ plane (axis="x"): drop X  → projected_x = 0

Columns beyond X/Y/Z are preserved unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

import numpy as np

from ...base import PipelineOperation

logger = logging.getLogger(__name__)

_VALID_AXES = {"x", "y", "z"}
_AXIS_COL = {"x": 0, "y": 1, "z": 2}
_PLANE_LABEL = {"x": "YZ", "y": "XZ", "z": "XY"}


class PlaneProjection(PipelineOperation):
    """
    Projects every point onto an axis-aligned plane by zeroing one coordinate.

    NUMPY_ONLY: single slice-assignment, sub-millisecond for any cloud size.
    """

    NUMPY_ONLY = True

    def __init__(self, axis: str = "z", inplace: bool = False) -> None:
        axis = str(axis).lower().strip()
        if axis not in _VALID_AXES:
            raise ValueError(f"axis must be 'x', 'y', or 'z', got '{axis}'")
        self.axis = axis
        self.col = _AXIS_COL[axis]
        self.inplace = bool(inplace)

    def apply(self, pts: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        if pts.shape[0] == 0:
            return pts, {"projected_axis": self.axis, "point_count": 0}

        mean_before = float(pts[:, self.col].mean())
        out = pts if self.inplace else pts.copy()
        out[:, self.col] = 0.0

        return out, {
            "projected_axis": self.axis,
            "projection_plane": _PLANE_LABEL[self.axis],
            "point_count": int(pts.shape[0]),
            "mean_dropped_coord": round(mean_before, 4),
        }
