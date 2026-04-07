"""
Densify — Pipeline Operation (Dispatcher)
==========================================

This module is the main entry point for the densify pipeline operation.
It dispatches to the appropriate algorithm class based on configuration:

  nearest_neighbor → NearestNeighborDensify
  mls              → MLSDensify
  poisson          → PoissonDensify
  statistical      → StatisticalDensify

The Densify class inherits from PipelineOperation and handles:
  - Input validation and normalisation (tensor/legacy PointCloud)
  - Enabled/disabled/insufficient-points skip logic
  - Algorithm resolution (explicit algorithm vs quality_preset)
  - Delegation to the correct algorithm subclass
  - Normal estimation for synthetic points
  - Metadata assembly (status, counts, timing)
  - Fail-safe error handling (never raises)

All algorithm implementations live in their own modules under the
``density/`` package and inherit from ``DensityAlgorithmBase``.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d

from ...base import PipelineOperation, _tensor_map_keys
from .density_base import (
    MIN_INPUT_POINTS,
    MAX_MULTIPLIER,
    PRESET_ALGORITHM_MAP,
    _VALID_ALGORITHMS,
    _VALID_PRESETS,
    _VALID_LOG_LEVELS,
    _ENV_LOG_LEVEL,
    DensityAlgorithmBase,
    DensifyAlgorithm,
    DensifyConfig,
    DensifyLogLevel,
    DensifyMetadata,
    DensifyMLSParams,
    DensifyNNParams,
    DensifyPoissonParams,
    DensifyQualityPreset,
    DensifyStatisticalParams,
    DensifyStatus,
)
from .nearest_neighbor import NearestNeighborDensify
from .mls import MLSDensify
from .poisson import PoissonDensify
from .statistical import StatisticalDensify

# ─────────────────────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Main dispatcher class
# ─────────────────────────────────────────────────────────────────────────────


class Densify(PipelineOperation):
    """
    Point cloud densification operation — volumetric, sensor-agnostic.

    Dispatches to the appropriate algorithm class (NearestNeighborDensify,
    MLSDensify, PoissonDensify, StatisticalDensify) based on configuration.

    Args:
        enabled:              Enable/disable toggle (default True).
        algorithm:            Algorithm key string, or None to use quality_preset.
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

        Dispatches to the appropriate algorithm class. Uses global neighbour
        searches (full-cloud KDTree) — no scanline or ring-based processing.

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
        """Resolve effective log level: explicit kwarg > env var > 'minimal'."""
        if explicit is not None:
            return explicit
        env_val = os.environ.get(_ENV_LOG_LEVEL, "").strip().lower()
        if env_val in _VALID_LOG_LEVELS:
            return env_val
        return "minimal"

    @staticmethod
    def _coerce_params(value: Optional[Any], model_cls: type) -> Optional[Any]:
        """Coerce a params value to the correct Pydantic model (None/dict/model)."""
        if value is None:
            return None
        if isinstance(value, dict):
            return model_cls(**value)
        return value

    def _validate_input(
        self, pcd: Any
    ) -> Tuple[o3d.t.geometry.PointCloud, int, Any]:
        """Normalise the input pcd to a tensor PointCloud."""
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
        """Return the algorithm string to execute."""
        if self.algorithm is not None:
            return self.algorithm
        return PRESET_ALGORITHM_MAP[self.quality_preset]

    def _compute_target_count(self, original_count: int) -> int:
        """Compute the target point count using density_multiplier."""
        effective_multiplier = min(max(self.density_multiplier, 1.0), MAX_MULTIPLIER)
        return int(original_count * effective_multiplier)

    def _run_algorithm(
        self,
        pcd: o3d.t.geometry.PointCloud,
        target_count: int,
        algorithm: str,
    ) -> o3d.t.geometry.PointCloud:
        """Dispatch to the appropriate algorithm class."""
        n_new = target_count - self._get_count(pcd)
        if n_new <= 0:
            return pcd

        # Build algorithm instance with its params and the current log_level
        algo_instance = self._build_algorithm(algorithm)
        return algo_instance.apply(pcd, n_new)

    def _build_algorithm(self, algorithm: str) -> DensityAlgorithmBase:
        """Instantiate the algorithm class for the given algorithm key."""
        if algorithm == "nearest_neighbor":
            return NearestNeighborDensify(
                params=self.nn_params, log_level=self.log_level
            )
        elif algorithm == "mls":
            return MLSDensify(
                params=self.mls_params, log_level=self.log_level
            )
        elif algorithm == "poisson":
            return PoissonDensify(
                params=self.poisson_params, log_level=self.log_level
            )
        elif algorithm == "statistical":
            return StatisticalDensify(
                params=self.statistical_params, log_level=self.log_level
            )
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

    # ── Normal estimation ─────────────────────────────────────────────────────

    def _estimate_normals(
        self,
        result_pcd: o3d.t.geometry.PointCloud,
        original_pcd: o3d.t.geometry.PointCloud,
        n_original: int,
    ) -> o3d.t.geometry.PointCloud:
        """Estimate normals for synthetic points (indices n_original onward)."""
        orig_keys = _tensor_map_keys(original_pcd.point)
        if "normals" not in orig_keys:
            if self.log_level == "full":
                logger.info(
                    "Densify: Input cloud has no normals — skipping normal estimation"
                )
            return result_pcd

        orig_normals = original_pcd.point["normals"].numpy()
        result_count = self._get_count(result_pcd)
        n_synthetic = result_count - n_original
        if n_synthetic <= 0:
            return result_pcd

        orig_pts = original_pcd.point.positions.numpy()
        synth_pts = result_pcd.point.positions.numpy()[n_original:]

        try:
            from scipy.spatial import KDTree

            kd_orig = KDTree(orig_pts.astype(np.float64))
            k = min(10, n_original)
            _, neighbor_idxs = kd_orig.query(synth_pts.astype(np.float64), k=k)
            if k == 1:
                neighbor_idxs = neighbor_idxs[:, np.newaxis]

            synth_normals = orig_normals[neighbor_idxs].mean(axis=1)
            norms_len = np.linalg.norm(synth_normals, axis=1, keepdims=True)
            norms_len = np.where(norms_len < 1e-8, 1.0, norms_len)
            synth_normals /= norms_len

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
    def _compute_mean_nn_dist_global(pts: np.ndarray) -> float:
        """Delegate to DensityAlgorithmBase for backward compatibility."""
        return DensityAlgorithmBase._compute_mean_nn_dist_global(pts)

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
