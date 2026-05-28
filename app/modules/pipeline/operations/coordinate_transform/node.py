"""
coordinate_transform/node.py -- Coordinate Transformation pipeline operation.
==============================================================================

Applies rigid-body and scaling transformations to a point cloud:
translation (tx, ty, tz), rotation (rx, ry, rz in degrees), and
uniform or per-axis scaling.

The 4x4 transformation matrix is built once at construction time
(T * R * S order) and applied to every incoming frame.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d

from ...base import PipelineOperation


class CoordinateTransform(PipelineOperation):
    """
    Applies translation, rotation, and scaling to a point cloud.

    Args:
        translation: [tx, ty, tz] offset in metres.
        rotation: [rx, ry, rz] Euler angles in degrees (applied X -> Y -> Z).
        scale: [sx, sy, sz] per-axis scale factors.
        order: Matrix composition order -- "trs" (default) or "srt".
    """

    def __init__(
        self,
        translation: Optional[list] = None,
        rotation: Optional[list] = None,
        scale: Optional[list] = None,
        order: str = "trs",
    ) -> None:
        self._translation = np.asarray(
            translation if translation is not None else [0.0, 0.0, 0.0],
            dtype=np.float64,
        )
        self._rotation_deg = np.asarray(
            rotation if rotation is not None else [0.0, 0.0, 0.0],
            dtype=np.float64,
        )
        self._scale = np.asarray(
            scale if scale is not None else [1.0, 1.0, 1.0],
            dtype=np.float64,
        )
        self._order = order.lower()
        self._matrix = self._build_matrix()

    # ------------------------------------------------------------------
    # Matrix construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rotation_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
        """Build a 4x4 rotation matrix from Euler angles (degrees, XYZ order)."""
        rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
        cx, sx = np.cos(rx), np.sin(rx)
        cy, sy = np.cos(ry), np.sin(ry)
        cz, sz = np.cos(rz), np.sin(rz)

        Rx = np.array([
            [1, 0, 0],
            [0, cx, -sx],
            [0, sx, cx],
        ])
        Ry = np.array([
            [cy, 0, sy],
            [0, 1, 0],
            [-sy, 0, cy],
        ])
        Rz = np.array([
            [cz, -sz, 0],
            [sz, cz, 0],
            [0, 0, 1],
        ])

        R = np.eye(4, dtype=np.float64)
        R[:3, :3] = Rz @ Ry @ Rx
        return R

    @staticmethod
    def _translation_matrix(tx: float, ty: float, tz: float) -> np.ndarray:
        T = np.eye(4, dtype=np.float64)
        T[:3, 3] = [tx, ty, tz]
        return T

    @staticmethod
    def _scale_matrix(sx: float, sy: float, sz: float) -> np.ndarray:
        S = np.eye(4, dtype=np.float64)
        S[0, 0], S[1, 1], S[2, 2] = sx, sy, sz
        return S

    def _build_matrix(self) -> np.ndarray:
        T = self._translation_matrix(*self._translation)
        R = self._rotation_matrix(*self._rotation_deg)
        S = self._scale_matrix(*self._scale)

        if self._order == "srt":
            return T @ R @ S
        # Default "trs" -- conceptually: scale first, then rotate, then translate.
        return T @ R @ S

    # ------------------------------------------------------------------
    # PipelineOperation interface
    # ------------------------------------------------------------------

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:
        is_identity = np.allclose(self._matrix, np.eye(4))
        if is_identity:
            count = self._point_count(pcd)
            return pcd, {
                "point_count": count,
                "skipped": True,
                "skip_reason": "Identity transform",
            }

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            out, count = self._apply_tensor(pcd)
        elif isinstance(pcd, o3d.geometry.PointCloud):
            out, count = self._apply_legacy(pcd)
        else:
            raise TypeError(f"Unsupported point cloud type: {type(pcd)}")

        return out, {
            "point_count": count,
            "skipped": False,
            "translation": self._translation.tolist(),
            "rotation_deg": self._rotation_deg.tolist(),
            "scale": self._scale.tolist(),
        }

    # ------------------------------------------------------------------
    # Tensor point cloud path
    # ------------------------------------------------------------------

    def _apply_tensor(self, pcd: o3d.t.geometry.PointCloud):
        if "positions" not in pcd.point:
            return pcd, 0

        out = pcd.clone()
        pts = out.point.positions.numpy().astype(np.float64)
        transformed = self._transform_points(pts)
        out.point.positions = o3d.core.Tensor(
            transformed.astype(np.float32),
            dtype=o3d.core.Dtype.Float32,
        )
        return out, int(transformed.shape[0])

    # ------------------------------------------------------------------
    # Legacy point cloud path
    # ------------------------------------------------------------------

    def _apply_legacy(self, pcd: o3d.geometry.PointCloud):
        out = o3d.geometry.PointCloud(pcd)
        pts = np.asarray(out.points, dtype=np.float64)
        if pts.size == 0:
            return out, 0
        transformed = self._transform_points(pts)
        out.points = o3d.utility.Vector3dVector(transformed)
        return out, int(transformed.shape[0])

    # ------------------------------------------------------------------
    # Shared math
    # ------------------------------------------------------------------

    def _transform_points(self, pts: np.ndarray) -> np.ndarray:
        """Apply the 4x4 matrix to (N, 3) points and return (N, 3)."""
        N = pts.shape[0]
        ones = np.ones((N, 1), dtype=np.float64)
        homogeneous = np.hstack([pts, ones])  # (N, 4)
        transformed = (self._matrix @ homogeneous.T).T  # (N, 4)
        return transformed[:, :3]

    @staticmethod
    def _point_count(pcd: Any) -> int:
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            return int(pcd.point.positions.shape[0]) if "positions" in pcd.point else 0
        return len(pcd.points)
