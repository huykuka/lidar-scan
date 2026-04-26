"""
Kalman-filtered velocity estimation from a vertically-mounted 2D LiDAR.

The vertical LiDAR scans a plane perpendicular to the vehicle's travel direction.
When a vehicle enters the scan plane, points suddenly become much closer than the
background.  The leading edge position is tracked frame-to-frame and a 1D Kalman
filter smooths the raw velocity estimate.

State vector:  [position, velocity]  (along the travel axis)
Measurement:   leading-edge position extracted from each scan line

Usage:
    estimator = VelocityEstimator(process_noise=0.1, measurement_noise=0.5)

    for frame in frames:
        result = estimator.update(scan_points, timestamp)
        if result is not None:
            print(result.velocity, result.position)
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class VelocityResult:
    """Output of a single velocity estimator update."""
    position: float
    velocity: float
    raw_edge_position: float
    timestamp: float
    vehicle_present: bool


class KalmanFilter1D:
    """Minimal constant-velocity 1D Kalman filter.

    State: [position, velocity]
    Model: position_{k+1} = position_k + velocity_k * dt
           velocity_{k+1} = velocity_k
    """

    def __init__(self, process_noise: float = 0.1, measurement_noise: float = 0.5):
        self.x = np.zeros(2)          # [position, velocity]
        self.P = np.eye(2) * 1000.0   # large initial uncertainty
        self.q = process_noise
        self.r = measurement_noise
        self._initialized = False

    def predict(self, dt: float) -> None:
        if dt <= 0:
            return
        F = np.array([[1.0, dt],
                      [0.0, 1.0]])
        Q = np.array([[self.q * dt**3 / 3.0, self.q * dt**2 / 2.0],
                      [self.q * dt**2 / 2.0, self.q * dt]])
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update(self, measurement: float) -> None:
        H = np.array([[1.0, 0.0]])
        y = measurement - H @ self.x
        S = H @ self.P @ H.T + self.r
        K = (self.P @ H.T) / S[0, 0]
        self.x = self.x + K.flatten() * y
        I_KH = np.eye(2) - K @ H
        self.P = I_KH @ self.P

    def initialize(self, position: float) -> None:
        self.x = np.array([position, 0.0])
        self.P = np.eye(2) * 1000.0
        self._initialized = True

    @property
    def position(self) -> float:
        return float(self.x[0])

    @property
    def velocity(self) -> float:
        return float(self.x[1])

    @property
    def initialized(self) -> bool:
        return self._initialized

    def reset(self) -> None:
        self.x = np.zeros(2)
        self.P = np.eye(2) * 1000.0
        self._initialized = False


class VelocityEstimator:
    """Estimates vehicle velocity from a vertical 2D LiDAR scan plane.

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
        self._kf = KalmanFilter1D(process_noise, measurement_noise)
        self._bg_threshold = bg_threshold
        self._bg_learning_frames = bg_learning_frames
        self._travel_axis = travel_axis

        self._bg_accumulator: list[np.ndarray] = []
        self._bg_distances: Optional[np.ndarray] = None  # median background per beam
        self._last_t: Optional[float] = None
        self._vehicle_present = False

    def update(self, points: np.ndarray, timestamp: float) -> Optional[VelocityResult]:
        """Process one scan frame and return the smoothed velocity estimate.

        Args:
            points: (N, 2+) array — at minimum columns for scan-plane X and Y.
                    For raw polar scans, convert to Cartesian before calling.
            timestamp: Unix timestamp of the scan.

        Returns:
            VelocityResult if a vehicle is detected (or was recently detected),
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
            return VelocityResult(
                position=self._kf.position,
                velocity=0.0,
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
            return VelocityResult(
                position=edge_position,
                velocity=0.0,
                raw_edge_position=edge_position,
                timestamp=timestamp,
                vehicle_present=True,
            )

        dt = timestamp - self._last_t if self._last_t is not None else 0.0
        self._last_t = timestamp

        if dt > 0:
            self._kf.predict(dt)
        self._kf.update(edge_position)
        self._vehicle_present = True

        return VelocityResult(
            position=self._kf.position,
            velocity=self._kf.velocity,
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
    def current_velocity(self) -> float:
        return self._kf.velocity if self._kf.initialized else 0.0

    @property
    def current_position(self) -> float:
        return self._kf.position if self._kf.initialized else 0.0
