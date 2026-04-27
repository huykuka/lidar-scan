"""
Unit tests for ProfileAccumulator and VehicleProfile.

Covers:
  - Single-sensor accumulation and finish
  - Multi-sensor accumulation (two side LiDARs)
  - min_scan_lines enforcement
  - max_gap_s timeout
  - VehicleProfile properties (duration, estimated_length)
  - abort / inactive state
"""
import numpy as np
import pytest

from app.modules.application.vehicle_profiler.profiler import (
    ProfileAccumulator,
    VehicleProfile,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _scan_line(n: int = 20) -> np.ndarray:
    """Simple 2D scan line — a horizontal arc."""
    rng = np.random.default_rng(42)
    return rng.uniform(-1, 1, (n, 2)).astype(np.float32)


def _scan_line_3d(n: int = 20, z_offset: float = 0.0) -> np.ndarray:
    """3D scan line simulating pose-transformed world-space points."""
    rng = np.random.default_rng(42)
    pts = rng.uniform(-1, 1, (n, 3)).astype(np.float64)
    pts[:, 2] = z_offset
    return pts


# ─────────────────────────────────────────────────────────────────────────────
# TestProfileAccumulator
# ─────────────────────────────────────────────────────────────────────────────


class TestProfileAccumulator:
    def test_not_active_by_default(self):
        acc = ProfileAccumulator()
        assert acc.active is False

    def test_start_vehicle_activates(self):
        acc = ProfileAccumulator()
        acc.start_vehicle()
        assert acc.active is True

    def test_add_scan_line_ignored_when_inactive(self):
        acc = ProfileAccumulator()
        acc.add_scan_line("s1", _scan_line(), position=1.0, timestamp=0.0)
        assert acc.scan_count == 0

    def test_single_sensor_accumulation(self):
        acc = ProfileAccumulator(min_scan_lines=3)
        acc.start_vehicle()
        for i in range(5):
            acc.add_scan_line("s1", _scan_line(), position=float(i) * 0.2, timestamp=float(i) * 0.1)
        assert acc.scan_count == 5
        profile = acc.finish_vehicle()
        assert profile is not None
        assert profile.scan_count == 5
        assert len(profile.points) == 5 * 20
        assert profile.points.shape[1] == 3

    def test_multi_sensor_accumulation(self):
        acc = ProfileAccumulator(min_scan_lines=4)
        acc.start_vehicle()
        acc.add_scan_line("left", _scan_line(10), position=0.0, timestamp=0.0)
        acc.add_scan_line("right", _scan_line(15), position=0.0, timestamp=0.0)
        acc.add_scan_line("left", _scan_line(10), position=0.15, timestamp=0.1)
        acc.add_scan_line("right", _scan_line(15), position=0.15, timestamp=0.1)
        profile = acc.finish_vehicle()
        assert profile is not None
        assert set(profile.sensor_ids) == {"left", "right"}
        assert len(profile.points) == 2 * 10 + 2 * 15

    def test_min_scan_lines_enforced(self):
        acc = ProfileAccumulator(min_scan_lines=10)
        acc.start_vehicle()
        for i in range(5):
            acc.add_scan_line("s1", _scan_line(), position=float(i), timestamp=float(i))
        profile = acc.finish_vehicle()
        assert profile is None

    def test_max_gap_clears_data_but_stays_active(self):
        acc = ProfileAccumulator(min_scan_lines=2, max_gap_s=1.0)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(), position=0.0, timestamp=0.0)
        assert acc.scan_count == 1
        # Gap too large — clears accumulated data but stays active
        acc.add_scan_line("s1", _scan_line(), position=5.0, timestamp=5.0)
        assert acc.active is True
        assert acc.scan_count == 0
        # Can resume accumulating after the gap
        acc.add_scan_line("s1", _scan_line(), position=5.1, timestamp=5.1)
        acc.add_scan_line("s1", _scan_line(), position=5.2, timestamp=5.2)
        profile = acc.finish_vehicle()
        assert profile is not None
        assert profile.scan_count == 2

    def test_abort_clears_state(self):
        acc = ProfileAccumulator()
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(), position=1.0, timestamp=0.0)
        acc.abort()
        assert acc.active is False
        assert acc.scan_count == 0

    def test_finish_when_inactive_returns_none(self):
        acc = ProfileAccumulator()
        assert acc.finish_vehicle() is None

    def test_along_track_position_increases(self):
        acc = ProfileAccumulator(min_scan_lines=2)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(5), position=0.0, timestamp=0.0)
        acc.add_scan_line("s1", _scan_line(5), position=2.0, timestamp=1.0)
        profile = acc.finish_vehicle()
        assert profile is not None
        # Default travel_axis=2 (Z): first scan at position=0.0, second at 2.0
        z_values = profile.points[:, 2]
        assert np.min(z_values) == pytest.approx(0.0)
        assert np.max(z_values) == pytest.approx(2.0)

    def test_travel_axis_x(self):
        """When travel_axis=0 (X), position goes to X column."""
        acc = ProfileAccumulator(min_scan_lines=2, travel_axis=0)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(5), position=0.0, timestamp=0.0)
        acc.add_scan_line("s1", _scan_line(5), position=3.0, timestamp=1.0)
        profile = acc.finish_vehicle()
        assert profile is not None
        x_values = profile.points[:, 0]
        assert np.min(x_values) == pytest.approx(0.0)
        assert np.max(x_values) == pytest.approx(3.0)
        assert profile.estimated_length == pytest.approx(3.0)

    def test_travel_axis_y(self):
        """When travel_axis=1 (Y), position goes to Y column."""
        acc = ProfileAccumulator(min_scan_lines=2, travel_axis=1)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(5), position=0.0, timestamp=0.0)
        acc.add_scan_line("s1", _scan_line(5), position=4.0, timestamp=1.0)
        profile = acc.finish_vehicle()
        assert profile is not None
        y_values = profile.points[:, 1]
        assert np.min(y_values) == pytest.approx(0.0)
        assert np.max(y_values) == pytest.approx(4.0)
        assert profile.estimated_length == pytest.approx(4.0)

    def test_min_position_delta_deduplicates(self):
        """Scan lines closer than min_position_delta are skipped."""
        acc = ProfileAccumulator(min_scan_lines=2, min_position_delta=0.05)
        acc.start_vehicle()
        # First scan always accepted
        acc.add_scan_line("s1", _scan_line(5), position=0.0, timestamp=0.0)
        assert acc.scan_count == 1
        # Second scan at barely moved position — skipped
        acc.add_scan_line("s1", _scan_line(5), position=0.01, timestamp=0.1)
        assert acc.scan_count == 1
        # Third scan has moved enough — accepted
        acc.add_scan_line("s1", _scan_line(5), position=0.06, timestamp=0.2)
        assert acc.scan_count == 2
        profile = acc.finish_vehicle()
        assert profile is not None
        assert profile.scan_count == 2

    def test_min_position_delta_zero_accepts_forward(self):
        """min_position_delta=0 (default) accepts any forward movement."""
        acc = ProfileAccumulator(min_scan_lines=2, min_position_delta=0.0)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(5), position=0.0, timestamp=0.0)
        acc.add_scan_line("s1", _scan_line(5), position=0.001, timestamp=0.1)
        acc.add_scan_line("s1", _scan_line(5), position=0.002, timestamp=0.2)
        assert acc.scan_count == 3

    def test_backward_position_rejected(self):
        """Scan lines with decreasing position are always rejected."""
        acc = ProfileAccumulator(min_scan_lines=2, min_position_delta=0.0)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(5), position=1.0, timestamp=0.0)
        assert acc.scan_count == 1
        # Backward — rejected
        acc.add_scan_line("s1", _scan_line(5), position=0.5, timestamp=0.1)
        assert acc.scan_count == 1
        # Same position — allowed (multi-sensor at same timestamp)
        acc.add_scan_line("s1", _scan_line(5), position=1.0, timestamp=0.2)
        assert acc.scan_count == 2
        # Forward — accepted
        acc.add_scan_line("s1", _scan_line(5), position=1.001, timestamp=0.3)
        assert acc.scan_count == 3

    def test_empty_points_ignored(self):
        acc = ProfileAccumulator(min_scan_lines=2)
        acc.start_vehicle()
        acc.add_scan_line("s1", np.empty((0, 2)), position=1.0, timestamp=0.0)
        assert acc.scan_count == 0

    def test_none_points_ignored(self):
        acc = ProfileAccumulator(min_scan_lines=2)
        acc.start_vehicle()
        acc.add_scan_line("s1", None, position=1.0, timestamp=0.0)
        assert acc.scan_count == 0

    def test_3d_points_preserve_xy(self):
        """3D (pose-transformed) points should keep X/Y from the sensor pose."""
        acc = ProfileAccumulator(min_scan_lines=2)
        acc.start_vehicle()
        pts = _scan_line_3d(10, z_offset=5.0)
        acc.add_scan_line("s1", pts, position=0.0, timestamp=0.0)
        acc.add_scan_line("s1", pts, position=1.0, timestamp=1.0)
        profile = acc.finish_vehicle()
        assert profile is not None
        # X/Y should match the input
        np.testing.assert_array_almost_equal(profile.points[:10, 0], pts[:, 0])
        np.testing.assert_array_almost_equal(profile.points[:10, 1], pts[:, 1])

    def test_3d_points_position_replaces_z(self):
        """3D points get their Z coordinate replaced with the detector position (default)."""
        acc = ProfileAccumulator(min_scan_lines=2)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line_3d(5, z_offset=1.0), position=0.0, timestamp=0.0)
        acc.add_scan_line("s1", _scan_line_3d(5, z_offset=1.0), position=2.0, timestamp=1.0)
        profile = acc.finish_vehicle()
        assert profile is not None
        # First scan: z = 0.0 (position replaces original z_offset)
        assert profile.points[0, 2] == pytest.approx(0.0)
        # Second scan: z = 2.0
        assert profile.points[5, 2] == pytest.approx(2.0)

    def test_3d_points_position_replaces_travel_axis_x(self):
        """3D points get X replaced with position when travel_axis=0."""
        acc = ProfileAccumulator(min_scan_lines=2, travel_axis=0)
        acc.start_vehicle()
        pts = _scan_line_3d(5, z_offset=1.0)
        acc.add_scan_line("s1", pts.copy(), position=0.0, timestamp=0.0)
        acc.add_scan_line("s1", pts.copy(), position=3.0, timestamp=1.0)
        profile = acc.finish_vehicle()
        assert profile is not None
        # First scan: all X = 0.0 (position replaces original X)
        np.testing.assert_array_almost_equal(profile.points[:5, 0], np.full(5, 0.0))
        # Second scan: all X = 3.0
        np.testing.assert_array_almost_equal(profile.points[5:10, 0], np.full(5, 3.0))
        # Y and Z should be untouched
        np.testing.assert_array_almost_equal(profile.points[:5, 1], pts[:, 1])
        np.testing.assert_array_almost_equal(profile.points[:5, 2], pts[:, 2])

    def test_multi_sensor_3d_merge(self):
        """Two side sensors at different Z offsets (simulating different mount positions)
        should produce a merged cloud with distinct Z ranges."""
        acc = ProfileAccumulator(min_scan_lines=4)
        acc.start_vehicle()
        # Left sensor mounted at z=0, right at z=2
        acc.add_scan_line("left", _scan_line_3d(10, z_offset=0.0), position=0.0, timestamp=0.0)
        acc.add_scan_line("right", _scan_line_3d(10, z_offset=2.0), position=0.0, timestamp=0.0)
        acc.add_scan_line("left", _scan_line_3d(10, z_offset=0.0), position=0.5, timestamp=0.5)
        acc.add_scan_line("right", _scan_line_3d(10, z_offset=2.0), position=0.5, timestamp=0.5)
        profile = acc.finish_vehicle()
        assert profile is not None
        assert set(profile.sensor_ids) == {"left", "right"}
        assert len(profile.points) == 40


