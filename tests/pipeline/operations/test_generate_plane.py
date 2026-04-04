"""
TDD Tests for GeneratePlane pipeline operation.

Written BEFORE implementation (Phase 1 TDD gate).
All tests should FAIL until generate_plane.py is implemented.

Covers:
- Input validation (mode, voxel_size, size, plane_model, point count, input type)
- Square mode: output types, metadata keys/values, vertex count, triangle count, area
- Boundary mode: output types, metadata, rectangular hull, collinear points, RANSAC fallback
- Integration: PlaneSegmentation → GeneratePlane chain
- Performance benchmarks (marked @pytest.mark.slow)
"""
from __future__ import annotations

import math
import time

import numpy as np
import open3d as o3d
import pytest

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_tensor_pcd(points: np.ndarray) -> o3d.t.geometry.PointCloud:
    """Convenience: build an o3d.t.geometry.PointCloud from (N,3) numpy array."""
    pcd = o3d.t.geometry.PointCloud()
    pcd.point.positions = o3d.core.Tensor(points.astype(np.float32))
    return pcd


def _make_flat_cloud(n: int = 100, x_range=(-1, 1), y_range=(-1, 1), z_noise: float = 0.0,
                     rng_seed: int = 0) -> o3d.t.geometry.PointCloud:
    """Create a flat point cloud on the z≈0 plane."""
    rng = np.random.default_rng(rng_seed)
    xy = rng.uniform([x_range[0], y_range[0]], [x_range[1], y_range[1]], (n, 2))
    z = rng.normal(0, z_noise, (n, 1)) if z_noise > 0 else np.zeros((n, 1))
    pts = np.hstack([xy, z]).astype(np.float32)
    return _make_tensor_pcd(pts)


def _make_legacy_pcd(n: int = 100) -> o3d.geometry.PointCloud:
    """Create an o3d.geometry.PointCloud (legacy API)."""
    rng = np.random.default_rng(42)
    pts = rng.uniform(-1, 1, (n, 3)).astype(np.float64)
    pts[:, 2] = 0.0  # flat
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    return pcd


# ─────────────────────────────────────────────
# Lazy import (will fail until implementation exists — that's the TDD gate)
# ─────────────────────────────────────────────

def _import_generate_plane():
    from app.modules.pipeline.operations.generate_plane import GeneratePlane
    return GeneratePlane


# ═══════════════════════════════════════════════
# SECTION 1: Validation Tests
# ═══════════════════════════════════════════════

class TestValidation:
    """Parameter and input validation tests."""

    def test_invalid_mode_raises(self):
        """mode='invalid' must raise ValueError."""
        GeneratePlane = _import_generate_plane()
        with pytest.raises(ValueError, match="mode must be"):
            GeneratePlane(mode="invalid")

    def test_invalid_voxel_size_zero(self):
        """voxel_size=0 must raise ValueError."""
        GeneratePlane = _import_generate_plane()
        with pytest.raises(ValueError, match="voxel_size must be > 0"):
            GeneratePlane(voxel_size=0)

    def test_invalid_voxel_size_negative(self):
        """voxel_size=-0.1 must raise ValueError."""
        GeneratePlane = _import_generate_plane()
        with pytest.raises(ValueError, match="voxel_size must be > 0"):
            GeneratePlane(voxel_size=-0.1)

    def test_invalid_size_zero(self):
        """mode='square', size=0 must raise ValueError when apply() is called."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=0, voxel_size=0.05)
        pcd = _make_flat_cloud(50)
        with pytest.raises(ValueError, match="size must be > 0"):
            gen.apply(pcd)

    def test_invalid_size_negative(self):
        """mode='square', size=-1 must raise ValueError when apply() is called."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=-1, voxel_size=0.05)
        pcd = _make_flat_cloud(50)
        with pytest.raises(ValueError, match="size must be > 0"):
            gen.apply(pcd)

    def test_degenerate_plane_model(self):
        """plane_model=[0,0,0,0] (zero normal) must raise ValueError."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0.0, 0.0, 0.0, 0.0])
        pcd = _make_flat_cloud(50)
        with pytest.raises(ValueError, match="degenerate normal vector"):
            gen.apply(pcd)

    def test_insufficient_points_empty(self):
        """Empty PointCloud (0 points) must raise ValueError."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        pcd = o3d.t.geometry.PointCloud()
        pcd.point.positions = o3d.core.Tensor(np.zeros((0, 3), dtype=np.float32))
        with pytest.raises(ValueError, match="Insufficient points"):
            gen.apply(pcd)

    def test_two_points_only(self):
        """PointCloud with 2 points must raise ValueError."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        pts = np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float32)
        pcd = _make_tensor_pcd(pts)
        with pytest.raises(ValueError, match="Insufficient points"):
            gen.apply(pcd)

    def test_unsupported_input_type(self):
        """Passing a string instead of a PointCloud must raise TypeError."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        with pytest.raises(TypeError, match="Unsupported input type"):
            gen.apply("not_a_point_cloud")


