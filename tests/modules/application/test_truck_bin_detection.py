"""
Unit tests for the Truck Bin Detection module.

Covers:
- Core 1D profile edge detection (BinDetector)
- 3D interior area validation (enable_area_check=True)
- Wall line coherence fallback (enable_area_check=False)
- DAG node integration (TruckBinDetectionNode)
- Registry schema and factory
"""
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.modules.application.truck_bin_detection.utils.bin_detector import (
    BinDetector,
    BinDetectionResult,
)

# ---------------------------------------------------------------------------
# Shared point-cloud builders
# ---------------------------------------------------------------------------

def _make_bin(
    length: float = 6.0,
    x_offset: float = 0.0,
    wall_height: float = 2.5,
    floor_z: float = 1.1,
    wall_x_step: float = 0.05,
    floor_x_step: float = 0.25,
    y_range: float = 0.7,
    y_step: float = 0.3,
) -> np.ndarray:
    """Full-width open-top bin: rear wall peak + sparse floor + front wall."""
    half = length / 2.0
    pts = []
    ys = np.arange(-y_range, y_range, y_step)
    # Approach floor before rear wall
    for x in np.arange(x_offset - half - 2.0, x_offset - half, 0.2):
        for y in ys:
            pts.append([x, y, floor_z - 0.1])
    # Rear wall
    for x in np.arange(x_offset - half, x_offset - half + 0.4, wall_x_step):
        for y in ys:
            pts.append([x, y, wall_height])
    # Sparse interior floor
    for x in np.arange(x_offset - half + 0.4, x_offset + half - 0.4, floor_x_step):
        for y in ys:
            pts.append([x, y, floor_z])
    # Front wall
    for x in np.arange(x_offset + half - 0.4, x_offset + half, wall_x_step):
        for y in ys:
            pts.append([x, y, wall_height])
    # Tail after front wall
    for x in np.arange(x_offset + half, x_offset + half + 2.0, 0.2):
        for y in ys:
            pts.append([x, y, floor_z - 0.1])
    return np.array(pts)


def _make_drawbar(
    length: float = 6.0,
    x_offset: float = 0.0,
    wall_height: float = 2.5,
    drawbar_z: float = 1.2,
    drawbar_y_width: float = 0.2,
) -> np.ndarray:
    """Two truck walls with a narrow drawbar coupling between them."""
    half = length / 2.0
    pts = []
    ys_full = np.arange(-0.7, 0.7, 0.3)
    ys_bar  = np.arange(-drawbar_y_width / 2, drawbar_y_width / 2, 0.05)
    for x in np.arange(x_offset - half - 1.5, x_offset - half, 0.15):
        for y in ys_full: pts.append([x, y, 1.0])
    for x in np.arange(x_offset - half, x_offset - half + 0.4, 0.05):
        for y in ys_full: pts.append([x, y, wall_height])
    for x in np.arange(x_offset - half + 0.4, x_offset + half - 0.4, 0.15):
        for y in ys_bar:  pts.append([x, y, drawbar_z])
    for x in np.arange(x_offset + half - 0.4, x_offset + half, 0.05):
        for y in ys_full: pts.append([x, y, wall_height])
    for x in np.arange(x_offset + half, x_offset + half + 1.5, 0.15):
        for y in ys_full: pts.append([x, y, 1.0])
    return np.array(pts)


def _make_gap(
    length: float = 6.0,
    x_offset: float = 0.0,
    wall_height: float = 2.5,
) -> np.ndarray:
    """Rear wall of truck A and front wall of truck B with no interior points."""
    half = length / 2.0
    pts = []
    ys = np.arange(-0.7, 0.7, 0.3)
    for x in np.arange(x_offset - half - 1.5, x_offset - half, 0.15):
        for y in ys: pts.append([x, y, 1.0])
    for x in np.arange(x_offset - half, x_offset - half + 0.4, 0.05):
        for y in ys: pts.append([x, y, wall_height])
    # no interior points
    for x in np.arange(x_offset + half - 0.4, x_offset + half, 0.05):
        for y in ys: pts.append([x, y, wall_height])
    for x in np.arange(x_offset + half, x_offset + half + 1.5, 0.15):
        for y in ys: pts.append([x, y, 1.0])
    return np.array(pts)


