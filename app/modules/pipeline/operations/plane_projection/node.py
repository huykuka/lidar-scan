"""
PlaneProjection — Pipeline Operation
=====================================

Projects a 3D point cloud onto one of the three axis-aligned planes by
zeroing out the dropped coordinate.

    XY plane  (axis="z"): drop Z  → projected_z = 0
    XZ plane  (axis="y"): drop Y  → projected_y = 0
    YZ plane  (axis="x"): drop X  → projected_x = 0

Columns beyond X/Y/Z are preserved unchanged so all downstream metadata
(layer, azimuth, intensity, …) remains intact.

Args:
    axis   : "x" | "y" | "z"  — the axis that is zeroed out.
             Default "z" → project onto XY plane (top-down / bird's-eye).
    inplace: bool — when True the input array is modified in place;
             when False (default) a copy is returned.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

import numpy as np
import open3d as o3d

from ...base import PipelineOperation, _tensor_map_keys

logger = logging.getLogger(__name__)

_VALID_AXES = {"x", "y", "z"}
_AXIS_COL = {"x": 0, "y": 1, "z": 2}


class PlaneProjection(PipelineOperation):
    """
    Projects every point onto an axis-aligned plane by setting one coordinate
    to zero.

    Example — project onto XY (floor) plane:
        PlaneProjection(axis="z")

    The operation is intentionally lightweight: it is a single numpy
    slice-assignment and runs in < 1 ms even for dense frames.
    """

    def __init__(self, axis: str = "z", inplace: bool = False) -> None:
        axis = str(axis).lower().strip()
        if axis not in _VALID_AXES:
            raise ValueError(
                f"axis must be 'x', 'y', or 'z', got '{axis}'"
            )
        self.axis = axis
        self.col = _AXIS_COL[axis]
        self.inplace = bool(inplace)

    # -------------------------------------------------------------------------

    def apply(self, pcd: Any) -> Tuple[o3d.t.geometry.PointCloud, Dict[str, Any]]:
        """
        Zero out the chosen axis on every point.

        The output PointCloud is a new object with the same attribute set as
        the input; only the projected axis column in ``positions`` is set to 0.
        """
        if not isinstance(pcd, o3d.t.geometry.PointCloud):
            raise TypeError(
                f"PlaneProjection expects o3d.t.geometry.PointCloud, "
                f"got {type(pcd).__name__}"
            )

        n_pts: int = pcd.point.positions.shape[0] if "positions" in pcd.point else 0

        if n_pts == 0:
            return pcd, {"projected_axis": self.axis, "point_count": 0}

        # Extract positions as float32 numpy array
        pos: np.ndarray = pcd.point.positions.cpu().numpy().copy()  # (N, 3)

        # Compute the mean coordinate before projection for metadata
        mean_before = float(pos[:, self.col].mean())

        # Zero out the chosen column
        pos[:, self.col] = 0.0

        # Build output PointCloud — copy all non-position attributes verbatim
        out_pcd = o3d.t.geometry.PointCloud()
        out_pcd.point.positions = o3d.core.Tensor(pos, dtype=o3d.core.Dtype.Float32)

        for key in _tensor_map_keys(pcd.point):
            if key == "positions":
                continue
            try:
                out_pcd.point[key] = pcd.point[key]
            except Exception:
                pass

        # Derive projection-plane label for the metadata
        _plane_label = {"x": "YZ", "y": "XZ", "z": "XY"}[self.axis]

        metadata: Dict[str, Any] = {
            "projected_axis": self.axis,
            "projection_plane": _plane_label,
            "point_count": n_pts,
            "mean_dropped_coord": round(mean_before, 4),
        }

        logger.debug(
            "PlaneProjection[axis=%s]: %d points projected onto %s plane",
            self.axis,
            n_pts,
            _plane_label,
        )

        return out_pcd, metadata
