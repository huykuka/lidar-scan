"""
TDD Tests for Densify pipeline operation.

Written BEFORE full implementation (TDD Phase 0 gate).
Tests must be collectable (importable) once densify.py skeleton exists, even if they
fail until each algorithm is implemented.

Covers:
- Phase 1: Class construction & validation
- Phase 2: Fail-safe behaviour (F5)
- Phase 3: Nearest Neighbour algorithm (F1, US1)
- Phase 4: Statistical Upsampling algorithm (F1)
- Phase 5: MLS algorithm (F1)
- Phase 6: Poisson Reconstruction algorithm (F1)
- Phase 7: Quality preset system (F3)
- Phase 8: Density target modes (F2)
- Phase 9: Normal estimation (F4)
- Phase 10: Metadata schema (F7)
- Phase 11: Integration tests (DAG pipeline)
- Phase 12: Stress / robustness tests (marked @pytest.mark.slow)

References: qa-tasks.md, technical.md §3–8, api-spec.md §1–4
"""
from __future__ import annotations

import time
from typing import Optional
from unittest.mock import patch

import numpy as np
import open3d as o3d
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_pcd(n: int, seed: int = 42) -> o3d.geometry.PointCloud:
    """Create a legacy PointCloud with n random points in [0,1]^3."""
    rng = np.random.default_rng(seed)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(rng.random((n, 3)).astype(np.float64))
    return pcd


def make_tensor_pcd(
    pts: Optional[np.ndarray] = None, n: int = 1000
) -> o3d.t.geometry.PointCloud:
    """Create a tensor PointCloud. If pts is None, generate n random points."""
    if pts is None:
        pts = np.random.default_rng(0).random((n, 3)).astype(np.float32)
    pcd = o3d.t.geometry.PointCloud()
    pcd.point.positions = o3d.core.Tensor(pts.astype(np.float32))
    return pcd


def make_pcd_with_normals(n: int, seed: int = 99) -> o3d.geometry.PointCloud:
    """Create a legacy PointCloud on unit-sphere surface with estimated normals."""
    rng = np.random.default_rng(seed)
    pts = rng.standard_normal((n, 3))
    pts /= np.linalg.norm(pts, axis=1, keepdims=True)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(knn=10))
    return pcd


def get_count(pcd) -> int:
    """Return point count for either legacy or tensor PointCloud."""
    if isinstance(pcd, o3d.t.geometry.PointCloud):
        return (
            int(pcd.point.positions.shape[0]) if "positions" in pcd.point else 0
        )
    return len(pcd.points)


def get_positions(pcd) -> np.ndarray:
    """Extract positions as (N,3) numpy array from either pcd type."""
    if isinstance(pcd, o3d.t.geometry.PointCloud):
        return pcd.point.positions.numpy()
    return np.asarray(pcd.points)


# ─────────────────────────────────────────────────────────────────────────────
# Lazy import helper – fails loudly until densify.py skeleton exists
# ─────────────────────────────────────────────────────────────────────────────


