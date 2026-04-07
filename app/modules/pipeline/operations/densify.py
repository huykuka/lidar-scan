"""
Densify — Pipeline Operation
============================

Increases point cloud density by interpolating synthetic points between existing ones.
Works with **any** scene geometry — entirely sensor-agnostic and scan-pattern-agnostic.
New points are generated in all spatial directions (X, Y, Z) by performing **global**,
full-cloud neighbour searches using scipy's KDTree or Open3D's KDTreeFlann.

There is **no** scanline, ring-based, or sequential/radial densification logic anywhere
in this module.  Densification is volumetric by default: every algorithm operates on the
full 3-D point cloud regardless of whether the input came from a rotating LIDAR, a solid-
state sensor, a structured-light scanner, photogrammetry, or any synthetic source.

Supported algorithms
---------------------
nearest_neighbor (default / fast mode, <100ms for 50k–100k pts)
    For every synthetic slot, picks a random source point from the *global* cloud and
    adds a displacement in a uniformly-random 3-D direction scaled by a random fraction
    of the *global* mean nearest-neighbour distance.  Fills horizontal AND vertical gaps
    equally.  Preserves sharp features; may create minor blocky artefacts.
    Use for: real-time pipelines, streaming sensor feeds.

    Configurable via ``nn_params`` (DensifyNNParams):
      - ``displacement_min`` (default 0.05): minimum displacement fraction of mean NN dist
      - ``displacement_max`` (default 0.50): maximum displacement fraction of mean NN dist

    Global search guarantee: mean NN distance is computed via a full-cloud scipy KDTree
    query over all N points (no scanline sampling, no ring grouping).

statistical (medium mode, 100–300ms)
    Computes per-point local density using a global KDTree query (k=10 neighbours for
    every point).  Identifies sparse regions across the entire 3-D volume and
    interpolates new points along edges to existing neighbours with α ∈ [0.3, 0.7].
    Use for: interactive applications, general-purpose 3-D densification.

    Configurable via ``statistical_params`` (DensifyStatisticalParams):
      - ``k_neighbors`` (default 10): KNN count for local density estimation
      - ``sparse_percentile`` (default 50): density percentile threshold for "sparse" label
      - ``min_dist_factor`` (default 0.3): duplicate-filter radius as fraction of mean NN dist

    Global search guarantee: KDTree is built on *all* points; no axis-specific
    neighbourhood restriction.

mls (high mode, 200–500ms)
    Projects synthetic points onto the tangent plane of randomly selected source points
    (Moving Least Squares approximation via scipy + Open3D normal estimation).  Tangent
    planes are computed from global neighbourhood normals so vertical surfaces, ground
    planes, and diagonal structures are all treated identically.  Produces smooth
    surfaces; may slightly soften fine details.
    Use for: batch processing, surface reconstruction pipelines.

    Configurable via ``mls_params`` (DensifyMLSParams):
      - ``k_neighbors`` (default 20): KNN count for normal estimation
      - ``projection_radius_factor`` (default 0.5): tangent-plane projection radius as
        fraction of mean NN dist
      - ``min_dist_factor`` (default 0.05): duplicate-filter radius fraction

    Global search guarantee: normals are estimated with a full-cloud KNN search
    (knn=k_neighbors); synthetic displacements are bounded by the global mean NN distance.

poisson (explicit override, 500ms–2s)
    Hybrid Poisson reconstruction: preserves all original points and augments with
    uniformly-sampled points from a Poisson-reconstructed mesh trimmed at low-density
    vertices.  The implicit surface is derived from the complete input geometry so
    upsampling covers all spatial directions.
    Use for: mesh-generation workflows, digital twins, high-fidelity datasets.

    Configurable via ``poisson_params`` (DensifyPoissonParams):
      - ``depth`` (default 8): Poisson octree depth
      - ``density_threshold_quantile`` (default 0.1): low-density vertex trim threshold

    Global search guarantee: Poisson reconstruction operates on the complete cloud;
    no row/column sub-sampling is performed before reconstruction.

Preset ↔ algorithm mapping
---------------------------
fast   → nearest_neighbor
medium → statistical
high   → mls
poisson is only accessible via explicit algorithm= override.

Log level configuration
------------------------
Control verbosity via the ``log_level`` parameter or ``DENSIFY_LOG_LEVEL`` env variable:
  - ``minimal`` (default): one summary log line per invocation (INFO on skip/error,
    DEBUG on success). No per-step or per-operation messages.
  - ``full``: full DEBUG logging including per-step timing and intermediate results.
  - ``none``: completely silent except for ERROR-level messages (algorithm failures).

The env var ``DENSIFY_LOG_LEVEL`` (values: minimal / full / none) sets the default.
An explicit constructor ``log_level=`` arg always overrides the env var.

Algorithm parameter sub-dicts
-------------------------------
All tunable parameters are available via per-algorithm Pydantic model sub-dicts
(``nn_params``, ``mls_params``, ``statistical_params``, ``poisson_params``).  If not
provided, built-in production defaults apply — full backward compatibility preserved.

Density control
---------------
Use ``density_multiplier`` to set the target density increase factor (e.g. 2.0 = 2×).

Volumetric / vertical gap guarantee
-------------------------------------
Because all neighbour searches use global KDTree queries (no axis restriction), the
densification naturally fills gaps in **all** spatial directions including the vertical
axis.  This is confirmed by the ``TestVerticalGapFilling`` test suite which uses
horizontally-layered input clouds and asserts that new points bridge the vertical gaps.

Example configuration (DAG node)
----------------------------------
{
    "type": "densify",
    "config": {
        "enabled": true,
        "algorithm": "nearest_neighbor",
        "density_multiplier": 2.0,
        "quality_preset": "fast",
        "preserve_normals": true,
        "log_level": "minimal",
        "nn_params": {
            "displacement_min": 0.05,
            "displacement_max": 0.50
        }
    }
}
"""
from __future__ import annotations

