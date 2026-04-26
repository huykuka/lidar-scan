"""
Vehicle detection and Kalman-filtered position tracking from a vertical 2D LiDAR.

The vertical LiDAR scans a plane perpendicular to the vehicle's travel direction.
When a vehicle enters the scan plane, points suddenly become much closer than the
background.  The leading edge position is tracked frame-to-frame and a Kalman
filter (via ``pykalman``) smooths the position estimate.

State vector:  [position, velocity]  (along the travel axis)
Measurement:   leading-edge position extracted from each scan line

Usage:
    detector = VehicleDetector(process_noise=0.1, measurement_noise=0.5)

    for frame in frames:
        result = detector.update(scan_points, timestamp)
        if result is not None:
            print(result.position, result.vehicle_present)
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from pykalman import KalmanFilter


@dataclass
class DetectionResult:
    """Output of a single vehicle detector update."""
    position: float
    raw_edge_position: float
    timestamp: float
    vehicle_present: bool


class PositionTracker:
    """Kalman-filtered 1D position/velocity tracker using pykalman.

    State: [position, velocity]
    Model: constant-velocity with variable dt.
    Observation: position only.
    """

    def __init__(self, process_noise: float = 0.1, measurement_noise: float = 0.5):
        self._q = process_noise
        self._r = measurement_noise
        self._obs_mat = np.array([[1.0, 0.0]])
        self._obs_cov = np.array([[self._r]])
        self._state_mean = np.zeros(2)
        self._state_cov = np.eye(2) * 1000.0
        self._initialized = False

    def _make_kf(self, dt: float) -> KalmanFilter:
        """Build a KalmanFilter configured for the given time step."""
        F = np.array([[1.0, dt], [0.0, 1.0]])
        Q = np.array([
            [self._q * dt**3 / 3.0, self._q * dt**2 / 2.0],
            [self._q * dt**2 / 2.0, self._q * dt],
        ])
        return KalmanFilter(
            transition_matrices=F,
            observation_matrices=self._obs_mat,
            transition_covariance=Q,
            observation_covariance=self._obs_cov,
        )

    def predict_and_update(self, measurement: float, dt: float) -> None:
        """Run one predict-then-update cycle with the given dt."""
        if dt <= 0:
            dt = 1e-6
        kf = self._make_kf(dt)
        self._state_mean, self._state_cov = kf.filter_update(
            self._state_mean, self._state_cov, observation=measurement,
        )

    def initialize(self, position: float) -> None:
        self._state_mean = np.array([position, 0.0])
        self._state_cov = np.eye(2) * 1000.0
        self._initialized = True

    @property
    def position(self) -> float:
        return float(self._state_mean[0])

    @property
    def velocity(self) -> float:
        return float(self._state_mean[1])

    @property
    def initialized(self) -> bool:
        return self._initialized

    def reset(self) -> None:
        self._state_mean = np.zeros(2)
        self._state_cov = np.eye(2) * 1000.0
        self._initialized = False


class VehicleDetector:
    """Detects vehicles and tracks their position from a vertical 2D LiDAR.

    Detection strategy:
      1. Convert polar (angle, distance) scan to Cartesian.
      2. Compute a background distance model from initial frames (median).
      3. Points significantly closer than background indicate the vehicle.
      4. The leading edge (first/last vehicle point along the travel axis)
         is tracked and fed into a Kalman filter.

    Args:
        process_noise:       Kalman Q scaling — trust in constant-velocity model.
        measurement_noise:   Kalman R — trust in the raw edge measurement.
        bg_threshold:        Distance (m) closer than background to classify as vehicle.
        bg_learning_frames:  Number of initial frames used to learn the background.
        travel_axis:         Index into Cartesian scan coords for the travel direction.
                             0 = X (default), 1 = Y.
    """

    def __init__(
        self,
        process_noise: float = 0.1,
        measurement_noise: float = 0.5,
        bg_threshold: float = 0.3,
        bg_learning_frames: int = 20,
        travel_axis: int = 0,
    ):
        self._kf = PositionTracker(process_noise, measurement_noise)
        self._bg_threshold = bg_threshold
        self._bg_learning_frames = bg_learning_frames
        self._travel_axis = travel_axis

        self._bg_accumulator: list[np.ndarray] = []
        self._bg_distances: Optional[np.ndarray] = None  # median background per beam
        self._last_t: Optional[float] = None
        self._vehicle_present = False

    def update(self, points: np.ndarray, timestamp: float) -> Optional[DetectionResult]:
        """Process one scan frame and return the detection/position result.

        Args:
            points: (N, 2+) array — at minimum columns for scan-plane X and Y.
                    For raw polar scans, convert to Cartesian before calling.
            timestamp: Unix timestamp of the scan.

        Returns:
            DetectionResult if a vehicle is detected (or was recently detected),
            None during background learning or when no vehicle is present.
        """
        if points is None or len(points) < 2:
            return None

        distances = np.linalg.norm(points[:, :2], axis=1)

        # --- Background learning phase ---
        if self._bg_distances is None:
            self._bg_accumulator.append(distances)
            if len(self._bg_accumulator) >= self._bg_learning_frames:
                max_len = max(len(d) for d in self._bg_accumulator)
                padded = np.full((len(self._bg_accumulator), max_len), np.nan)
                for i, d in enumerate(self._bg_accumulator):
                    padded[i, :len(d)] = d
                self._bg_distances = np.nanmedian(padded, axis=0)
                self._bg_accumulator.clear()
            return None

        # --- Vehicle detection ---
        n = min(len(distances), len(self._bg_distances))
        delta = self._bg_distances[:n] - distances[:n]
        vehicle_mask = delta > self._bg_threshold

        vehicle_indices = np.nonzero(vehicle_mask)[0]

        if len(vehicle_indices) == 0:
            if self._vehicle_present:
                self._vehicle_present = False
                self._kf.reset()
            self._last_t = timestamp
            return DetectionResult(
                position=self._kf.position,
                raw_edge_position=0.0,
                timestamp=timestamp,
                vehicle_present=False,
            )

        # Leading-edge position along travel axis
        vehicle_points = points[:n][vehicle_mask]
        edge_position = float(np.min(vehicle_points[:, self._travel_axis]))

        # --- Kalman filter ---
        if not self._kf.initialized:
            self._kf.initialize(edge_position)
            self._vehicle_present = True
            self._last_t = timestamp
            return DetectionResult(
                position=edge_position,
                raw_edge_position=edge_position,
                timestamp=timestamp,
                vehicle_present=True,
            )

        dt = timestamp - self._last_t if self._last_t is not None else 0.0
        self._last_t = timestamp

        self._kf.predict_and_update(edge_position, dt)
        self._vehicle_present = True

        return DetectionResult(
            position=self._kf.position,
            raw_edge_position=edge_position,
            timestamp=timestamp,
            vehicle_present=True,
        )

    def reset_tracking(self) -> None:
        """Reset only the Kalman filter and vehicle state, preserving the background model.

        Use this between vehicles so the next vehicle can be detected immediately
        without re-learning the background.
        """
        self._kf.reset()
        self._last_t = None
        self._vehicle_present = False

    def reset(self) -> None:
        """Full reset including the background model.  Use for session/config changes."""
        self.reset_tracking()
        self._bg_accumulator.clear()
        self._bg_distances = None

    @property
    def vehicle_present(self) -> bool:
        return self._vehicle_present

    @property
    def current_position(self) -> float:
        return self._kf.position if self._kf.initialized else 0.0