# ═══════════════════════════════════════════════
# SECTION 2: Square Mode Tests
# ═══════════════════════════════════════════════

class TestSquareMode:
    """Tests for mode='square'."""

    @pytest.fixture
    def flat_pcd_100(self) -> o3d.t.geometry.PointCloud:
        return _make_flat_cloud(100)

    def test_square_mode_basic_output_type(self, flat_pcd_100):
        """Square mode must return (o3d.t.geometry.PointCloud, dict)."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        result = gen.apply(flat_pcd_100)
        assert isinstance(result, tuple), "apply() must return a tuple"
        assert len(result) == 2, "Tuple must have 2 elements"
        vertex_pcd, metadata = result
        assert isinstance(vertex_pcd, o3d.t.geometry.PointCloud), \
            "First return value must be o3d.t.geometry.PointCloud"
        assert isinstance(metadata, dict), "Second return value must be dict"

    def test_square_mode_metadata_keys(self, flat_pcd_100):
        """Square mode metadata must contain all 7 required keys."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_100)
        required_keys = {"mesh", "vertex_count", "triangle_count", "area",
                         "plane_model", "mode", "voxel_size"}
        assert required_keys.issubset(set(metadata.keys())), \
            f"Missing metadata keys: {required_keys - set(metadata.keys())}"

    def test_square_mode_mesh_in_metadata(self, flat_pcd_100):
        """metadata['mesh'] must be an o3d.t.geometry.TriangleMesh."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_100)
        assert isinstance(metadata["mesh"], o3d.t.geometry.TriangleMesh), \
            "metadata['mesh'] must be o3d.t.geometry.TriangleMesh"

    def test_square_mode_vertex_count(self, flat_pcd_100):
        """size=1.0, voxel_size=0.05 → ceil(1/0.05)=20 → 20×20=400 vertices."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_100)
        assert metadata["vertex_count"] == 400, \
            f"Expected 400 vertices, got {metadata['vertex_count']}"

    def test_square_mode_triangle_count(self, flat_pcd_100):
        """size=1.0, voxel_size=0.05 → 19×19×2=722 triangles."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_100)
        assert metadata["triangle_count"] == 722, \
            f"Expected 722 triangles, got {metadata['triangle_count']}"

    def test_square_mode_area(self, flat_pcd_100):
        """size=2.0 → area must be 4.0 (within 0.001 tolerance)."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=2.0, voxel_size=0.1,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_100)
        assert abs(metadata["area"] - 4.0) < 0.001, \
            f"Expected area≈4.0, got {metadata['area']}"

    def test_square_mode_plane_model_in_metadata(self, flat_pcd_100):
        """Square mode metadata must contain plane_model=[0.0, 0.0, 1.0, 0.0]."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_100)
        pm = metadata["plane_model"]
        assert len(pm) == 4, "plane_model must have 4 elements"
        expected = [0.0, 0.0, 1.0, 0.0]
        for i, (got, exp) in enumerate(zip(pm, expected)):
            assert abs(got - exp) < 1e-6, \
                f"plane_model[{i}]: expected {exp}, got {got}"

    def test_square_mode_vertex_pcd_positions_count(self, flat_pcd_100):
        """Returned PointCloud must have N=vertex_count positions."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        vertex_pcd, metadata = gen.apply(flat_pcd_100)
        n_positions = vertex_pcd.point.positions.shape[0]
        assert n_positions == metadata["vertex_count"], \
            f"PointCloud positions count ({n_positions}) != vertex_count ({metadata['vertex_count']})"

    def test_square_mode_vertices_on_z0(self, flat_pcd_100):
        """All returned vertex Z values must be approximately 0.0 for z-aligned plane."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        vertex_pcd, _ = gen.apply(flat_pcd_100)
        positions = vertex_pcd.point.positions.cpu().numpy()
        z_values = positions[:, 2]
        assert np.allclose(z_values, 0.0, atol=1e-4), \
            f"All Z values should be ~0.0, max abs: {np.abs(z_values).max()}"

    def test_square_mode_vertex_limit_exceeded(self, flat_pcd_100):
        """size=100, voxel_size=0.001 → >1M vertices → ValueError."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=100.0, voxel_size=0.001,
                            plane_model=[0, 0, 1, 0])
        with pytest.raises(ValueError, match="1,000,000"):
            gen.apply(flat_pcd_100)

    def test_square_mode_accepts_legacy_pcd(self):
        """Legacy o3d.geometry.PointCloud input must work without error."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.1,
                            plane_model=[0, 0, 1, 0])
        legacy_pcd = _make_legacy_pcd(50)
        # Must not raise
        vertex_pcd, metadata = gen.apply(legacy_pcd)
        assert isinstance(vertex_pcd, o3d.t.geometry.PointCloud)
        assert metadata["vertex_count"] > 0

    def test_square_mode_mode_echo_in_metadata(self, flat_pcd_100):
        """metadata['mode'] must echo the configured mode."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_100)
        assert metadata["mode"] == "square"

    def test_square_mode_voxel_size_echo_in_metadata(self, flat_pcd_100):
        """metadata['voxel_size'] must echo the configured voxel_size."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_100)
        assert metadata["voxel_size"] == pytest.approx(0.05)


# ═══════════════════════════════════════════════
# SECTION 3: Boundary Mode Tests
# ═══════════════════════════════════════════════

class TestBoundaryMode:
    """Tests for mode='boundary'."""

    @pytest.fixture
    def flat_pcd_200(self) -> o3d.t.geometry.PointCloud:
        """Dense flat cloud suitable for boundary hull computation."""
        return _make_flat_cloud(200, x_range=(-1, 1), y_range=(-1, 1))

    def test_boundary_mode_basic_output_type(self, flat_pcd_200):
        """Boundary mode must return (o3d.t.geometry.PointCloud, dict)."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="boundary", voxel_size=0.2,
                            plane_model=[0, 0, 1, 0])
        result = gen.apply(flat_pcd_200)
        assert isinstance(result, tuple) and len(result) == 2
        vertex_pcd, metadata = result
        assert isinstance(vertex_pcd, o3d.t.geometry.PointCloud)
        assert isinstance(metadata, dict)

    def test_boundary_mode_metadata_keys(self, flat_pcd_200):
        """Boundary mode metadata must contain all 7 required keys."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="boundary", voxel_size=0.2,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_200)
        required_keys = {"mesh", "vertex_count", "triangle_count", "area",
                         "plane_model", "mode", "voxel_size"}
        assert required_keys.issubset(set(metadata.keys())), \
            f"Missing keys: {required_keys - set(metadata.keys())}"

    def test_boundary_mode_mesh_in_metadata(self, flat_pcd_200):
        """metadata['mesh'] must be an o3d.t.geometry.TriangleMesh."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="boundary", voxel_size=0.2,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_200)
        assert isinstance(metadata["mesh"], o3d.t.geometry.TriangleMesh)

    def test_boundary_mode_rectangular_hull(self):
        """4 corner points of 1m×1m square should produce positive vertex/triangle count."""
        GeneratePlane = _import_generate_plane()
        # Use a dense fill rather than 4 corners so hull has interior points
        rng = np.random.default_rng(10)
        xy = rng.uniform(-0.5, 0.5, (80, 2))
        z = np.zeros((80, 1))
        pts = np.hstack([xy, z]).astype(np.float32)
        pcd = _make_tensor_pcd(pts)
        gen = GeneratePlane(mode="boundary", voxel_size=0.15,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(pcd)
        assert metadata["vertex_count"] > 0, "vertex_count must be positive"
        assert metadata["triangle_count"] > 0, "triangle_count must be positive"

    def test_boundary_mode_plane_model_echo(self, flat_pcd_200):
        """Supplied plane_model must be echoed in metadata."""
        GeneratePlane = _import_generate_plane()
        pm = [0.02, -0.01, 0.999, -0.15]
        gen = GeneratePlane(mode="boundary", voxel_size=0.2, plane_model=pm)
        # Normalise plane_model so normal is valid
        normal_len = math.sqrt(pm[0]**2 + pm[1]**2 + pm[2]**2)
        assert normal_len > 1e-6

        _, metadata = gen.apply(flat_pcd_200)
        # The echoed plane_model may be normalised or raw — we just check it's a 4-list
        assert len(metadata["plane_model"]) == 4
        # Original [a,b,c,d] should appear or be normalised version
        echoed = metadata["plane_model"]
        for v in echoed:
            assert isinstance(v, float), f"plane_model elements must be float, got {type(v)}"

    def test_boundary_mode_area_positive(self, flat_pcd_200):
        """Boundary mode area must be > 0."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="boundary", voxel_size=0.2,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_200)
        assert metadata["area"] > 0.0, f"area must be > 0, got {metadata['area']}"

    def test_boundary_collinear_raises(self):
        """All points on a single line must raise ValueError about colinear points."""
        GeneratePlane = _import_generate_plane()
        # All points along X axis: (t, 0, 0) for t in [0,1]
        t = np.linspace(0, 1, 20, dtype=np.float32)
        pts = np.column_stack([t, np.zeros_like(t), np.zeros_like(t)])
        pcd = _make_tensor_pcd(pts)
        gen = GeneratePlane(mode="boundary", voxel_size=0.05,
                            plane_model=[0, 0, 1, 0])
        with pytest.raises(ValueError, match="colinear"):
            gen.apply(pcd)

    def test_boundary_mode_accepts_legacy_pcd(self):
        """Legacy o3d.geometry.PointCloud input must work in boundary mode."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="boundary", voxel_size=0.2,
                            plane_model=[0, 0, 1, 0])
        legacy_pcd = _make_legacy_pcd(80)
        vertex_pcd, metadata = gen.apply(legacy_pcd)
        assert isinstance(vertex_pcd, o3d.t.geometry.PointCloud)
        assert metadata["vertex_count"] > 0

    def test_boundary_mode_auto_ransac(self):
        """Without plane_model, boundary mode should fit RANSAC and succeed."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="boundary", voxel_size=0.2)
        # Flat cloud — RANSAC should trivially find z=0 plane
        pcd = _make_flat_cloud(150)
        # Must not raise
        vertex_pcd, metadata = gen.apply(pcd)
        assert metadata["vertex_count"] > 0
        assert len(metadata["plane_model"]) == 4

    def test_boundary_mode_mode_echo_in_metadata(self, flat_pcd_200):
        """metadata['mode'] must be 'boundary'."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="boundary", voxel_size=0.2,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_200)
        assert metadata["mode"] == "boundary"

    def test_boundary_mode_voxel_size_echo_in_metadata(self, flat_pcd_200):
        """metadata['voxel_size'] must match configured voxel_size."""
        GeneratePlane = _import_generate_plane()
        gen = GeneratePlane(mode="boundary", voxel_size=0.2,
                            plane_model=[0, 0, 1, 0])
        _, metadata = gen.apply(flat_pcd_200)
        assert metadata["voxel_size"] == pytest.approx(0.2)


