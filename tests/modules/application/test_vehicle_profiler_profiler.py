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
        acc.add_scan_line("s1", _scan_line(), velocity=1.0, timestamp=0.0)
        assert acc.scan_count == 0

    def test_single_sensor_accumulation(self):
        acc = ProfileAccumulator(min_scan_lines=3)
        acc.start_vehicle()
        for i in range(5):
            acc.add_scan_line("s1", _scan_line(), velocity=2.0, timestamp=float(i) * 0.1)
        assert acc.scan_count == 5
        profile = acc.finish_vehicle()
        assert profile is not None
        assert profile.scan_count == 5
        assert len(profile.points) == 5 * 20
        assert profile.points.shape[1] == 3

    def test_multi_sensor_accumulation(self):
        acc = ProfileAccumulator(min_scan_lines=4)
        acc.start_vehicle()
        acc.add_scan_line("left", _scan_line(10), velocity=1.5, timestamp=0.0)
        acc.add_scan_line("right", _scan_line(15), velocity=1.5, timestamp=0.0)
        acc.add_scan_line("left", _scan_line(10), velocity=1.5, timestamp=0.1)
        acc.add_scan_line("right", _scan_line(15), velocity=1.5, timestamp=0.1)
        profile = acc.finish_vehicle()
        assert profile is not None
        assert set(profile.sensor_ids) == {"left", "right"}
        assert len(profile.points) == 2 * 10 + 2 * 15

    def test_min_scan_lines_enforced(self):
        acc = ProfileAccumulator(min_scan_lines=10)
        acc.start_vehicle()
        for i in range(5):
            acc.add_scan_line("s1", _scan_line(), velocity=1.0, timestamp=float(i))
        profile = acc.finish_vehicle()
        assert profile is None

    def test_max_gap_aborts_accumulation(self):
        acc = ProfileAccumulator(min_scan_lines=2, max_gap_s=1.0)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(), velocity=1.0, timestamp=0.0)
        # Gap too large
        acc.add_scan_line("s1", _scan_line(), velocity=1.0, timestamp=5.0)
        assert acc.active is False

    def test_abort_clears_state(self):
        acc = ProfileAccumulator()
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(), velocity=1.0, timestamp=0.0)
        acc.abort()
        assert acc.active is False
        assert acc.scan_count == 0

    def test_finish_when_inactive_returns_none(self):
        acc = ProfileAccumulator()
        assert acc.finish_vehicle() is None

    def test_along_track_position_increases(self):
        acc = ProfileAccumulator(min_scan_lines=2)
        acc.start_vehicle()
        acc.add_scan_line("s1", _scan_line(5), velocity=2.0, timestamp=0.0)
        acc.add_scan_line("s1", _scan_line(5), velocity=2.0, timestamp=1.0)
        profile = acc.finish_vehicle()
        assert profile is not None
        # First scan line at along_track=0, second at along_track=2.0 (2 m/s * 1 s)
        z_values = profile.points[:, 2]
        assert np.min(z_values) == pytest.approx(0.0)
        assert np.max(z_values) == pytest.approx(2.0)

    def test_empty_points_ignored(self):
        acc = ProfileAccumulator(min_scan_lines=2)
        acc.start_vehicle()
        acc.add_scan_line("s1", np.empty((0, 2)), velocity=1.0, timestamp=0.0)
        assert acc.scan_count == 0

    def test_none_points_ignored(self):
        acc = ProfileAccumulator(min_scan_lines=2)
        acc.start_vehicle()
        acc.add_scan_line("s1", None, velocity=1.0, timestamp=0.0)
        assert acc.scan_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# TestVehicleProfile
# ─────────────────────────────────────────────────────────────────────────────


class TestVehicleProfile:
    def test_duration(self):
        p = VehicleProfile(
            points=np.zeros((10, 3)),
            start_time=100.0, end_time=105.0,
            scan_count=10, sensor_ids=["s1"],
            mean_velocity=2.0,
        )
        assert p.duration == pytest.approx(5.0)

    def test_estimated_length(self):
        pts = np.zeros((10, 3))
        pts[:, 2] = np.linspace(0, 4.5, 10)  # along-track from 0 to 4.5
        p = VehicleProfile(
            points=pts,
            start_time=0.0, end_time=1.0,
            scan_count=10, sensor_ids=["s1"],
            mean_velocity=4.5,
        )
        assert p.estimated_length == pytest.approx(4.5)

    def test_estimated_length_empty(self):
        p = VehicleProfile(
            points=np.empty((0, 3)),
            start_time=0.0, end_time=0.0,
            scan_count=0, sensor_ids=[],
            mean_velocity=0.0,
        )
        assert p.estimated_length == 0.0
