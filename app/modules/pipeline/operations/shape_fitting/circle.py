"""Circle/disc fitter — fits a circle to a point cloud and samples on it."""
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base import ShapeFitterBase


class CircleFitter(ShapeFitterBase):
    """Fit a circle (3D ring or filled disc) to a point cloud."""

    def fit(self, positions: np.ndarray) -> Optional[Tuple[np.ndarray, Dict[str, Any], List[Any]]]:
        try:
            import pyransac3d as pyrsc
        except ImportError:
            raise ImportError("pyransac3d required: pip install pyransac3d")

        circle = pyrsc.Circle()
        center, radius, inliers = circle.fit(
            positions, thresh=self.thresh, maxIteration=self.max_iterations,
        )

        if center is None or radius is None or len(inliers) == 0:
            return None

        if self.refine and len(inliers) > 3:
            center, radius, normal = self._refine(positions[inliers], center, radius)
        else:
            normal = self.estimate_normal(positions[inliers])

        sampled = self._sample(center, radius, normal)

        params = {
            "center": [float(c) for c in center],
            "radius": float(radius),
            "normal": [float(n) for n in normal],
            "inlier_count": len(inliers),
        }

        shapes = self._build_shapes(center, radius) if self.emit_shapes else []
        return sampled, params, shapes

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def _sample(self, center: List[float], radius: float, normal: np.ndarray) -> np.ndarray:
        """Sample points on the circle edge or filled disc."""
        center_arr = np.array(center, dtype=np.float64)
        u, v = self.build_orthonormal_basis(normal)
        n = self.num_output_points

        if not self.fill:
            angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
            points = center_arr + radius * (
                np.outer(np.cos(angles), u) + np.outer(np.sin(angles), v)
            )
        else:
            # Sunflower pattern for uniform area distribution
            golden_angle = np.pi * (3.0 - np.sqrt(5.0))
            indices = np.arange(n, dtype=np.float64)
            r = radius * np.sqrt(indices / n)
            theta = golden_angle * indices
            points = center_arr + (
                np.outer(r * np.cos(theta), u) + np.outer(r * np.sin(theta), v)
            )

        return points

    # ------------------------------------------------------------------
    # Refinement
    # ------------------------------------------------------------------

    def _refine(
        self, inlier_points: np.ndarray, center_init: List[float], radius_init: float
    ) -> Tuple[List[float], float, np.ndarray]:
        """Refine circle fit with least squares. Returns (center, radius, normal)."""
        normal = self.estimate_normal(inlier_points)

        try:
            from scipy.optimize import least_squares as lsq
        except ImportError:
            return center_init, radius_init, normal

        center_arr = np.array(center_init, dtype=np.float64)
        centroid = inlier_points.mean(axis=0)
        u, v = self.build_orthonormal_basis(normal)

        rel = inlier_points - centroid
        pts_2d = np.column_stack([rel @ u, rel @ v])
        c_2d = (center_arr - centroid) @ np.column_stack([u, v])

        def residuals(params):
            cx, cy, r = params
            return np.sqrt((pts_2d[:, 0] - cx) ** 2 + (pts_2d[:, 1] - cy) ** 2) - r

        result = lsq(residuals, [c_2d[0], c_2d[1], radius_init], method="lm")

        if result.success:
            cx, cy, r = result.x
            center_3d = centroid + cx * u + cy * v
            return center_3d.tolist(), abs(r), normal

        return center_init, radius_init, normal

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    @staticmethod
    def _build_shapes(center: List[float], radius: float) -> List[Any]:
        from app.services.nodes.shapes import CubeShape

        return [
            CubeShape(
                center=center,
                size=[radius * 2, radius * 2, 0.01],
                color="#ff8800",
                opacity=0.5,
                wireframe=True,
                label=f"circle r={radius:.3f}",
            )
        ]
