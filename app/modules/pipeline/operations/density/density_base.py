"""
density_base.py — Shared base class and utilities for Densify algorithm modules.
=================================================================================

Defines:
  - DensityAlgorithmBase: Abstract base class for all densification algorithms.
  - Shared utility methods: _compute_mean_nn_dist_global, _make_tensor_pcd_from_positions,
    _get_count, _tangent_basis, _filter_too_close.
  - Re-exports all Pydantic config/param models and enums so consumers can import
    them from this single location.

All algorithm implementations (NearestNeighborDensify, MLSDensify, PoissonDensify,
StatisticalDensify) must:
  1. Inherit from DensityAlgorithmBase.
  2. Implement the abstract ``apply(pcd, n_new)`` method.
  3. Accept their corresponding params model in ``__init__``.
"""
from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Module-level constants (shared across all algorithm modules)
# ─────────────────────────────────────────────────────────────────────────────
MIN_INPUT_POINTS: int = 10
MAX_MULTIPLIER: float = 8.0

_VALID_ALGORITHMS = frozenset({"nearest_neighbor", "mls", "poisson", "statistical"})


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class DensifyAlgorithm(str, Enum):
    """Available densification algorithms.  All use global KDTree searches."""

    NEAREST_NEIGHBOR = "nearest_neighbor"
    MLS = "mls"
    POISSON = "poisson"
    STATISTICAL = "statistical"


