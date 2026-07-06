"""
density_models.py — Pydantic models and enums for the Densify pipeline operation.
==================================================================================

Splits out all data-only definitions from ``density_base.py`` so that:
  - Algorithm implementations (density_base.py) can import just the types they need.
  - Consumers (e.g. tests, densify.py) have a stable, lightweight import target.

Exports:
  - Enums: DensifyAlgorithm, DensifyStatus
  - Per-algorithm param models: DensifyNNParams, DensifyMLSParams,
      DensifyStatisticalParams, DensifyPoissonParams
  - Top-level models: DensifyConfig, DensifyMetadata
  - Constants: MIN_INPUT_POINTS, MIN_MULTIPLIER, MAX_MULTIPLIER, _VALID_ALGORITHMS
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_INPUT_POINTS: int = 10
MIN_MULTIPLIER: float = 1.0
MAX_MULTIPLIER: float = 8.0

_VALID_ALGORITHMS = frozenset({"nearest_neighbor", "mls", "poisson", "statistical"})


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
        k_neighbors: Max nearest neighbours within search_radius for normal estimation.
            Range: [3, ∞).  Default: 20.
        search_radius: KDTree hybrid search radius in metres for normal estimation.
            Only neighbours within this distance AND up to k_neighbors count are used.
            Range: (0.0, ∞).  Default: 0.1.
        projection_radius_factor: Tangent-plane projection radius as a fraction of
            the global mean NN distance.  Range: (0.0, 2.0].  Default: 0.5.
        min_dist_factor: Duplicate-filter radius as a fraction of the global mean NN
            distance.  Range: [0.0, 1.0].  Default: 0.05.
    """

    k_neighbors: int = Field(
        default=20,
        ge=3,
        description="Max nearest neighbours within search_radius for normal estimation. Default 20.",
    )
    search_radius: float = Field(
        default=0.1,
        gt=0.0,
        description="KDTree hybrid search radius in metres for normal estimation. Default 0.1.",
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
        max_nn: Max nearest neighbours within search_radius for normal estimation.
            Range: [3, ∞).  Default: 30.
        search_radius: KDTree hybrid search radius in metres for normal estimation.
            Only neighbours within this distance AND up to max_nn count are used.
            Range: (0.0, ∞).  Default: 0.1.
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
    max_nn: int = Field(
        default=30,
        ge=3,
        description="Max nearest neighbours within search_radius for normal estimation. Default 30.",
    )
    search_radius: float = Field(
        default=0.1,
        gt=0.0,
        description="KDTree hybrid search radius in metres for normal estimation. Default 0.1.",
    )

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────────────────────────
# Top-level config / metadata models
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
        if not (MIN_MULTIPLIER <= v <= MAX_MULTIPLIER):
            raise ValueError(f"density_multiplier must be in [{MIN_MULTIPLIER}, {MAX_MULTIPLIER}], got {v}")
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