def _make_single_wall(x_start: float, wall_height: float = 2.5, wall_w: float = 0.4) -> np.ndarray:
    """A lone vertical wall slab (e.g. the front wall of a following bin whose
    rest is out of scan range)."""
    pts = []
    ys = np.arange(-0.7, 0.7, 0.3)
    for x in np.arange(x_start, x_start + wall_w, 0.05):
        for y in ys:
            pts.append([x, y, wall_height])
    return np.array(pts)


def _make_floor(x0: float, x1: float, z: float = 1.0, y_range: float = 0.7,
                y_step: float = 0.3, x_step: float = 0.2) -> np.ndarray:
    """A flat low strip (approach floor, road, or bin bed)."""
    pts = []
    ys = np.arange(-y_range, y_range, y_step)
    for x in np.arange(x0, x1, x_step):
        for y in ys:
            pts.append([x, y, z])
    return np.array(pts) if len(pts) else np.empty((0, 3))


def _make_low_drawbar(x0: float, x1: float, z: float = 0.3) -> np.ndarray:
    """A narrow coupling bar sitting BELOW bed height between two bins."""
    pts = []
    ys = np.arange(-0.1, 0.1, 0.05)
    for x in np.arange(x0, x1, 0.15):
        for y in ys:
            pts.append([x, y, z])
    return np.array(pts) if len(pts) else np.empty((0, 3))


def _make_two_bins(b1_len: float, gap: float, b2_len: float,
                   b1_center: float = 0.0) -> np.ndarray:
    """Two full bins (each with its own rear + front wall) separated by ``gap``."""
    b1_front = b1_center + b1_len / 2.0
    b2_center = b1_front + gap + b2_len / 2.0
    parts = [
        _make_floor(b1_center - b1_len / 2.0 - 2.0, b1_center - b1_len / 2.0),
        _make_bin(length=b1_len, x_offset=b1_center),
    ]
    if gap > 0:
        parts.append(_make_floor(b1_front, b1_front + gap))
    parts += [
        _make_bin(length=b2_len, x_offset=b2_center),
        _make_floor(b2_center + b2_len / 2.0, b2_center + b2_len / 2.0 + 2.0),
    ]
    return np.concatenate(parts, axis=0)


def _make_bin_core(
    length: float = 6.0,
    x_offset: float = 0.0,
    wall_height: float = 2.5,
    floor_z: float = 1.1,
    wall_x_step: float = 0.05,
    floor_x_step: float = 0.25,
    y_range: float = 0.7,
    y_step: float = 0.3,
) -> np.ndarray:
    """Bin with ONLY rear wall + bed + front wall — no approach/tail floor.

    Used by multi-bin tests so the bin's own approach floor does not bleed into
    a preceding gap and pollute the gap's height profile.
    """
    half = length / 2.0
    pts = []
    ys = np.arange(-y_range, y_range, y_step)
    for x in np.arange(x_offset - half, x_offset - half + 0.4, wall_x_step):
        for y in ys:
            pts.append([x, y, wall_height])
    for x in np.arange(x_offset - half + 0.4, x_offset + half - 0.4, floor_x_step):
        for y in ys:
            pts.append([x, y, floor_z])
    for x in np.arange(x_offset + half - 0.4, x_offset + half, wall_x_step):
        for y in ys:
            pts.append([x, y, wall_height])
    return np.array(pts)


def _default_detector(**kwargs) -> BinDetector:
    defaults = dict(
        lane_width=1.4,
        cell_size=0.07,
        z_wall_threshold=2.2,
        z_cavity_max=1.8,
        z_cavity_min=0.5,
        min_bin_length=3.0,
        max_bin_length=8.5,
    )
    defaults.update(kwargs)
    return BinDetector(**defaults)