# ─────────────────────────────────────────────────────────────────────────────
# TestVehicleProfile
# ─────────────────────────────────────────────────────────────────────────────


class TestVehicleProfile:
    def test_duration(self):
        p = VehicleProfile(
            points=np.zeros((10, 3)),
            start_time=100.0, end_time=105.0,
            scan_count=10, sensor_ids=["s1"],
        )
        assert p.duration == pytest.approx(5.0)

    def test_estimated_length(self):
        pts = np.zeros((10, 3))
        pts[:, 2] = np.linspace(0, 4.5, 10)  # along-track from 0 to 4.5
        p = VehicleProfile(
            points=pts,
            start_time=0.0, end_time=1.0,
            scan_count=10, sensor_ids=["s1"],
        )
        assert p.estimated_length == pytest.approx(4.5)

    def test_estimated_length_travel_axis_x(self):
        pts = np.zeros((10, 3))
        pts[:, 0] = np.linspace(0, 3.0, 10)  # along-track on X
        p = VehicleProfile(
            points=pts,
            start_time=0.0, end_time=1.0,
            scan_count=10, sensor_ids=["s1"],
            travel_axis=0,
        )
        assert p.estimated_length == pytest.approx(3.0)

    def test_estimated_length_empty(self):
        p = VehicleProfile(
            points=np.empty((0, 3)),
            start_time=0.0, end_time=0.0,
            scan_count=0, sensor_ids=[],
        )
        assert p.estimated_length == 0.0
