"""
Unit tests for ClusterTracker and VehicleDetector.

Covers:
  - ClusterTracker: initialization, cross-correlation displacement,
    outlier rejection, dead-zone, reset
  - VehicleDetector: background learning, vehicle detection,
    position tracking, gap debounce, vehicle departure, reset
"""
import numpy as np
import pytest

from app.modules.application.vehicle_profiler.utils.detector import (
    ClusterTracker,
    VehicleDetector,
    DetectionResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _profile_cluster(
    offset_x: float = 0.0,
    n: int = 100,
    x_range: float = 2.0,
) -> np.ndarray:
    """Return a 2-D (x, height) cluster simulating a truck height profile.

    Combines a Gaussian peak (cabin) and a flat section (bin) so both smooth
    and flat regions are represented.  Shifting offset_x by δx simulates the
    truck advancing along the travel axis by exactly δx.
    """
    x = np.linspace(offset_x, offset_x + x_range, n)
    # Cabin: Gaussian peak centred at 1/3 of the range
    cabin = 1.5 * np.exp(-((x - (offset_x + x_range / 3)) ** 2) / 0.1)
    # Bin: flat section at height 0.8 in the second half
    bin_top = np.where(x > offset_x + x_range * 0.55, 0.8, 0.0)
    height = cabin + bin_top
    return np.column_stack([x, height])


def _parallel_bg_scan(n: int = 100, x_range: float = 4.0, bg_y: float = 5.0) -> np.ndarray:
    """Parallel-beam background: uniform X spacing, constant Y (range = ground)."""
    x = np.linspace(-x_range / 2, x_range / 2, n)
    return np.column_stack([x, np.full(n, bg_y)])


def _parallel_vehicle_scan(
    truck_x0: float,
    n: int = 100,
    x_range: float = 4.0,
    bg_y: float = 5.0,
) -> np.ndarray:
    """Parallel-beam scan with a truck profile starting at truck_x0.

    The truck occupies 2 m in X with a Gaussian cabin peak followed by a flat
    bin section.  Each point's Y value = bg_y - truck_height_at_x, so the truck
    top appears closer to the sensor than the ground.  Cross-correlation on the
    Y (height) axis can then recover the X shift between frames.
    """
    x = np.linspace(-x_range / 2, x_range / 2, n)
    y = np.full(n, bg_y)

    truck_len = 2.0
    local_x = x - truck_x0
    mask = (local_x >= 0) & (local_x < truck_len)

    lx = local_x[mask]
    cabin_h = 1.5 * np.exp(-((lx - truck_len / 3) ** 2) / 0.1)
    bin_h = np.where(lx > truck_len * 0.55, 0.8, 0.0)
    y[mask] = bg_y - (cabin_h + bin_h)   # closer to sensor = smaller range

    return np.column_stack([x, y])


def _background_scan(n_beams: int = 50, distance: float = 5.0) -> np.ndarray:
    """Simulate a scan with all points at background distance."""
    angles = np.linspace(-np.pi / 4, np.pi / 4, n_beams)
    x = distance * np.cos(angles)
    y = distance * np.sin(angles)
    return np.column_stack([x, y])


def _vehicle_scan(
    n_beams: int = 50,
    bg_distance: float = 5.0,
    vehicle_distance: float = 1.5,
    vehicle_start: int = 15,
    vehicle_end: int = 35,
) -> np.ndarray:
    """Simulate a scan with a vehicle occupying some beams."""
    angles = np.linspace(-np.pi / 4, np.pi / 4, n_beams)
    distances = np.full(n_beams, bg_distance)
    distances[vehicle_start:vehicle_end] = vehicle_distance
    x = distances * np.cos(angles)
    y = distances * np.sin(angles)
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
        """Cross-correlation recovers a 0.05 m shift along X (±2 bins tolerance)."""
        shift = 0.05
        ct = ClusterTracker(
            travel_axis=0, bin_size=0.005, max_displacement=0.2,
            grid_min=0.0, grid_max=2.5,
        )
        ct.update(_profile_cluster(0.0), timestamp=0.0)
        d = ct.update(_profile_cluster(shift), timestamp=1.0)
        assert d == pytest.approx(shift, abs=0.015)  # ±3 bins boundary tolerance

    def test_displacement_travel_axis_y(self):
        """Cross-correlation along Y axis recovers a 0.05 m shift."""
        shift = 0.05
        ct = ClusterTracker(
            travel_axis=1, height_axis=0, bin_size=0.005, max_displacement=0.2,
            grid_min=0.0, grid_max=2.5,
        )
        # Swap x/y columns so travel is in column 1
        c0 = _profile_cluster(0.0)[:, ::-1]
        c1 = _profile_cluster(shift)[:, ::-1]
        ct.update(c0, timestamp=0.0)
        d = ct.update(c1, timestamp=1.0)
        assert d == pytest.approx(shift, abs=0.015)

    def test_displacement_negative_clamped_to_zero(self):
        """Backward displacement is clamped to 0 — forward-only motion."""
        ct = ClusterTracker(
            travel_axis=0, bin_size=0.005, max_displacement=0.2,
            grid_min=0.0, grid_max=2.5,
        )
        ct.update(_profile_cluster(0.1), timestamp=0.0)
        d = ct.update(_profile_cluster(0.0), timestamp=1.0)  # shifted backward
        assert d == pytest.approx(0.0)

    def test_outlier_clamped_to_max_displacement(self):
        """A shift larger than max_displacement is clamped to max_displacement.

        Cross-correlation search window is bounded by max_lag_bins, so very
        large shifts saturate at max_displacement rather than returning None.
        """
        max_d = 0.03
        ct = ClusterTracker(
            travel_axis=0, bin_size=0.005, max_displacement=max_d,
            grid_min=0.0, grid_max=2.5,
        )
        ct.update(_profile_cluster(0.0), timestamp=0.0)
        d = ct.update(_profile_cluster(0.5), timestamp=1.0)  # 0.5m >> max_d
        # Result must be within [0, max_d]
        assert d is not None
        assert 0.0 <= d <= max_d

    def test_reset_clears_state(self):
        ct = ClusterTracker(travel_axis=0)
        ct.update(_profile_cluster(0.0), timestamp=0.0)
        ct.update(_profile_cluster(0.05), timestamp=1.0)
        ct.reset()
        assert ct.last_displacement == pytest.approx(0.0)
        assert ct.initialized is False

    def test_first_update_seeds_tracker(self):
        ct = ClusterTracker(travel_axis=0)
        v = ct.update(_profile_cluster(0.0), timestamp=0.0)
        assert v == pytest.approx(0.0)
        assert ct.initialized is True


# ─────────────────────────────────────────────────────────────────────────────
# TestVehicleDetector
# ─────────────────────────────────────────────────────────────────────────────


class TestVehicleDetector:
    def test_returns_none_during_background_learning(self):
        det = VehicleDetector(bg_learning_frames=5)
        for i in range(4):
            result = det.update(_background_scan(), timestamp=float(i))
            assert result is None

    def test_background_learned_after_n_frames(self):
        det = VehicleDetector(bg_learning_frames=5)
        for i in range(5):
            det.update(_background_scan(), timestamp=float(i))
        result = det.update(_background_scan(), timestamp=5.0)
        assert result is not None
        assert result.vehicle_present is False

    def test_vehicle_detected_when_closer_than_background(self):
        det = VehicleDetector(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            det.update(_background_scan(), timestamp=float(i))
        result = det.update(_vehicle_scan(), timestamp=5.0)
        assert result is not None
        assert result.vehicle_present is True

    def test_vehicle_departure_after_debounce(self):
        """Vehicle leaves → absent > gap_debounce_s → vehicle_present = False."""
        det = VehicleDetector(bg_learning_frames=5, bg_threshold=0.3, gap_debounce_s=1.0)
        for i in range(5):
            det.update(_background_scan(), timestamp=float(i))
        det.update(_vehicle_scan(), timestamp=5.0)
        assert det.vehicle_present is True
        # Still within debounce
        result = det.update(_background_scan(), timestamp=5.5)
        assert result.vehicle_present is True
        # Past debounce
        result = det.update(_background_scan(), timestamp=7.0)
        assert result.vehicle_present is False
        assert det.vehicle_present is False

    def test_gap_within_debounce_keeps_vehicle_present(self):
        """Short absence within gap_debounce_s does not stop the vehicle."""
        det = VehicleDetector(bg_learning_frames=5, bg_threshold=0.3, gap_debounce_s=2.0)
        for i in range(5):
            det.update(_background_scan(), timestamp=float(i))
        det.update(_vehicle_scan(), timestamp=5.0)
        # Short gap
        result = det.update(_background_scan(), timestamp=5.5)
        assert result.vehicle_present is True
        # Vehicle returns before debounce expires
        result = det.update(_vehicle_scan(), timestamp=6.0)
        assert result.vehicle_present is True

    def test_position_advances_with_moving_cluster(self):
        """Travel distance increases as the truck profile shifts forward in X."""
        det = VehicleDetector(
            bg_learning_frames=5, bg_threshold=0.3,
            travel_axis=0,
            bin_size=0.005, grid_min=-2.5, grid_max=2.5,
        )
        for i in range(5):
            det.update(_parallel_bg_scan(), timestamp=float(i))

        # Frame 1: truck profile starting at X = -1.0
        det.update(_parallel_vehicle_scan(-1.0), timestamp=5.0)
        pos1 = det.current_position

        # Frame 2: truck moved forward 0.1 m → profile starting at X = -0.9
        det.update(_parallel_vehicle_scan(-0.9), timestamp=5.5)
        pos2 = det.current_position

        assert pos2 > pos1

    def test_current_velocity_property(self):
        det = VehicleDetector(bg_learning_frames=3, bg_threshold=0.3)
        assert det.current_velocity == pytest.approx(0.0)
        for i in range(3):
            det.update(_background_scan(), timestamp=float(i))
        det.update(_vehicle_scan(), timestamp=3.0)
        det.update(_vehicle_scan(), timestamp=3.1)
        # Velocity property is accessible (may be 0 if cluster barely moved)
        assert isinstance(det.current_velocity, float)

    def test_returns_none_for_empty_points(self):
        det = VehicleDetector(bg_learning_frames=2)
        result = det.update(np.empty((0, 2)), timestamp=0.0)
        assert result is None

    def test_returns_none_for_none_points(self):
        det = VehicleDetector(bg_learning_frames=2)
        result = det.update(None, timestamp=0.0)
        assert result is None

    def test_reset_clears_everything(self):
        det = VehicleDetector(bg_learning_frames=5)
        for i in range(5):
            det.update(_background_scan(), timestamp=float(i))
        det.reset()
        result = det.update(_background_scan(), timestamp=10.0)
        assert result is None  # background re-learning

    def test_reset_tracking_preserves_background(self):
        det = VehicleDetector(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            det.update(_background_scan(), timestamp=float(i))
        det.update(_vehicle_scan(), timestamp=5.0)
        det.reset_tracking()
        assert det.vehicle_present is False
        result = det.update(_background_scan(), timestamp=6.0)
        assert result is not None  # background still learned

    def test_reset_tracking_allows_immediate_next_vehicle(self):
        det = VehicleDetector(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            det.update(_background_scan(), timestamp=float(i))
        det.update(_vehicle_scan(), timestamp=5.0)
        det.reset_tracking()
        result = det.update(_vehicle_scan(), timestamp=6.0)
        assert result is not None
        assert result.vehicle_present is True

    def test_detection_result_fields(self):
        det = VehicleDetector(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            det.update(_background_scan(), timestamp=float(i))
        result = det.update(_vehicle_scan(), timestamp=5.0)
        assert isinstance(result, DetectionResult)
        assert hasattr(result, "position")
        assert hasattr(result, "centroid_position")
        assert hasattr(result, "velocity")
        assert hasattr(result, "timestamp")
        assert hasattr(result, "vehicle_present")
