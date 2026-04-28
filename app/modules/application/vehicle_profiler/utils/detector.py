"""
Vehicle detection and Kalman-filtered position tracking from a vertical 2D LiDAR.

The vertical LiDAR scans a plane perpendicular to the vehicle's travel direction.
When a vehicle enters the scan plane, points suddenly become much closer than the
background.  The leading edge position is tracked frame-to-frame and a Kalman
filter smooths the position estimate.

State vector:  [position, velocity]  (along the travel axis, metres / m/s)
Measurement:   leading-edge position extracted from each scan line

Usage:
    detector = VehicleDetector(process_noise=0.1, measurement_noise=0.5)

    for frame in frames:
        result = detector.update(scan_points, timestamp)
        if result is not None:
            print(result.position, result.vehicle_present)
"""
import csv
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class DetectionResult:
    """Output of a single vehicle detector update."""
    position: float
    raw_edge_position: float
    timestamp: float
    vehicle_present: bool


class PositionTracker:
    """Kalman filter for 1D position/velocity tracking.

    State:       [position, velocity]  — metres / m/s
    Model:       constant-velocity  x(t+1) = F·x(t)
    Observation: position only       z = H·x

    Separate predict / update steps give full control:
      - predict()        → advance state by dt with no sensor input
      - update(z)        → correct state with a new measurement
      - predict_update() → both in one call (normal frame)
    """

    def __init__(self, process_noise: float = 0.1, measurement_noise: float = 0.5):
        self._q = process_noise      # process noise scaling
        self._r = measurement_noise  # measurement noise (m²)

        # State and covariance
        self._x = np.zeros(2)            # [position, velocity]
        self._P = np.eye(2) * 1000.0    # large initial uncertainty
        self._H = np.array([[1.0, 0.0]])  # observe position only
        self._R = np.array([[measurement_noise]])
        self._initialized = False
        self._update_count: int = 0     # number of accepted updates so far
        self._rejected_count: int = 0   # consecutive gate rejections

    def _F_Q(self, dt: float):
        """Transition matrix and process noise for time step dt."""
        F = np.array([[1.0, dt],
                      [0.0, 1.0]])
        Q = np.array([
            [self._q * dt ** 3 / 3.0, self._q * dt ** 2 / 2.0],
            [self._q * dt ** 2 / 2.0, self._q * dt],
        ])
        return F, Q

    def predict(self, dt: float) -> None:
        """Advance state forward by dt with no measurement."""
        if dt <= 0:
            dt = 1e-6
        F, Q = self._F_Q(dt)
        self._x = F @ self._x
        self._P = F @ self._P @ F.T + Q

    def update(self, z: float) -> None:
        """Correct state with measurement z (position in metres)."""
        H, R = self._H, self._R
        S = H @ self._P @ H.T + R
        K = self._P @ H.T @ np.linalg.inv(S)
        self._x = self._x + K @ (np.array([z]) - H @ self._x)
        self._P = (np.eye(2) - K @ H) @ self._P
        self._update_count += 1

    @property
    def is_confident(self) -> bool:
        """True once the filter has processed enough updates to trust its velocity."""
        return self._update_count >= 5

    def predict_update(self, z: float, dt: float) -> None:
        """Predict then update — normal per-frame call."""
        self.predict(dt)
        self.update(z)

    def initialize(self, position: float) -> None:
        self._x = np.array([position, 0.0])
        self._P = np.eye(2) * 1000.0
        self._initialized = True

    @property
    def position(self) -> float:
        return float(self._x[0])

    @property
    def velocity(self) -> float:
        return float(self._x[1])

    @property
    def initialized(self) -> bool:
        return self._initialized

    def reset(self) -> None:
        self._x = np.zeros(2)
        self._P = np.eye(2) * 1000.0
        self._initialized = False
        self._update_count = 0
        self._rejected_count = 0


