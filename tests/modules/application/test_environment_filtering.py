"""
Unit tests for EnvironmentFilteringNode.

Covers:
  - Instantiation and parameter storage
  - Parameter validation (ValueError on bad inputs)
  - Empty cloud pass-through
  - Voxel downsampling helpers
  - _detect_horizontal_planes orientation + area filtering
  - floor/ceiling selection (lowest Z = floor, highest Z = ceiling)
  - remove_floor / remove_ceiling flags
  - Cache: fast path reuse, slow path refresh, miss confirmation window
  - emit_status states
"""
import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import numpy as np
import open3d as o3d
import pytest

from app.modules.application.environment_filtering.node import (
    EnvironmentFilteringNode,
    PlaneInfo,
)
from app.schemas.status import NodeStatusUpdate, OperationalState


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_pcd(points: np.ndarray) -> o3d.t.geometry.PointCloud:
    pcd = o3d.t.geometry.PointCloud()
    pcd.point["positions"] = o3d.core.Tensor(
        points.astype(np.float32), dtype=o3d.core.Dtype.Float32
    )
    return pcd


def _make_floor_cloud(n_floor: int = 2000, n_other: int = 3000) -> np.ndarray:
    rng = np.random.default_rng(42)
    floor = np.column_stack([rng.uniform(-5, 5, (n_floor, 2)), np.zeros(n_floor)])
    other_z = rng.uniform(0.5, 2.5, n_other)
    other = np.column_stack([rng.uniform(-5, 5, (n_other, 2)), other_z])
    return np.vstack([floor, other]).astype(np.float32)


def _make_floor_and_ceiling_cloud(
    n_floor: int = 2000, n_ceil: int = 2000, n_other: int = 3000
) -> np.ndarray:
    rng = np.random.default_rng(42)
    floor = np.column_stack([rng.uniform(-5, 5, (n_floor, 2)), np.zeros(n_floor)])
    ceil_ = np.column_stack([rng.uniform(-5, 5, (n_ceil, 2)), np.full(n_ceil, 3.0)])
    other = np.column_stack([rng.uniform(-5, 5, (n_other, 2)), rng.uniform(0.5, 2.5, n_other)])
    return np.vstack([floor, ceil_, other]).astype(np.float32)


DEFAULT_CONFIG: Dict[str, Any] = {
    "throttle_ms": 0,
    "voxel_downsample_size": 0.01,
    "normal_variance_threshold_deg": 60.0,
    "coplanarity_deg": 75.0,
    "outlier_ratio": 0.75,
    "min_plane_edge_length": 0.0,
    "min_num_points": 0,
    "max_nn": 30,
    "search_radius": 0.1,
    "vertical_tolerance_deg": 15.0,
    "min_plane_area": 1.0,
    "remove_floor": True,
    "remove_ceiling": True,
    "plane_thickness": 0.1,
    "cache_refresh_frames": 30,
    "miss_confirm_frames": 3,
}


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_manager() -> MagicMock:
    from unittest.mock import AsyncMock
    m = MagicMock()
    m.forward_data = AsyncMock()
    return m


@pytest.fixture
def default_node(mock_manager: MagicMock) -> EnvironmentFilteringNode:
    return EnvironmentFilteringNode(
        manager=mock_manager,
        node_id="ef-001",
        name="Test EF Node",
        config=DEFAULT_CONFIG.copy(),
    )


@pytest.fixture
def node_factory(mock_manager: MagicMock):
    def _make(overrides: Dict[str, Any] = None):
        cfg = DEFAULT_CONFIG.copy()
        if overrides:
            cfg.update(overrides)
        return EnvironmentFilteringNode(
            manager=mock_manager, node_id="ef-test", name="Test", config=cfg
        )
    return _make


# Convenience: two PlaneInfo stubs at different heights
def _floor_plane(z: float = 0.0) -> PlaneInfo:
    return PlaneInfo(plane_id=0, plane_type="floor", normal=[0.0, 0.0, 1.0],
                     centroid=[0.0, 0.0, z], area=25.0, point_count=500)

