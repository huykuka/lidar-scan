"""
Unit tests for ClusterTracker and VehicleDetector.

Covers:
  - ClusterTracker: initialization, ICP displacement, outlier rejection,
    dead-zone, reset
  - VehicleDetector: DBSCAN-based detection, trigger gate, departure,
    position tracking, reset
"""
import numpy as np
import pytest

from app.modules.application.vehicle_profiler.utils.detector import (
    ClusterTracker,
    VehicleDetector,
    DetectionResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Scan helpers
# ─────────────────────────────────────────────────────────────────────────────


def _profile_cluster(
    offset_x: float = 0.0,
    n: int = 100,
    x_range: float = 2.0,
) -> np.ndarray:
    """2-D (x, height) cluster simulating a truck height profile.

    Shifting offset_x by δx simulates the truck advancing along X by exactly δx.
    """
    x = np.linspace(offset_x, offset_x + x_range, n)
    cabin = 1.5 * np.exp(-((x - (offset_x + x_range / 3)) ** 2) / 0.1)
    bin_top = np.where(x > offset_x + x_range * 0.55, 0.8, 0.0)
    return np.column_stack([x, cabin + bin_top])


def _dense_cluster(
    cx: float = 0.0,
    cy: float = 0.0,
    n: int = 30,
    spread: float = 0.1,
) -> np.ndarray:
    """Compact 2-D cluster centred at (cx, cy) — guaranteed to form a single DBSCAN cluster."""
    rng = np.random.default_rng(42)
    xy = rng.normal(loc=[cx, cy], scale=spread, size=(n, 2))
    return xy


def _sparse_noise(n: int = 5, x_range: float = 10.0) -> np.ndarray:
    """Random sparse points that won't form a DBSCAN cluster."""
    rng = np.random.default_rng(0)
    x = rng.uniform(-x_range / 2, x_range / 2, n)
    y = rng.uniform(-x_range / 2, x_range / 2, n)
    return np.column_stack([x, y])


# ─────────────────────────────────────────────────────────────────────────────
# TestClusterTracker
# ─────────────────────────────────────────────────────────────────────────────


class TestClusterTracker:
    def test_initial_state(self):
        ct = ClusterTracker(travel_axis=0)
        assert ct.last_displacement == pytest.approx(0.0)
        assert ct.initialized is False

    def test_first_update_seeds_tracker(self):
        ct = ClusterTracker(travel_axis=0)
        v = ct.update(_profile_cluster(0.0), timestamp=0.0)
        assert v == pytest.approx(0.0)
        assert ct.initialized is True

    def test_displacement_from_known_shift(self):
        """ICP recovers a 0.05 m shift along X."""
        shift = 0.05
        ct = ClusterTracker(travel_axis=0, max_displacement=0.2)
        ct.update(_profile_cluster(0.0), timestamp=0.0)
        d = ct.update(_profile_cluster(shift), timestamp=1.0)
        assert d == pytest.approx(shift, abs=0.015)

    def test_displacement_travel_axis_y(self):
        """ICP along Y axis recovers a 0.05 m shift."""
        shift = 0.05
        ct = ClusterTracker(travel_axis=1, max_displacement=0.2)
        c0 = _profile_cluster(0.0)[:, ::-1]
        c1 = _profile_cluster(shift)[:, ::-1]
        ct.update(c0, timestamp=0.0)
        d = ct.update(c1, timestamp=1.0)
        assert d == pytest.approx(shift, abs=0.015)

    def test_displacement_negative_returned_as_negative(self):
        ct = ClusterTracker(travel_axis=0, max_displacement=0.2)
        ct.update(_profile_cluster(0.1), timestamp=0.0)
        d = ct.update(_profile_cluster(0.0), timestamp=1.0)
        assert d is not None and d < 0.0

    def test_outlier_clamped_to_max_displacement(self):
        """A shift larger than max_displacement is rejected (returns None)."""
        ct = ClusterTracker(travel_axis=0, max_displacement=0.03)
        ct.update(_profile_cluster(0.0), timestamp=0.0)
        d = ct.update(_profile_cluster(0.5), timestamp=1.0)
        assert d is None

    def test_reset_clears_state(self):
        ct = ClusterTracker(travel_axis=0)
        ct.update(_profile_cluster(0.0), timestamp=0.0)
        ct.update(_profile_cluster(0.05), timestamp=1.0)
        ct.reset()
        assert ct.last_displacement == pytest.approx(0.0)
        assert ct.initialized is False


# ─────────────────────────────────────────────────────────────────────────────
# TestVehicleDetector — DBSCAN-based
# ─────────────────────────────────────────────────────────────────────────────


def _make_detector(**kw) -> VehicleDetector:
    """Convenience factory with sensible test defaults."""
    defaults = dict(
        min_vehicle_points=10,
        dbscan_eps=0.5,
        dbscan_min_samples=3,
        trigger_distance=None,
    )
    defaults.update(kw)
    return VehicleDetector(**defaults)


class TestVehicleDetector:
    def test_no_vehicle_when_scan_empty_or_none(self):
        det = _make_detector()
        assert det.update(None, 0.0) is None
        assert det.update(np.empty((0, 2)), 0.0) is None

    def test_no_vehicle_on_sparse_noise(self):
        """Sparse points don't cluster → vehicle_present=False."""
        det = _make_detector()
        result = det.update(_sparse_noise(n=5), 0.0)
        assert result is not None
        assert result.vehicle_present is False

    def test_vehicle_detected_on_dense_cluster(self):
        det = _make_detector(min_vehicle_points=10)
        result = det.update(_dense_cluster(n=30), 0.0)
        assert result is not None
        assert result.vehicle_present is True

    def test_detection_result_fields(self):
        det = _make_detector()
        result = det.update(_dense_cluster(n=30), 0.0)
        assert isinstance(result, DetectionResult)
        assert hasattr(result, "position")
        assert hasattr(result, "velocity")
        assert hasattr(result, "timestamp")
        assert hasattr(result, "vehicle_present")
        assert hasattr(result, "icp_valid")

    def test_vehicle_departure_immediate(self):
        """Cluster disappears → vehicle_present=False on next frame."""
        det = _make_detector(min_vehicle_points=10)
        det.update(_dense_cluster(n=30), 0.0)
        assert det.vehicle_present is True
        result = det.update(_sparse_noise(n=3), 1.0)
        assert result.vehicle_present is False
        assert det.vehicle_present is False

    def test_vehicle_returns_after_gap(self):
        """Truck re-enters after gap — tracking restarts."""
        det = _make_detector(min_vehicle_points=10)
        det.update(_dense_cluster(n=30), 0.0)
        det.update(_sparse_noise(n=3), 1.0)
        assert det.vehicle_present is False
        result = det.update(_dense_cluster(n=30), 2.0)
        assert result.vehicle_present is True

    def test_position_advances_with_moving_cluster(self):
        """Position increases as cluster shifts along travel axis."""
        det = _make_detector(
            min_vehicle_points=10,
            dbscan_eps=0.5,
            dbscan_min_samples=3,
            max_correspondence_distance=1.0,
            max_displacement=0.5,
        )
        det.update(_profile_cluster(0.0), 0.0)
        pos0 = det.current_position
        det.update(_profile_cluster(0.1), 1.0)
        pos1 = det.current_position
        det.update(_profile_cluster(0.2), 2.0)
        pos2 = det.current_position
        assert pos2 > pos1 >= pos0

    def test_current_velocity_accessible(self):
        det = _make_detector()
        assert det.current_velocity == pytest.approx(0.0)
        det.update(_dense_cluster(n=30), 0.0)
        det.update(_dense_cluster(n=30), 0.1)
        assert isinstance(det.current_velocity, float)

    def test_reset_clears_everything(self):
        det = _make_detector(min_vehicle_points=10)
        det.update(_dense_cluster(n=30), 0.0)
        assert det.vehicle_present is True
        det.reset()
        assert det.vehicle_present is False
        assert det.current_position == pytest.approx(0.0)
        assert det.current_velocity == pytest.approx(0.0)

    def test_reset_tracking_preserves_detector_state(self):
        """reset_tracking() clears pose/velocity but is otherwise a full reset
        (no background to preserve in the new design)."""
        det = _make_detector(min_vehicle_points=10)
        det.update(_dense_cluster(n=30), 0.0)
        det.reset_tracking()
        assert det.vehicle_present is False
        # Cluster should be re-detectable immediately after reset
        result = det.update(_dense_cluster(n=30), 1.0)
        assert result.vehicle_present is True

    def test_min_vehicle_points_gate(self):
        """Cluster below min_vehicle_points is ignored."""
        det = _make_detector(min_vehicle_points=50)
        result = det.update(_dense_cluster(n=30), 0.0)
        assert result.vehicle_present is False

    def test_dbscan_separates_noise_from_cluster(self):
        """Mixing a real cluster with sparse noise — cluster still detected."""
        det = _make_detector(min_vehicle_points=10)
        cluster = _dense_cluster(cx=0.0, n=30)
        noise = _sparse_noise(n=4, x_range=10.0)
        mixed = np.vstack([cluster, noise])
        result = det.update(mixed, 0.0)
        assert result.vehicle_present is True


# ─────────────────────────────────────────────────────────────────────────────
# TestVehicleDetectorTriggerGate
# ─────────────────────────────────────────────────────────────────────────────


def _scan_at_x(cx: float, n: int = 30) -> np.ndarray:
    """Dense cluster centred at X=cx."""
    return _dense_cluster(cx=cx, cy=0.0, n=n, spread=0.05)


class TestVehicleDetectorTriggerGate:
    def test_no_detection_when_cluster_outside_gate(self):
        """Cluster far before gate (X=-5) with trigger_distance=1.0 → not detected."""
        det = _make_detector(min_vehicle_points=10, trigger_distance=1.0)
        result = det.update(_scan_at_x(-5.0), 0.0)
        assert result.vehicle_present is False

    def test_detection_when_cluster_inside_gate(self):
        """Cluster at X=-0.5 with trigger_distance=1.0 → detected."""
        det = _make_detector(min_vehicle_points=10, trigger_distance=1.0)
        result = det.update(_scan_at_x(-0.5), 0.0)
        assert result.vehicle_present is True

    def test_detection_at_gate_boundary(self):
        """Cluster at X=-1.0 exactly (edge of window) → detected."""
        det = _make_detector(min_vehicle_points=10, trigger_distance=1.0)
        result = det.update(_scan_at_x(-1.0), 0.0)
        assert result.vehicle_present is True

    def test_no_gate_when_trigger_distance_none(self):
        """trigger_distance=None → full scan used, cluster anywhere triggers."""
        det = _make_detector(min_vehicle_points=10, trigger_distance=None)
        result = det.update(_scan_at_x(-50.0), 0.0)
        assert result.vehicle_present is True

    def test_departure_when_cluster_moves_out_of_gate(self):
        """Cluster enters gate, then moves to X=-5 — departs."""
        det = _make_detector(min_vehicle_points=10, trigger_distance=1.0)
        det.update(_scan_at_x(-0.5), 0.0)
        assert det.vehicle_present is True
        result = det.update(_scan_at_x(-5.0), 1.0)
        assert result.vehicle_present is False

    def test_vehicle_stays_present_inside_gate(self):
        """Multiple frames inside gate — stays present."""
        det = _make_detector(min_vehicle_points=10, trigger_distance=2.0)
        for t, x in enumerate([-1.5, -1.0, -0.5, 0.0]):
            result = det.update(_scan_at_x(x), float(t))
            assert result.vehicle_present is True