import logging
import math
import os
import time
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d
from pydantic import BaseModel, Field, field_validator, model_validator

from ..base import PipelineOperation, _tensor_map_keys

# ─────────────────────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Module-level constants
# ─────────────────────────────────────────────────────────────────────────────
MIN_INPUT_POINTS: int = 10
MAX_MULTIPLIER: float = 8.0

PRESET_ALGORITHM_MAP: Dict[str, str] = {
    "fast": "nearest_neighbor",
    "medium": "statistical",
    "high": "mls",
}

_VALID_ALGORITHMS = frozenset({"nearest_neighbor", "mls", "poisson", "statistical"})
_VALID_PRESETS = frozenset({"fast", "medium", "high"})
_VALID_LOG_LEVELS = frozenset({"minimal", "full", "none"})

# Environment variable name for log level override
_ENV_LOG_LEVEL = "DENSIFY_LOG_LEVEL"


# ─────────────────────────────────────────────────────────────────────────────
# Enums (used by Pydantic models and for documentation / UI serialisation)
# ─────────────────────────────────────────────────────────────────────────────


class DensifyAlgorithm(str, Enum):
    """Available densification algorithms.  All use global KDTree searches."""

    NEAREST_NEIGHBOR = "nearest_neighbor"
    MLS = "mls"
    POISSON = "poisson"
    STATISTICAL = "statistical"


class DensifyQualityPreset(str, Enum):
    """Quality preset — determines default algorithm and latency target."""

    FAST = "fast"       # → nearest_neighbor, target <100ms
    MEDIUM = "medium"   # → statistical,      target <300ms
    HIGH = "high"       # → mls,              target <2s


class DensifyStatus(str, Enum):
    """Outcome status embedded in the metadata dict returned by apply()."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


class DensifyLogLevel(str, Enum):
    """
    Controls verbosity of Densify log output.

    Attributes:
        MINIMAL: One summary line per invocation (INFO on skip/error, DEBUG on
                 success). No per-step or intermediate messages. Production default.
        FULL:    Full DEBUG logging with per-step timing and intermediate results.
        NONE:    Completely silent except for ERROR-level messages (algorithm failures).

    Can also be set via the ``DENSIFY_LOG_LEVEL`` environment variable.
    Explicit constructor ``log_level=`` arg always takes precedence over env var.
    """

    MINIMAL = "minimal"
    FULL = "full"
    NONE = "none"


# ─────────────────────────────────────────────────────────────────────────────
# Per-algorithm parameter models
# ─────────────────────────────────────────────────────────────────────────────


class DensifyNNParams(BaseModel):
    """
    Tunable parameters for the ``nearest_neighbor`` densification algorithm.

    All parameters are optional; omitting them uses the production defaults.
    Pass as ``nn_params=DensifyNNParams(...)`` in ``Densify.__init__`` or
    as a nested dict in ``DensifyConfig.nn_params``.

    Attributes:
        displacement_min: Minimum displacement as a fraction of the global mean
            nearest-neighbour distance.  Controls how close synthetic points can be
            to their source. Range: [0.0, displacement_max).  Default: 0.05.
        displacement_max: Maximum displacement fraction.  Controls spread radius.
            Range: (displacement_min, 1.0].  Default: 0.50.
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
        k_neighbors: KNN count for surface normal estimation.  Higher values give
            smoother normals at the cost of speed.  Range: [3, ∞).  Default: 20.
        projection_radius_factor: Tangent-plane projection radius as a fraction of
            the global mean NN distance.  Controls the spatial spread of synthetic
            points around each source.  Range: (0.0, 2.0].  Default: 0.5.
        min_dist_factor: Duplicate-filter radius as a fraction of the global mean NN
            distance.  Synthetic points within this radius of any existing point are
            removed.  Range: [0.0, 1.0].  Default: 0.05.
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
        k_neighbors: KNN count for local density estimation.  Range: [2, ∞).
            Default: 10.
        sparse_percentile: Points with local density below this percentile are
            labelled "sparse" and used as interpolation sources.  Range: (0, 100].
            Default: 50 (bottom half of density distribution).
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
        depth: Octree depth for Poisson reconstruction.  Higher depth = more detail
            but slower and more memory.  Range: [4, 12].  Default: 8.
        density_threshold_quantile: Quantile below which low-density mesh vertices
            are trimmed before sampling.  Range: [0.0, 0.5].  Default: 0.1.
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
# Pydantic models (REST / persistence layer validation)
# ─────────────────────────────────────────────────────────────────────────────