class VehicleDetector:
    """Detects vehicles and tracks their Kalman-filtered position from a vertical 2D LiDAR.

    Detection strategy:
      1. Compute a background distance model from initial frames (median).
      2. Points significantly closer than background indicate the vehicle.
      3. The leading edge position is fed into a Kalman filter for smooth tracking.
      4. Short gaps (bin, trailer) are bridged by dead-reckoning using the
         estimated velocity.

    Args:
        process_noise:        Kalman Q — trust in constant-velocity model.
        measurement_noise:    Kalman R — trust in the raw edge measurement.
        bg_threshold:         Distance (m) closer than background to classify as vehicle.
        bg_learning_frames:   Initial frames used to learn the background.
        travel_axis:          Axis index for vehicle travel direction (0=X, 1=Y).
        absence_hold_frames:  Consecutive empty frames to tolerate before declaring
                              vehicle gone. Bridges bin/trailer gaps.
    """

    def __init__(
        self,
        process_noise: float = 0.1,
        measurement_noise: float = 0.5,
        bg_threshold: float = 0.3,
        bg_learning_frames: int = 20,
        travel_axis: int = 0,
        absence_hold_frames: int = 10,
        min_vehicle_points: int = 5,
        innovation_gate: float = 0.5,
    ):
        self._kf = PositionTracker(process_noise, measurement_noise)
        self._bg_threshold = bg_threshold
        self._bg_learning_frames = bg_learning_frames
        self._travel_axis = travel_axis
        self._absence_hold_frames = absence_hold_frames
        self._min_vehicle_points = min_vehicle_points
        self._innovation_gate = innovation_gate

        self._bg_accumulator: list[np.ndarray] = []
        self._bg_distances: Optional[np.ndarray] = None
        self._last_t: Optional[float] = None
        self._vehicle_present = False
        self._absence_count: int = 0

        # Travel distance: integrated from velocity×dt, never reset on filter
        # reinitialisation so the profile coordinate never jumps backwards.
        self._travel_distance: float = 0.0

        # Debug recording
        self._debug_records: list[dict] = []

    def update(self, points: np.ndarray, timestamp: float) -> Optional[DetectionResult]:
        """Process one scan frame and return the detection/position result.

        Returns None during background learning. After that always returns a
        DetectionResult with vehicle_present True/False.
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
                self._absence_count += 1

                if self._absence_count <= self._absence_hold_frames:
                    # Bridge the gap — predict only, no measurement.
                    dt = timestamp - self._last_t if self._last_t is not None else 0.0
                    self._last_t = timestamp
                    self._kf.predict(dt)
                    self._travel_distance += self._kf.velocity * dt
                    return DetectionResult(
                        position=self._travel_distance,
                        raw_edge_position=0.0,
                        timestamp=timestamp,
                        vehicle_present=True,
                    )

                # Hold exhausted — vehicle truly left
                self._vehicle_present = False
                self._absence_count = 0
                self._kf.reset()

            self._last_t = timestamp
            return DetectionResult(
                position=self._kf.position,
                raw_edge_position=0.0,
                timestamp=timestamp,
                vehicle_present=False,
            )

        # --- Vehicle points found ---
        # Require a minimum number of points to accept the measurement.
        # Bin walls / floor give only a few stray points at the wrong position —
        # treat those frames the same as absence (predict only).
        if len(vehicle_indices) < self._min_vehicle_points:
            if self._vehicle_present and self._kf.initialized:
                dt = timestamp - self._last_t if self._last_t is not None else 0.0
                self._last_t = timestamp
                self._kf.predict(dt)
                self._travel_distance += self._kf.velocity * dt
                return DetectionResult(
                    position=self._travel_distance,
                    raw_edge_position=0.0,
                    timestamp=timestamp,
                    vehicle_present=True,
                )

        self._absence_count = 0

        vehicle_points = points[:n][vehicle_mask]
        edge_position = float(np.min(vehicle_points[:, self._travel_axis]))

        dt = timestamp - self._last_t if self._last_t is not None else 0.0
        self._last_t = timestamp

        if not self._kf.initialized:
            self._kf.initialize(edge_position)
            self._vehicle_present = True
            return DetectionResult(
                position=self._travel_distance,
                raw_edge_position=edge_position,
                timestamp=timestamp,
                vehicle_present=True,
            )

        # Innovation gate — only apply once the filter is confident about velocity.
        # In the first few frames velocity=0 so the gate would reject everything
        # and keep position stuck. Always accept measurements until we're confident.
        predicted = self._kf.position + self._kf.velocity * dt
        innovation = abs(edge_position - predicted)
        self._kf.predict(dt)

        if not self._kf.is_confident or innovation <= self._innovation_gate:
            self._kf.update(edge_position)
            self._kf._rejected_count = 0
        else:
            self._kf._rejected_count += 1
            # Divergence guard: if the filter has been consistently wrong for
            # too many consecutive frames, it has diverged (e.g. truck stopped
            # while velocity estimate is still large). Reinitialize to the
            # current measurement so tracking can recover.
            if self._kf._rejected_count >= 10:
                self._kf.reset()
                self._kf.update(edge_position)

        # Accumulate travel distance from the filtered velocity — this never
        # jumps on filter reinitialisation because it is purely integrative.
        self._travel_distance += self._kf.velocity * dt
        self._vehicle_present = True

        return DetectionResult(
            position=self._travel_distance,
            raw_edge_position=edge_position,
            timestamp=timestamp,
            vehicle_present=True,
        )

    def reset_tracking(self) -> None:
        """Reset Kalman state and vehicle presence, preserving the background model."""
        self._kf.reset()
        self._last_t = None
        self._vehicle_present = False
        self._absence_count = 0
        self._travel_distance = 0.0

    def reset(self) -> None:
        """Full reset including the background model."""
        self.reset_tracking()
        self._bg_accumulator.clear()
        self._bg_distances = None

    def dump_csv(self, path: str = "/tmp/vehicle_detector_debug.csv") -> str:
        """Write recorded position/velocity samples to CSV and return the path."""
        if not self._debug_records:
            return path
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._debug_records[0].keys())
            writer.writeheader()
            writer.writerows(self._debug_records)
        self._debug_records.clear()
        return path

    @property
    def vehicle_present(self) -> bool:
        return self._vehicle_present

    @property
    def current_position(self) -> float:
        return self._travel_distance

    @property
    def current_velocity(self) -> float:
        return self._kf.velocity if self._kf.initialized else 0.0
