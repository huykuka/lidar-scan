"""
Densify — Pipeline Operation
============================

Increases point cloud density by interpolating synthetic points between existing ones.
Works with any point cloud geometry — not specific to any sensor type or scan pattern.

Supported algorithms
---------------------
nearest_neighbor (default / fast mode, <100ms for 50k–100k pts)
    Copies attributes from the nearest original point and adds a spatially-jittered
    copy. Preserves sharp features; may create minor blocky artefacts.
    Use for: real-time pipelines, streaming sensor feeds.

statistical (medium mode, 100–300ms)
    Identifies locally sparse regions via per-point density estimation and interpolates
    new points along the edges to existing neighbours with random α ∈ [0.3, 0.7].
    Use for: interactive applications, general-purpose densification.

mls (high mode, 200–500ms)
    Projects synthetic points onto the tangent plane of each source point (Moving Least
    Squares approximation via scipy + Open3D normal estimation).  Produces smooth
    surfaces; may slightly soften fine details.
    Use for: batch processing, surface reconstruction pipelines.

poisson (explicit override, 500ms–2s)
    Hybrid Poisson reconstruction: preserves all original points and augments with
    uniformly-sampled points from a trimmed Poisson mesh.
    Use for: mesh-generation workflows, digital twins, high-fidelity datasets.

Preset ↔ algorithm mapping
---------------------------
fast   → nearest_neighbor
medium → statistical
high   → mls
poisson is only accessible via explicit algorithm= override.

Density control
---------------
Use ``density_multiplier`` to set the target density increase factor (e.g. 2.0 = 2×).
Optionally use ``target_point_count`` to specify an absolute output point count directly.
When ``target_point_count`` is set it takes precedence over ``density_multiplier``.

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
    """Available densification algorithms."""

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
            "Densification algorithm. If set explicitly, takes precedence over "
            "quality_preset. Defaults to nearest_neighbor."
        ),
    )
    density_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=8.0,
        description=(
            "Target density increase factor. 2.0 doubles the point count. "
            "Range: 1.0 (no change) to 8.0 (max, memory guard). "
            "Ignored if target_point_count is set."
        ),
    )
    target_point_count: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Optional: absolute output point count. If provided, overrides "
            "density_multiplier. The implied multiplier is clamped to [1.0, 8.0]."
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
            "neighbours from the original cloud. Silently skipped if input has no normals."
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
    Point cloud densification operation.

    Increases spatial density of sparse point clouds by interpolating additional
    points using one of four selectable algorithms.

    Args:
        enabled:             Enable/disable toggle (default True).
        algorithm:           Algorithm key string, or None to use quality_preset.
                             Valid: 'nearest_neighbor', 'mls', 'poisson', 'statistical'.
        density_multiplier:  Target density factor (default 2.0, range [1.0, 8.0]).
        target_point_count:  Absolute output point count; overrides density_multiplier
                             when set. The implied multiplier is clamped to [1.0, 8.0].
        quality_preset:      'fast' | 'medium' | 'high' (default 'fast').
        preserve_normals:    Interpolate normals for synthetic points (default True).
    """

    def __init__(
        self,
        enabled: bool = True,
        algorithm: Optional[str] = None,
        density_multiplier: float = 2.0,
        target_point_count: Optional[int] = None,
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
        self.target_point_count: Optional[int] = (
            int(target_point_count) if target_point_count is not None else None
        )
        self.quality_preset: str = quality_preset
        self.preserve_normals: bool = bool(preserve_normals)

        logger.info(
            "Densify: Initialized with algorithm=%s, multiplier=%s, preset=%s",
            algorithm if algorithm is not None else f"<preset:{quality_preset}>",
            density_multiplier,
            quality_preset,
        )

    # ─── Public API ──────────────────────────────────────────────────────────

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:  # type: ignore[override]
        """
        Densify the input point cloud.

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
            "Densify: Using %s with %.2fx multiplier",
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
        Compute the target point count.

        If ``target_point_count`` is set, use it directly (with multiplier clamped to
        [1.0, MAX_MULTIPLIER]).  Otherwise multiply by ``density_multiplier``.
        Result is clamped to [original_count, original_count * MAX_MULTIPLIER].
        """
        if self.target_point_count is not None:
            # target_point_count is an absolute count — derive implied multiplier and clamp
            if original_count > 0:
                effective_multiplier = float(self.target_point_count) / float(original_count)
            else:
                effective_multiplier = 1.0
        else:
            effective_multiplier = self.density_multiplier

        # Clamp to [1.0, MAX_MULTIPLIER]
        effective_multiplier = max(1.0, min(effective_multiplier, MAX_MULTIPLIER))
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
        Nearest-neighbour densification.

        Generates n_new synthetic points by adding jittered displacements
        from randomly-selected source points. Displacement magnitude is a
        random fraction of the mean nearest-neighbour distance.
        """
        pcd_legacy = pcd.to_legacy()
        try:
            pts = np.asarray(pcd_legacy.points, dtype=np.float64)  # (N, 3)
            n_orig = len(pts)

            # Compute mean NN distance (sample up to 200 points for speed)
            mean_nn_dist = self._compute_mean_nn_dist(pcd_legacy, pts, max_samples=200)

            rng = np.random.default_rng()
            synthetic = np.empty((n_new, 3), dtype=np.float32)

            points_per_source = max(1, math.ceil(n_new / n_orig))
            idx = 0
            while idx < n_new:
                # Pick a random source point
                src_idx = rng.integers(0, n_orig)
                src_pt = pts[src_idx]

                for _ in range(points_per_source):
                    if idx >= n_new:
                        break
                    # Random unit direction
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
        finally:
            del pcd_legacy

    def _densify_mls(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Moving Least Squares tangent-plane projection densification.

        Projects synthetic points onto the tangent plane of nearby source points.
        Requires scipy (already in project deps via generate_plane.py).
        """
        from scipy.spatial import KDTree  # lazy import

        pcd_legacy = pcd.to_legacy()
        try:
            pts = np.asarray(pcd_legacy.points, dtype=np.float64)
            n_orig = len(pts)

            # Ensure normals for tangent plane construction
            if not pcd_legacy.has_normals():
                pcd_legacy.estimate_normals(
                    o3d.geometry.KDTreeSearchParamKNN(knn=20)
                )
                pcd_legacy.normalize_normals()
            norms = np.asarray(pcd_legacy.normals, dtype=np.float64)  # (N, 3)

            mean_nn_dist = self._compute_mean_nn_dist(pcd_legacy, pts, max_samples=200)
            projection_radius = mean_nn_dist * 0.5
            # min_dist must be < sigma (projection_radius/3) so tangent-plane synthetics aren't
            # all filtered out; use 0.05× mean_nn_dist as a loose duplicate guard.
            min_dist = mean_nn_dist * 0.05

            kd_tree = KDTree(pts)
            rng = np.random.default_rng()

            synthetic = np.empty((n_new, 3), dtype=np.float32)
            points_per_source = max(1, math.ceil(n_new / n_orig))
            idx = 0
            while idx < n_new:
                src_idx = rng.integers(0, n_orig)
                p = pts[src_idx]
                n = norms[src_idx]

                # Build tangent plane basis {u, v}
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
        Hybrid Poisson reconstruction densification.

        Preserves all original points and augments with n_new uniformly-sampled
        points from a Poisson-reconstructed mesh trimmed at low-density vertices.
        """
        pcd_legacy = pcd.to_legacy()
        try:
            pts_orig = np.asarray(pcd_legacy.points, dtype=np.float32)

            # Ensure normals for Poisson
            if not pcd_legacy.has_normals():
                pcd_legacy.estimate_normals(
                    o3d.geometry.KDTreeSearchParamKNN(knn=30)
                )
                pcd_legacy.normalize_normals()

            # Poisson reconstruction
            mesh, densities = (
                o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                    pcd_legacy,
                    depth=8,
                    width=0,
                    scale=1.1,
                    linear_fit=False,
                )
            )

            # Trim low-density vertices
            densities_arr = np.asarray(densities)
            threshold = float(np.quantile(densities_arr, 0.1))
            vertices_to_remove = densities_arr < threshold
            mesh.remove_vertices_by_mask(vertices_to_remove)

            # Guard: n_new capped at 7× original
            max_sample = int(len(pts_orig) * 7)
            n_sample = min(n_new, max_sample)
            if n_sample <= 0:
                n_sample = 1

            # Sample from mesh
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
        Statistical upsampling densification.

        Computes per-point local density; sparse-region points get interpolated
        neighbours placed at α ∈ [0.3, 0.7] along each edge to their k=10 NNs.
        """
        from scipy.spatial import KDTree  # lazy import

        pts = pcd.point.positions.numpy().astype(np.float64)
        n_orig = len(pts)

        kd_tree = KDTree(pts)
        k = min(11, n_orig)  # k+1 (first col is self)
        dists, idxs = kd_tree.query(pts, k=k)

        # Exclude self (col 0)
        dists = dists[:, 1:]    # (N, k-1)
        idxs = idxs[:, 1:]      # (N, k-1)

        # Local density: k / volume_of_sphere(radius = max_dist)
        max_dist = dists[:, -1]
        max_dist = np.where(max_dist < 1e-8, 1e-8, max_dist)
        local_density = (k - 1) / ((4.0 / 3.0) * math.pi * (max_dist ** 3))

        # Mean NN dist for min_dist filter
        mean_nn_dist = float(dists[:, 0].mean()) if dists.size > 0 else 0.01
        min_dist = mean_nn_dist * 0.3

        # Sparse-region points: bottom 50th percentile of density
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
                        new_pt = (1.0 - alpha) * p_i + alpha * p_j
                        synthetic_list.append(new_pt)
                        budget -= 1

        if len(synthetic_list) == 0:
            # Fallback to NN if statistical produced nothing
            return self._densify_nearest_neighbor(pcd, n_new)

        synthetic = np.array(synthetic_list, dtype=np.float32)

        # Post-filter: remove points too close to existing
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

        # Build KDTree on original positions for NN search
        orig_pts = original_pcd.point.positions.numpy()  # (n_orig, 3)
        synth_pts = result_pcd.point.positions.numpy()[n_original:]  # (n_synthetic, 3)

        try:
            from scipy.spatial import KDTree

            kd_orig = KDTree(orig_pts.astype(np.float64))
            k = min(10, n_original)
            _, neighbor_idxs = kd_orig.query(synth_pts.astype(np.float64), k=k)
            if k == 1:
                neighbor_idxs = neighbor_idxs[:, np.newaxis]

            # Mean of neighbor normals, then normalise to unit length
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
    def _compute_mean_nn_dist(
        pcd_legacy: o3d.geometry.PointCloud,
        pts: np.ndarray,
        max_samples: int = 200,
    ) -> float:
        """
        Estimate mean nearest-neighbour distance using KDTreeFlann.

        Samples up to max_samples points to keep the operation O(S) rather than O(N).
        Returns a fallback of 0.01 if computation fails.
        """
        try:
            kd = o3d.geometry.KDTreeFlann(pcd_legacy)
            n = len(pts)
            sample_size = min(n, max_samples)
            sample_idx = np.random.choice(n, size=sample_size, replace=False)
            nn_dists: list[float] = []
            for i in sample_idx:
                _, _, dist2 = kd.search_knn_vector_3d(pts[i], 2)
                if len(dist2) >= 2:
                    nn_dists.append(math.sqrt(float(dist2[1])))
            if nn_dists:
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
