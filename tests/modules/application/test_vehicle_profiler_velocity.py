"""
Unit tests for VelocityEstimator and KalmanFilter1D.

Covers:
  - KalmanFilter1D: initialization, predict, update, reset, property access
  - VelocityEstimator: background learning, vehicle detection,
    Kalman-filtered velocity, vehicle departure, reset
"""
import numpy as np
import pytest

from app.modules.application.vehicle_profiler.velocity import (
    KalmanFilter1D,
    VelocityEstimator,
    VelocityResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


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
# TestKalmanFilter1D
# ─────────────────────────────────────────────────────────────────────────────


class TestKalmanFilter1D:
    def test_initial_state(self):
        kf = KalmanFilter1D()
        assert kf.position == 0.0
        assert kf.velocity == 0.0
        assert kf.initialized is False

    def test_initialize_sets_position(self):
        kf = KalmanFilter1D()
        kf.initialize(3.5)
        assert kf.position == pytest.approx(3.5)
        assert kf.velocity == pytest.approx(0.0)
        assert kf.initialized is True

    def test_predict_advances_position(self):
        kf = KalmanFilter1D()
        kf.initialize(0.0)
        kf.x[1] = 2.0  # set velocity = 2 m/s
        kf.predict(1.0)
        assert kf.position == pytest.approx(2.0)
        assert kf.velocity == pytest.approx(2.0)

    def test_predict_zero_dt_no_change(self):
        kf = KalmanFilter1D()
        kf.initialize(5.0)
        kf.predict(0.0)
        assert kf.position == pytest.approx(5.0)

    def test_update_moves_toward_measurement(self):
        kf = KalmanFilter1D()
        kf.initialize(0.0)
        kf.update(10.0)
        assert kf.position > 0.0

    def test_reset(self):
        kf = KalmanFilter1D()
        kf.initialize(5.0)
        kf.reset()
        assert kf.position == 0.0
        assert kf.velocity == 0.0
        assert kf.initialized is False

    def test_convergence_with_repeated_updates(self):
        kf = KalmanFilter1D(process_noise=0.1, measurement_noise=0.1)
        kf.initialize(0.0)
        for _ in range(50):
            kf.predict(0.1)
            kf.update(5.0)
        assert kf.position == pytest.approx(5.0, abs=0.5)


# ─────────────────────────────────────────────────────────────────────────────
# TestVelocityEstimator
# ─────────────────────────────────────────────────────────────────────────────


class TestVelocityEstimator:
    def test_returns_none_during_background_learning(self):
        est = VelocityEstimator(bg_learning_frames=5)
        for i in range(4):
            result = est.update(_background_scan(), timestamp=float(i))
            assert result is None

    def test_background_learned_after_n_frames(self):
        est = VelocityEstimator(bg_learning_frames=5)
        for i in range(5):
            est.update(_background_scan(), timestamp=float(i))
        # After learning, a background scan should return no vehicle
        result = est.update(_background_scan(), timestamp=5.0)
        assert result is not None
        assert result.vehicle_present is False

    def test_vehicle_detected_when_closer_than_background(self):
        est = VelocityEstimator(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            est.update(_background_scan(), timestamp=float(i))
        result = est.update(_vehicle_scan(), timestamp=5.0)
        assert result is not None
        assert result.vehicle_present is True

    def test_velocity_zero_on_first_detection(self):
        est = VelocityEstimator(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            est.update(_background_scan(), timestamp=float(i))
        result = est.update(_vehicle_scan(), timestamp=5.0)
        assert result.velocity == pytest.approx(0.0)

    def test_vehicle_departure_resets_state(self):
        est = VelocityEstimator(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            est.update(_background_scan(), timestamp=float(i))
        # Vehicle enters
        est.update(_vehicle_scan(), timestamp=5.0)
        assert est.vehicle_present is True
        # Vehicle leaves
        result = est.update(_background_scan(), timestamp=6.0)
        assert result.vehicle_present is False
        assert est.vehicle_present is False

    def test_reset_clears_everything(self):
        est = VelocityEstimator(bg_learning_frames=5)
        for i in range(5):
            est.update(_background_scan(), timestamp=float(i))
        est.reset()
        # Should need to re-learn background
        result = est.update(_background_scan(), timestamp=10.0)
        assert result is None

    def test_returns_none_for_empty_points(self):
        est = VelocityEstimator(bg_learning_frames=2)
        result = est.update(np.empty((0, 2)), timestamp=0.0)
        assert result is None

    def test_returns_none_for_none_points(self):
        est = VelocityEstimator(bg_learning_frames=2)
        result = est.update(None, timestamp=0.0)
        assert result is None

    def test_current_velocity_property(self):
        est = VelocityEstimator(bg_learning_frames=3, bg_threshold=0.3)
        assert est.current_velocity == 0.0
        for i in range(3):
            est.update(_background_scan(), timestamp=float(i))
        est.update(_vehicle_scan(), timestamp=3.0)
        # After first detection, velocity should still be 0
        assert est.current_velocity == pytest.approx(0.0)

    def test_velocity_nonzero_after_moving_edge(self):
        est = VelocityEstimator(
            bg_learning_frames=5, bg_threshold=0.3,
            process_noise=1.0, measurement_noise=0.1,
            travel_axis=0,
        )
        for i in range(5):
            est.update(_background_scan(), timestamp=float(i))

        # Create two scans where the vehicle edge clearly moves along X axis
        n = 50
        angles = np.linspace(-np.pi / 4, np.pi / 4, n)
        bg = 5.0

        # Frame 1: vehicle at x ~ 1.0
        d1 = np.full(n, bg)
        d1[20:35] = 1.0
        scan1 = np.column_stack([d1 * np.cos(angles), d1 * np.sin(angles)])
        est.update(scan1, timestamp=5.0)

        # Frame 2: vehicle at x ~ 0.5 (moved closer along travel axis)
        d2 = np.full(n, bg)
        d2[20:35] = 0.5
        scan2 = np.column_stack([d2 * np.cos(angles), d2 * np.sin(angles)])
        est.update(scan2, timestamp=5.5)

        assert est.current_velocity != 0.0

    def test_reset_tracking_preserves_background(self):
        est = VelocityEstimator(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            est.update(_background_scan(), timestamp=float(i))
        est.update(_vehicle_scan(), timestamp=5.0)
        assert est.vehicle_present is True

        est.reset_tracking()
        assert est.vehicle_present is False
        # Background should still be learned — next frame returns a result (not None)
        result = est.update(_background_scan(), timestamp=6.0)
        assert result is not None
        assert result.vehicle_present is False

    def test_reset_tracking_allows_immediate_next_vehicle(self):
        est = VelocityEstimator(bg_learning_frames=5, bg_threshold=0.3)
        for i in range(5):
            est.update(_background_scan(), timestamp=float(i))
        # First vehicle
        est.update(_vehicle_scan(), timestamp=5.0)
        est.reset_tracking()
        # Second vehicle detected immediately (no re-learning needed)
        result = est.update(_vehicle_scan(), timestamp=6.0)
        assert result is not None
        assert result.vehicle_present is True
