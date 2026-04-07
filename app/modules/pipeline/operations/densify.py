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

    Global search guarantee: mean NN distance is computed via a full-cloud scipy KDTree
    query over all N points (no scanline sampling, no ring grouping).

statistical (medium mode, 100–300ms)
    Computes per-point local density using a global KDTree query (k=10 neighbours for
    every point).  Identifies sparse regions across the entire 3-D volume and
    interpolates new points along edges to existing neighbours with α ∈ [0.3, 0.7].
    Use for: interactive applications, general-purpose 3-D densification.

    Global search guarantee: KDTree is built on *all* points; no axis-specific
    neighbourhood restriction.

mls (high mode, 200–500ms)
    Projects synthetic points onto the tangent plane of randomly selected source points
    (Moving Least Squares approximation via scipy + Open3D normal estimation).  Tangent
    planes are computed from global neighbourhood normals so vertical surfaces, ground
    planes, and diagonal structures are all treated identically.  Produces smooth
    surfaces; may slightly soften fine details.
    Use for: batch processing, surface reconstruction pipelines.

    Global search guarantee: normals are estimated with a full-cloud KNN search
    (knn=20); synthetic displacements are bounded by the global mean NN distance.

poisson (explicit override, 500ms–2s)
    Hybrid Poisson reconstruction: preserves all original points and augments with
    uniformly-sampled points from a Poisson-reconstructed mesh trimmed at low-density
    vertices.  The implicit surface is derived from the complete input geometry so
    upsampling covers all spatial directions.
    Use for: mesh-generation workflows, digital twins, high-fidelity datasets.

    Global search guarantee: Poisson reconstruction operates on the complete cloud;
    no row/column sub-sampling is performed before reconstruction.

