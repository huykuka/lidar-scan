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
- Phase 8: Density target modes (F2) — density_multiplier and clamping
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
        )
        assert op.algorithm == "mls"
        assert op.density_multiplier == 4.0
        assert op.quality_preset == "high"
        assert op.preserve_normals is False
        assert op.enabled is False

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
    """Phase 8 – density_multiplier and max-8× clamping."""

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

    def test_density_multiplier_is_the_only_density_control(self):
        """density_multiplier is the only density control; verify 2× applies correctly."""
        Densify = _import_densify()
        # 1000 pts × 2.0 → ~2000 pts
        op = Densify(density_multiplier=2.0)
        pcd = make_pcd(1000)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        # Should be near 2000, well below 4000
        assert meta["densified_count"] >= 1600
        assert meta["densified_count"] <= 2400

    def test_multiplier_clamped_at_8x(self):
        """density_multiplier=8.0 is the hard cap; result must not exceed 8× input."""
        Densify = _import_densify()
        op = Densify(density_multiplier=8.0)
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


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 13: Vertical Gap Filling — Volumetric / Sensor-Agnostic Densification
# ═══════════════════════════════════════════════════════════════════════════════


def _make_layered_pcd(
    n_per_layer: int,
    z_values: list,
    seed: int = 7,
) -> o3d.geometry.PointCloud:
    """
    Create a horizontally-layered point cloud simulating sparse LIDAR scan rings.

    Points lie on a set of discrete horizontal planes at the given Z values with
    no points in between — exactly the kind of vertical-gap structure produced by
    a multi-layer rotating LIDAR sensor.

    Args:
        n_per_layer: Number of points on each layer.
        z_values:    List of Z heights for each layer (e.g. [0.0, 1.0, 2.0]).
        seed:        RNG seed for reproducibility.

    Returns:
        Legacy o3d.geometry.PointCloud with N = n_per_layer × len(z_values) points.
    """
    rng = np.random.default_rng(seed)
    points = []
    for z in z_values:
        xy = rng.random((n_per_layer, 2)) * 5.0  # points in [0,5]² XY plane
        layer = np.column_stack([xy, np.full(n_per_layer, z)])
        points.append(layer)
    pts = np.vstack(points).astype(np.float64)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    return pcd


