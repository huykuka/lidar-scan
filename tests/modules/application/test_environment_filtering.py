"""
TDD test suite for EnvironmentFilteringNode — application-level DAG node.

References:
  - backend-tasks.md Phase 4 (unit test spec)
  - api-spec.md § 5 (metadata contract)
  - technical.md § 4, 5 (class design, algorithm)
  - requirements.md (acceptance criteria)
"""
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import open3d as o3d
import pytest

from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
from app.schemas.status import NodeStatusUpdate, OperationalState


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_pcd(points: np.ndarray) -> o3d.t.geometry.PointCloud:
    """Create a tensor PointCloud from (N, 3) numpy array."""
    pcd = o3d.t.geometry.PointCloud()
    pcd.point["positions"] = o3d.core.Tensor(
        points.astype(np.float32), dtype=o3d.core.Dtype.Float32
    )
    return pcd


def _make_floor_cloud(n_floor: int = 2000, n_other: int = 3000) -> np.ndarray:
    """Synthetic cloud: floor at Z=0 + random points above."""
    rng = np.random.default_rng(42)
    floor = rng.uniform(-5, 5, (n_floor, 2))
    floor_pts = np.column_stack([floor, np.zeros(n_floor)])

    other = rng.uniform(-5, 5, (n_other, 2))
    other_z = rng.uniform(0.5, 2.5, n_other)
    other_pts = np.column_stack([other, other_z])

    return np.vstack([floor_pts, other_pts]).astype(np.float32)


def _make_floor_and_ceiling_cloud(
    n_floor: int = 2000, n_ceil: int = 2000, n_other: int = 3000
) -> np.ndarray:
    """Synthetic cloud: floor at Z=0, ceiling at Z=3, random between."""
    rng = np.random.default_rng(42)
    floor = np.column_stack([rng.uniform(-5, 5, (n_floor, 2)), np.zeros(n_floor)])
    ceil_ = np.column_stack([rng.uniform(-5, 5, (n_ceil, 2)), np.full(n_ceil, 3.0)])
    other = np.column_stack(
        [rng.uniform(-5, 5, (n_other, 2)), rng.uniform(0.5, 2.5, n_other)]
    )
    return np.vstack([floor, ceil_, other]).astype(np.float32)


