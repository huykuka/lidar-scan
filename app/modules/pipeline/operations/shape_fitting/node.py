"""
Shape fitting operation — fits geometric primitives to point clouds using RANSAC,
then outputs a downsampled point cloud sampled uniformly on the fitted shape surface.

Each shape type lives in its own submodule (circle.py, plane.py, etc.).
"""
from typing import Any, Dict, Tuple

import numpy as np

from ...base import PipelineOperation
from .circle import CircleFitter
from .plane import PlaneFitter


_FITTER_MAP = {
    "circle": CircleFitter,
    "plane": PlaneFitter,
    # Future:
    # "cylinder": CylinderFitter,
    # "cone": ConeFitter,
    # "rectangle": RectangleFitter,
}


class ShapeFitting(PipelineOperation):
    """Fit a geometric primitive to input points, then output a clean point cloud
    sampled uniformly on the fitted shape surface.

    Args:
        shape: Type of shape to fit. One of "circle", "plane".
        thresh: RANSAC inlier distance threshold (meters).
        max_iterations: Maximum RANSAC iterations.
        num_output_points: Number of points to sample on the fitted shape.
        fill: If True, fill the interior (e.g. disc instead of ring).
        refine: If True, refine the RANSAC result with scipy least_squares.
        emit_shapes: Emit fitted shape as a visual shape in metadata.
    """

    NUMPY_ONLY: bool = True

    def __init__(
        self,
        shape: str = "circle",
        thresh: float = 0.01,
        max_iterations: int = 1000,
        num_output_points: int = 128,
        fill: bool = False,
        refine: bool = True,
        emit_shapes: bool = True,
    ):
        shape = shape.lower()
        if shape not in _FITTER_MAP:
            raise ValueError(
                f"Unsupported shape '{shape}'. Available: {list(_FITTER_MAP.keys())}"
            )

        self.shape = shape
        self._fitter = _FITTER_MAP[shape](
            thresh=thresh,
            max_iterations=max_iterations,
            num_output_points=num_output_points,
            fill=fill,
            refine=refine,
            emit_shapes=emit_shapes,
        )

    def apply(self, points: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        if points is None or len(points) < 3:
            return points, {}

        positions = points[:, :3].astype(np.float64)
        result = self._fitter.fit(positions)

        if result is None:
            return points, {"fit_success": False}

        sampled_xyz, params, shapes = result

        num_cols = points.shape[1] if points.ndim == 2 else 3
        out = np.zeros((len(sampled_xyz), num_cols), dtype=np.float32)
        out[:, :3] = sampled_xyz.astype(np.float32)

        metadata: Dict[str, Any] = {
            "fit_success": True,
            "shape_type": self.shape,
            "output_points": len(sampled_xyz),
            "input_points": len(points),
            **params,
        }

        if shapes:
            metadata["shapes"] = shapes

        return out, metadata