# ═══════════════════════════════════════════════
# SECTION 4: Integration-Style Tests
# ═══════════════════════════════════════════════

def test_chain_segmentation_to_generate_plane():
    """
    PlaneSegmentation → GeneratePlane chaining test.

    Runs PlaneSegmentation on a flat cloud, extracts plane_model,
    then feeds to GeneratePlane(mode='boundary').
    """
    from app.modules.pipeline.operations.segmentation import PlaneSegmentation
    GeneratePlane = _import_generate_plane()

    rng = np.random.default_rng(42)
    xy = rng.uniform(-2, 2, (200, 2))
    z = rng.normal(0, 0.005, (200, 1)).astype(np.float32)
    pts = np.hstack([xy, z]).astype(np.float32)
    pcd = _make_tensor_pcd(pts)

    seg = PlaneSegmentation(distance_threshold=0.02, ransac_n=3, num_iterations=500)
    seg_pcd, seg_meta = seg.apply(pcd)
    assert "plane_model" in seg_meta, "PlaneSegmentation must provide plane_model in metadata"

    plane_model = seg_meta["plane_model"]
    gen = GeneratePlane(mode="boundary", voxel_size=0.1, plane_model=plane_model)
    vertex_pcd, mesh_meta = gen.apply(seg_pcd)

    assert mesh_meta["vertex_count"] > 0
    assert mesh_meta["triangle_count"] > 0
    assert mesh_meta["area"] > 0.0
    assert isinstance(mesh_meta["mesh"], o3d.t.geometry.TriangleMesh)