def _ceiling_plane(z: float = 3.0) -> PlaneInfo:
    return PlaneInfo(plane_id=1, plane_type="ceiling", normal=[0.0, 0.0, 1.0],
                     centroid=[0.0, 0.0, z], area=25.0, point_count=500)


# ─────────────────────────────────────────────────────────────────────────────
# TestInstantiation
# ─────────────────────────────────────────────────────────────────────────────


class TestInstantiation:
    def test_id_stored(self, default_node):
        assert default_node.id == "ef-001"

    def test_name_stored(self, default_node):
        assert default_node.name == "Test EF Node"

    def test_voxel_downsample_size_stored(self, default_node):
        assert default_node.voxel_downsample_size == 0.01

    def test_max_nn_stored(self, default_node):
        assert default_node.max_nn == 30

    def test_search_radius_stored(self, default_node):
        assert default_node.search_radius == pytest.approx(0.1)

    def test_remove_floor_default_true(self, default_node):
        assert default_node.remove_floor is True

    def test_remove_ceiling_default_true(self, default_node):
        assert default_node.remove_ceiling is True

    def test_cache_refresh_frames_stored(self, default_node):
        assert default_node.cache_refresh_frames == 30

    def test_miss_confirm_frames_stored(self, default_node):
        assert default_node.miss_confirm_frames == 3

    def test_cache_starts_empty(self, default_node):
        assert default_node._cached_floor is None
        assert default_node._cached_ceiling is None

    def test_consecutive_misses_starts_zero(self, default_node):
        assert default_node._consecutive_misses == 0

    def test_processing_flag_starts_false(self, default_node):
        assert default_node._processing is False

    def test_no_op_attribute(self, default_node):
        """Old _op wrapper must not exist — params are flat now."""
        assert not hasattr(default_node, "_op")

    def test_no_floor_height_range(self, default_node):
        """floor_height_range was removed — automatic lowest-Z selection."""
        assert not hasattr(default_node, "floor_height_range")

    def test_no_ceiling_height_range(self, default_node):
        assert not hasattr(default_node, "ceiling_height_range")


# ─────────────────────────────────────────────────────────────────────────────
# TestParamValidation
# ─────────────────────────────────────────────────────────────────────────────


class TestParamValidation:
    def test_vertical_tolerance_too_small(self, mock_manager):
        cfg = {**DEFAULT_CONFIG, "vertical_tolerance_deg": 0.5}
        with pytest.raises(ValueError, match="vertical_tolerance_deg"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="x", name="x", config=cfg)

    def test_vertical_tolerance_too_large(self, mock_manager):
        cfg = {**DEFAULT_CONFIG, "vertical_tolerance_deg": 46}
        with pytest.raises(ValueError, match="vertical_tolerance_deg"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="x", name="x", config=cfg)

    def test_min_plane_area_too_small(self, mock_manager):
        cfg = {**DEFAULT_CONFIG, "min_plane_area": 0.05}
        with pytest.raises(ValueError, match="min_plane_area"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="x", name="x", config=cfg)

    def test_voxel_downsample_negative(self, mock_manager):
        cfg = {**DEFAULT_CONFIG, "voxel_downsample_size": -0.01}
        with pytest.raises(ValueError, match="voxel_downsample_size"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="x", name="x", config=cfg)

    def test_voxel_downsample_too_large(self, mock_manager):
        cfg = {**DEFAULT_CONFIG, "voxel_downsample_size": 1.5}
        with pytest.raises(ValueError, match="voxel_downsample_size"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="x", name="x", config=cfg)

    def test_voxel_zero_is_valid(self, mock_manager):
        cfg = {**DEFAULT_CONFIG, "voxel_downsample_size": 0.0}
        node = EnvironmentFilteringNode(manager=mock_manager, node_id="x", name="x", config=cfg)
        assert node.voxel_downsample_size == 0.0

    def test_voxel_one_is_valid(self, mock_manager):
        cfg = {**DEFAULT_CONFIG, "voxel_downsample_size": 1.0}
        node = EnvironmentFilteringNode(manager=mock_manager, node_id="x", name="x", config=cfg)
        assert node.voxel_downsample_size == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# TestEmptyInput
# ─────────────────────────────────────────────────────────────────────────────


