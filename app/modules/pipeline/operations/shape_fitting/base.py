"""Base class for shape fitters."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class ShapeFitterBase(ABC):
    """Base class all shape fitters inherit from.

    Each fitter is responsible for:
      1. Fitting the shape to input positions (RANSAC + optional refinement)
      2. Sampling points on the fitted shape surface
      3. Building visual shapes for the frontend
    """

    def __init__(
        self,
        thresh: float = 0.01,
        max_iterations: int = 1000,
        num_output_points: int = 128,
        fill: bool = False,
        refine: bool = True,
        emit_shapes: bool = True,
    ):
        self.thresh = float(thresh)
        self.max_iterations = int(max_iterations)
        self.num_output_points = int(num_output_points)
        self.fill = bool(fill)
        self.refine = bool(refine)
        self.emit_shapes = bool(emit_shapes)

    @abstractmethod
    def fit(self, positions: np.ndarray) -> Optional[Tuple[np.ndarray, Dict[str, Any], List[Any]]]:
        """Fit shape and return (sampled_xyz, params_dict, shapes_list) or None."""
        ...

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_normal(points: np.ndarray) -> np.ndarray:
        """Estimate plane normal from points using PCA (smallest eigenvector)."""
        centroid = points.mean(axis=0)
        centered = points - centroid
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        return vh[-1]

    @staticmethod
    def build_orthonormal_basis(normal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Build orthonormal (u, v) vectors in the plane defined by normal."""
        normal = normal / np.linalg.norm(normal)
        arbitrary = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(normal, arbitrary)) > 0.9:
            arbitrary = np.array([0.0, 1.0, 0.0])
        u = np.cross(normal, arbitrary)
        u /= np.linalg.norm(u)
        v = np.cross(normal, u)
        return u, v
