"""
coordinate_transform/node.py -- Coordinate Transformation pipeline operation.
==============================================================================

Applies rigid-body and scaling transformations to a point cloud:
translation (tx, ty, tz), rotation (rx, ry, rz in degrees), and
uniform or per-axis scaling.

NUMPY_ONLY: apply() receives and returns a raw (N, M) numpy array.
The 4x4 transformation matrix is built once at construction time and
applied directly to XYZ columns with no Open3D allocation or thread hop.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from ...base import PipelineOperation


class CoordinateTransform(PipelineOperation):
    """
    Applies translation, rotation, and scaling to a point cloud.

    NUMPY_ONLY: operates directly on the (N, M) float32 array.
    XYZ columns are transformed; extra columns (intensity, ring, etc.)
    are passed through unchanged.

    Args:
        translation: [tx, ty, tz] offset in metres.
        rotation: [rx, ry, rz] Euler angles in degrees (applied X -> Y -> Z).
        scale: [sx, sy, sz] per-axis scale factors.
        order: Matrix composition order — "trs" (default) or "srt".
            "trs": Translate → Rotate → Scale  (p' = S @ R @ T @ p)
            "srt": Scale → Rotate → Translate  (p' = T @ R @ S @ p)
    """

    NUMPY_ONLY = True

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
        self._is_identity = bool(np.allclose(self._matrix, np.eye(4)))

    # ------------------------------------------------------------------
    # Matrix construction
    # ------------------------------------------------------------------

    @staticmethod
    def _rotation_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
        rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
        cx, sx = np.cos(rx), np.sin(rx)
        cy, sy = np.cos(ry), np.sin(ry)
        cz, sz = np.cos(rz), np.sin(rz)
        Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
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
            # Scale → Rotate → Translate
            return T @ R @ S
        # Default "trs": Translate → Rotate → Scale  (p' = S @ R @ T @ p)
        return S @ R @ T

    # ------------------------------------------------------------------
    # PipelineOperation interface
    # ------------------------------------------------------------------

    def apply(self, pts: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        if self._is_identity:
            return pts, {
                "point_count": int(pts.shape[0]),
                "skipped": True,
                "skip_reason": "Identity transform",
            }

        xyz = pts[:, :3].astype(np.float64)
        N = xyz.shape[0]
        ones = np.ones((N, 1), dtype=np.float64)
        xyz_h = np.hstack([xyz, ones])          # (N, 4)
        xyz_out = (self._matrix @ xyz_h.T).T[:, :3].astype(pts.dtype)

        if pts.shape[1] > 3:
            out = pts.copy()
            out[:, :3] = xyz_out
        else:
            out = xyz_out

        return out, {
            "point_count": int(out.shape[0]),
            "skipped": False,
            "translation": self._translation.tolist(),
            "rotation_deg": self._rotation_deg.tolist(),
            "scale": self._scale.tolist(),
        }