def test_integration_segmentation_chain():
    """Alias for the chain test (matching backend-tasks.md §4.1 naming)."""
    test_chain_segmentation_to_generate_plane()


# ═══════════════════════════════════════════════
# SECTION 5: Performance Benchmarks
# ═══════════════════════════════════════════════

@pytest.mark.slow
def test_benchmark_square_1m_voxel_01():
    """Square 1m×1m, voxel=0.01 must complete in < 100ms."""
    GeneratePlane = _import_generate_plane()
    gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.01,
                        plane_model=[0, 0, 1, 0])
    pcd = _make_flat_cloud(100)
    start = time.perf_counter()
    gen.apply(pcd)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 100, f"Square mode took {elapsed_ms:.1f}ms (limit: 100ms)"


@pytest.mark.slow
def test_benchmark_boundary_1k_pts_voxel_01():
    """Boundary 1k pts, voxel=0.01 must complete in < 500ms."""
    GeneratePlane = _import_generate_plane()
    rng = np.random.default_rng(0)
    pts = rng.uniform(-1, 1, (1000, 2))
    z = np.zeros((1000, 1))
    pts3d = np.hstack([pts, z]).astype(np.float32)
    pcd = _make_tensor_pcd(pts3d)
    gen = GeneratePlane(mode="boundary", voxel_size=0.01, plane_model=[0, 0, 1, 0])
    start = time.perf_counter()
    gen.apply(pcd)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 500, f"Boundary mode took {elapsed_ms:.1f}ms (limit: 500ms)"
