"""
centroid_calculation/node.py — Centroid Calculation pipeline operation.
========================================================================

Computes the geometric centroid (mean XYZ) of the incoming point cloud
and optionally translates the cloud to be centred at the origin.

The pass-through point cloud is always forwarded unchanged on the output
port so downstream nodes continue to receive data.  Centroid metadata is
embedded in the payload extras dict.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d

from ...base import PipelineOperation


class CentroidCalculation(PipelineOperation):
    """
    Computes the centroid of a point cloud and optionally centres it.

    Args:
        center_cloud (bool): If True, translate the cloud so its centroid
            sits at the origin (0, 0, 0).  Default: False.
        compute_per_axis_stats (bool): If True, add per-axis min/max/std
            statistics to the metadata dict.  Default: False.
    """

    def __init__(
        self,
        center_cloud: bool = False,
        compute_per_axis_stats: bool = False,
    ) -> None:
        self.center_cloud = bool(center_cloud)
        self.compute_per_axis_stats = bool(compute_per_axis_stats)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_positions(pcd: Any) -> Optional[np.ndarray]:
        """Extract (N, 3) float64 positions from tensor or legacy pcd."""
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            if "positions" not in pcd.point:
                return None
            return pcd.point.positions.numpy().astype(np.float64)
        # Legacy PointCloud
        pts = np.asarray(pcd.points, dtype=np.float64)
        return pts if pts.size > 0 else None

    @staticmethod
    def _compute_centroid(pts: np.ndarray) -> np.ndarray:
        """Return the mean (3,) centroid vector."""
        return pts.mean(axis=0)

    @staticmethod
    def _per_axis_stats(pts: np.ndarray) -> Dict[str, Any]:
        """Return per-axis min, max, std."""
        return {
            "x_min": float(pts[:, 0].min()),
            "x_max": float(pts[:, 0].max()),
            "x_std": float(pts[:, 0].std()),
            "y_min": float(pts[:, 1].min()),
            "y_max": float(pts[:, 1].max()),
            "y_std": float(pts[:, 1].std()),
            "z_min": float(pts[:, 2].min()),
            "z_max": float(pts[:, 2].max()),
            "z_std": float(pts[:, 2].std()),
        }

    # ------------------------------------------------------------------
    # PipelineOperation interface
    # ------------------------------------------------------------------

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:
        """
        Compute centroid and optionally centre the cloud.

        Returns:
            Tuple of (point_cloud, metadata_dict).
            The point cloud is either unchanged or translated to origin.
        """
        pts = self._get_positions(pcd)

        if pts is None or len(pts) == 0:
            return pcd, {
                "point_count": 0,
                "centroid_x": None,
                "centroid_y": None,
                "centroid_z": None,
                "centered": False,
                "skipped": True,
                "skip_reason": "Empty or missing positions",
            }

        centroid = self._compute_centroid(pts)

        metadata: Dict[str, Any] = {
            "point_count": int(len(pts)),
            "centroid_x": float(centroid[0]),
            "centroid_y": float(centroid[1]),
            "centroid_z": float(centroid[2]),
            "centered": self.center_cloud,
            "skipped": False,
        }

        if self.compute_per_axis_stats:
            metadata.update(self._per_axis_stats(pts))

        if not self.center_cloud:
            return pcd, metadata

        # ── Centre the cloud ──────────────────────────────────────────
        translation = -centroid

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            out = pcd.clone()
            shifted = (
                out.point.positions.numpy().astype(np.float64) + translation
            )
            out.point.positions = o3d.core.Tensor(
                shifted.astype(np.float32),
                dtype=o3d.core.Dtype.Float32,
            )
        else:
            # Legacy PointCloud — translate() operates in-place on a copy
            out = o3d.geometry.PointCloud(pcd)
            out.translate(translation)

        return out, metadata