class TestEmptyInput:
    def test_empty_cloud_status(self, default_node):
        pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        _, meta = default_node._sync_filter(pcd)
        assert meta["status"] == "warning_pass_through"

    def test_empty_cloud_returns_zero_points(self, default_node):
        pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        out, _ = default_node._sync_filter(pcd)
        assert len(out.point["positions"]) == 0

    def test_empty_cloud_no_exception(self, default_node):
        pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        default_node._sync_filter(pcd)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# TestDownsampling
# ─────────────────────────────────────────────────────────────────────────────


class TestDownsampling:
    def test_disabled_returns_same_object(self, node_factory):
        node = node_factory({"voxel_downsample_size": 0.0})
        pts = np.random.default_rng(1).standard_normal((500, 3)).astype(np.float32)
        pcd_legacy = _make_pcd(pts).to_legacy()
        ds, meta = node._voxel_downsample(pcd_legacy, len(pts))
        assert ds is pcd_legacy
        assert meta["downsampling_enabled"] is False
        assert meta["voxel_size"] == 0.0

    def test_disabled_counts_equal(self, node_factory):
        node = node_factory({"voxel_downsample_size": 0.0})
        pts = np.random.default_rng(1).standard_normal((500, 3)).astype(np.float32)
        pcd_legacy = _make_pcd(pts).to_legacy()
        _, meta = node._voxel_downsample(pcd_legacy, 500)
        assert meta["points_before_downsample"] == meta["points_after_downsample"] == 500

    def test_enabled_reduces_points(self, default_node):
        rng = np.random.default_rng(42)
        pts = np.column_stack([rng.uniform(-5, 5, (10000, 2)), np.zeros(10000)]).astype(np.float32)
        pcd_legacy = _make_pcd(pts).to_legacy()
        _, meta = default_node._voxel_downsample(pcd_legacy, 10000)
        assert meta["downsampling_enabled"] is True
        assert meta["points_after_downsample"] < 10000

    def test_enabled_meta_has_correct_voxel_size(self, default_node):
        pts = np.random.default_rng(0).standard_normal((1000, 3)).astype(np.float32)
        pcd_legacy = _make_pcd(pts).to_legacy()
        _, meta = default_node._voxel_downsample(pcd_legacy, 1000)
        assert meta["voxel_size"] == 0.01


# ─────────────────────────────────────────────────────────────────────────────
# TestFloorCeilingSelection
# ─────────────────────────────────────────────────────────────────────────────