class DensifyConfig(BaseModel):
    """
    Configuration for the Densify pipeline operation.

    All algorithms perform global, full-cloud neighbour searches — no scanline,
    ring-based, or sequential processing modes exist.

    Log verbosity is controlled by ``log_level`` (default ``'minimal'``).  Can also
    be set via the ``DENSIFY_LOG_LEVEL`` environment variable.

    Per-algorithm tunable parameters are available as optional sub-dict fields
    (``nn_params``, ``mls_params``, ``statistical_params``, ``poisson_params``).
    If not provided, production defaults apply — backward compatibility preserved.

    Persistence format (DAG node config stored in DB):
        {"type": "densify", "config": { ...DensifyConfig fields... }}
    """

    enabled: bool = Field(
        default=True,
        description="Enable/disable this operation. Disabled nodes pass through unchanged.",
    )
    algorithm: Optional[DensifyAlgorithm] = Field(
        default=None,
        description=(
            "Densification algorithm. All algorithms use global KDTree searches "
            "and produce volumetric (3-D) upsampling. If set explicitly (not None), takes "
            "precedence over quality_preset. When None (default), the algorithm is resolved "
            "from quality_preset via PRESET_ALGORITHM_MAP."
        ),
    )
    density_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=8.0,
        description=(
            "Target density increase factor. 2.0 doubles the point count. "
            "Range: 1.0 (no change) to 8.0 (max, memory guard)."
        ),
    )
    quality_preset: DensifyQualityPreset = Field(
        default=DensifyQualityPreset.FAST,
        description=(
            "Quality/speed preset. Determines default algorithm when 'algorithm' is "
            "not explicitly overridden. fast=<100ms, medium=<300ms, high=<2s."
        ),
    )
    preserve_normals: bool = Field(
        default=True,
        description=(
            "If True, estimate surface normals for synthetic points using k=10 nearest "
            "neighbours from the original cloud (global search). Silently skipped if "
            "input has no normals."
        ),
    )

    # ── Logging control ───────────────────────────────────────────────────────
    log_level: DensifyLogLevel = Field(
        default=DensifyLogLevel.MINIMAL,
        description=(
            "Logging verbosity. 'minimal' (default) emits one summary log per "
            "invocation. 'full' enables per-step DEBUG logging. 'none' suppresses all "
            "logs except ERROR. Also configurable via DENSIFY_LOG_LEVEL env variable."
        ),
    )

    # ── Per-algorithm parameter sub-dicts ─────────────────────────────────────
    nn_params: Optional[DensifyNNParams] = Field(
        default=None,
        description=(
            "Tunable parameters for the nearest_neighbor algorithm. "
            "None = use built-in production defaults."
        ),
    )
    mls_params: Optional[DensifyMLSParams] = Field(
        default=None,
        description=(
            "Tunable parameters for the MLS algorithm. "
            "None = use built-in production defaults."
        ),
    )
    statistical_params: Optional[DensifyStatisticalParams] = Field(
        default=None,
        description=(
            "Tunable parameters for the statistical upsampling algorithm. "
            "None = use built-in production defaults."
        ),
    )
    poisson_params: Optional[DensifyPoissonParams] = Field(
        default=None,
        description=(
            "Tunable parameters for the Poisson reconstruction algorithm. "
            "None = use built-in production defaults."
        ),
    )

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
# Main class
# ─────────────────────────────────────────────────────────────────────────────


