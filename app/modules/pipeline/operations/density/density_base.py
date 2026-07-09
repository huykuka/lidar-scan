"""
density_base.py — Abstract base class and utilities for Densify algorithm modules.
====================================================================================

Defines:
  - DensityAlgorithmBase: Abstract base class for all densification algorithms.
  - Shared utility methods: _compute_mean_nn_dist_global, _make_tensor_pcd_from_positions,
    _get_count, _tangent_basis, _filter_too_close.

All Pydantic config/param models and enums are defined in ``density_models.py``
and re-exported here for backward-compatible single-location imports.

All algorithm implementations (NearestNeighborDensify, MLSDensify, PoissonDensify,
StatisticalDensify) must:
  1. Inherit from DensityAlgorithmBase.
  2. Implement the abstract ``apply(pcd, n_new)`` method.
  3. Accept their corresponding params model in ``__init__``.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Tuple

import numpy as np
import open3d as o3d

from ...base import get_point_count

# Re-export everything from density_models for backward-compatible imports
from .density_models import (  # noqa: F401  (intentional re-export)
    MIN_INPUT_POINTS,
    MIN_MULTIPLIER,
    MAX_MULTIPLIER,
    _VALID_ALGORITHMS,
    DensifyAlgorithm,
    DensifyStatus,
    DensifyNNParams,
    DensifyMLSParams,
    DensifyStatisticalParams,
    DensifyPoissonParams,
    DensifyConfig,
    DensifyMetadata,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base class for algorithm modules
# ─────────────────────────────────────────────────────────────────────────────


class DensityAlgorithmBase(ABC):
    """
    Abstract base for all densification algorithm implementations.

    Each concrete subclass implements a single densification strategy
    (nearest_neighbor, mls, poisson, statistical) and is responsible only
    for generating ``n_new`` synthetic points from the input tensor PointCloud.
    """

    @abstractmethod
    def apply(
            self,
            pcd: o3d.t.geometry.PointCloud,
            n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Generate ``n_new`` synthetic points and merge with the original ``pcd``.

        Args:
            pcd:   Input tensor PointCloud (already validated, >= MIN_INPUT_POINTS).
            n_new: Number of synthetic points to generate.

        Returns:
            New tensor PointCloud containing original + synthetic points.
        """

    # ── Shared utility methods (available to all subclasses) ──────────────────

    @staticmethod
    def _get_count(pcd: Any) -> int:
        """Return point count for either tensor or legacy pcd."""
        return get_point_count(pcd)

    @staticmethod
    def _make_tensor_pcd_from_positions(pts: np.ndarray) -> o3d.t.geometry.PointCloud:
        """Wrap a (N,3) float32 numpy array into an o3d.t.geometry.PointCloud."""
        result = o3d.t.geometry.PointCloud()
        result.point.positions = o3d.core.Tensor(pts.astype(np.float32))
        return result

    @staticmethod
    def _compute_mean_nn_dist_global(pts: np.ndarray) -> float:
        """
        Compute the mean nearest-neighbour distance over the **global** point cloud.

        Uses scipy KDTree querying the 2 nearest neighbours for every point.
        This gives a 3-D global estimate of point spacing not biased toward any
        scan structure (rings, scanlines, rows, etc.).

        For very large clouds (N > 10_000) a random sample of 1000 points is used
        for speed while still capturing the global distribution.

        Returns a fallback of 0.01 if computation fails.
        """
        from scipy.spatial import KDTree  # lazy import

        try:
            n = len(pts)
            if n < 2:
                return 0.01

            sample_size = min(n, 1000)
            if sample_size < n:
                rng = np.random.default_rng()
                sample_idx = rng.choice(n, size=sample_size, replace=False)
                sample_pts = pts[sample_idx]
            else:
                sample_pts = pts

            kd = KDTree(pts.astype(np.float64))
            dists, _ = kd.query(sample_pts.astype(np.float64), k=2)
            nn_dists = dists[:, 1]
            nn_dists = nn_dists[nn_dists > 1e-10]
            if len(nn_dists) > 0:
                return float(np.mean(nn_dists))
        except Exception:
            pass
        return 0.01

    @staticmethod
    def _tangent_basis(
            normal: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute two orthonormal vectors {u, v} perpendicular to ``normal``.

        Uses the cross-product with a world axis; falls back if near-parallel.
        Result is valid for any surface orientation including vertical faces.
        """
        n = normal / (np.linalg.norm(normal) + 1e-10)
        world_z = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        cross = np.cross(n, world_z)
        if np.linalg.norm(cross) < 1e-6:
            world_x = np.array([1.0, 0.0, 0.0], dtype=np.float64)
            cross = np.cross(n, world_x)
        u = cross / (np.linalg.norm(cross) + 1e-10)
        v = np.cross(n, u)
        v = v / (np.linalg.norm(v) + 1e-10)
        return u, v

    @staticmethod
    def _filter_too_close(
            synthetic: np.ndarray,
            kd_existing: Any,
            min_dist: float,
    ) -> np.ndarray:
        """
        Remove synthetic points within min_dist of any existing (original) point.

        Uses scipy KDTree.query_ball_point in batch for efficiency.
        """
        try:
            nearby = kd_existing.query_ball_point(
                synthetic.astype(np.float64), r=min_dist
            )
            keep = np.array([len(nb) == 0 for nb in nearby])
            return synthetic[keep]
        except Exception:
            return synthetic