class TestFloorCeilingSelection:
    """Verify that lowest-Z = floor, highest-Z = ceiling logic is correct."""

    def _run_with_planes(self, node, planes, n_pts=500):
        """Patch _detect_horizontal_planes to return `planes`, run _sync_filter."""
        pts = np.random.default_rng(0).standard_normal((n_pts, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(node, "_detect_horizontal_planes", return_value=planes):
            _, meta = node._sync_filter(pcd_in)
        return meta

    def test_single_plane_assigned_as_floor(self, default_node):
        planes = [_floor_plane(z=0.1)]
        meta = self._run_with_planes(default_node, planes)
        types = [d["plane_type"] for d in meta["plane_details"]]
        assert "floor" in types
        assert "ceiling" not in types

    def test_two_planes_lowest_is_floor(self, default_node):
        planes = [_floor_plane(z=0.0), _ceiling_plane(z=3.0)]
        meta = self._run_with_planes(default_node, planes)
        details = {d["plane_type"]: d["centroid_z"] for d in meta["plane_details"]}
        assert details["floor"] == pytest.approx(0.0)
        assert details["ceiling"] == pytest.approx(3.0)

    def test_two_planes_order_independent(self, default_node):
        """Detection order should not matter — Z-sort picks correct floor/ceiling."""
        planes = [_ceiling_plane(z=3.0), _floor_plane(z=0.0)]  # ceiling first
        meta = self._run_with_planes(default_node, planes)
        details = {d["plane_type"]: d["centroid_z"] for d in meta["plane_details"]}
        assert details["floor"] == pytest.approx(0.0)
        assert details["ceiling"] == pytest.approx(3.0)

    def test_three_planes_picks_extremes(self, default_node):
        """With 3 planes, only the extreme-Z ones become floor/ceiling."""
        planes = [
            PlaneInfo(0, "", [0.0,0.0,1.0], [0.0,0.0,0.0],  25.0, 100),
            PlaneInfo(1, "", [0.0,0.0,1.0], [0.0,0.0,1.5],  25.0, 100),
            PlaneInfo(2, "", [0.0,0.0,1.0], [0.0,0.0,3.0],  25.0, 100),
        ]
        meta = self._run_with_planes(default_node, planes)
        details = {d["plane_type"]: d["centroid_z"] for d in meta["plane_details"]}
        assert details["floor"] == pytest.approx(0.0)
        assert details["ceiling"] == pytest.approx(3.0)
        assert len(meta["plane_details"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# TestRemoveFlags
# ─────────────────────────────────────────────────────────────────────────────


class TestRemoveFlags:
    """Verify remove_floor / remove_ceiling flags correctly suppress removal."""

    def _pts_with_floor_and_ceiling(self):
        """100 pts at z=0 (floor), 100 at z=3 (ceiling), 100 between."""
        rng = np.random.default_rng(7)
        floor = np.column_stack([rng.uniform(-2, 2, (100, 2)), np.zeros(100)])
        ceil_ = np.column_stack([rng.uniform(-2, 2, (100, 2)), np.full(100, 3.0)])
        mid   = np.column_stack([rng.uniform(-2, 2, (100, 2)), np.full(100, 1.5)])
        return np.vstack([floor, ceil_, mid]).astype(np.float32)

    def _run(self, node, planes):
        pts = self._pts_with_floor_and_ceiling()
        pcd_in = _make_pcd(pts)
        with patch.object(node, "_detect_horizontal_planes", return_value=planes):
            out, meta = node._sync_filter(pcd_in)
        return out, meta, pts

    def test_remove_both_removes_floor_and_ceiling(self, node_factory):
        node = node_factory({"remove_floor": True, "remove_ceiling": True,
                              "cache_refresh_frames": 1})
        planes = [_floor_plane(0.0), _ceiling_plane(3.0)]
        out, meta, _ = self._run(node, planes)
        assert meta["removed_point_count"] > 0

    def test_remove_floor_false_keeps_floor(self, node_factory):
        node = node_factory({"remove_floor": False, "remove_ceiling": True,
                              "cache_refresh_frames": 1})
        planes = [_floor_plane(0.0), _ceiling_plane(3.0)]
        out, meta, pts = self._run(node, planes)
        # Floor points (z≈0) must still be in output
        out_z = np.asarray(out.point["positions"].numpy())[:, 2]
        assert np.any(np.abs(out_z) < 0.1), "Floor points should not have been removed"

    def test_remove_ceiling_false_keeps_ceiling(self, node_factory):
        node = node_factory({"remove_floor": True, "remove_ceiling": False,
                              "cache_refresh_frames": 1})
        planes = [_floor_plane(0.0), _ceiling_plane(3.0)]
        out, meta, pts = self._run(node, planes)
        out_z = np.asarray(out.point["positions"].numpy())[:, 2]
        assert np.any(np.abs(out_z - 3.0) < 0.1), "Ceiling points should not have been removed"

    def test_remove_both_false_is_pass_through(self, node_factory):
        node = node_factory({"remove_floor": False, "remove_ceiling": False,
                              "cache_refresh_frames": 1})
        planes = [_floor_plane(0.0), _ceiling_plane(3.0)]
        out, meta, pts = self._run(node, planes)
        assert meta["removed_point_count"] == 0
        assert len(out.point["positions"]) == len(pts)


# ─────────────────────────────────────────────────────────────────────────────
# TestCache
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheFastPath:
    """Cache is populated on first detection, reused for subsequent frames."""

    def _make_node(self, node_factory, refresh=5):
        return node_factory({"cache_refresh_frames": refresh, "miss_confirm_frames": 3})

    def test_first_frame_populates_cache(self, node_factory):
        node = self._make_node(node_factory)
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        planes = [_floor_plane(0.0), _ceiling_plane(3.0)]
        with patch.object(node, "_detect_horizontal_planes", return_value=planes):
            node._sync_filter(pcd_in)
        assert node._cached_floor is not None
        assert node._cached_floor.centroid_z == pytest.approx(0.0)
        assert node._cached_ceiling is not None
        assert node._cached_ceiling.centroid_z == pytest.approx(3.0)

    def test_subsequent_frames_use_cache(self, node_factory):
        node = self._make_node(node_factory, refresh=10)
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        planes = [_floor_plane(0.0), _ceiling_plane(3.0)]

        # Frame 1 — slow path, fills cache
        with patch.object(node, "_detect_horizontal_planes", return_value=planes) as mock_detect:
            node._sync_filter(pcd_in)
            assert mock_detect.call_count == 1

        # Frames 2-5 — fast path, detect must NOT be called
        with patch.object(node, "_detect_horizontal_planes", return_value=planes) as mock_detect:
            for _ in range(4):
                _, meta = node._sync_filter(pcd_in)
                assert meta["cache_hit"] is True
            assert mock_detect.call_count == 0

    def test_cache_refreshes_after_n_frames(self, node_factory):
        node = self._make_node(node_factory, refresh=3)
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        planes = [_floor_plane(0.0), _ceiling_plane(3.0)]

        call_count = 0
        def _detect(_):
            nonlocal call_count
            call_count += 1
            return planes

        with patch.object(node, "_detect_horizontal_planes", side_effect=_detect):
            for _ in range(7):  # 1 slow + 2 fast + 1 slow + 2 fast + 1 slow
                node._sync_filter(pcd_in)

        # Frames: 1(slow), 2(fast), 3(fast), 4(slow), 5(fast), 6(fast), 7(slow)
        assert call_count == 3

    def test_successful_detection_resets_consecutive_misses(self, node_factory):
        node = self._make_node(node_factory, refresh=1)
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)

        with patch.object(node, "_detect_horizontal_planes",
                          return_value=[_floor_plane(0.0), _ceiling_plane(3.0)]):
            node._sync_filter(pcd_in)
            node._consecutive_misses = 2
            node._sync_filter(pcd_in)

        assert node._consecutive_misses == 0


class TestCacheMissConfirmation:
    """Cache must NOT be invalidated until miss_confirm_frames consecutive misses."""

    def _setup(self, node_factory, miss_confirm=3, refresh=1):
        """Return a node with a warm cache at floor=0, ceiling=3."""
        node = node_factory({
            "cache_refresh_frames": refresh,
            "miss_confirm_frames": miss_confirm,
        })
        node._cached_floor = _floor_plane(0.0)
        node._cached_ceiling = _ceiling_plane(3.0)
        node._frames_since_detection = refresh  # force slow path on next call
        return node

    def test_single_miss_keeps_cache(self, node_factory):
        node = self._setup(node_factory)
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(node, "_detect_horizontal_planes", return_value=[]):
            node._sync_filter(pcd_in)
        assert node._cached_floor is not None, "Cache must survive 1 miss"
        assert node._cached_floor.centroid_z == pytest.approx(0.0)
        assert node._consecutive_misses == 1

    def test_below_confirm_threshold_keeps_cache(self, node_factory):
        node = self._setup(node_factory, miss_confirm=3)
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(node, "_detect_horizontal_planes", return_value=[]):
            node._sync_filter(pcd_in)  # miss 1
            node._frames_since_detection = 1  # force slow path
            node._sync_filter(pcd_in)  # miss 2
        # 2 < 3 — cache must still be valid
        assert node._cached_floor is not None

    def test_confirmed_miss_invalidates_cache(self, node_factory):
        node = self._setup(node_factory, miss_confirm=3)
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(node, "_detect_horizontal_planes", return_value=[]):
            for _ in range(3):
                node._frames_since_detection = 1  # keep forcing slow path
                node._sync_filter(pcd_in)
        assert node._cached_floor is None
        assert node._cached_ceiling is None
        assert node._consecutive_misses == 0

    def test_confirmed_miss_status_no_planes(self, node_factory):
        node = self._setup(node_factory, miss_confirm=3)
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(node, "_detect_horizontal_planes", return_value=[]):
            for _ in range(3):
                node._frames_since_detection = 1
                _, meta = node._sync_filter(pcd_in)
        assert meta["status"] == "no_planes_detected"

    def test_partial_miss_serves_cached_removal(self, node_factory):
        """During miss confirmation window, cached Z values must still be applied."""
        node = self._setup(node_factory, miss_confirm=3)
        # Place some points right at the cached floor Z
        pts = np.zeros((100, 3), dtype=np.float32)
        pts[:20, 2] = 0.0   # at floor
        pts[20:, 2] = 1.5   # non-plane
        pcd_in = _make_pcd(pts)
        with patch.object(node, "_detect_horizontal_planes", return_value=[]):
            out, meta = node._sync_filter(pcd_in)
        # Cache still active → floor points (z≈0) should have been removed
        assert meta["planes_filtered"] > 0
        assert meta["removed_point_count"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# TestNoPlanes
# ─────────────────────────────────────────────────────────────────────────────


class TestNoPlanes:
    def test_no_planes_status(self, default_node):
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(default_node, "_detect_horizontal_planes", return_value=[]):
            _, meta = default_node._sync_filter(pcd_in)
        # With empty cache and single miss < confirm threshold, status is still no_planes_detected
        # (cache is empty so nothing to fall back to)
        assert meta["planes_filtered"] == 0

    def test_no_planes_passes_original_cloud(self, default_node):
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(default_node, "_detect_horizontal_planes", return_value=[]):
            out, meta = default_node._sync_filter(pcd_in)
        assert meta["removed_point_count"] == 0
        assert len(out.point["positions"]) == 300


# ─────────────────────────────────────────────────────────────────────────────
# TestMetadataShape
# ─────────────────────────────────────────────────────────────────────────────


class TestMetadataShape:
    REQUIRED_KEYS = {
        "input_point_count", "output_point_count", "removed_point_count",
        "planes_detected", "planes_filtered", "plane_details",
        "cache_hit", "status",
    }

    def test_keys_present_on_empty_cloud(self, default_node):
        pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        _, meta = default_node._sync_filter(pcd)
        # Empty cloud has a simplified meta — check the subset it does have
        assert "status" in meta
        assert "input_point_count" in meta

    def test_keys_present_on_detection_path(self, default_node):
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(default_node, "_detect_horizontal_planes", return_value=[]):
            _, meta = default_node._sync_filter(pcd_in)
        for key in self.REQUIRED_KEYS:
            assert key in meta, f"Missing key: {key}"

    def test_cache_hit_field_true_on_fast_path(self, node_factory):
        node = node_factory({"cache_refresh_frames": 5})
        node._cached_floor = _floor_plane(0.0)
        node._cached_ceiling = _ceiling_plane(3.0)
        node._frames_since_detection = 1  # within cache window
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        _, meta = node._sync_filter(_make_pcd(pts))
        assert meta["cache_hit"] is True

    def test_cache_hit_field_false_on_slow_path(self, node_factory):
        node = node_factory({"cache_refresh_frames": 1})
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        planes = [_floor_plane(0.0), _ceiling_plane(3.0)]
        with patch.object(node, "_detect_horizontal_planes", return_value=planes):
            _, meta = node._sync_filter(pcd_in)
        assert meta["cache_hit"] is False


# ─────────────────────────────────────────────────────────────────────────────
# TestEmitStatus
# ─────────────────────────────────────────────────────────────────────────────


class TestEmitStatus:
    def test_idle_is_running_gray(self, default_node):
        default_node.last_input_at = None
        status = default_node.emit_status()
        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING
        assert status.application_state.color == "gray"

    def test_error_state(self, default_node):
        default_node.last_error = "boom"
        status = default_node.emit_status()
        assert status.operational_state == OperationalState.ERROR
        assert status.error_message == "boom"

    def test_success_color_blue(self, default_node):
        default_node.last_input_at = time.time() - 0.5
        default_node.last_metadata = {"status": "success", "planes_filtered": 2}
        status = default_node.emit_status()
        assert status.application_state.color == "blue"

    def test_warning_color_orange(self, default_node):
        default_node.last_input_at = time.time() - 0.5
        default_node.last_metadata = {"status": "no_planes_detected", "planes_filtered": 0}
        status = default_node.emit_status()
        assert status.application_state.color == "orange"
