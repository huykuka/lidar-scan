"""
reconstruction_base.py — Shared base class, enums, and param models for Surface Reconstruction.
=================================================================================================

Defines:
  - ReconstructionAlgorithmBase: Abstract base class for all reconstruction algorithms.
  - Shared utility methods for Open3D point cloud handling.
  - Pydantic config/param models and enums.

All algorithm implementations (AlphaShapeReconstruction, BallPivotingReconstruction,
PoissonReconstruction) must:
  1. Inherit from ReconstructionAlgorithmBase.
  2. Implement the abstract ``reconstruct(pcd)`` method.
  3. Accept their corresponding params model in ``__init__``.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MIN_INPUT_POINTS: int = 10

_VALID_ALGORITHMS = frozenset({"alpha_shape", "ball_pivoting", "poisson"})


class ReconstructionAlgorithm(str, Enum):
    ALPHA_SHAPE = "alpha_shape"
    BALL_PIVOTING = "ball_pivoting"
    POISSON = "poisson"


class ReconstructionStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


# ─────────────────────────────────────────────────────────────────────────────
# Per-algorithm parameter models
# ─────────────────────────────────────────────────────────────────────────────


class AlphaShapeParams(BaseModel):
    """Parameters for the alpha shape reconstruction algorithm.

    Attributes:
        alpha: Controls the level of detail. Smaller = finer, larger = coarser hull.
    """
    alpha: float = Field(
        default=0.03,
        gt=0.0,
        le=10.0,
        description="Alpha radius controlling surface detail. Smaller = finer. Default 0.03.",
    )

    model_config = {"populate_by_name": True}


class BallPivotingParams(BaseModel):
    """Parameters for the Ball Pivoting Algorithm (BPA).

    Attributes:
        radii: Comma-separated list of ball radii used for pivoting.
            Multiple radii lets the algorithm handle varying point densities.
    """
    radii: str = Field(
        default="0.005,0.01,0.02,0.04",
        description="Comma-separated ball radii. Default '0.005,0.01,0.02,0.04'.",
    )

    model_config = {"populate_by_name": True}

    def get_radii_list(self) -> list[float]:
        return [float(r.strip()) for r in self.radii.split(",") if r.strip()]


class PoissonReconstructionParams(BaseModel):
    """Parameters for Poisson surface reconstruction.

    Attributes:
        depth: Tree depth controlling reconstruction detail. Higher = more detail.
        width: Finest octree cell width. 0 means inferred from depth.
        scale: Ratio between the reconstruction cube and the bounding cube of the samples.
        linear_fit: Use linear interpolation for surface positioning.
        density_quantile: Remove low-density vertices below this quantile (0.0-1.0).
    """
    depth: int = Field(
        default=8,
        ge=1,
        le=13,
        description="Octree depth. Higher = finer detail but slower. Default 8.",
    )
    width: float = Field(
        default=0.0,
        ge=0.0,
        description="Finest octree cell width. 0 = auto from depth. Default 0.",
    )
    scale: float = Field(
        default=1.1,
        gt=0.0,
        le=5.0,
        description="Ratio between reconstruction cube and bounding cube. Default 1.1.",
    )
    linear_fit: bool = Field(
        default=False,
        description="Use linear interpolation for positioning. Default False.",
    )
    density_quantile: float = Field(
        default=0.01,
        ge=0.0,
        le=1.0,
        description="Remove vertices with density below this quantile. Default 0.01.",
    )

    model_config = {"populate_by_name": True}


class ReconstructionConfig(BaseModel):
    """Top-level config for the surface reconstruction dispatcher."""
    algorithm: str = Field(default="poisson")
    sample_points: int = Field(
        default=0,
        ge=0,
        description="Resample mesh to N points. 0 = return mesh vertices as point cloud.",
    )
    estimate_normals: bool = Field(
        default=True,
        description="Estimate normals on input if missing (required by BPA and Poisson).",
    )
    normal_radius: float = Field(
        default=0.1,
        gt=0.0,
        description="Search radius for normal estimation. Default 0.1.",
    )
    normal_max_nn: int = Field(
        default=30,
        ge=3,
        description="Max neighbours for normal estimation. Default 30.",
    )

    model_config = {"populate_by_name": True}


class ReconstructionMetadata(BaseModel):
    """Metadata returned alongside the output point cloud."""
    status: str = "success"
    algorithm: str = ""
    input_points: int = 0
    output_points: int = 0
    mesh_vertices: int = 0
    mesh_triangles: int = 0
    elapsed_ms: float = 0.0

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────


def _get_count(pcd: Any) -> int:
    """Return the point count for either legacy or tensor Open3D point clouds."""
    if isinstance(pcd, o3d.t.geometry.PointCloud):
        return pcd.point.positions.shape[0] if "positions" in pcd.point else 0
    if isinstance(pcd, o3d.geometry.PointCloud):
        return len(pcd.points)
    return 0


def _to_legacy(pcd: Any) -> o3d.geometry.PointCloud:
    """Convert tensor PointCloud to legacy, or return as-is if already legacy."""
    if isinstance(pcd, o3d.t.geometry.PointCloud):
        return pcd.to_legacy()
    return pcd


def _to_tensor(pcd: o3d.geometry.PointCloud, device: str = "CPU:0") -> o3d.t.geometry.PointCloud:
    """Convert legacy PointCloud to tensor."""
    return o3d.t.geometry.PointCloud.from_legacy(pcd, device=o3d.core.Device(device))


def _ensure_normals(
    pcd: o3d.geometry.PointCloud,
    radius: float = 0.1,
    max_nn: int = 30,
) -> o3d.geometry.PointCloud:
    """Estimate normals on a legacy PointCloud if not already present."""
    if not pcd.has_normals() or len(pcd.normals) == 0:
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=max_nn)
        )
        pcd.orient_normals_consistent_tangent_plane(k=max_nn)
    return pcd


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base
# ─────────────────────────────────────────────────────────────────────────────


class ReconstructionAlgorithmBase(ABC):
    """Abstract base for surface reconstruction algorithms.

    Each subclass implements ``reconstruct()`` which takes a legacy PointCloud
    (with normals already estimated) and returns a TriangleMesh.
    """

    @abstractmethod
    def reconstruct(self, pcd: o3d.geometry.PointCloud) -> o3d.geometry.TriangleMesh:
        """Run surface reconstruction and return a triangle mesh."""
        ...