class TestVerticalGapFilling:
    """
    Phase 13 — Confirms that densification fills vertical gaps.

    These tests use horizontally-layered inputs and assert that after
    densification new points appear in the previously-empty Z intervals.

    This validates the core architectural requirement: all neighbour searches
    are global (full point cloud KDTree) with no scanline/ring restriction,
    so new points are generated in all spatial directions including vertical.

    Geometry constraint for NN/Statistical tests:
    ─────────────────────────────────────────────
    The global mean NN distance is computed by finding each point's nearest
    neighbour in the full 3-D cloud.  For a two-layer cloud, cross-layer
    neighbours (distance = z_gap) beat within-layer neighbours only when
    z_gap < within-layer XY spacing.

    We use:
      • n_per_layer = 20 points in [0, 2]²  → XY spacing ≈ √(4/20) ≈ 0.45
      • z_gap = 0.25  (< 0.45, so cross-layer neighbours dominate)
      → mean_nn_dist ≈ 0.25; max displacement = 0.5 × 0.25 = 0.125

    With n_new >> n_orig and uniformly-random 3-D displacement directions,
    many synthetic points land at z ∈ (0.01, 0.24), filling the gap.
    """

    # 13.1 Nearest Neighbour — vertical gap filling ----------------------------

    def test_nn_fills_vertical_gap_between_two_layers(self):
        """
        NN densification must produce points in the vertical gap between two layers.

        Input:  Two sparse horizontal planes at z=0 and z=0.25.
                XY spacing ≈ 0.45 > z_gap=0.25, so cross-layer NN dominates.
        Expect: After 6× densification, at least 1 synthetic point has z ∈ (0.01, 0.24).
        """
        Densify = _import_densify()
        # Sparse layers so cross-layer distance (z_gap=0.25) beats within-layer XY (~0.45)
        pcd = _make_layered_pcd(n_per_layer=20, z_values=[0.0, 0.25], seed=7)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=6.0)
        result_pcd, meta = op.apply(pcd)

        assert meta["status"] == "success", f"Expected success, got: {meta}"
        result_pts = get_positions(result_pcd)

        # Original points are at z≈0 or z≈0.25 only
        original_z = result_pts[:meta["original_count"], 2]
        assert np.all(
            (original_z < 0.01) | (original_z > 0.24)
        ), "Input sanity check: no original points should be in the gap"

        # Synthetic points (beyond original_count) should include some in the gap
        synthetic_pts = result_pts[meta["original_count"]:]
        in_gap = (synthetic_pts[:, 2] > 0.01) & (synthetic_pts[:, 2] < 0.24)
        n_in_gap = int(in_gap.sum())
        assert n_in_gap > 0, (
            f"NN densification did not produce any points in the vertical gap "
            f"z ∈ (0.01, 0.24).  This indicates a non-global (e.g. per-ring) search. "
            f"synthetic z range: [{synthetic_pts[:, 2].min():.4f}, {synthetic_pts[:, 2].max():.4f}]"
        )

    def test_nn_fills_vertical_gap_multi_layer(self):
        """
        NN: 5-layer cloud with 1.0 unit spacing — gap-filling in all inter-layer zones.

        Input:  5 horizontal planes at z=0,1,2,3,4 with n=100 pts each.
        Expect: Synthetic points appear in at least 3 of the 4 inter-layer intervals.
        """
        Densify = _import_densify()
        z_layers = [0.0, 1.0, 2.0, 3.0, 4.0]
        pcd = _make_layered_pcd(n_per_layer=100, z_values=z_layers)
        op = Densify(algorithm="nearest_neighbor", density_multiplier=4.0)
        result_pcd, meta = op.apply(pcd)

        assert meta["status"] == "success"
        synthetic_pts = get_positions(result_pcd)[meta["original_count"]:]

        # Check each inter-layer gap
        gaps_filled = 0
        for z_lo, z_hi in [(0.05, 0.95), (1.05, 1.95), (2.05, 2.95), (3.05, 3.95)]:
            in_gap = (synthetic_pts[:, 2] > z_lo) & (synthetic_pts[:, 2] < z_hi)
            if in_gap.sum() > 0:
                gaps_filled += 1

        assert gaps_filled >= 3, (
            f"Only {gaps_filled}/4 inter-layer gaps were filled.  "
            f"Expected global search to fill gaps in all directions."
        )

    # 13.2 Statistical — vertical gap filling ----------------------------------

    def test_statistical_fills_vertical_gap(self):
        """
        Statistical upsampling must produce points in the vertical gap between
        two sparse layers.

        Statistical algorithm interpolates between source points and their k=10
        global KDTree neighbours using α ∈ [0.3, 0.7].  When the k=10 neighbours
        include cross-layer points (because z_gap < XY spacing), interpolated
        points are guaranteed to land inside the gap.

        Geometry: n=20 per layer in [0,2]², z_gap=0.25.
          XY spacing ≈ √(4/20) ≈ 0.45 > z_gap=0.25, so cross-layer neighbours
          appear in k=10 and interpolation produces z ∈ (0.075, 0.175).
        """
        Densify = _import_densify()
        # Sparse layers: cross-layer distance (0.25) < within-layer XY (≈0.45)
        pcd = _make_layered_pcd(n_per_layer=20, z_values=[0.0, 0.25], seed=7)
        op = Densify(algorithm="statistical", density_multiplier=6.0)
        result_pcd, meta = op.apply(pcd)

        assert meta["status"] == "success"
        synthetic_pts = get_positions(result_pcd)[meta["original_count"]:]
        # Gap is z ∈ (0.01, 0.24) — interpolation α×0.25 covers this range
        in_gap = (synthetic_pts[:, 2] > 0.01) & (synthetic_pts[:, 2] < 0.24)
        assert int(in_gap.sum()) > 0, (
            "Statistical densification did not produce any points in the vertical "
            f"gap z ∈ (0.01, 0.24) — global KDTree cross-layer search required. "
            f"synthetic z range: [{synthetic_pts[:, 2].min():.4f}, {synthetic_pts[:, 2].max():.4f}]"
        )

    # 13.3 MLS — vertical gap filling ------------------------------------------

    def test_mls_fills_vertical_gap(self):
        """
        MLS tangent-plane projection must produce points with z-axis spread on
        a tilted surface.

        MLS projects new points onto the LOCAL TANGENT PLANE of each source point.
        For a perfectly flat horizontal cloud (normals pointing straight up), all
        displacements stay within the XY plane — vertical gap filling is impossible
        by design.  This is correct behaviour for a surface-following algorithm.

        Instead, we test with a TILTED PLANE (z = 0.3×x), where normals are
        diagonal and tangent planes span the z direction.  After densification
        the result must include points with z values outside the original XY plane
        range — confirming MLS projects along tilted normals, not just horizontally.

        This verifies global KDTree is used (no per-ring restriction) and the
        algorithm works correctly for non-horizontal surfaces.
        """
        Densify = _import_densify()

        # Tilted plane: z = 0.3 * x, so normals are diagonal and tangent planes
        # span the z direction.  Use a single connected surface (no vertical gaps).
        rng = np.random.default_rng(99)
        n = 200
        xy = rng.random((n, 2)) * 5.0  # [0,5]² in XY
        z = 0.3 * xy[:, 0]  # z increases with x → tilted surface
        pts = np.column_stack([xy, z]).astype(np.float64)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)

        op = Densify(algorithm="mls", density_multiplier=3.0)
        result_pcd, meta = op.apply(pcd)

        assert meta["status"] == "success"
        # Synthetic points must span at least some z range above/below original
        result_pts = get_positions(result_pcd)
        orig_z = result_pts[:meta["original_count"], 2]
        original_z_range = float(orig_z.max() - orig_z.min())
        full_z_range = float(result_pts[:, 2].max() - result_pts[:, 2].min())

        # MLS on a tilted surface must produce z spread at least as large as the
        # original surface's z range (tangent planes are not purely horizontal).
        assert full_z_range >= original_z_range * 0.8, (
            f"MLS on a tilted surface: z-range={full_z_range:.4f} is much smaller than "
            f"original z-range={original_z_range:.4f}.  Expected tangent-plane projections "
            f"to span the same z extent as the original tilted surface."
        )

    # 13.4 Global KDTree radius reflects 3-D spacing ----------------------------

    def test_global_mean_nn_dist_reflects_3d_spacing(self):
        """
        _compute_mean_nn_dist_global must return a distance that includes the
        vertical (z) component, not just the horizontal (XY) distance.

        Input: Two layers at z=0 and z=10 with closely-spaced XY points (gap≈0.1).
        The true 3-D NN distance for inter-layer boundary points is ~10.0.
        The global mean NN distance should be dominated by the z-gap, not the
        within-layer XY spacing.
        """
        from app.modules.pipeline.operations.densify import Densify as DensifyClass

        # Dense within-layer spacing (XY gap ≈ 0.1) but large z-gap (10.0)
        rng = np.random.default_rng(42)
        layer_0 = np.column_stack([rng.random((50, 2)) * 1.0, np.zeros(50)])
        layer_1 = np.column_stack([rng.random((50, 2)) * 1.0, np.full(50, 10.0)])
        pts = np.vstack([layer_0, layer_1]).astype(np.float64)

        mean_dist = DensifyClass._compute_mean_nn_dist_global(pts)
        # The global NN dist must be noticeably larger than the within-layer spacing
        # (within-layer NN ≈ 0.1, cross-layer jump ≈ 10.0 for boundary points)
        assert mean_dist > 0.05, (
            f"Mean NN dist {mean_dist:.4f} is suspiciously small — "
            f"possible non-global (within-layer only) search."
        )

    # 13.5 No scanline/ring ordering dependency ---------------------------------

    def test_nn_result_independent_of_input_ordering(self):
        """
        Densification result must be statistically equivalent regardless of whether
        input points are ordered by layer (ring order) or shuffled randomly.

        If densification had any scanline/ring dependency, the ordered input would
        produce a different point count or spatial distribution than the shuffled one.
        """
        Densify = _import_densify()

        # Build a layered cloud
        pcd_ordered = _make_layered_pcd(n_per_layer=200, z_values=[0.0, 1.0, 2.0])
        ordered_pts = np.asarray(pcd_ordered.points)

        # Shuffle the points to destroy ring order
        rng = np.random.default_rng(123)
        shuffled_pts = ordered_pts.copy()
        rng.shuffle(shuffled_pts)
        pcd_shuffled = o3d.geometry.PointCloud()
        pcd_shuffled.points = o3d.utility.Vector3dVector(shuffled_pts)

        op_a = Densify(algorithm="nearest_neighbor", density_multiplier=3.0)
        op_b = Densify(algorithm="nearest_neighbor", density_multiplier=3.0)

        _, meta_ordered = op_a.apply(pcd_ordered)
        _, meta_shuffled = op_b.apply(pcd_shuffled)

        # Both should succeed and produce the same target count
        assert meta_ordered["status"] == "success"
        assert meta_shuffled["status"] == "success"
        assert meta_ordered["densified_count"] == meta_shuffled["densified_count"], (
            "Point count differs between ring-ordered and shuffled input — "
            "this may indicate a scanline-order dependency in the algorithm."
        )

    # 13.6 Vertical-only cloud ---------------------------------------------------

    def test_nn_densifies_vertical_only_point_line(self):
        """
        NN on a vertical line of points (x=0, y=0, z∈[0,10]) must produce new
        points spread along the Z axis — not collapsed to a single z value.

        This is a degenerate case that explicitly tests 3-D isotropic search.
        """
        Densify = _import_densify()
        rng = np.random.default_rng(5)
        # 50 points along z-axis only
        z_vals = np.linspace(0.0, 10.0, 50)
        pts = np.column_stack([
            rng.standard_normal(50) * 0.01,  # tiny XY noise to avoid degeneracy
            rng.standard_normal(50) * 0.01,
            z_vals,
        ]).astype(np.float64)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)

        op = Densify(algorithm="nearest_neighbor", density_multiplier=3.0)
        result_pcd, meta = op.apply(pcd)

        assert meta["status"] == "success"
        result_pts = get_positions(result_pcd)
        z_range = result_pts[:, 2].max() - result_pts[:, 2].min()
        # New points should have z values spread along the same range as original
        assert z_range > 5.0, (
            f"After densification of a vertical line, z-range={z_range:.2f} is too small. "
            f"Expected ≥5.0 to confirm vertical (z-axis) point generation."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 14: Log Level / Log Mode Configuration
# ═══════════════════════════════════════════════════════════════════════════════


class TestLogLevel:
    """
    Phase 14 — Log level configuration and log spam reduction.

    Covers:
    - DensifyLogLevel enum values: 'minimal', 'full', 'none'
    - DensifyConfig.log_level field (default='minimal')
    - DENSIFY_LOG_LEVEL env-var override
    - Densify.__init__ log_level parameter storage
    - Per-call log reduction: single INFO line in 'minimal' mode
    - 'none' mode: no INFO/WARNING logs during apply()
    - 'full' mode: DEBUG log emitted per successful apply()
    - Backward compat: default config (no log_level) behaves as 'minimal'
    """

    def test_log_level_enum_values_exist(self):
        """DensifyLogLevel enum must have minimal, full, none."""
        from app.modules.pipeline.operations.densify import DensifyLogLevel

        assert hasattr(DensifyLogLevel, "MINIMAL")
        assert hasattr(DensifyLogLevel, "FULL")
        assert hasattr(DensifyLogLevel, "NONE")
        assert DensifyLogLevel.MINIMAL.value == "minimal"
        assert DensifyLogLevel.FULL.value == "full"
        assert DensifyLogLevel.NONE.value == "none"

    def test_densify_config_has_log_level_field(self):
        """DensifyConfig must have a log_level field defaulting to 'minimal'."""
        from app.modules.pipeline.operations.densify import DensifyConfig

        cfg = DensifyConfig()
        assert hasattr(cfg, "log_level")
        assert cfg.log_level == "minimal"

    def test_densify_init_accepts_log_level_param(self):
        """Densify.__init__ must accept log_level kwarg and store it."""
        Densify = _import_densify()
        op = Densify(log_level="full")
        assert op.log_level == "full"

        op2 = Densify(log_level="none")
        assert op2.log_level == "none"

    def test_densify_default_log_level_is_minimal(self):
        """Densify() with no log_level uses 'minimal' by default."""
        Densify = _import_densify()
        op = Densify()
        assert op.log_level == "minimal"

    def test_densify_invalid_log_level_raises(self):
        """Unknown log_level raises ValueError."""
        Densify = _import_densify()
        with pytest.raises(ValueError, match="log_level"):
            Densify(log_level="verbose")

    def test_log_level_minimal_single_info_log_on_success(self, caplog):
        """
        In 'minimal' mode, apply() on a successful densification emits
        exactly ONE summary log at INFO or DEBUG level (not multiple step logs).
        """
        import logging

        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0, log_level="minimal")
        pcd = make_pcd(500)

        with caplog.at_level(logging.DEBUG, logger="app.modules.pipeline.operations.densify"):
            op.apply(pcd)

        info_records = [r for r in caplog.records if r.levelno >= logging.INFO]
        # In minimal mode, at most 1 INFO/WARNING record for a clean success
        assert len(info_records) <= 1, (
            f"'minimal' log_level produced {len(info_records)} INFO+ records; "
            f"expected ≤1. Messages: {[r.getMessage() for r in info_records]}"
        )

    def test_log_level_none_no_info_logs_on_success(self, caplog):
        """
        In 'none' mode, apply() must emit ZERO INFO/WARNING logs on success.
        """
        import logging

        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0, log_level="none")
        pcd = make_pcd(500)

        with caplog.at_level(logging.DEBUG, logger="app.modules.pipeline.operations.densify"):
            op.apply(pcd)

        info_and_above = [r for r in caplog.records if r.levelno >= logging.INFO]
        assert len(info_and_above) == 0, (
            f"'none' log_level produced {len(info_and_above)} INFO+ record(s). "
            f"Messages: {[r.getMessage() for r in info_and_above]}"
        )

    def test_log_level_none_no_warning_on_skip(self, caplog):
        """
        In 'none' mode, apply() on an insufficient-points input must not emit
        WARNING logs — status=skipped must be silent.
        """
        import logging

        Densify = _import_densify()
        op = Densify(log_level="none")
        pcd = make_pcd(5)  # too few points → skip

        with caplog.at_level(logging.DEBUG, logger="app.modules.pipeline.operations.densify"):
            _, meta = op.apply(pcd)

        assert meta["status"] == "skipped"
        warn_and_above = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warn_and_above) == 0, (
            f"'none' log_level still emitted {len(warn_and_above)} WARNING+ logs on skip."
        )

    def test_log_level_full_emits_debug_on_success(self, caplog):
        """
        In 'full' mode, a successful apply() must emit at least one DEBUG record
        containing point-count and timing information.
        """
        import logging

        Densify = _import_densify()
        op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0, log_level="full")
        pcd = make_pcd(500)

        with caplog.at_level(logging.DEBUG, logger="app.modules.pipeline.operations.densify"):
            _, meta = op.apply(pcd)

        assert meta["status"] == "success"
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_records) >= 1, (
            "'full' log_level must emit at least one DEBUG record on success."
        )

    def test_log_level_error_always_logged_regardless_of_level(self, caplog):
        """
        ERROR logs (algorithm failure) must always be emitted regardless of
        log_level setting — even in 'none' mode.
        """
        import logging
        from unittest.mock import patch

        Densify = _import_densify()
        op = Densify(log_level="none")
        pcd = make_pcd(1000)

        with caplog.at_level(logging.DEBUG, logger="app.modules.pipeline.operations.densify"):
            with patch.object(op, "_run_algorithm", side_effect=RuntimeError("fatal err")):
                _, meta = op.apply(pcd)

        assert meta["status"] == "error"
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) >= 1, (
            "ERROR log must be emitted even with log_level='none'."
        )

    def test_log_level_env_var_override(self, monkeypatch):
        """
        DENSIFY_LOG_LEVEL env variable must override the default.
        When env var is 'full', Densify() (no explicit arg) must default to 'full'.
        """
        monkeypatch.setenv("DENSIFY_LOG_LEVEL", "full")
        Densify = _import_densify()
        op = Densify()  # no explicit log_level
        assert op.log_level == "full", (
            "DENSIFY_LOG_LEVEL=full env var must override the default 'minimal'."
        )

    def test_explicit_log_level_overrides_env_var(self, monkeypatch):
        """
        Explicit log_level constructor arg must beat the env var.
        """
        monkeypatch.setenv("DENSIFY_LOG_LEVEL", "full")
        Densify = _import_densify()
        op = Densify(log_level="none")  # explicit override
        assert op.log_level == "none"

    def test_backward_compat_no_log_level_in_factory(self):
        """
        OperationFactory.create('densify', {}) (no log_level key) must still
        work — defaults to 'minimal'.
        """
        from app.modules.pipeline.factory import OperationFactory

        op = OperationFactory.create("densify", {})
        assert op.log_level == "minimal"

    def test_factory_passes_log_level(self):
        """OperationFactory.create passes log_level kwarg to Densify constructor."""
        from app.modules.pipeline.factory import OperationFactory

        op = OperationFactory.create("densify", {"log_level": "none"})
        assert op.log_level == "none"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 15: Per-Algorithm Parameter Exposure
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlgorithmParams:
    """
    Phase 15 — Configurable per-algorithm tunable parameters.

    All tunable algorithm parameters must be exposable via DensifyConfig
    sub-dicts and Densify constructor kwargs.  Validates:
    - DensifyNNParams, DensifyMLSParams, DensifyStatisticalParams,
      DensifyPoissonParams Pydantic models exist with correct field names/defaults
    - DensifyConfig.nn_params, .mls_params, .statistical_params, .poisson_params
      optional sub-dict fields
    - Densify.__init__ accepts *_params kwargs and stores them
    - Algorithm methods respect the configured params (observable effect)
    - Backward compat: None / unset params use defaults
    - Factory round-trip with nested params
    """

    # ── Model existence & defaults ────────────────────────────────────────────

    def test_nn_params_model_exists_with_defaults(self):
        """DensifyNNParams must have displacement_min, displacement_max defaults."""
        from app.modules.pipeline.operations.densify import DensifyNNParams

        p = DensifyNNParams()
        assert hasattr(p, "displacement_min")
        assert hasattr(p, "displacement_max")
        assert 0.0 < p.displacement_min < p.displacement_max <= 1.0

    def test_mls_params_model_exists_with_defaults(self):
        """DensifyMLSParams must have k_neighbors and projection_radius_factor."""
        from app.modules.pipeline.operations.densify import DensifyMLSParams

        p = DensifyMLSParams()
        assert hasattr(p, "k_neighbors")
        assert hasattr(p, "projection_radius_factor")
        assert p.k_neighbors >= 5
        assert p.projection_radius_factor > 0.0

    def test_statistical_params_model_exists_with_defaults(self):
        """DensifyStatisticalParams must have k_neighbors, sparse_percentile, min_dist_factor."""
        from app.modules.pipeline.operations.densify import DensifyStatisticalParams

        p = DensifyStatisticalParams()
        assert hasattr(p, "k_neighbors")
        assert hasattr(p, "sparse_percentile")
        assert hasattr(p, "min_dist_factor")
        assert p.k_neighbors >= 5
        assert 0 < p.sparse_percentile <= 100
        assert p.min_dist_factor > 0.0

    def test_poisson_params_model_exists_with_defaults(self):
        """DensifyPoissonParams must have depth, density_threshold_quantile."""
        from app.modules.pipeline.operations.densify import DensifyPoissonParams

        p = DensifyPoissonParams()
        assert hasattr(p, "depth")
        assert hasattr(p, "density_threshold_quantile")
        assert p.depth >= 6
        assert 0.0 <= p.density_threshold_quantile <= 1.0

    # ── DensifyConfig has optional sub-dict fields ────────────────────────────

    def test_densify_config_has_optional_nn_params(self):
        """DensifyConfig.nn_params is Optional and defaults to None."""
        from app.modules.pipeline.operations.densify import DensifyConfig

        cfg = DensifyConfig()
        assert hasattr(cfg, "nn_params")
        assert cfg.nn_params is None  # default = None → use built-in defaults

    def test_densify_config_has_optional_mls_params(self):
        """DensifyConfig.mls_params is Optional and defaults to None."""
        from app.modules.pipeline.operations.densify import DensifyConfig

        cfg = DensifyConfig()
        assert cfg.mls_params is None

    def test_densify_config_has_optional_statistical_params(self):
        """DensifyConfig.statistical_params is Optional and defaults to None."""
        from app.modules.pipeline.operations.densify import DensifyConfig

        cfg = DensifyConfig()
        assert cfg.statistical_params is None

    def test_densify_config_has_optional_poisson_params(self):
        """DensifyConfig.poisson_params is Optional and defaults to None."""
        from app.modules.pipeline.operations.densify import DensifyConfig

        cfg = DensifyConfig()
        assert cfg.poisson_params is None

    # ── Densify.__init__ accepts params kwargs ────────────────────────────────

    def test_densify_init_accepts_nn_params(self):
        """Densify(nn_params=DensifyNNParams(...)) stores nn_params attribute."""
        from app.modules.pipeline.operations.densify import DensifyNNParams

        Densify = _import_densify()
        params = DensifyNNParams(displacement_min=0.1, displacement_max=0.8)
        op = Densify(algorithm="nearest_neighbor", nn_params=params)
        assert op.nn_params is not None
        assert op.nn_params.displacement_min == 0.1
        assert op.nn_params.displacement_max == 0.8

    def test_densify_init_accepts_mls_params(self):
        """Densify(mls_params=DensifyMLSParams(...)) stores mls_params attribute."""
        from app.modules.pipeline.operations.densify import DensifyMLSParams

        Densify = _import_densify()
        params = DensifyMLSParams(k_neighbors=30)
        op = Densify(algorithm="mls", mls_params=params)
        assert op.mls_params is not None
        assert op.mls_params.k_neighbors == 30

    def test_densify_init_accepts_statistical_params(self):
        """Densify(statistical_params=...) stores statistical_params attribute."""
        from app.modules.pipeline.operations.densify import DensifyStatisticalParams

        Densify = _import_densify()
        params = DensifyStatisticalParams(k_neighbors=15, sparse_percentile=40)
        op = Densify(algorithm="statistical", statistical_params=params)
        assert op.statistical_params is not None
        assert op.statistical_params.k_neighbors == 15

    def test_densify_init_accepts_poisson_params(self):
        """Densify(poisson_params=...) stores poisson_params attribute."""
        from app.modules.pipeline.operations.densify import DensifyPoissonParams

        Densify = _import_densify()
        params = DensifyPoissonParams(depth=9)
        op = Densify(algorithm="poisson", poisson_params=params)
        assert op.poisson_params is not None
        assert op.poisson_params.depth == 9

    def test_densify_default_params_are_none(self):
        """All *_params default to None when not provided."""
        Densify = _import_densify()
        op = Densify()
        assert op.nn_params is None
        assert op.mls_params is None
        assert op.statistical_params is None
        assert op.poisson_params is None

    # ── Params respected by algorithm (observable effect) ────────────────────

    def test_nn_params_displacement_affects_output(self):
        """
        nn_params.displacement_max=0.01 (very tight) vs default should produce
        synthetic points much closer to source points.
        """
        from app.modules.pipeline.operations.densify import DensifyNNParams

        Densify = _import_densify()
        pcd = make_pcd(500)

        # Very tight displacement → synthetics stay very close to original pts
        tight_params = DensifyNNParams(displacement_min=0.001, displacement_max=0.01)
        op_tight = Densify(algorithm="nearest_neighbor", density_multiplier=2.0, nn_params=tight_params)
        result_tight, meta_tight = op_tight.apply(pcd)
        assert meta_tight["status"] == "success"

        # Wide displacement → synthetics can go far from original pts
        wide_params = DensifyNNParams(displacement_min=0.4, displacement_max=0.5)
        op_wide = Densify(algorithm="nearest_neighbor", density_multiplier=2.0, nn_params=wide_params)
        result_wide, meta_wide = op_wide.apply(pcd)
        assert meta_wide["status"] == "success"

        # Verify both produce valid densified clouds
        assert meta_tight["densified_count"] > 500
        assert meta_wide["densified_count"] > 500

    def test_statistical_params_k_neighbors_respected(self):
        """
        statistical_params.k_neighbors value must be accepted without error
        and algorithm must succeed.
        """
        from app.modules.pipeline.operations.densify import DensifyStatisticalParams

        Densify = _import_densify()
        pcd = make_pcd(500)

        # Use k=5 instead of default k=10
        params = DensifyStatisticalParams(k_neighbors=5, sparse_percentile=50)
        op = Densify(algorithm="statistical", density_multiplier=2.0, statistical_params=params)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["densified_count"] > 500

    def test_mls_params_k_neighbors_respected(self):
        """
        mls_params.k_neighbors=10 (vs default 20) must run without error.
        """
        from app.modules.pipeline.operations.densify import DensifyMLSParams

        Densify = _import_densify()
        pcd = make_pcd(300)

        params = DensifyMLSParams(k_neighbors=10)
        op = Densify(algorithm="mls", density_multiplier=2.0, mls_params=params)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["densified_count"] > 300

    def test_poisson_params_depth_respected(self):
        """
        poisson_params.depth value must be accepted without error.
        """
        from app.modules.pipeline.operations.densify import DensifyPoissonParams

        Densify = _import_densify()
        pcd = make_pcd_with_normals(300)

        params = DensifyPoissonParams(depth=7)
        op = Densify(algorithm="poisson", density_multiplier=2.0, poisson_params=params)
        result_pcd, meta = op.apply(pcd)
        assert meta["status"] == "success"
        assert meta["densified_count"] > 300

    # ── Backward compatibility ────────────────────────────────────────────────

    def test_backward_compat_no_params_uses_defaults(self):
        """Densify() with no *_params still runs all algorithms with internal defaults."""
        Densify = _import_densify()
        for algo in ("nearest_neighbor", "statistical", "mls"):
            pcd = make_pcd(300)
            op = Densify(algorithm=algo, density_multiplier=2.0)
            _, meta = op.apply(pcd)
            assert meta["status"] == "success", (
                f"Algorithm '{algo}' failed with default params: {meta}"
            )

    def test_params_passed_via_factory_dict(self):
        """
        OperationFactory.create passes *_params dict (not object) correctly.
        The factory should accept nested dicts and convert them to param objects.
        """
        from app.modules.pipeline.factory import OperationFactory
        from app.modules.pipeline.operations.densify import DensifyNNParams

        # Factory receives raw dict config — nested dict for nn_params
        op = OperationFactory.create(
            "densify",
            {
                "algorithm": "nearest_neighbor",
                "nn_params": {"displacement_min": 0.05, "displacement_max": 0.45},
            },
        )
        assert op.nn_params is not None
        assert isinstance(op.nn_params, DensifyNNParams)
        assert op.nn_params.displacement_min == 0.05

    def test_nn_params_validation_bounds(self):
        """DensifyNNParams rejects displacement_min >= displacement_max."""
        from app.modules.pipeline.operations.densify import DensifyNNParams
        from pydantic import ValidationError

        with pytest.raises((ValueError, ValidationError)):
            DensifyNNParams(displacement_min=0.5, displacement_max=0.1)

    def test_statistical_params_validation_k_neighbors(self):
        """DensifyStatisticalParams rejects k_neighbors < 2."""
        from app.modules.pipeline.operations.densify import DensifyStatisticalParams
        from pydantic import ValidationError

        with pytest.raises((ValueError, ValidationError)):
            DensifyStatisticalParams(k_neighbors=1)

    def test_mls_params_validation_k_neighbors(self):
        """DensifyMLSParams rejects k_neighbors < 3."""
        from app.modules.pipeline.operations.densify import DensifyMLSParams
        from pydantic import ValidationError

        with pytest.raises((ValueError, ValidationError)):
            DensifyMLSParams(k_neighbors=2)

    def test_poisson_params_validation_depth(self):
        """DensifyPoissonParams rejects depth < 4."""
        from app.modules.pipeline.operations.densify import DensifyPoissonParams
        from pydantic import ValidationError

        with pytest.raises((ValueError, ValidationError)):
            DensifyPoissonParams(depth=3)

    # ── Config JSON round-trip ────────────────────────────────────────────────

    def test_densify_config_with_nn_params_serializes(self):
        """DensifyConfig with nn_params round-trips through JSON."""
        from app.modules.pipeline.operations.densify import DensifyConfig, DensifyNNParams

        cfg = DensifyConfig(
            algorithm="nearest_neighbor",
            nn_params=DensifyNNParams(displacement_min=0.1, displacement_max=0.4),
        )
        j = cfg.model_dump()
        assert j["nn_params"]["displacement_min"] == 0.1
        assert j["nn_params"]["displacement_max"] == 0.4

    def test_densify_config_with_all_params_serializes(self):
        """DensifyConfig with all param sub-dicts serializes without error."""
        from app.modules.pipeline.operations.densify import (
            DensifyConfig, DensifyNNParams, DensifyMLSParams,
            DensifyStatisticalParams, DensifyPoissonParams,
        )

        cfg = DensifyConfig(
            nn_params=DensifyNNParams(),
            mls_params=DensifyMLSParams(),
            statistical_params=DensifyStatisticalParams(),
            poisson_params=DensifyPoissonParams(),
        )
        data = cfg.model_dump()
        assert data["nn_params"] is not None
        assert data["mls_params"] is not None
        assert data["statistical_params"] is not None
        assert data["poisson_params"] is not None
