"""Plane fitter — fits a plane to a point cloud and samples a grid on it."""
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base import ShapeFitterBase


class PlaneFitter(ShapeFitterBase):
    """Fit a plane to a point cloud and output a sampled grid."""

    def fit(self, positions: np.ndarray) -> Optional[Tuple[np.ndarray, Dict[str, Any], List[Any]]]:
        try:
            import pyransac3d as pyrsc
        except ImportError:
            raise ImportError("pyransac3d required: pip install pyransac3d")

        plane = pyrsc.Plane()
        equation, inliers = plane.fit(
            positions, thresh=self.thresh, maxIteration=self.max_iterations,
        )

        if equation is None or len(inliers) == 0:
            return None

        normal = np.array(equation[:3], dtype=np.float64)
        normal /= np.linalg.norm(normal)

        inlier_pts = positions[inliers]
        sampled = self._sample(inlier_pts, normal)

        params = {
            "equation": [float(e) for e in equation],
            "normal": [float(n) for n in normal],
            "inlier_count": len(inliers),
        }

        return sampled, params, []

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def _sample(self, inlier_pts: np.ndarray, normal: np.ndarray) -> np.ndarray:
        """Sample a grid of points on the plane bounded by inlier extent."""
        u, v = self.build_orthonormal_basis(normal)
        centroid = inlier_pts.mean(axis=0)
        rel = inlier_pts - centroid
        u_coords = rel @ u
        v_coords = rel @ v

        n = self.num_output_points
        side = int(np.ceil(np.sqrt(n)))
        us = np.linspace(u_coords.min(), u_coords.max(), side)
        vs = np.linspace(v_coords.min(), v_coords.max(), side)
        uu, vv = np.meshgrid(us, vs)
        uu, vv = uu.ravel(), vv.ravel()

        points = centroid + np.outer(uu, u) + np.outer(vv, v)
        return points[:n]