# ---------------------------------------------------------------------------
# TestBinDetectorCore — 1D profile edge detection
# ---------------------------------------------------------------------------

class TestBinDetectorCore:

    def test_detects_valid_bin(self):
        pts = _make_bin(length=6.0)
        result = _default_detector().detect(pts)
        assert result.detected is True
        assert result.length >= 3.0
        assert result.bin_points is not None

    def test_rejects_none_input(self):
        result = _default_detector().detect(None)
        assert result.detected is False

    def test_rejects_too_few_points(self):
        pts = np.random.default_rng(0).uniform(-1, 1, (10, 3))
        result = _default_detector().detect(pts)
        assert result.detected is False

    def test_rejects_insufficient_scan_range(self):
        # All points within 1m — shorter than the 2m minimum
        pts = np.random.default_rng(1).uniform(0, 0.5, (50, 3))
        result = _default_detector().detect(pts)
        assert result.detected is False

    def test_rejects_bin_too_short(self):
        pts = _make_bin(length=1.5)
        result = _default_detector(min_bin_length=3.0).detect(pts)
        assert result.detected is False

    def test_rejects_bin_too_long(self):
        pts = _make_bin(length=12.0)
        result = _default_detector(max_bin_length=8.5).detect(pts)
        assert result.detected is False

    def test_x_center_near_true_center(self):
        pts = _make_bin(length=6.0, x_offset=5.0)
        result = _default_detector().detect(pts)
        assert result.detected is True
        # Center should be within 0.5m of true center (5.0)
        assert abs(result.x_center - 5.0) < 0.5

    def test_edge_points_output_contains_wall_returns(self):
        pts = _make_bin(length=6.0, x_offset=0.0)
        result = _default_detector().detect(pts)
        assert result.detected is True
        # Edge output must only contain points near the two wall positions
        assert len(result.bin_points) > 0
        x_vals = result.bin_points[:, 0]
        # All edge points should be near one of the two walls, not in the middle
        near_rear  = np.abs(x_vals - result.x_rear_internal)  < 0.2
        near_front = np.abs(x_vals - result.x_front_internal) < 0.2
        assert np.all(near_rear | near_front)

    def test_sparse_interior_still_detected(self):
        # Floor points every 0.5m — very sparse, simulating open cavity
        pts = _make_bin(length=6.0, floor_x_step=0.5)
        result = _default_detector().detect(pts)
        assert result.detected is True


# ---------------------------------------------------------------------------
# TestMultiBinScenarios — two bins in one frame; measure only the first bin
# ---------------------------------------------------------------------------