DEFAULT_CONFIG: Dict[str, Any] = {
    "throttle_ms": 0,
    "voxel_downsample_size": 0.01,
    "normal_variance_threshold_deg": 60.0,
    "coplanarity_deg": 75.0,
    "outlier_ratio": 0.75,
    "min_plane_edge_length": 0.0,
    "min_num_points": 0,
    "knn": 30,
    "vertical_tolerance_deg": 15.0,
    "floor_height_min": -0.5,
    "floor_height_max": 0.5,
    "ceiling_height_min": 2.0,
    "ceiling_height_max": 4.0,
    "min_plane_area": 1.0,
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_manager() -> Mock:
    manager = Mock()
    manager.forward_data = AsyncMock()
    return manager


@pytest.fixture
def default_node(mock_manager: Mock) -> EnvironmentFilteringNode:
    return EnvironmentFilteringNode(
        manager=mock_manager,
        node_id="ef-001",
        name="Test EF Node",
        config=DEFAULT_CONFIG.copy(),
        throttle_ms=0,
    )


@pytest.fixture
def node_factory(mock_manager: Mock):
    """Factory for creating nodes with custom config overrides."""
    def _make(config_overrides: Dict[str, Any] = None):
        cfg = DEFAULT_CONFIG.copy()
        if config_overrides:
            cfg.update(config_overrides)
        return EnvironmentFilteringNode(
            manager=mock_manager,
            node_id="ef-test",
            name="Test EF Node",
            config=cfg,
            throttle_ms=0,
        )
    return _make


# ─────────────────────────────────────────────────────────────────────────────
# TestInstantiation
# ─────────────────────────────────────────────────────────────────────────────


class TestInstantiation:
    def test_id_stored(self, default_node: EnvironmentFilteringNode) -> None:
        assert default_node.id == "ef-001"

    def test_name_stored(self, default_node: EnvironmentFilteringNode) -> None:
        assert default_node.name == "Test EF Node"

    def test_voxel_downsample_size_default(self, default_node: EnvironmentFilteringNode) -> None:
        assert default_node.voxel_downsample_size == 0.01

    def test_processing_flag_starts_false(self, default_node: EnvironmentFilteringNode) -> None:
        assert default_node._processing is False

    def test_last_error_starts_none(self, default_node: EnvironmentFilteringNode) -> None:
        assert default_node.last_error is None

    def test_op_instantiated(self, default_node: EnvironmentFilteringNode) -> None:
        from app.modules.pipeline.operations.patch_plane_segmentation.node import PatchPlaneSegmentation
        assert isinstance(default_node._op, PatchPlaneSegmentation)

    def test_floor_height_range_set(self, default_node: EnvironmentFilteringNode) -> None:
        assert default_node.floor_height_range == (-0.5, 0.5)

    def test_ceiling_height_range_set(self, default_node: EnvironmentFilteringNode) -> None:
        assert default_node.ceiling_height_range == (2.0, 4.0)


# ─────────────────────────────────────────────────────────────────────────────
# TestParamValidation
# ─────────────────────────────────────────────────────────────────────────────


class TestParamValidation:
    def test_vertical_tolerance_too_small(self, mock_manager: Mock) -> None:
        cfg = DEFAULT_CONFIG.copy()
        cfg["vertical_tolerance_deg"] = 0.5
        with pytest.raises(ValueError, match="vertical_tolerance_deg"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)

    def test_vertical_tolerance_too_large(self, mock_manager: Mock) -> None:
        cfg = DEFAULT_CONFIG.copy()
        cfg["vertical_tolerance_deg"] = 46
        with pytest.raises(ValueError, match="vertical_tolerance_deg"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)

    def test_min_plane_area_too_small(self, mock_manager: Mock) -> None:
        cfg = DEFAULT_CONFIG.copy()
        cfg["min_plane_area"] = 0.05
        with pytest.raises(ValueError, match="min_plane_area"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)

    def test_floor_height_range_inverted(self, mock_manager: Mock) -> None:
        cfg = DEFAULT_CONFIG.copy()
        cfg["floor_height_min"] = 1.0
        cfg["floor_height_max"] = -1.0
        with pytest.raises(ValueError, match="floor_height_range"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)

    def test_ceiling_height_range_inverted(self, mock_manager: Mock) -> None:
        cfg = DEFAULT_CONFIG.copy()
        cfg["ceiling_height_min"] = 5.0
        cfg["ceiling_height_max"] = 2.0
        with pytest.raises(ValueError, match="ceiling_height_range"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)

    def test_voxel_downsample_negative(self, mock_manager: Mock) -> None:
        cfg = DEFAULT_CONFIG.copy()
        cfg["voxel_downsample_size"] = -0.01
        with pytest.raises(ValueError, match="voxel_downsample_size"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)

    def test_voxel_downsample_too_large(self, mock_manager: Mock) -> None:
        cfg = DEFAULT_CONFIG.copy()
        cfg["voxel_downsample_size"] = 1.5
        with pytest.raises(ValueError, match="voxel_downsample_size"):
            EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)

    def test_valid_boundary_voxel_zero(self, mock_manager: Mock) -> None:
        """voxel_downsample_size=0.0 must be valid (disables downsampling)."""
        cfg = DEFAULT_CONFIG.copy()
        cfg["voxel_downsample_size"] = 0.0
        node = EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)
        assert node.voxel_downsample_size == 0.0

    def test_valid_boundary_voxel_one(self, mock_manager: Mock) -> None:
        """voxel_downsample_size=1.0 must be valid (upper boundary)."""
        cfg = DEFAULT_CONFIG.copy()
        cfg["voxel_downsample_size"] = 1.0
        node = EnvironmentFilteringNode(manager=mock_manager, node_id="ef", name="n", config=cfg)
        assert node.voxel_downsample_size == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# TestEmptyInput
# ─────────────────────────────────────────────────────────────────────────────


class TestEmptyInput:
    def test_empty_cloud_returns_pass_through(self, default_node: EnvironmentFilteringNode) -> None:
        empty_pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        pcd_out, meta = default_node._sync_filter(empty_pcd)
        assert meta["status"] == "warning_pass_through"

    def test_empty_cloud_returns_same_cloud(self, default_node: EnvironmentFilteringNode) -> None:
        empty_pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        pcd_out, meta = default_node._sync_filter(empty_pcd)
        assert len(pcd_out.point["positions"]) == 0

    def test_empty_cloud_no_exception(self, default_node: EnvironmentFilteringNode) -> None:
        empty_pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        # Must not raise
        default_node._sync_filter(empty_pcd)