def _import_densify():
    from app.modules.pipeline.operations.densify import Densify

    return Densify


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: Class Construction & Validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassConstruction:
    """Phase 1 – __init__ defaults, attribute storage, and validation guards."""

    # 1.1 Default configuration ---------------------------------------------------

    def test_densify_default_init(self):
        """Densify() with no args uses spec defaults."""
        Densify = _import_densify()
        op = Densify()
        assert op.density_multiplier == 2.0
        assert op.preserve_normals is True
        assert op.enabled is True

    def test_densify_default_algorithm_is_none_or_nearest_neighbor(self):
        """Default algorithm is either None (use-preset) or 'nearest_neighbor'."""
        Densify = _import_densify()
        op = Densify()
        assert op.algorithm in (None, "nearest_neighbor")

    def test_densify_default_quality_preset(self):
        """Default quality_preset is 'fast'."""
        Densify = _import_densify()
        op = Densify()
        assert op.quality_preset == "fast"

    def test_densify_custom_config_stored(self):
        """Custom constructor args are stored as attributes."""
        Densify = _import_densify()
        op = Densify(
            algorithm="mls",
            density_multiplier=4.0,
            quality_preset="high",
            preserve_normals=False,
            enabled=False,
            target_layer_count=32,
        )
        assert op.algorithm == "mls"
        assert op.density_multiplier == 4.0
        assert op.quality_preset == "high"
        assert op.preserve_normals is False
        assert op.enabled is False
        assert op.target_layer_count == 32

    # 1.2 Invalid configuration ---------------------------------------------------

    def test_densify_invalid_algorithm(self):
        """Unknown algorithm name raises ValueError."""
        Densify = _import_densify()
        with pytest.raises(ValueError, match="algorithm"):
            Densify(algorithm="bilinear")

    def test_densify_invalid_multiplier_too_high(self):
        """density_multiplier > 8.0 raises ValueError."""
        Densify = _import_densify()
        with pytest.raises(ValueError, match="density_multiplier"):
            Densify(density_multiplier=9.0)

    def test_densify_invalid_multiplier_too_low(self):
        """density_multiplier < 1.0 raises ValueError."""
        Densify = _import_densify()
        with pytest.raises(ValueError, match="density_multiplier"):
            Densify(density_multiplier=0.5)

    def test_densify_invalid_preset(self):
        """Unknown quality_preset raises ValueError."""
        Densify = _import_densify()
        with pytest.raises(ValueError, match="quality_preset"):
            Densify(quality_preset="ultra")

    def test_densify_boundary_multiplier_exactly_1(self):
        """density_multiplier=1.0 is the minimum valid value (no error)."""
        Densify = _import_densify()
        op = Densify(density_multiplier=1.0)
        assert op.density_multiplier == 1.0

    def test_densify_boundary_multiplier_exactly_8(self):
        """density_multiplier=8.0 is the maximum valid value (no error)."""
        Densify = _import_densify()
        op = Densify(density_multiplier=8.0)
        assert op.density_multiplier == 8.0

    # 1.3 Factory registration ----------------------------------------------------

    def test_densify_factory_default(self):
        """OperationFactory.create('densify', {}) returns a Densify instance."""
        from app.modules.pipeline.factory import OperationFactory

        Densify = _import_densify()
        op = OperationFactory.create("densify", {})
        assert isinstance(op, Densify)

    def test_densify_factory_with_config(self):
        """Factory correctly passes config kwargs to Densify.__init__."""
        from app.modules.pipeline.factory import OperationFactory

        Densify = _import_densify()
        op = OperationFactory.create(
            "densify", {"algorithm": "poisson", "density_multiplier": 4.0}
        )
        assert isinstance(op, Densify)
        assert op.algorithm == "poisson"
        assert op.density_multiplier == 4.0

    def test_densify_factory_unknown_type(self):
        """Creating an unknown operation type raises ValueError."""
        from app.modules.pipeline.factory import OperationFactory

        with pytest.raises(ValueError, match="densify_v2"):
            OperationFactory.create("densify_v2", {})


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: Fail-Safe Behaviour
# ═══════════════════════════════════════════════════════════════════════════════