class DensifyStatus(str, Enum):
    """Outcome status embedded in the metadata dict returned by apply()."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


# ─────────────────────────────────────────────────────────────────────────────
# Per-algorithm parameter models
# ─────────────────────────────────────────────────────────────────────────────


class DensifyNNParams(BaseModel):
    """
    Tunable parameters for the ``nearest_neighbor`` densification algorithm.

    Attributes:
        displacement_min: Minimum displacement as a fraction of the global mean
            nearest-neighbour distance.  Range: [0.0, displacement_max).  Default: 0.05.
        displacement_max: Maximum displacement fraction.  Range: (displacement_min, 1.0].
            Default: 0.50.
    """

    displacement_min: float = Field(
        default=0.05,
        ge=0.0,
        lt=1.0,
        description="Min displacement factor (fraction of global mean NN dist). Default 0.05.",
    )
    displacement_max: float = Field(
        default=0.50,
        gt=0.0,
        le=1.0,
        description="Max displacement factor (fraction of global mean NN dist). Default 0.50.",
    )

    @model_validator(mode="after")
    def validate_range(self) -> "DensifyNNParams":
        if self.displacement_min >= self.displacement_max:
            raise ValueError(
                f"displacement_min ({self.displacement_min}) must be < "
                f"displacement_max ({self.displacement_max})"
            )
        return self

    model_config = {"populate_by_name": True}


class DensifyMLSParams(BaseModel):
    """
    Tunable parameters for the ``mls`` (Moving Least Squares) densification algorithm.

    Attributes:
        k_neighbors: KNN count for surface normal estimation.  Range: [3, ∞).  Default: 20.
        projection_radius_factor: Tangent-plane projection radius as a fraction of
            the global mean NN distance.  Range: (0.0, 2.0].  Default: 0.5.
        min_dist_factor: Duplicate-filter radius as a fraction of the global mean NN
            distance.  Range: [0.0, 1.0].  Default: 0.05.
    """

    k_neighbors: int = Field(
        default=20,
        ge=3,
        description="KNN for normal estimation. Default 20.",
    )
    projection_radius_factor: float = Field(
        default=0.5,
        gt=0.0,
        le=2.0,
        description="Tangent-plane radius factor (× mean NN dist). Default 0.5.",
    )
    min_dist_factor: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Duplicate-filter radius factor (× mean NN dist). Default 0.05.",
    )

    model_config = {"populate_by_name": True}


class DensifyStatisticalParams(BaseModel):
    """
    Tunable parameters for the ``statistical`` upsampling densification algorithm.

    Attributes:
        k_neighbors: KNN count for local density estimation.  Range: [2, ∞).  Default: 10.
        sparse_percentile: Points with local density below this percentile are
            labelled "sparse".  Range: (0, 100].  Default: 50.
        min_dist_factor: Duplicate-filter radius as a fraction of mean NN distance.
            Range: [0.0, 1.0].  Default: 0.3.
    """

    k_neighbors: int = Field(
        default=10,
        ge=2,
        description="KNN for local density estimation. Default 10.",
    )
    sparse_percentile: float = Field(
        default=50.0,
        gt=0.0,
        le=100.0,
        description="Density percentile threshold for 'sparse' label. Default 50.",
    )
    min_dist_factor: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Duplicate-filter radius factor (× mean NN dist). Default 0.3.",
    )

    model_config = {"populate_by_name": True}


class DensifyPoissonParams(BaseModel):
    """
    Tunable parameters for the ``poisson`` reconstruction densification algorithm.

    Attributes:
        depth: Octree depth for Poisson reconstruction.  Range: [4, 12].  Default: 8.
        density_threshold_quantile: Quantile below which low-density mesh vertices
            are trimmed.  Range: [0.0, 0.5].  Default: 0.1.
    """

    depth: int = Field(
        default=8,
        ge=4,
        le=12,
        description="Poisson octree depth. Default 8.",
    )
    density_threshold_quantile: float = Field(
        default=0.1,
        ge=0.0,
        le=0.5,
        description="Low-density vertex trim quantile. Default 0.1.",
    )

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic config / metadata models
# ─────────────────────────────────────────────────────────────────────────────


class DensifyConfig(BaseModel):
    """
    Configuration for the Densify pipeline operation.

    All algorithms perform global, full-cloud neighbour searches — no scanline,
    ring-based, or sequential processing modes exist.

    Persistence format (DAG node config stored in DB):
        {"type": "densify", "config": { ...DensifyConfig fields... }}
    """

    enabled: bool = Field(
        default=True,
        description="Enable/disable this operation. Disabled nodes pass through unchanged.",
    )
    algorithm: DensifyAlgorithm = Field(
        default=DensifyAlgorithm.NEAREST_NEIGHBOR,
        description="Densification algorithm. All algorithms use global KDTree searches.",
    )
    density_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=8.0,
        description="Target density increase factor. 2.0 doubles the point count.",
    )
    preserve_normals: bool = Field(
        default=True,
        description="If True, estimate surface normals for synthetic points.",
    )

    # Per-algorithm parameter sub-dicts
    nn_params: Optional[DensifyNNParams] = Field(default=None)
    mls_params: Optional[DensifyMLSParams] = Field(default=None)
    statistical_params: Optional[DensifyStatisticalParams] = Field(default=None)
    poisson_params: Optional[DensifyPoissonParams] = Field(default=None)

    @field_validator("density_multiplier")
    @classmethod
    def validate_multiplier(cls, v: float) -> float:
        if not (1.0 <= v <= 8.0):
            raise ValueError(f"density_multiplier must be in [1.0, 8.0], got {v}")
        return round(v, 4)

    model_config = {"use_enum_values": True, "populate_by_name": True}


class DensifyMetadata(BaseModel):
    """
    Structured output metadata from a Densify.apply() call.
    Always returned — even on skip or error.
    """

    status: DensifyStatus
    original_count: int = Field(ge=0)
    densified_count: int = Field(ge=0)
    density_ratio: float = Field(ge=0.0)
    algorithm_used: str
    processing_time_ms: float = Field(ge=0.0)
    skip_reason: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)

    model_config = {"use_enum_values": True}


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
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            return (
                int(pcd.point.positions.shape[0])
                if "positions" in pcd.point
                else 0
            )
        return len(pcd.points)

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