# ─────────────────────────────────────────────────────────────────────────────
# TestNoPlanes
# ─────────────────────────────────────────────────────────────────────────────


class TestNoPlanes:
    def test_no_planes_returns_status_no_planes(self, default_node: EnvironmentFilteringNode) -> None:
        """Random spherical cloud → no dominant planar patches → no_planes_detected."""
        rng = np.random.default_rng(0)
        pts = rng.standard_normal((500, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)

        with patch.object(default_node, "_apply_with_boxes", return_value=([], np.full(len(pts), -1, dtype=np.int32), pts)):
            pcd_out, meta = default_node._sync_filter(pcd_in)

        assert meta["status"] == "no_planes_detected"

    def test_no_planes_returns_original_cloud(self, default_node: EnvironmentFilteringNode) -> None:
        rng = np.random.default_rng(0)
        pts = rng.standard_normal((500, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)

        with patch.object(default_node, "_apply_with_boxes", return_value=([], np.full(len(pts), -1, dtype=np.int32), pts)):
            pcd_out, meta = default_node._sync_filter(pcd_in)

        assert meta["output_point_count"] == 500


# ─────────────────────────────────────────────────────────────────────────────
# TestNoValidPlanes
# ─────────────────────────────────────────────────────────────────────────────


class TestNoValidPlanes:
    def test_planes_but_none_valid_pass_through(self, node_factory) -> None:
        """Planes detected but none pass validation → warning_pass_through."""
        node = node_factory({"min_plane_area": 1000.0})  # Extremely high area threshold
        pts = _make_floor_cloud(n_floor=500, n_other=500)
        pcd_in = _make_pcd(pts)

        # Patch _classify_plane to always return None
        with patch.object(node, "_classify_plane", return_value=None):
            # Provide fake oboxes
            fake_obox = MagicMock()
            fake_obox.center = np.array([0.0, 0.0, 0.0])
            fake_obox.extent = np.array([10.0, 10.0, 0.1])
            fake_obox.R = np.eye(3)
            n = len(pts)
            with patch.object(node, "_apply_with_boxes", return_value=([fake_obox], np.zeros(n, dtype=np.int32), pts)):
                pcd_out, meta = node._sync_filter(pcd_in)

        assert meta["status"] == "warning_pass_through"
        assert meta["planes_filtered"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# TestOrientationCheck
# ─────────────────────────────────────────────────────────────────────────────


class TestOrientationCheck:
    def _make_obox_with_normal(self, normal_vec: np.ndarray) -> MagicMock:
        """Create a mock OBB whose R[:, 2] is the given normal vector."""
        obox = MagicMock()
        # Build rotation matrix: Z column = normal
        normal = normal_vec / np.linalg.norm(normal_vec)
        R = np.eye(3)
        R[:, 2] = normal
        obox.R = R
        obox.center = np.array([0.0, 0.0, 0.1])  # floor height
        obox.extent = np.array([5.0, 5.0, 0.1])
        return obox

    def test_perfectly_vertical_normal_passes(self, default_node: EnvironmentFilteringNode) -> None:
        obox = self._make_obox_with_normal(np.array([0.0, 0.0, 1.0]))
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is not None

    def test_slightly_tilted_passes_within_tolerance(self, default_node: EnvironmentFilteringNode) -> None:
        # 10° tilt, tolerance=15° → should pass
        import math
        angle = math.radians(10)
        normal = np.array([np.sin(angle), 0, np.cos(angle)])
        obox = self._make_obox_with_normal(normal)
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is not None

    def test_beyond_tolerance_fails(self, default_node: EnvironmentFilteringNode) -> None:
        # 20° tilt, tolerance=15° → should fail
        import math
        angle = math.radians(20)
        normal = np.array([np.sin(angle), 0, np.cos(angle)])
        obox = self._make_obox_with_normal(normal)
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# TestPositionCheck
# ─────────────────────────────────────────────────────────────────────────────


class TestPositionCheck:
    def _make_obox_at_z(self, z: float) -> MagicMock:
        obox = MagicMock()
        obox.R = np.eye(3)
        obox.center = np.array([0.0, 0.0, z])
        obox.extent = np.array([5.0, 5.0, 0.1])
        return obox

    def test_floor_z_within_range_passes(self, default_node: EnvironmentFilteringNode) -> None:
        obox = self._make_obox_at_z(0.1)
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is not None

    def test_floor_z_outside_range_fails(self, default_node: EnvironmentFilteringNode) -> None:
        obox = self._make_obox_at_z(1.5)  # Outside floor [-0.5, 0.5] AND ceiling [2.0, 4.0]
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is None

    def test_ceiling_z_within_range_passes(self, default_node: EnvironmentFilteringNode) -> None:
        obox = self._make_obox_at_z(2.5)
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is not None

    def test_ceiling_z_outside_range_fails(self, default_node: EnvironmentFilteringNode) -> None:
        obox = self._make_obox_at_z(5.0)
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# TestSizeCheck
# ─────────────────────────────────────────────────────────────────────────────


class TestSizeCheck:
    def _make_obox_with_extent(self, extents: tuple) -> MagicMock:
        obox = MagicMock()
        obox.R = np.eye(3)
        obox.center = np.array([0.0, 0.0, 0.1])
        obox.extent = np.array(extents)
        return obox

    def test_large_area_passes(self, default_node: EnvironmentFilteringNode) -> None:
        obox = self._make_obox_with_extent((10.0, 10.0, 0.1))  # area=100m²
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is not None

    def test_small_area_fails(self, default_node: EnvironmentFilteringNode) -> None:
        obox = self._make_obox_with_extent((0.3, 0.3, 0.1))  # area=0.09m² < 1.0m²
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# TestMultiCriteriaAND
# ─────────────────────────────────────────────────────────────────────────────


class TestMultiCriteriaAND:
    def test_passes_orientation_and_position_but_fails_size(self, default_node: EnvironmentFilteringNode) -> None:
        """All 3 criteria must pass. Failing size alone → None."""
        obox = MagicMock()
        obox.R = np.eye(3)
        obox.center = np.array([0.0, 0.0, 0.1])  # floor position ✓
        obox.extent = np.array([0.2, 0.2, 0.05])  # area=0.04m² < 1.0 ✗
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is None

    def test_all_criteria_pass(self, default_node: EnvironmentFilteringNode) -> None:
        obox = MagicMock()
        obox.R = np.eye(3)
        obox.center = np.array([0.0, 0.0, 0.1])
        obox.extent = np.array([5.0, 5.0, 0.05])  # area=25m² ✓
        labels = np.zeros(100, dtype=np.int32)
        pts = np.zeros((100, 3), dtype=np.float32)
        result = default_node._classify_plane(obox, labels, pts, 0)
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# TestMetadataShape
# ─────────────────────────────────────────────────────────────────────────────


class TestMetadataShape:
    REQUIRED_KEYS = {
        "downsampling_enabled",
        "voxel_size",
        "points_before_downsample",
        "points_after_downsample",
        "input_point_count",
        "output_point_count",
        "removed_point_count",
        "planes_detected",
        "planes_filtered",
        "plane_details",
        "status",
    }

    def test_metadata_keys_present_on_pass_through(self, default_node: EnvironmentFilteringNode) -> None:
        empty_pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        _, meta = default_node._sync_filter(empty_pcd)
        for key in self.REQUIRED_KEYS:
            assert key in meta, f"Missing key: {key}"

    def test_metadata_keys_present_no_planes(self, default_node: EnvironmentFilteringNode) -> None:
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(default_node, "_apply_with_boxes", return_value=([], np.full(300, -1, dtype=np.int32), pts)):
            _, meta = default_node._sync_filter(pcd_in)
        for key in self.REQUIRED_KEYS:
            assert key in meta, f"Missing key: {key}"


# ─────────────────────────────────────────────────────────────────────────────
# TestEmitStatus
# ─────────────────────────────────────────────────────────────────────────────


class TestEmitStatusIdle:
    def test_idle_is_running_state(self, default_node: EnvironmentFilteringNode) -> None:
        status = default_node.emit_status()
        assert isinstance(status, NodeStatusUpdate)
        assert status.operational_state == OperationalState.RUNNING

    def test_idle_color_gray(self, default_node: EnvironmentFilteringNode) -> None:
        default_node.last_input_at = None
        status = default_node.emit_status()
        assert status.application_state.color == "gray"


class TestEmitStatusError:
    def test_error_state_when_last_error_set(self, default_node: EnvironmentFilteringNode) -> None:
        default_node.last_error = "test error"
        status = default_node.emit_status()
        assert status.operational_state == OperationalState.ERROR

    def test_error_message_propagated(self, default_node: EnvironmentFilteringNode) -> None:
        default_node.last_error = "test error"
        status = default_node.emit_status()
        assert status.error_message == "test error"


class TestEmitStatusWarning:
    def test_warning_color_orange_when_no_planes(self, default_node: EnvironmentFilteringNode) -> None:
        default_node.last_input_at = time.time() - 0.5
        default_node.last_metadata = {"status": "no_planes_detected", "planes_filtered": 0}
        status = default_node.emit_status()
        assert status.application_state.color == "orange"


# ─────────────────────────────────────────────────────────────────────────────
# TestDownsamplingDisabled
# ─────────────────────────────────────────────────────────────────────────────


class TestDownsamplingDisabled:
    def test_disabled_returns_false_in_meta(self, node_factory) -> None:
        node = node_factory({"voxel_downsample_size": 0.0})
        pts = np.random.default_rng(1).standard_normal((500, 3)).astype(np.float32)
        pcd = _make_pcd(pts)
        ds_pcd, meta = node._voxel_downsample(pcd)
        assert meta["downsampling_enabled"] is False

    def test_disabled_points_before_equals_after(self, node_factory) -> None:
        node = node_factory({"voxel_downsample_size": 0.0})
        pts = np.random.default_rng(1).standard_normal((500, 3)).astype(np.float32)
        pcd = _make_pcd(pts)
        ds_pcd, meta = node._voxel_downsample(pcd)
        assert meta["points_before_downsample"] == meta["points_after_downsample"]

    def test_disabled_returns_same_object(self, node_factory) -> None:
        node = node_factory({"voxel_downsample_size": 0.0})
        pts = np.random.default_rng(1).standard_normal((500, 3)).astype(np.float32)
        pcd = _make_pcd(pts)
        ds_pcd, meta = node._voxel_downsample(pcd)
        # Should return same object (no copy)
        assert ds_pcd is pcd

    def test_disabled_voxel_size_zero_in_meta(self, node_factory) -> None:
        node = node_factory({"voxel_downsample_size": 0.0})
        pts = np.random.default_rng(1).standard_normal((500, 3)).astype(np.float32)
        pcd = _make_pcd(pts)
        _, meta = node._voxel_downsample(pcd)
        assert meta["voxel_size"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# TestDownsamplingDefault
# ─────────────────────────────────────────────────────────────────────────────


class TestDownsamplingDefault:
    def test_default_downsampling_reduces_points(self, default_node: EnvironmentFilteringNode) -> None:
        # Dense grid of 10k points over 10x10m area
        rng = np.random.default_rng(42)
        pts = np.column_stack([rng.uniform(-5, 5, (10000, 2)), np.zeros(10000)]).astype(np.float32)
        pcd = _make_pcd(pts)
        ds_pcd, meta = default_node._voxel_downsample(pcd)
        assert meta["downsampling_enabled"] is True
        assert meta["points_after_downsample"] < meta["points_before_downsample"]

    def test_default_downsampling_meta_correct(self, default_node: EnvironmentFilteringNode) -> None:
        rng = np.random.default_rng(42)
        pts = np.column_stack([rng.uniform(-5, 5, (5000, 2)), np.zeros(5000)]).astype(np.float32)
        pcd = _make_pcd(pts)
        _, meta = default_node._voxel_downsample(pcd)
        assert meta["voxel_size"] == 0.01
        assert meta["points_before_downsample"] == 5000


# ─────────────────────────────────────────────────────────────────────────────
# TestDownsamplingAggressive
# ─────────────────────────────────────────────────────────────────────────────


class TestDownsamplingAggressive:
    def test_large_voxel_small_cloud_logs_warning(self, node_factory, caplog) -> None:
        """Very large voxel on sparse cloud → logs warning, no exception."""
        import logging
        node = node_factory({"voxel_downsample_size": 0.5})
        rng = np.random.default_rng(0)
        pts = rng.uniform(-1, 1, (200, 3)).astype(np.float32)  # Will reduce to < 100
        pcd = _make_pcd(pts)

        with caplog.at_level(logging.WARNING):
            ds_pcd, meta = node._voxel_downsample(pcd)

        # Should not raise, and meta should exist
        assert meta is not None


# ─────────────────────────────────────────────────────────────────────────────
# TestIndexMapping
# ─────────────────────────────────────────────────────────────────────────────


class TestIndexMapping:
    def test_exact_match_points_are_found(self, default_node: EnvironmentFilteringNode) -> None:
        """Downsampled points should map to nearby original points."""
        plane_pts_ds = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=np.float64)
        orig_pts = np.array([
            [0.005, 0.0, 0.0],   # within 0.005 radius of [0,0,0] → should match
            [5.0, 5.0, 5.0],     # far away → should NOT match
            [1.005, 0.0, 0.0],   # within 0.005 radius of [1,0,0] → should match
        ], dtype=np.float64)
        radius = 0.01
        mask = default_node._map_indices_to_original(plane_pts_ds, orig_pts, radius)
        assert mask[0] is np.bool_(True)
        assert mask[1] is np.bool_(False)
        assert mask[2] is np.bool_(True)

    def test_mask_length_equals_original(self, default_node: EnvironmentFilteringNode) -> None:
        plane_pts_ds = np.array([[0.0, 0.0, 0.0]], dtype=np.float64)
        orig_pts = np.random.default_rng(0).standard_normal((100, 3))
        mask = default_node._map_indices_to_original(plane_pts_ds, orig_pts, 0.1)
        assert len(mask) == 100


# ─────────────────────────────────────────────────────────────────────────────
# TestOutputAtOriginalResolution
# ─────────────────────────────────────────────────────────────────────────────


class TestOutputAtOriginalResolution:
    def test_output_resolution_matches_input_minus_removed(self, default_node: EnvironmentFilteringNode) -> None:
        """With downsampling, output = original_count - removed_count (not downsampled count)."""
        # This test uses patched sub-methods to isolate the output resolution guarantee
        n_orig = 1000
        n_removed = 200
        pts = np.random.default_rng(42).standard_normal((n_orig, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)

        # Simulate: first 200 points flagged for removal
        removal_mask = np.zeros(n_orig, dtype=bool)
        removal_mask[:n_removed] = True

        # Mock downsampling to return same cloud (disabled path)
        with patch.object(default_node, "_voxel_downsample",
                          return_value=(pcd_in, {"downsampling_enabled": False, "voxel_size": 0.0,
                                                  "points_before_downsample": n_orig,
                                                  "points_after_downsample": n_orig})):
            # Mock plane detection to return one fake plane
            fake_obox = MagicMock()
            fake_obox.R = np.eye(3)
            fake_obox.center = np.array([0.0, 0.0, 0.0])
            fake_obox.extent = np.array([5.0, 5.0, 0.1])

            labels = np.full(n_orig, -1, dtype=np.int32)
            labels[:n_removed] = 0  # first 200 pts belong to plane 0

            with patch.object(default_node, "_apply_with_boxes",
                               return_value=([fake_obox], labels, pts.astype(np.float64))):
                # Mock classify_plane to pass all criteria
                from app.modules.application.environment_filtering.node import PlaneInfo
                fake_plane = PlaneInfo(
                    plane_id=0, plane_type="floor",
                    normal=[0, 0, 1], centroid_z=0.0,
                    area=25.0, point_count=n_removed
                )
                with patch.object(default_node, "_classify_plane", return_value=fake_plane):
                    pcd_out, meta = default_node._sync_filter(pcd_in)

        assert meta["output_point_count"] == n_orig - n_removed
        assert meta["removed_point_count"] == n_removed


# ─────────────────────────────────────────────────────────────────────────────
# TestDownsamplingMetadata
# ─────────────────────────────────────────────────────────────────────────────


class TestDownsamplingMetadata:
    def test_downsampling_fields_in_no_planes_path(self, default_node: EnvironmentFilteringNode) -> None:
        """Downsampling fields must appear in metadata even on no_planes_detected path."""
        pts = np.random.default_rng(0).standard_normal((300, 3)).astype(np.float32)
        pcd_in = _make_pcd(pts)
        with patch.object(default_node, "_apply_with_boxes",
                          return_value=([], np.full(300, -1, dtype=np.int32), pts)):
            _, meta = default_node._sync_filter(pcd_in)

        assert "downsampling_enabled" in meta
        assert "voxel_size" in meta
        assert "points_before_downsample" in meta
        assert "points_after_downsample" in meta

    def test_downsampling_fields_in_warning_path(self, node_factory) -> None:
        """Downsampling metadata must be present even in warning_pass_through path."""
        node = node_factory()
        empty_pcd = _make_pcd(np.zeros((0, 3), dtype=np.float32))
        _, meta = node._sync_filter(empty_pcd)
        assert "downsampling_enabled" in meta
        assert "points_before_downsample" in meta
        assert "points_after_downsample" in meta