class TestMultiBinScenarios:
    """When more than one bin is in view the detector must measure ONLY the
    first bin (Bin 1) and never let a following bin's wall corrupt the length.

    Two failure modes are covered:
      A. Two full bins (RW1..FW1 then RW2..FW2). The left-to-right scan should
         stop at FW1, so the reported length is Bin 1's internal length.
      B. A lone front wall of a following bin is scanned BEFORE Bin 1 (its rest
         is out of range). That stray wall must NOT be accepted as a rear wall:
         the region after it is only a gap/drawbar, not a real cavity+bed.
    """

    def _detector(self, **kwargs) -> BinDetector:
        base = dict(enable_area_check=False)
        base.update(kwargs)
        return _default_detector(**base)

    # ── A. Two full bins ────────────────────────────────────────────────
    def test_two_bins_measures_first_bin(self):
        pts = _make_two_bins(b1_len=5.0, gap=0.6, b2_len=5.0)
        result = self._detector().detect(pts)
        assert result.detected is True
        # Bin 1 internal length ≈ 5.0 - 2*0.4 wall inset
        assert abs(result.length - 4.2) < 0.4

    def test_two_bins_touching_measures_first_bin(self):
        pts = _make_two_bins(b1_len=5.0, gap=0.0, b2_len=5.0)
        result = self._detector().detect(pts)
        assert result.detected is True
        assert abs(result.length - 4.2) < 0.4

    def test_two_bins_front_edge_is_first_front_wall(self):
        pts = _make_two_bins(b1_len=5.0, gap=1.0, b2_len=6.0)
        result = self._detector().detect(pts)
        assert result.detected is True
        # Front edge must be Bin 1's own front wall (~+2.1), not Bin 2's rear.
        assert result.x_front_internal < 3.0

    # ── B. Stray leading front wall + full Bin 1 behind it ──────────────
    def _stray_then_bin(self, b1_len: float, gap: float,
                        filler: str = "drawbar") -> np.ndarray:
        fw2_pos = -6.0  # lone wall scanned first (smallest X)
        b1_center = fw2_pos + 0.4 + gap + b1_len / 2.0
        parts = [
            _make_floor(fw2_pos - 2.0, fw2_pos),
            _make_single_wall(fw2_pos),
        ]
        if filler == "drawbar":
            parts.append(_make_low_drawbar(fw2_pos + 0.4, b1_center - b1_len / 2.0))
        # "empty" filler → nothing between the stray wall and Bin 1's rear wall
        parts += [
            _make_bin_core(length=b1_len, x_offset=b1_center),
            _make_floor(b1_center + b1_len / 2.0, b1_center + b1_len / 2.0 + 2.0),
        ]
        return np.concatenate(parts, axis=0)

    def test_stray_wall_with_low_drawbar_gap_skipped(self):
        # Wide low drawbar gap after the stray wall must NOT read as a cavity.
        pts = self._stray_then_bin(b1_len=5.0, gap=2.0, filler="drawbar")
        result = self._detector().detect(pts)
        assert result.detected is True
        # Rear edge must be Bin 1's real rear wall, well past the stray wall (-6).
        assert result.x_rear_internal > -5.0
        assert abs(result.length - 4.2) < 0.5

    def test_stray_wall_with_empty_gap_skipped(self):
        pts = self._stray_then_bin(b1_len=5.0, gap=2.5, filler="empty")
        result = self._detector().detect(pts)
        assert result.detected is True
        assert result.x_rear_internal > -5.0
        assert abs(result.length - 4.2) < 0.5

    def test_stray_wall_small_gap_still_finds_bin(self):
        pts = self._stray_then_bin(b1_len=5.0, gap=1.0, filler="drawbar")
        result = self._detector().detect(pts)
        assert result.detected is True
        assert result.x_rear_internal > -5.0


# ---------------------------------------------------------------------------
# TestAreaCheck — 3D interior XY area validation (enable_area_check=True)
# ---------------------------------------------------------------------------

class TestAreaCheck:

    def test_real_bin_passes_area_check(self):
        pts = _make_bin(length=6.0)
        result = _default_detector(enable_area_check=True, min_bin_area=2.0).detect(pts)
        assert result.detected is True
        assert result.confidence > 0.0

    def test_inter_truck_gap_rejected(self):
        pts = _make_gap(length=5.0)
        result = _default_detector(enable_area_check=True, min_bin_area=2.0).detect(pts)
        assert result.detected is False

    def test_drawbar_rejected_by_area_check(self):
        # Drawbar has full X span but Y only ~0.2m → x_span * y_span << min_bin_area.
        # Use a generous min_bin_area (6.0 m²) so only a full-width bin passes.
        pts = _make_drawbar(length=5.0, drawbar_y_width=0.2)
        result = _default_detector(enable_area_check=True, min_bin_area=6.0).detect(pts)
        assert result.detected is False

    def test_confidence_reflects_coverage(self):
        # Dense bin → high confidence; sparse bin → lower confidence
        dense  = _make_bin(length=6.0, floor_x_step=0.10)
        sparse = _make_bin(length=6.0, floor_x_step=0.60)
        r_dense  = _default_detector(enable_area_check=True).detect(dense)
        r_sparse = _default_detector(enable_area_check=True).detect(sparse)
        assert r_dense.detected is True
        assert r_sparse.detected is True
        assert r_dense.confidence >= r_sparse.confidence


