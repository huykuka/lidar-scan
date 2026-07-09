"""
centroid_calculation/node.py — Centroid Calculation pipeline operation.
========================================================================

Computes the geometric centroid (mean XYZ) of the incoming point cloud
and outputs a single-point cloud at that centroid position.

NUMPY_ONLY: apply() receives and returns a raw (N, M) numpy array.
No Open3D allocation, no thread hop.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np

from ...base import PipelineOperation


class CentroidCalculation(PipelineOperation):
    """
    Computes the centroid of a point cloud and outputs it as a single point.

    The output is a (1, M) array whose XYZ columns are the mean XYZ of all
    input points. All other columns (intensity, layer, etc.) are set to the
    mean value of the corresponding input column so downstream nodes receive
    a representative attribute set.

    NUMPY_ONLY: operates directly on the (N, M) float32 array.

    Args:
        compute_per_axis_stats: Add per-axis min/max/std to metadata.
    """

    NUMPY_ONLY = True

    def __init__(
        self,
        compute_per_axis_stats: bool = False,
        # kept for backward-compat but no longer used
        center_cloud: bool = False,
    ) -> None:
        self.compute_per_axis_stats = bool(compute_per_axis_stats)

    @staticmethod
    def _per_axis_stats(xyz: np.ndarray) -> Dict[str, Any]:
        return {
            "x_min": float(xyz[:, 0].min()), "x_max": float(xyz[:, 0].max()), "x_std": float(xyz[:, 0].std()),
            "y_min": float(xyz[:, 1].min()), "y_max": float(xyz[:, 1].max()), "y_std": float(xyz[:, 1].std()),
            "z_min": float(xyz[:, 2].min()), "z_max": float(xyz[:, 2].max()), "z_std": float(xyz[:, 2].std()),
        }

    def apply(self, pts: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        if pts.shape[0] == 0:
            return pts, {
                "point_count": 0,
                "centroid_x": None, "centroid_y": None, "centroid_z": None,
                "skipped": True,
                "skip_reason": "Empty point cloud",
            }

        # Single row: mean of every column so attributes are representative
        centroid_row = pts.mean(axis=0, keepdims=True)  # (1, M)

        meta: Dict[str, Any] = {
            "point_count": int(pts.shape[0]),
            "centroid_x": float(centroid_row[0, 0]),
            "centroid_y": float(centroid_row[0, 1]),
            "centroid_z": float(centroid_row[0, 2]),
        }

        if self.compute_per_axis_stats:
            meta.update(self._per_axis_stats(pts[:, :3]))

        return centroid_row, meta