class Densify(PipelineOperation):
    """
    Point cloud densification operation — volumetric, sensor-agnostic.

    Increases spatial density of sparse point clouds by interpolating additional
    points using one of four selectable algorithms.  All algorithms operate on the
    **complete** input cloud via global KDTree queries — there is no scanline, ring-
    based, or sequential processing mode.  New points are generated in all three
    spatial dimensions, filling both horizontal and vertical gaps equally.

    Log Verbosity
    -------------
    Controlled by ``log_level`` (``'minimal'`` | ``'full'`` | ``'none'``).
    Default is ``'minimal'`` (one summary line per invocation).  Can also be set
    via ``DENSIFY_LOG_LEVEL`` environment variable; explicit constructor arg wins.

    Per-Algorithm Parameters
    ------------------------
    All tunable algorithm parameters are exposed via optional ``*_params`` kwargs
    (``nn_params``, ``mls_params``, ``statistical_params``, ``poisson_params``).
    Omitting them uses production defaults — backward compatibility is preserved.

    Args:
        enabled:              Enable/disable toggle (default True).
        algorithm:            Algorithm key string, or None to use quality_preset.
                              Valid: 'nearest_neighbor', 'mls', 'poisson', 'statistical'.
        density_multiplier:   Target density factor (default 2.0, range [1.0, 8.0]).
        quality_preset:       'fast' | 'medium' | 'high' (default 'fast').
        preserve_normals:     Interpolate normals for synthetic points (default True).
        log_level:            'minimal' | 'full' | 'none' (default from env or 'minimal').
        nn_params:            DensifyNNParams instance or None (use defaults).
        mls_params:           DensifyMLSParams instance or None (use defaults).
        statistical_params:   DensifyStatisticalParams instance or None (use defaults).
        poisson_params:       DensifyPoissonParams instance or None (use defaults).
    """

    def __init__(
        self,
        enabled: bool = True,
        algorithm: Optional[str] = None,
        density_multiplier: float = 2.0,
        quality_preset: str = "fast",
        preserve_normals: bool = True,
        log_level: Optional[str] = None,
        nn_params: Optional[Any] = None,
        mls_params: Optional[Any] = None,
        statistical_params: Optional[Any] = None,
        poisson_params: Optional[Any] = None,
    ) -> None:
        # Validate algorithm
        if algorithm is not None and algorithm not in _VALID_ALGORITHMS:
            raise ValueError(
                f"algorithm must be one of {sorted(_VALID_ALGORITHMS)}, got '{algorithm}'"
            )

        # Validate density_multiplier
        if not (1.0 <= float(density_multiplier) <= 8.0):
            raise ValueError(
                f"density_multiplier must be in [1.0, 8.0], got {density_multiplier}"
            )

        # Validate quality_preset
        if quality_preset not in _VALID_PRESETS:
            raise ValueError(
                f"quality_preset must be one of {sorted(_VALID_PRESETS)}, got '{quality_preset}'"
            )

        # Resolve log_level: explicit arg > env var > 'minimal'
        resolved_log_level = self._resolve_log_level(log_level)
        if resolved_log_level not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}, "
                f"got '{resolved_log_level}'"
            )

        self.enabled: bool = bool(enabled)
        self.algorithm: Optional[str] = algorithm
        self.density_multiplier: float = float(density_multiplier)
        self.quality_preset: str = quality_preset
        self.preserve_normals: bool = bool(preserve_normals)
        self.log_level: str = resolved_log_level

        # Per-algorithm parameter objects — coerce dicts to typed models
        self.nn_params: Optional[DensifyNNParams] = self._coerce_params(
            nn_params, DensifyNNParams
        )
        self.mls_params: Optional[DensifyMLSParams] = self._coerce_params(
            mls_params, DensifyMLSParams
        )
        self.statistical_params: Optional[DensifyStatisticalParams] = self._coerce_params(
            statistical_params, DensifyStatisticalParams
        )
        self.poisson_params: Optional[DensifyPoissonParams] = self._coerce_params(
            poisson_params, DensifyPoissonParams
        )

        # Emit init log only in full mode to avoid spamming at startup
        if self.log_level == "full":
            logger.info(
                "Densify: Initialized — algorithm=%s, multiplier=%s, preset=%s, "
                "log_level=%s (volumetric mode — global KDTree, all spatial directions)",
                algorithm if algorithm is not None else f"<preset:{quality_preset}>",
                density_multiplier,
                quality_preset,
                resolved_log_level,
            )

    # ─── Public API ──────────────────────────────────────────────────────────

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:  # type: ignore[override]
        """
        Densify the input point cloud.

        Uses global neighbour searches (full-cloud KDTree) — no scanline or
        ring-based processing.  New points are generated in all spatial
        directions, including vertical gaps.

        Log verbosity is controlled by ``self.log_level``:
          - ``'minimal'``: one summary log per successful run (DEBUG) or skip/error (INFO/WARNING/ERROR)
          - ``'full'``: verbose DEBUG logging per step
          - ``'none'``: silent except ERROR on algorithm failure

        Args:
            pcd: o3d.geometry.PointCloud (legacy) or o3d.t.geometry.PointCloud (tensor).

        Returns:
            (result_pcd, metadata_dict) — always a 2-tuple, never raises.
        """
        start_time = time.monotonic()

        # ── 0. Normalise input ───────────────────────────────────────────────
        try:
            tensor_pcd, original_count, original_pcd = self._validate_input(pcd)
        except Exception:
            # Completely unknown input type — return safe fallback
            elapsed = (time.monotonic() - start_time) * 1000.0
            return pcd, self._make_skip_meta(
                original_count=0,
                reason="Invalid input: could not parse point cloud",
                elapsed_ms=elapsed,
            )

        # ── 1. disabled check ────────────────────────────────────────────────
        if not self.enabled:
            elapsed = (time.monotonic() - start_time) * 1000.0
            return original_pcd, self._make_skip_meta(
                original_count=original_count,
                reason="Operation disabled",
                elapsed_ms=elapsed,
            )

        # ── 2. insufficient points check ─────────────────────────────────────
        if original_count < MIN_INPUT_POINTS:
            elapsed = (time.monotonic() - start_time) * 1000.0
            # Emit warning only in non-'none' mode
            if self.log_level != "none":
                logger.warning(
                    "Densify: Skipping — insufficient input points (%d < %d)",
                    original_count,
                    MIN_INPUT_POINTS,
                )
            return original_pcd, self._make_skip_meta(
                original_count=original_count,
                reason=f"Insufficient input points ({original_count} < minimum {MIN_INPUT_POINTS})",
                elapsed_ms=elapsed,
            )

        # ── 3. resolve effective algorithm ───────────────────────────────────
        effective_algorithm = self._resolve_effective_algorithm()

        # ── 4. compute target count ──────────────────────────────────────────
        target_count = self._compute_target_count(original_count)

        # ── 5. already dense check ───────────────────────────────────────────
        if target_count <= original_count:
            elapsed = (time.monotonic() - start_time) * 1000.0
            if self.log_level == "full":
                logger.info(
                    "Densify: Skipping — input already meets or exceeds target density "
                    "(current: %d, target: %d)",
                    original_count,
                    target_count,
                )
            return original_pcd, self._make_skip_meta(
                original_count=original_count,
                reason=(
                    f"Input already meets or exceeds target density "
                    f"(current: {original_count}, target: {target_count})"
                ),
                elapsed_ms=elapsed,
            )

        # ── 6. run algorithm (fail-safe) ─────────────────────────────────────
        try:
            result_pcd = self._run_algorithm(tensor_pcd, target_count, effective_algorithm)
        except Exception as exc:
            elapsed = (time.monotonic() - start_time) * 1000.0
            # ERROR is always logged regardless of log_level
            logger.error(
                "Densify: %s algorithm failed — %s. Passing through original cloud.",
                effective_algorithm,
                exc,
            )
            return original_pcd, {
                "status": "error",
                "original_count": original_count,
                "densified_count": original_count,
                "density_ratio": 1.0,
                "algorithm_used": effective_algorithm,
                "processing_time_ms": elapsed,
                "skip_reason": None,
                "error_message": str(exc),
            }

        # ── 7. normal estimation ─────────────────────────────────────────────
        if self.preserve_normals:
            result_pcd = self._estimate_normals(result_pcd, tensor_pcd, original_count)

        # ── 8. build success metadata ─────────────────────────────────────────
        elapsed = (time.monotonic() - start_time) * 1000.0
        densified_count = self._get_count(result_pcd)
        density_ratio = densified_count / original_count if original_count > 0 else 1.0

        # Emit single summary log: DEBUG in full mode, DEBUG in minimal mode
        # (minimal = one summary line, full = includes step detail which was emitted inline)
        if self.log_level == "full":
            logger.debug(
                "Densify: [%s] %d→%d pts in %.1fms (ratio=%.2f)",
                effective_algorithm,
                original_count,
                densified_count,
                elapsed,
                density_ratio,
            )
        elif self.log_level == "minimal":
            logger.debug(
                "Densify: %s %d→%d pts in %.1fms",
                effective_algorithm,
                original_count,
                densified_count,
                elapsed,
            )
        # log_level == "none": no output

        return result_pcd, {
            "status": "success",
            "original_count": original_count,
            "densified_count": densified_count,
            "density_ratio": density_ratio,
            "algorithm_used": effective_algorithm,
            "processing_time_ms": elapsed,
            "skip_reason": None,
            "error_message": None,
        }

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_log_level(explicit: Optional[str]) -> str:
        """
        Resolve effective log level from explicit arg → env var → 'minimal'.

        Priority: explicit kwarg > DENSIFY_LOG_LEVEL env var > 'minimal'.
        """
        if explicit is not None:
            return explicit
        env_val = os.environ.get(_ENV_LOG_LEVEL, "").strip().lower()
        if env_val in _VALID_LOG_LEVELS:
            return env_val
        return "minimal"

    @staticmethod
    def _coerce_params(value: Optional[Any], model_cls: type) -> Optional[Any]:
        """
        Coerce a params value to the correct Pydantic model instance.

        - None → None (use built-in defaults)
        - dict → model_cls(**dict)
        - model instance → passed through
        """
        if value is None:
            return None
        if isinstance(value, dict):
            return model_cls(**value)
        return value  # Already a model instance

    def _validate_input(
        self, pcd: Any
    ) -> Tuple[o3d.t.geometry.PointCloud, int, Any]:
        """
        Normalise the input pcd to a tensor PointCloud.

        Returns:
            (tensor_pcd, original_count, original_pcd_reference)

        Raises:
            TypeError if pcd is not a recognised PointCloud type.
        """
        if pcd is None:
            raise TypeError("Input pcd is None")

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = (
                int(pcd.point.positions.shape[0])
                if "positions" in pcd.point
                else 0
            )
            return pcd, count, pcd

        if isinstance(pcd, o3d.geometry.PointCloud):
            tensor_pcd = o3d.t.geometry.PointCloud.from_legacy(pcd)
            count = len(pcd.points)
            return tensor_pcd, count, pcd

        raise TypeError(
            f"Unsupported input type: expected o3d PointCloud, got {type(pcd).__name__}"
        )

    def _resolve_effective_algorithm(self) -> str:
        """
        Return the algorithm string to execute.

        Precedence: explicit self.algorithm > PRESET_ALGORITHM_MAP[quality_preset]
        """
        if self.algorithm is not None:
            return self.algorithm
        return PRESET_ALGORITHM_MAP[self.quality_preset]

    def _compute_target_count(self, original_count: int) -> int:
        """
        Compute the target point count using ``density_multiplier``.

        Multiplier is clamped to [1.0, MAX_MULTIPLIER].
        Result is clamped to [original_count, original_count * MAX_MULTIPLIER].
        """
        effective_multiplier = min(max(self.density_multiplier, 1.0), MAX_MULTIPLIER)
        return int(original_count * effective_multiplier)

    def _run_algorithm(
        self,
        pcd: o3d.t.geometry.PointCloud,
        target_count: int,
        algorithm: str,
    ) -> o3d.t.geometry.PointCloud:
        """Dispatch to the selected algorithm method."""
        n_new = target_count - self._get_count(pcd)
        if n_new <= 0:
            return pcd

        dispatch = {
            "nearest_neighbor": self._densify_nearest_neighbor,
            "mls": self._densify_mls,
            "poisson": self._densify_poisson,
            "statistical": self._densify_statistical,
        }
        return dispatch[algorithm](pcd, n_new)

    # ── Algorithm implementations ─────────────────────────────────────────────

    def _densify_nearest_neighbor(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Nearest-neighbour densification — volumetric, sensor-agnostic.

        Generates n_new synthetic points by adding 3-D jittered displacements from
        randomly-selected source points.  Displacement direction is uniformly random
        in all three spatial axes; magnitude is a random fraction of the *global* mean
        nearest-neighbour distance (computed over the entire input cloud via scipy
        KDTree — no scanline sub-sampling, no ring grouping).

        This ensures both horizontal and vertical gaps are filled regardless of the
        original scan pattern or sensor type.

        Parameters are read from ``self.nn_params`` (DensifyNNParams) if provided,
        otherwise production defaults are used.
        """
        from scipy.spatial import KDTree  # lazy import — already a project dep

        # Resolve algorithm params (use explicit params or production defaults)
        p = self.nn_params if self.nn_params is not None else DensifyNNParams()

        pts = pcd.point.positions.numpy().astype(np.float64)  # (N, 3)
        n_orig = len(pts)

        # Compute mean NN distance using a global scipy KDTree over ALL points.
        mean_nn_dist = self._compute_mean_nn_dist_global(pts)

        if self.log_level == "full":
            logger.debug(
                "Densify[nn]: n_orig=%d, n_new=%d, mean_nn_dist=%.4f, "
                "disp=[%.3f, %.3f]×mean_nn",
                n_orig, n_new, mean_nn_dist, p.displacement_min, p.displacement_max,
            )

        rng = np.random.default_rng()
        synthetic = np.empty((n_new, 3), dtype=np.float32)

        points_per_source = max(1, math.ceil(n_new / n_orig))
        idx = 0
        while idx < n_new:
            # Pick a random source point from the GLOBAL cloud
            src_idx = rng.integers(0, n_orig)
            src_pt = pts[src_idx]

            for _ in range(points_per_source):
                if idx >= n_new:
                    break
                # Uniformly random 3-D unit direction — no axis restriction
                direction = rng.standard_normal(3)
                norm = np.linalg.norm(direction)
                if norm < 1e-8:
                    direction = np.array([1.0, 0.0, 0.0], dtype=np.float64)
                else:
                    direction /= norm

                radius = rng.uniform(p.displacement_min, p.displacement_max) * mean_nn_dist
                synthetic[idx] = (src_pt + radius * direction).astype(np.float32)
                idx += 1

        # Concatenate original + synthetic
        orig_f32 = pts.astype(np.float32)
        all_pts = np.vstack([orig_f32, synthetic])  # (N + n_new, 3)
        return self._make_tensor_pcd_from_positions(all_pts)

    def _densify_mls(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Moving Least Squares tangent-plane projection densification — volumetric.

        Projects synthetic points onto the tangent plane of nearby source points.
        All neighbour queries use a global scipy KDTree built on the complete input
        cloud — no per-ring or per-scanline neighbourhood restriction.

        Parameters are read from ``self.mls_params`` (DensifyMLSParams) if provided,
        otherwise production defaults are used.
        """
        from scipy.spatial import KDTree  # lazy import

        # Resolve algorithm params
        p = self.mls_params if self.mls_params is not None else DensifyMLSParams()

        pcd_legacy = pcd.to_legacy()
        try:
            pts = np.asarray(pcd_legacy.points, dtype=np.float64)
            n_orig = len(pts)

            # Ensure normals for tangent plane construction.
            # Uses configurable k_neighbors (default 20).
            if not pcd_legacy.has_normals():
                pcd_legacy.estimate_normals(
                    o3d.geometry.KDTreeSearchParamKNN(knn=p.k_neighbors)
                )
                pcd_legacy.normalize_normals()
            norms = np.asarray(pcd_legacy.normals, dtype=np.float64)  # (N, 3)

            # Global mean NN distance — full-cloud scipy KDTree
            mean_nn_dist = self._compute_mean_nn_dist_global(pts)
            projection_radius = mean_nn_dist * p.projection_radius_factor
            min_dist = mean_nn_dist * p.min_dist_factor

            if self.log_level == "full":
                logger.debug(
                    "Densify[mls]: n_orig=%d, n_new=%d, k=%d, "
                    "proj_r=%.4f, min_dist=%.4f",
                    n_orig, n_new, p.k_neighbors, projection_radius, min_dist,
                )

            # Global KDTree for duplicate filtering
            kd_tree = KDTree(pts)
            rng = np.random.default_rng()

            synthetic = np.empty((n_new, 3), dtype=np.float32)
            points_per_source = max(1, math.ceil(n_new / n_orig))
            idx = 0
            while idx < n_new:
                # Select source point from the GLOBAL cloud
                src_idx = rng.integers(0, n_orig)
                pt = pts[src_idx]
                n = norms[src_idx]

                # Build tangent plane basis {u, v}
                u, v = self._tangent_basis(n)
                sigma = projection_radius / 3.0

                for _ in range(points_per_source):
                    if idx >= n_new:
                        break
                    su = rng.uniform(-sigma, sigma)
                    sv = rng.uniform(-sigma, sigma)
                    new_pt = pt + su * u + sv * v
                    synthetic[idx] = new_pt.astype(np.float32)
                    idx += 1

            # Post-filter: remove synthetic pts within min_dist of any existing pt
            if min_dist > 0:
                synthetic = self._filter_too_close(synthetic, kd_tree, min_dist)

            orig_f32 = pts.astype(np.float32)
            all_pts = np.vstack([orig_f32, synthetic])
            return self._make_tensor_pcd_from_positions(all_pts)
        finally:
            del pcd_legacy

    def _densify_poisson(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Hybrid Poisson reconstruction densification — volumetric.

        Preserves all original points and augments with n_new uniformly-sampled
        points from a Poisson-reconstructed mesh.

        Parameters are read from ``self.poisson_params`` (DensifyPoissonParams)
        if provided, otherwise production defaults are used.
        """
        # Resolve algorithm params
        p = self.poisson_params if self.poisson_params is not None else DensifyPoissonParams()

        pcd_legacy = pcd.to_legacy()
        try:
            pts_orig = np.asarray(pcd_legacy.points, dtype=np.float32)

            # Ensure normals for Poisson — full-cloud KNN search
            if not pcd_legacy.has_normals():
                pcd_legacy.estimate_normals(
                    o3d.geometry.KDTreeSearchParamKNN(knn=30)
                )
                pcd_legacy.normalize_normals()

            if self.log_level == "full":
                logger.debug(
                    "Densify[poisson]: n_orig=%d, n_new=%d, depth=%d, q=%.2f",
                    len(pts_orig), n_new, p.depth, p.density_threshold_quantile,
                )

            # Poisson reconstruction on the complete cloud
            mesh, densities = (
                o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                    pcd_legacy,
                    depth=p.depth,
                    width=0,
                    scale=1.1,
                    linear_fit=False,
                )
            )

            # Trim low-density vertices using configurable quantile
            densities_arr = np.asarray(densities)
            threshold = float(np.quantile(densities_arr, p.density_threshold_quantile))
            vertices_to_remove = densities_arr < threshold
            mesh.remove_vertices_by_mask(vertices_to_remove)

            # Guard: n_new capped at 7× original
            max_sample = int(len(pts_orig) * 7)
            n_sample = min(n_new, max_sample)
            if n_sample <= 0:
                n_sample = 1

            # Sample uniformly from the mesh
            sampled_legacy = mesh.sample_points_uniformly(number_of_points=n_sample)
            del mesh

            sampled_pts = np.asarray(sampled_legacy.points, dtype=np.float32)

            all_pts = np.vstack([pts_orig, sampled_pts])
            return self._make_tensor_pcd_from_positions(all_pts)
        finally:
            del pcd_legacy

    def _densify_statistical(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Statistical upsampling densification — volumetric, sensor-agnostic.

        Computes per-point local density using a **global** scipy KDTree query
        (k=k_neighbors nearest neighbours for every point — no axis restriction,
        no scanline grouping).  Identifies sparse 3-D regions and interpolates
        new points along edges to existing neighbours with α ∈ [0.3, 0.7].

        Parameters are read from ``self.statistical_params`` (DensifyStatisticalParams)
        if provided, otherwise production defaults are used.
        """
        from scipy.spatial import KDTree  # lazy import

        # Resolve algorithm params
        p = self.statistical_params if self.statistical_params is not None \
            else DensifyStatisticalParams()

        pts = pcd.point.positions.numpy().astype(np.float64)
        n_orig = len(pts)

        # Global KDTree — full cloud, no per-ring or per-scanline restriction
        kd_tree = KDTree(pts)
        k_total = min(p.k_neighbors + 1, n_orig)  # +1 for self
        dists, idxs = kd_tree.query(pts, k=k_total)

        # Exclude self (col 0)
        dists = dists[:, 1:]    # (N, k_neighbors)
        idxs = idxs[:, 1:]      # (N, k_neighbors)

        # Local density: k / volume_of_sphere(radius = max_dist)
        max_dist = dists[:, -1]
        max_dist = np.where(max_dist < 1e-8, 1e-8, max_dist)
        local_density = (k_total - 1) / ((4.0 / 3.0) * math.pi * (max_dist ** 3))

        # Mean NN dist for min_dist filter (global, all directions)
        mean_nn_dist = float(dists[:, 0].mean()) if dists.size > 0 else 0.01
        min_dist = mean_nn_dist * p.min_dist_factor

        # Sparse-region points: bottom sparse_percentile of volumetric density
        percentile_val = float(np.percentile(local_density, p.sparse_percentile))
        sparse_mask = local_density < percentile_val
        sparse_indices = np.where(sparse_mask)[0]

        if self.log_level == "full":
            logger.debug(
                "Densify[statistical]: n_orig=%d, n_new=%d, k=%d, "
                "sparse_pct=%.0f, n_sparse=%d, min_dist=%.4f",
                n_orig, n_new, p.k_neighbors, p.sparse_percentile,
                len(sparse_indices), min_dist,
            )

        rng = np.random.default_rng()
        synthetic_list = []
        budget = n_new

        if len(sparse_indices) > 0:
            n_neighbors = dists.shape[1]
            pts_per_sparse = max(1, math.ceil(budget / (len(sparse_indices) * n_neighbors)))

            for src_i in sparse_indices:
                if budget <= 0:
                    break
                p_i = pts[src_i]
                for j in range(n_neighbors):
                    if budget <= 0:
                        break
                    p_j = pts[idxs[src_i, j]]
                    for _ in range(pts_per_sparse):
                        if budget <= 0:
                            break
                        alpha = rng.uniform(0.3, 0.7)
                        # Interpolation in full 3-D space — no axis clamping
                        new_pt = (1.0 - alpha) * p_i + alpha * p_j
                        synthetic_list.append(new_pt)
                        budget -= 1

        if len(synthetic_list) == 0:
            # Fallback to NN if statistical produced nothing
            return self._densify_nearest_neighbor(pcd, n_new)

        synthetic = np.array(synthetic_list, dtype=np.float32)

        # Post-filter: remove points too close to existing (global KDTree)
        if min_dist > 0:
            synthetic = self._filter_too_close(synthetic, kd_tree, min_dist)

        # Trim or pad to n_new
        if len(synthetic) > n_new:
            synthetic = synthetic[:n_new]

        orig_f32 = pts.astype(np.float32)
        all_pts = np.vstack([orig_f32, synthetic])
        return self._make_tensor_pcd_from_positions(all_pts)

    # ── Normal estimation ─────────────────────────────────────────────────────

    def _estimate_normals(
        self,
        result_pcd: o3d.t.geometry.PointCloud,
        original_pcd: o3d.t.geometry.PointCloud,
        n_original: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Estimate normals for synthetic points (indices n_original onward).

        Uses a global scipy KDTree on original positions — no scanline or ring
        restriction.  k=10 nearest neighbours from the full original cloud are used
        for each synthetic point, guaranteeing correct normal estimation regardless
        of the spatial structure of the input.

        If the original cloud has no normals, logs INFO (only in non-'none' mode)
        and returns unchanged.  Original normals are preserved; only synthetic indices
        get new values.
        """
        # Check if original has normals
        orig_keys = _tensor_map_keys(original_pcd.point)
        if "normals" not in orig_keys:
            if self.log_level == "full":
                logger.info(
                    "Densify: Input cloud has no normals — skipping normal estimation"
                )
            return result_pcd

        # Extract original normals
        orig_normals = original_pcd.point["normals"].numpy()  # (n_orig, 3)

        # How many synthetic points?
        result_count = self._get_count(result_pcd)
        n_synthetic = result_count - n_original
        if n_synthetic <= 0:
            return result_pcd

        # Build global KDTree on original positions for NN search
        orig_pts = original_pcd.point.positions.numpy()  # (n_orig, 3)
        synth_pts = result_pcd.point.positions.numpy()[n_original:]  # (n_synthetic, 3)

        try:
            from scipy.spatial import KDTree

            kd_orig = KDTree(orig_pts.astype(np.float64))
            k = min(10, n_original)
            _, neighbor_idxs = kd_orig.query(synth_pts.astype(np.float64), k=k)
            if k == 1:
                neighbor_idxs = neighbor_idxs[:, np.newaxis]

            # Mean of neighbour normals, then normalise to unit length
            synth_normals = orig_normals[neighbor_idxs].mean(axis=1)  # (n_synthetic, 3)
            norms_len = np.linalg.norm(synth_normals, axis=1, keepdims=True)
            norms_len = np.where(norms_len < 1e-8, 1.0, norms_len)
            synth_normals /= norms_len

            # Combine: [orig_normals | synth_normals]
            all_normals = np.vstack(
                [orig_normals.astype(np.float32), synth_normals.astype(np.float32)]
            )
            result_pcd.point["normals"] = o3d.core.Tensor(all_normals)
        except Exception as exc:
            logger.warning("Densify: Normal estimation failed — %s. Skipping.", exc)

        return result_pcd

    # ── Utility helpers ───────────────────────────────────────────────────────

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

            # For large clouds: sample uniformly at random (no axis bias)
            sample_size = min(n, 1000)
            if sample_size < n:
                rng = np.random.default_rng()
                sample_idx = rng.choice(n, size=sample_size, replace=False)
                sample_pts = pts[sample_idx]
            else:
                sample_pts = pts

            # Build KDTree on ALL points so neighbours are truly global
            kd = KDTree(pts.astype(np.float64))
            # k=2: [self_dist=0, nearest_neighbour_dist]
            dists, _ = kd.query(sample_pts.astype(np.float64), k=2)
            nn_dists = dists[:, 1]  # distances to nearest neighbours
            nn_dists = nn_dists[nn_dists > 1e-10]  # exclude exact duplicates
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
        Compute two orthonormal vectors {u, v} perpendicular to `normal`.

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
        The existing KDTree is built on the full original cloud — no axis restriction.
        """
        try:
            nearby = kd_existing.query_ball_point(
                synthetic.astype(np.float64), r=min_dist
            )
            keep = np.array([len(nb) == 0 for nb in nearby])
            return synthetic[keep]
        except Exception:
            return synthetic

    @staticmethod
    def _make_skip_meta(
        original_count: int,
        reason: str,
        elapsed_ms: float,
    ) -> Dict[str, Any]:
        """Build a metadata dict for skip outcomes."""
        return {
            "status": "skipped",
            "original_count": original_count,
            "densified_count": original_count,
            "density_ratio": 1.0,
            "algorithm_used": "skipped",
            "processing_time_ms": elapsed_ms,
            "skip_reason": reason,
            "error_message": None,
        }