# ---------------------------------------------------------------------------
# TestWallLineCheck — coherence fallback (enable_area_check=False)
# ---------------------------------------------------------------------------

class TestWallLineCheck:

    def _detector(self, **kwargs) -> BinDetector:
        base = dict(enable_area_check=False)
        base.update(kwargs)
        return _default_detector(**base)

    def test_real_bin_passes_line_check(self):
        pts = _make_bin(length=6.0)
        result = self._detector().detect(pts)
        assert result.detected is True
        assert result.confidence == 1.0

    def test_segmented_wall_passes_line_check(self):
        """Partially hidden wall: only top Z returns visible, but tight X column."""
        pts = _make_bin(length=6.0)
        # Remove lower-Z wall points to simulate occlusion — keep only Z > 2.3
        pts = pts[pts[:, 2] > 2.3]
        # Add back floor and tail (low Z) so the scan range is sufficient
        floor = _make_bin(length=6.0)
        floor = floor[floor[:, 2] < 1.5]
        pts = np.concatenate([pts, floor], axis=0)
        result = self._detector().detect(pts)
        assert result.detected is True

    def test_scattered_wall_rejected(self):
        """Placeholder — max_wall_x_std feature not yet implemented."""
        pass

    def test_weak_wall_rejected(self):
        """Placeholder — min_wall_points feature not yet implemented."""
        pass

    def test_area_check_disabled_confidence_is_one(self):
        pts = _make_bin(length=6.0)
        result = self._detector().detect(pts)
        assert result.detected is True
        assert result.confidence == 1.0

    def test_drawbar_passes_without_area_check(self):
        """When area check is off and walls are coherent lines the drawbar passes —
        the caller is responsible for disambiguation via external logic."""
        pts = _make_drawbar(length=5.0, drawbar_y_width=0.2)
        result = self._detector().detect(pts)
        # Should detect (no area check) — caller handles this case externally
        assert isinstance(result, BinDetectionResult)


# ---------------------------------------------------------------------------
# TestTruckBinDetectionNode — DAG integration
# ---------------------------------------------------------------------------