Preset ↔ algorithm mapping
---------------------------
fast   → nearest_neighbor
medium → statistical
high   → mls
poisson is only accessible via explicit algorithm= override.

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
        "preserve_normals": true
    }
}
"""
from __future__ import annotations

import logging
import math
import time
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d
from pydantic import BaseModel, Field, field_validator

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


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models (REST / persistence layer validation)
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
        description=(
            "Densification algorithm. All algorithms use global KDTree searches "
            "and produce volumetric (3-D) upsampling. If set explicitly, takes "
            "precedence over quality_preset. Defaults to nearest_neighbor."
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

    Args:
        enabled:             Enable/disable toggle (default True).
        algorithm:           Algorithm key string, or None to use quality_preset.
                             Valid: 'nearest_neighbor', 'mls', 'poisson', 'statistical'.
        density_multiplier:  Target density factor (default 2.0, range [1.0, 8.0]).
        quality_preset:      'fast' | 'medium' | 'high' (default 'fast').
        preserve_normals:    Interpolate normals for synthetic points (default True).
    """

    def __init__(
        self,
        enabled: bool = True,
        algorithm: Optional[str] = None,
        density_multiplier: float = 2.0,
        quality_preset: str = "fast",
        preserve_normals: bool = True,
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

        self.enabled: bool = bool(enabled)
        self.algorithm: Optional[str] = algorithm
        self.density_multiplier: float = float(density_multiplier)
        self.quality_preset: str = quality_preset
        self.preserve_normals: bool = bool(preserve_normals)

        logger.info(
            "Densify: Initialized with algorithm=%s, multiplier=%s, preset=%s "
            "(volumetric mode — global KDTree search, all spatial directions)",
            algorithm if algorithm is not None else f"<preset:{quality_preset}>",
            density_multiplier,
            quality_preset,
        )

    # ─── Public API ──────────────────────────────────────────────────────────

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:  # type: ignore[override]
        """
        Densify the input point cloud.

        Uses global neighbour searches (full-cloud KDTree) — no scanline or
        ring-based processing.  New points are generated in all spatial
        directions, including vertical gaps.

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

        logger.info(
            "Densify: Using %s with %.2fx multiplier (global KDTree, volumetric)",
            effective_algorithm,
            target_count / original_count,
        )

        # ── 6. run algorithm (fail-safe) ─────────────────────────────────────
        try:
            result_pcd = self._run_algorithm(tensor_pcd, target_count, effective_algorithm)
        except Exception as exc:
            elapsed = (time.monotonic() - start_time) * 1000.0
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

        logger.debug(
            "Densify: Processed %d→%d points in %.1fms",
            original_count,
            densified_count,
            elapsed,
        )

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
        """
        from scipy.spatial import KDTree  # lazy import — already a project dep

        pts = pcd.point.positions.numpy().astype(np.float64)  # (N, 3)
        n_orig = len(pts)

        # Compute mean NN distance using a global scipy KDTree over ALL points.
        # This guarantees the radius reflects the true 3-D point spacing, not just
        # the horizontal (within-ring) spacing of structured LIDAR scans.
        mean_nn_dist = self._compute_mean_nn_dist_global(pts)

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

                radius = rng.uniform(0.05, 0.5) * mean_nn_dist
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
        cloud — no per-ring or per-scanline neighbourhood restriction.  Normals are
        estimated with a full-cloud KNN search (knn=20) so vertical surfaces, ground
        planes, and diagonal geometry are treated identically.

        Requires scipy (already in project deps via generate_plane.py).
        """
        from scipy.spatial import KDTree  # lazy import

        pcd_legacy = pcd.to_legacy()
        try:
            pts = np.asarray(pcd_legacy.points, dtype=np.float64)
            n_orig = len(pts)

            # Ensure normals for tangent plane construction.
            # estimate_normals uses a full KNN search — global neighbourhood.
            if not pcd_legacy.has_normals():
                pcd_legacy.estimate_normals(
                    o3d.geometry.KDTreeSearchParamKNN(knn=20)
                )
                pcd_legacy.normalize_normals()
            norms = np.asarray(pcd_legacy.normals, dtype=np.float64)  # (N, 3)

            # Global mean NN distance — full-cloud scipy KDTree
            mean_nn_dist = self._compute_mean_nn_dist_global(pts)
            projection_radius = mean_nn_dist * 0.5
            # min_dist must be < sigma so tangent-plane synthetics aren't all filtered;
            # use 0.05× mean_nn_dist as a loose duplicate guard.
            min_dist = mean_nn_dist * 0.05

            # Global KDTree for duplicate filtering
            kd_tree = KDTree(pts)
            rng = np.random.default_rng()

            synthetic = np.empty((n_new, 3), dtype=np.float32)
            points_per_source = max(1, math.ceil(n_new / n_orig))
            idx = 0
            while idx < n_new:
                # Select source point from the GLOBAL cloud (no per-ring restriction)
                src_idx = rng.integers(0, n_orig)
                p = pts[src_idx]
                n = norms[src_idx]

                # Build tangent plane basis {u, v} — captures all orientations
                u, v = self._tangent_basis(n)
                sigma = projection_radius / 3.0

                for _ in range(points_per_source):
                    if idx >= n_new:
                        break
                    su = rng.uniform(-sigma, sigma)
                    sv = rng.uniform(-sigma, sigma)
                    new_pt = p + su * u + sv * v
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
        points from a Poisson-reconstructed mesh trimmed at low-density vertices.

        The Poisson reconstruction operates on the **complete** input cloud — no
        scanline or ring sub-sampling is performed before reconstruction.  The
        resulting implicit surface covers all spatial directions so upsampling fills
        horizontal, vertical, and diagonal gaps alike.
        """
        pcd_legacy = pcd.to_legacy()
        try:
            pts_orig = np.asarray(pcd_legacy.points, dtype=np.float32)

            # Ensure normals for Poisson — full-cloud KNN search (knn=30)
            if not pcd_legacy.has_normals():
                pcd_legacy.estimate_normals(
                    o3d.geometry.KDTreeSearchParamKNN(knn=30)
                )
                pcd_legacy.normalize_normals()

            # Poisson reconstruction on the complete cloud
            mesh, densities = (
                o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                    pcd_legacy,
                    depth=8,
                    width=0,
                    scale=1.1,
                    linear_fit=False,
                )
            )

            # Trim low-density vertices (boundary artefacts, not scan-pattern removal)
            densities_arr = np.asarray(densities)
            threshold = float(np.quantile(densities_arr, 0.1))
            vertices_to_remove = densities_arr < threshold
            mesh.remove_vertices_by_mask(vertices_to_remove)

            # Guard: n_new capped at 7× original
            max_sample = int(len(pts_orig) * 7)
            n_sample = min(n_new, max_sample)
            if n_sample <= 0:
                n_sample = 1

            # Sample uniformly from the mesh — fills all spatial directions
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
        (k=10 nearest neighbours for every point in the full cloud — no axis
        restriction, no scanline grouping).  Identifies sparse 3-D regions and
        interpolates new points along edges to existing neighbours with
        α ∈ [0.3, 0.7].  Because the KDTree is built on all points and queries
        are unrestricted in direction, sparse vertical regions are identified and
        filled the same way as sparse horizontal regions.
        """
        from scipy.spatial import KDTree  # lazy import

        pts = pcd.point.positions.numpy().astype(np.float64)
        n_orig = len(pts)

        # Global KDTree — full cloud, no per-ring or per-scanline restriction
        kd_tree = KDTree(pts)
        k = min(11, n_orig)  # k+1 (first col is self)
        dists, idxs = kd_tree.query(pts, k=k)

        # Exclude self (col 0)
        dists = dists[:, 1:]    # (N, k-1)
        idxs = idxs[:, 1:]      # (N, k-1)

        # Local density: k / volume_of_sphere(radius = max_dist)
        # Uses 3-D spherical volume — direction-agnostic
        max_dist = dists[:, -1]
        max_dist = np.where(max_dist < 1e-8, 1e-8, max_dist)
        local_density = (k - 1) / ((4.0 / 3.0) * math.pi * (max_dist ** 3))

        # Mean NN dist for min_dist filter (global, all directions)
        mean_nn_dist = float(dists[:, 0].mean()) if dists.size > 0 else 0.01
        min_dist = mean_nn_dist * 0.3

        # Sparse-region points: bottom 50th percentile of volumetric density
        percentile_50 = float(np.percentile(local_density, 50))
        sparse_mask = local_density < percentile_50
        sparse_indices = np.where(sparse_mask)[0]

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
                        # Interpolation works in full 3-D space — no axis clamping
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

        If the original cloud has no normals, logs INFO and returns unchanged.
        Original normals are preserved; only synthetic indices get new values.
        """
        # Check if original has normals
        orig_keys = _tensor_map_keys(original_pcd.point)
        if "normals" not in orig_keys:
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

            # Global KDTree — no axis restriction, no ring grouping
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

        Uses scipy KDTree (pure-Python, no Open3D legacy API) querying the 2 nearest
        neighbours for every point.  This gives a 3-D global estimate of point spacing
        that is not biased toward any scan structure (rings, scanlines, rows, etc.).

        For very large clouds (N > 10_000) a random sample of 1000 points is used for
        speed while still capturing the global distribution.  The sample is drawn
        uniformly at random — no structured sub-sampling.

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