class TestFailSafe:
    """Phase 2 – Graceful handling of edge inputs and error conditions."""

    # 2.1 Insufficient points -----------------------------------------------------

    def test_densify_skip_insufficient_points_legacy(self):
        """Legacy pcd with < 10 points → status=skipped, original_count preserved."""
        Densify = _import_densify()
        pcd = make_pcd(5)
        op = Densify()
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "skipped"
        assert meta["original_count"] == 5
        assert meta["densified_count"] == 5
        assert meta.get("skip_reason") is not None

    def test_densify_skip_insufficient_points_tensor(self):
        """Tensor pcd with < 10 points → status=skipped."""
        Densify = _import_densify()
        pcd = make_tensor_pcd(n=5)
        op = Densify()
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "skipped"
        assert meta["original_count"] == 5

    def test_densify_skip_zero_points(self):
        """Empty (0-point) pcd → status=skipped, no crash."""
        Densify = _import_densify()
        pcd = make_pcd(0)
        op = Densify()
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "skipped"
        assert meta["original_count"] == 0

    # 2.2 Already dense input -----------------------------------------------------

    def test_densify_skip_already_dense(self):
        """multiplier=1.0 means target == original → status=skipped."""
        Densify = _import_densify()
        pcd = make_pcd(10000)
        op = Densify(density_multiplier=1.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "skipped"

    # 2.3 Disabled operation ------------------------------------------------------

    def test_densify_disabled(self):
        """enabled=False → status=skipped, original cloud returned unchanged."""
        Densify = _import_densify()
        op = Densify(enabled=False)
        pcd = make_pcd(1000)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "skipped"
        assert meta["densified_count"] == 1000
        assert "disabled" in meta["skip_reason"].lower()

    # 2.4 No exception propagation ------------------------------------------------

    def test_densify_no_exception_on_corrupt_input(self):
        """Passing a dict as pcd must NOT raise; must return (something, metadata)."""
        Densify = _import_densify()
        op = Densify()
        result = op.apply({"bad": "input"})
        assert isinstance(result, tuple) and len(result) == 2
        _, meta = result
        assert meta["status"] in ("error", "skipped")

    def test_densify_no_exception_on_none(self):
        """op.apply(None) must not raise; must return (something, metadata) tuple."""
        Densify = _import_densify()
        op = Densify()
        result = op.apply(None)
        assert isinstance(result, tuple) and len(result) == 2

    # 2.5 Error recovery ----------------------------------------------------------

    def test_densify_error_returns_original(self):
        """When _run_algorithm raises, result is original pcd and status=error."""
        Densify = _import_densify()
        pcd = make_pcd(1000)
        op = Densify()

        with patch.object(op, "_run_algorithm", side_effect=RuntimeError("simulated failure")):
            result_pcd, meta = op.apply(pcd)

        assert meta["status"] == "error"
        assert meta["error_message"] is not None
        assert "simulated failure" in meta["error_message"]
        assert meta["densified_count"] == 1000
        # Returned pcd is not None
        assert result_pcd is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3: Nearest Neighbour Algorithm
# ═══════════════════════════════════════════════════════════════════════════════


class TestNearestNeighbour:
    """Phase 3 – _densify_nearest_neighbor correctness and performance."""

    def test_nn_increases_point_count_legacy(self):
        """NN on legacy pcd with 2x multiplier: result count in [1500, 2500]."""
        Densify = _import_densify()
        pcd = make_pcd(1000)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["densified_count"] >= 1500
        assert meta["densified_count"] <= 2500
        assert meta["original_count"] == 1000

    def test_nn_increases_point_count_tensor(self):
        """NN on tensor pcd with 2x multiplier: result count in [1500, 2500]."""
        Densify = _import_densify()
        pcd = make_tensor_pcd(n=1000)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["densified_count"] >= 1500
        assert meta["densified_count"] <= 2500

    def test_nn_preserves_original_positions(self):
        """Original points must all appear in the result (NN only adds, never removes)."""
        Densify = _import_densify()
        pcd_legacy = make_pcd(200)
        original_pts = np.asarray(pcd_legacy.points)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd_legacy)
        assert meta["status"] == "success"

        result_pts = get_positions(result_pcd)
        for pt in original_pts:
            dists = np.linalg.norm(result_pts - pt, axis=1)
            assert np.any(dists < 1e-4), f"Original point {pt} not found in result"

    def test_nn_metadata_fields_complete(self):
        """All 7 required metadata keys must be present on success."""
        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        pcd = make_pcd(500)
        _, meta = op.apply(pcd)
        required = {
            "status", "original_count", "densified_count",
            "density_ratio", "algorithm_used", "processing_time_ms",
            "skip_reason",
        }
        assert required.issubset(set(meta.keys())), (
            f"Missing metadata keys: {required - set(meta.keys())}"
        )

    def test_nn_density_ratio_correct(self):
        """density_ratio == densified_count / original_count (exact float div)."""
        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        _, meta = op.apply(make_pcd(500))
        expected = meta["densified_count"] / meta["original_count"]
        assert abs(meta["density_ratio"] - expected) < 1e-6

    def test_nn_processing_time_recorded(self):
        """processing_time_ms must be a positive float."""
        Densify = _import_densify()
        _, meta = op = (None, None)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        _, meta = op.apply(make_pcd(500))
        assert isinstance(meta["processing_time_ms"], float)
        assert meta["processing_time_ms"] > 0.0

    def test_nn_result_is_tensor_pcd(self):
        """NN algorithm always returns o3d.t.geometry.PointCloud."""
        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        result_pcd, _ = op.apply(make_pcd(500))
        assert isinstance(result_pcd, o3d.t.geometry.PointCloud)

    @pytest.mark.slow
    def test_nn_performance_fast_mode(self):
        """NN on 100k points must complete in < 100ms (fast-mode SLA)."""
        Densify = _import_densify()
        pcd = make_pcd(100_000)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        _, meta = op.apply(pcd)
        assert meta["processing_time_ms"] < 100.0, (
            f"Too slow: {meta['processing_time_ms']:.1f}ms (SLA: 100ms)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4: Statistical Upsampling Algorithm
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatisticalUpsampling:
    """Phase 4 – _densify_statistical correctness."""

    def test_statistical_increases_point_count(self):
        """Statistical 2× on 1000 pts: result count in [1500, 2500]."""
        Densify = _import_densify()
        pcd = make_pcd(1000)
        op = Densify(algorithm="statistical", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["densified_count"] >= 1500
        assert meta["densified_count"] <= 2500

    def test_statistical_metadata_correct(self):
        """Statistical: status=success, all required keys present."""
        Densify = _import_densify()
        pcd = make_pcd(1000)
        op = Densify(algorithm="statistical", density_multiplier=2.0)
        _, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["algorithm_used"] == "statistical"
        required = {
            "status", "original_count", "densified_count",
            "density_ratio", "algorithm_used", "processing_time_ms",
        }
        assert required.issubset(set(meta.keys()))

    def test_statistical_no_duplicate_stacking(self):
        """Statistical result must not have points within 1e-5 of each other."""
        from scipy.spatial import KDTree

        Densify = _import_densify()
        pcd = make_pcd(500)
        op = Densify(algorithm="statistical", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"

        result_pts = get_positions(result_pcd)
        kd = KDTree(result_pts)
        pairs = kd.query_pairs(r=1e-5)
        assert len(pairs) == 0, f"{len(pairs)} near-duplicate points found"

    @pytest.mark.slow
    def test_statistical_performance_medium_mode(self):
        """Statistical on 100k points must complete in < 300ms."""
        Densify = _import_densify()
        pcd = make_pcd(100_000)
        op = Densify(algorithm="statistical", density_multiplier=2.0)
        _, meta = op.apply(pcd)
        assert meta["processing_time_ms"] < 300.0, (
            f"Too slow: {meta['processing_time_ms']:.1f}ms (SLA: 300ms)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5: MLS Algorithm
# ═══════════════════════════════════════════════════════════════════════════════


class TestMLS:
    """Phase 5 – _densify_mls correctness and tangent-plane accuracy."""

    def test_mls_increases_point_count(self):
        """MLS 2× on 1000 pts: result count in [1500, 2500]."""
        Densify = _import_densify()
        pcd = make_pcd(1000)
        op = Densify(algorithm="mls", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["densified_count"] >= 1500
        assert meta["densified_count"] <= 2500

    def test_mls_metadata_correct(self):
        """MLS: status=success, algorithm_used='mls', all keys present."""
        Densify = _import_densify()
        pcd = make_pcd(1000)
        op = Densify(algorithm="mls", density_multiplier=2.0)
        _, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["algorithm_used"] == "mls"
        required = {
            "status", "original_count", "densified_count",
            "density_ratio", "algorithm_used", "processing_time_ms",
        }
        assert required.issubset(set(meta.keys()))

    def test_mls_result_is_tensor_pcd(self):
        """MLS always returns o3d.t.geometry.PointCloud regardless of input type."""
        Densify = _import_densify()
        op = Densify(algorithm="mls", density_multiplier=2.0)
        result_pcd, _ = op.apply(make_pcd(500))
        assert isinstance(result_pcd, o3d.t.geometry.PointCloud)

    def test_mls_tangent_plane_accuracy(self):
        """MLS on z=0 plane: synthetic points must stay near z=0 (±0.1 tol)."""
        Densify = _import_densify()
        rng = np.random.default_rng(0)
        pts = np.column_stack(
            [rng.random((500, 2)) * 10.0, np.zeros(500)]
        ).astype(np.float32)
        pcd = make_tensor_pcd(pts)
        op = Densify(algorithm="mls", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        result_pts = get_positions(result_pcd)
        max_z_dev = float(np.abs(result_pts[:, 2]).max())
        assert max_z_dev < 0.1, (
            f"MLS points deviated too far from source plane: max |z|={max_z_dev:.4f}"
        )

    @pytest.mark.slow
    def test_mls_performance_medium_mode(self):
        """MLS on 10k points must complete in < 500ms (CI-friendly subset)."""
        Densify = _import_densify()
        pcd = make_pcd(10_000)
        op = Densify(algorithm="mls", density_multiplier=2.0)
        _, meta = op.apply(pcd)
        assert meta["processing_time_ms"] < 500.0, (
            f"Too slow: {meta['processing_time_ms']:.1f}ms (SLA: 500ms)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6: Poisson Reconstruction Algorithm
# ═══════════════════════════════════════════════════════════════════════════════


class TestPoisson:
    """Phase 6 – _densify_poisson correctness and hybrid-preserve property."""

    def test_poisson_increases_point_count(self):
        """Poisson 2× on 500 sphere-surface pts: count in expected range."""
        Densify = _import_densify()
        pcd = make_pcd_with_normals(500)  # normals needed by Poisson
        op = Densify(algorithm="poisson", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        # Poisson is hybrid (preserve + augment) so count > original
        assert meta["densified_count"] > meta["original_count"]

    def test_poisson_metadata_correct(self):
        """Poisson: status=success, algorithm_used='poisson'."""
        Densify = _import_densify()
        pcd = make_pcd_with_normals(500)
        op = Densify(algorithm="poisson", density_multiplier=2.0)
        _, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["algorithm_used"] == "poisson"

    def test_poisson_preserves_originals(self):
        """Poisson hybrid: first N positions in result match original positions."""
        Densify = _import_densify()
        n_orig = 300
        pcd = make_pcd_with_normals(n_orig)
        original_pts = np.asarray(pcd.points)
        op = Densify(algorithm="poisson", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"

        result_pts = get_positions(result_pcd)
        # Check first n_orig rows match originals
        first_n = result_pts[:n_orig]
        np.testing.assert_allclose(first_n, original_pts.astype(np.float32), atol=1e-3)

    @pytest.mark.slow
    def test_poisson_performance_high_mode(self):
        """Poisson on 5k sphere-surface pts must complete in < 2000ms."""
        Densify = _import_densify()
        pcd = make_pcd_with_normals(5000)
        op = Densify(algorithm="poisson", density_multiplier=2.0)
        _, meta = op.apply(pcd)
        assert meta["processing_time_ms"] < 2000.0, (
            f"Too slow: {meta['processing_time_ms']:.1f}ms (SLA: 2000ms)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7: Quality Preset System
# ═══════════════════════════════════════════════════════════════════════════════


class TestQualityPresets:
    """Phase 7 – Preset → algorithm resolution."""

    def test_preset_fast_uses_nn(self):
        """quality_preset='fast', no explicit algorithm → nearest_neighbor."""
        Densify = _import_densify()
        op = Densify(quality_preset="fast")
        pcd = make_pcd(500)
        _, meta = op.apply(pcd)
        assert meta["algorithm_used"] == "nearest_neighbor"

    def test_preset_medium_uses_statistical(self):
        """quality_preset='medium', no explicit algorithm → statistical."""
        Densify = _import_densify()
        op = Densify(quality_preset="medium")
        pcd = make_pcd(500)
        _, meta = op.apply(pcd)
        assert meta["algorithm_used"] == "statistical"

    def test_preset_high_uses_mls(self):
        """quality_preset='high', no explicit algorithm → mls."""
        Densify = _import_densify()
        op = Densify(quality_preset="high")
        pcd = make_pcd(500)
        _, meta = op.apply(pcd)
        assert meta["algorithm_used"] == "mls"

    def test_explicit_algorithm_overrides_preset(self):
        """Explicit algorithm='poisson' beats quality_preset='fast'."""
        Densify = _import_densify()
        op = Densify(algorithm="poisson", quality_preset="fast")
        pcd = make_pcd_with_normals(300)
        _, meta = op.apply(pcd)
        assert meta["algorithm_used"] == "poisson"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 8: Density Target Modes
# ═══════════════════════════════════════════════════════════════════════════════


class TestDensityTargets:
    """Phase 8 – multiplier, target_layer_count, and clamping."""

    def test_multiplier_2x(self):
        """1000 pts × 2.0 → result ~2000 pts (±20% tolerance for stochastic algs)."""
        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        _, meta = op.apply(make_pcd(1000))
        assert meta["densified_count"] >= 1600
        assert meta["densified_count"] <= 2400

    def test_multiplier_4x(self):
        """500 pts × 4.0 → result ~2000 pts (±20%)."""
        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=4.0)
        _, meta = op.apply(make_pcd(500))
        assert meta["densified_count"] >= 1600
        assert meta["densified_count"] <= 2400

    def test_multiplier_8x_max(self):
        """1000 pts × 8.0 → result ~8000 pts (±20%)."""
        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=8.0)
        _, meta = op.apply(make_pcd(1000))
        assert meta["densified_count"] >= 6400
        assert meta["densified_count"] <= 9600

    def test_target_layer_count_overrides_multiplier(self):
        """target_layer_count takes precedence over density_multiplier."""
        Densify = _import_densify()
        # target_layer_count=32 with 1024 pts → sqrt(1024)=32 layers → mult≈1.0 → skipped or minimal
        op = Densify(target_layer_count=32, density_multiplier=10.0)
        pcd = make_pcd(1000)
        result_pcd, meta = op.apply(pcd)
        # status should be either success or skipped — key is no exception and correct code path
        assert meta["status"] in ("success", "skipped")

    def test_multiplier_clamped_at_8x(self):
        """target_layer_count that would imply >8× is clamped to 8×."""
        Densify = _import_densify()
        op = Densify(target_layer_count=10000)
        pcd = make_pcd(100)
        result_pcd, meta = op.apply(pcd)
        # At most 8x + small tolerance for post-filter
        assert meta["densified_count"] <= 100 * 8 + 20


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 9: Normal Estimation
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormals:
    """Phase 9 – normal preservation and estimation for synthetic points."""

    def test_normals_preserved_for_original_points(self):
        """When input has normals and preserve_normals=True → result has 'normals'."""
        Densify = _import_densify()
        pcd = make_pcd_with_normals(500)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0, preserve_normals=True)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert "normals" in result_pcd.point, "Result must have 'normals' attribute"

    def test_normals_estimated_for_synthetic_points(self):
        """Synthetic points (indices n_orig..end) must have non-zero unit normals."""
        Densify = _import_densify()
        n_original = 500
        pcd = make_pcd_with_normals(n_original)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0, preserve_normals=True)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert "normals" in result_pcd.point

        result_norms = result_pcd.point["normals"].numpy()
        synthetic_norms = result_norms[n_original:]
        if len(synthetic_norms) > 0:
            norms_mag = np.linalg.norm(synthetic_norms, axis=1)
            assert np.all(norms_mag > 0.9), (
                f"Synthetic normals must be ≈unit-length; "
                f"min magnitude = {norms_mag.min():.4f}"
            )

    def test_normals_skipped_when_input_has_none(self):
        """preserve_normals=True but input has no normals → no crash, still success."""
        Densify = _import_densify()
        pcd = make_pcd(500)  # no normals
        op = Densify(algorithm="nearest_neighbor", preserve_normals=True)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        # Must not crash; normals silently skipped

    def test_normals_disabled(self):
        """preserve_normals=False → normals attribute NOT added to result."""
        Densify = _import_densify()
        pcd = make_pcd_with_normals(500)
        op = Densify(algorithm="nearest_neighbor", preserve_normals=False)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        # When preserve_normals=False, normals should not be in result
        assert "normals" not in result_pcd.point


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 10: Metadata Schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestMetadataSchema:
    """Phase 10 – metadata key completeness and correctness on all outcome paths."""

    _REQUIRED_KEYS = {
        "status", "original_count", "densified_count",
        "density_ratio", "algorithm_used", "processing_time_ms",
    }

    def test_metadata_all_keys_present_on_success(self):
        """All required metadata keys present when status=success."""
        Densify = _import_densify()
        _, meta = Densify(algorithm="nearest_neighbor").apply(make_pcd(500))
        assert self._REQUIRED_KEYS.issubset(set(meta.keys())), (
            f"Missing keys: {self._REQUIRED_KEYS - set(meta.keys())}"
        )

    def test_metadata_all_keys_present_on_skip(self):
        """All required metadata keys present when status=skipped; skip_reason set."""
        Densify = _import_densify()
        _, meta = Densify(enabled=False).apply(make_pcd(500))
        assert self._REQUIRED_KEYS.issubset(set(meta.keys()))
        assert meta.get("skip_reason") is not None

    def test_metadata_all_keys_present_on_error(self):
        """All required metadata keys present when status=error; error_message set."""
        Densify = _import_densify()
        op = Densify()
        with patch.object(op, "_run_algorithm", side_effect=RuntimeError("test error")):
            _, meta = op.apply(make_pcd(1000))
        assert self._REQUIRED_KEYS.issubset(set(meta.keys()))
        assert meta.get("error_message") is not None

    def test_metadata_density_ratio_calculation(self):
        """density_ratio == densified_count / original_count (exact)."""
        Densify = _import_densify()
        _, meta = Densify(algorithm="nearest_neighbor").apply(make_pcd(500))
        expected_ratio = meta["densified_count"] / meta["original_count"]
        assert abs(meta["density_ratio"] - expected_ratio) < 1e-6

    def test_metadata_algorithm_used_matches_config(self):
        """algorithm_used in metadata matches the configured algorithm."""
        Densify = _import_densify()
        _, meta = Densify(algorithm="mls").apply(make_pcd(500))
        assert meta["algorithm_used"] == "mls"

    def test_metadata_processing_time_always_positive(self):
        """processing_time_ms is a positive float on all outcome paths."""
        Densify = _import_densify()
        # success path
        _, meta_ok = Densify(algorithm="nearest_neighbor").apply(make_pcd(500))
        assert meta_ok["processing_time_ms"] > 0.0
        # skip path
        _, meta_skip = Densify(enabled=False).apply(make_pcd(500))
        assert meta_skip["processing_time_ms"] >= 0.0

    def test_metadata_error_message_none_on_success(self):
        """error_message is None on success path."""
        Densify = _import_densify()
        _, meta = Densify(algorithm="nearest_neighbor").apply(make_pcd(500))
        assert meta.get("error_message") is None

    def test_metadata_skip_reason_none_on_success(self):
        """skip_reason is None on success path."""
        Densify = _import_densify()
        _, meta = Densify(algorithm="nearest_neighbor").apply(make_pcd(500))
        assert meta.get("skip_reason") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 11: Integration Tests — DAG Pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class TestDAGIntegration:
    """Phase 11 – Integration with other pipeline operations and PointConverter."""

    def test_densify_accepts_tensor_pcd_from_upstream(self):
        """Simulate PointConverter.to_pcd() → Densify → PointConverter.to_points()."""
        from app.modules.pipeline.base import PointConverter

        Densify = _import_densify()
        rng = np.random.default_rng(7)
        points_in = rng.random((1000, 14)).astype(np.float32)
        pcd = PointConverter.to_pcd(points_in)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"

        points_out = PointConverter.to_points(result_pcd)
        assert points_out.shape[0] >= 1500
        assert points_out.shape[1] == 14  # structural columns preserved

    def test_densify_followed_by_downsample_consistency(self):
        """Densify → Downsample round-trip must not produce empty cloud."""
        from app.modules.pipeline.operations.downsample import Downsample

        Densify = _import_densify()
        pcd = make_pcd(1000)
        densify_op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        downsample_op = Downsample(voxel_size=0.05)
        dense_pcd, _ = densify_op.apply(pcd)
        sampled_pcd, _ = downsample_op.apply(dense_pcd)
        count = get_count(sampled_pcd)
        assert count > 0

    def test_densify_in_pipeline_chain(self):
        """Crop → Densify → StatisticalOutlierRemoval chain returns non-empty cloud."""
        from app.modules.pipeline.operations.crop import Crop
        from app.modules.pipeline.operations.outliers import StatisticalOutlierRemoval

        Densify = _import_densify()
        pcd = make_pcd(5000)
        crop_op = Crop(min_bound=[-5, -5, -5], max_bound=[5, 5, 5])
        densify_op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
        outlier_op = StatisticalOutlierRemoval()
        pcd, _ = crop_op.apply(pcd)
        pcd, _ = densify_op.apply(pcd)
        pcd, _ = outlier_op.apply(pcd)
        assert get_count(pcd) > 0

    def test_densify_registry_node_definition(self):
        """NodeDefinition for 'densify' must be registered in node_schema_registry."""
        from app.services.nodes.schema import node_schema_registry

        # Force registry load
        import app.modules.pipeline.registry  # noqa: F401

        # Use the public get_all() API (internal attr is _definitions, not _registry)
        schema_types = [nd.type for nd in node_schema_registry.get_all()]
        assert "densify" in schema_types, (
            "NodeDefinition for 'densify' not found in node_schema_registry"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 12: Stress / Robustness Tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
def test_stress_1000_frames_no_crash():
    """1000 frames of random-size point clouds must never raise an exception."""
    Densify = _import_densify()
    rng = np.random.default_rng(42)
    op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
    for i in range(1000):
        n = int(rng.integers(10, 5000))
        pcd = make_pcd(n, seed=i)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] in ("success", "skipped"), (
            f"Frame {i} (n={n}): unexpected status={meta['status']}"
        )


@pytest.mark.slow
def test_memory_not_growing():
    """100 frames of 10k pts must stay under 200MB peak (tracemalloc)."""
    import tracemalloc

    Densify = _import_densify()
    op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
    tracemalloc.start()
    for _ in range(100):
        pcd = make_pcd(10000)
        op.apply(pcd)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 200 * 1024 * 1024, (
        f"Peak memory too high: {peak / 1024 / 1024:.1f} MB (limit: 200 MB)"
    )