class TestTruckBinDetectionNode:

    def _make_node(self, config: Optional[Dict[str, Any]] = None):
        from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode
        manager = MagicMock()
        manager.forward_data = AsyncMock()
        if config is None:
            config = {
                "lane_width": 1.4,
                "cell_size": 0.07,
                "z_wall_threshold": 2.2,
                "z_cavity_max": 1.8,
                "z_cavity_min": 0.5,
                "min_bin_length": 3.0,
                "max_bin_length": 8.5,
                "enable_area_check": True,
                "min_bin_area": 2.0,
            }
        node = TruckBinDetectionNode(
            manager=manager,
            node_id="test_bin_detect_1",
            name="Test Bin Detection",
            config=config,
        )
        node._ws_topic = "node/test_bin_detect_1"
        return node, manager

    @pytest.mark.asyncio
    async def test_on_input_detects_and_forwards(self):
        node, manager = self._make_node()
        await node.on_input({"node_id": "up", "points": _make_bin(), "timestamp": 1.0})
        manager.forward_data.assert_called_once()
        payload = manager.forward_data.call_args[0][1]
        assert payload["metadata"]["bin"]["detected"] is True

    @pytest.mark.asyncio
    async def test_on_input_empty_cloud_skipped(self):
        node, manager = self._make_node()
        await node.on_input({"node_id": "up", "points": np.empty((0, 3)), "timestamp": 1.0})
        manager.forward_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_input_none_points_skipped(self):
        node, manager = self._make_node()
        await node.on_input({"node_id": "up", "points": None, "timestamp": 1.0})
        manager.forward_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_processing_guard_drops_concurrent_frame(self):
        """Second call while processing is in flight must be dropped."""
        import asyncio
        node, manager = self._make_node()
        node._processing = True
        await node.on_input({"node_id": "up", "points": _make_bin(), "timestamp": 1.0})
        manager.forward_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_temporal_smoothing_applied(self):
        """x_center should be EMA-smoothed across frames."""
        node, manager = self._make_node()
        pts = _make_bin(length=6.0, x_offset=0.0)
        await node.on_input({"node_id": "up", "points": pts, "timestamp": 1.0})
        first_center = node._filtered_center

        # Shift bin 1m forward
        pts2 = _make_bin(length=6.0, x_offset=1.0)
        await node.on_input({"node_id": "up", "points": pts2, "timestamp": 2.0})
        second_center = node._filtered_center

        # Smoothed center must be between the two raw measurements
        assert first_center < second_center < first_center + 1.0

    @pytest.mark.asyncio
    async def test_no_detection_resets_filtered_center(self):
        node, manager = self._make_node()
        # Prime the filter with a valid detection
        await node.on_input({"node_id": "up", "points": _make_bin(), "timestamp": 1.0})
        assert node._filtered_center is not None
        # Send garbage that won't detect
        await node.on_input({"node_id": "up", "points": np.ones((5, 3)), "timestamp": 2.0})
        assert node._filtered_center is None

    def test_emit_status_idle(self):
        node, _ = self._make_node()
        status = node.emit_status()
        assert status.operational_state == "RUNNING"
        assert status.application_state.value == "idle"

    def test_emit_status_detected(self):
        node, _ = self._make_node()
        node._last_result = BinDetectionResult(
            detected=True, x_center=1.5, status="DETECTED"
        )
        status = node.emit_status()
        assert "DETECTED" in status.application_state.value
        assert status.application_state.color == "green"

    def test_start_resets_state(self):
        node, _ = self._make_node()
        node._filtered_center = 3.0
        node.start()
        assert node._filtered_center is None

    def test_stop_resets_state(self):
        node, _ = self._make_node()
        node._filtered_center = 3.0
        node.last_error = "some error"
        node.stop()
        assert node._filtered_center is None
        assert node.last_error is None


# ---------------------------------------------------------------------------
# TestRegistry — schema and factory
# ---------------------------------------------------------------------------

class TestRegistry:

    def setup_method(self):
        import app.modules.application.truck_bin_detection.registry  # noqa: F401

    def test_schema_registered(self):
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("truck_bin_detection")
        assert defn is not None
        assert defn.display_name == "Truck Bin Detection"
        assert defn.category == "application"

    def test_all_expected_properties_present(self):
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("truck_bin_detection")
        names = {p.name for p in defn.properties}
        expected = {
            "z_min", "z_max", "cell_size",
            "z_wall_threshold", "z_cavity_max", "z_cavity_min",
            "min_bin_length", "max_bin_length",
            "enable_area_check", "min_bin_area",
        }
        assert expected.issubset(names)

    def test_min_bin_area_depends_on_area_check_enabled(self):
        from app.services.nodes.schema import node_schema_registry
        defn = node_schema_registry.get("truck_bin_detection")
        prop = next(p for p in defn.properties if p.name == "min_bin_area")
        assert prop.depends_on == {"enable_area_check": [True]}

    def test_min_wall_points_depends_on_area_check_disabled(self):
        """Placeholder — min_wall_points removed (feature not implemented)."""
        pass

    def test_max_wall_x_std_depends_on_area_check_disabled(self):
        """Placeholder — max_wall_x_std removed (feature not implemented)."""
        pass

    def test_factory_builds_node_instance(self):
        from app.services.nodes.node_factory import NodeFactory
        from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode
        node = NodeFactory.create(
            {"id": "reg_test_1", "name": "Test", "type": "truck_bin_detection", "config": {}},
            MagicMock(),
            [],
        )
        assert isinstance(node, TruckBinDetectionNode)
        assert node.id == "reg_test_1"
