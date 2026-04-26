"""
Profile accumulator — converts time-domain side-LiDAR scans into a spatial
vehicle profile using Kalman-filtered velocity.

Each side-mounted 2D LiDAR produces a scan line (a 2D cross-section) at each
timestamp.  Combined with the velocity from the vertical LiDAR, consecutive
scan lines are stacked along the travel axis to reconstruct a 3D profile of
the passing vehicle.

Usage:
    acc = ProfileAccumulator(travel_axis=0)
    acc.start_vehicle()
    for frame in side_frames:
        acc.add_scan_line(sensor_id, points_2d, velocity, timestamp)
    profile = acc.finish_vehicle()
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class VehicleProfile:
    """Completed vehicle profile — a 3D point cloud assembled from scan lines."""
    points: np.ndarray           # (N, 3) assembled point cloud
    start_time: float
    end_time: float
    scan_count: int
    sensor_ids: List[str]
    mean_velocity: float         # m/s averaged over the capture window

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def estimated_length(self) -> float:
        if len(self.points) == 0:
            return 0.0
        travel = self.points[:, 2]  # along-track axis stored in Z column
        return float(np.ptp(travel))


class ProfileAccumulator:
    """Accumulates 2D scan lines into a 3D vehicle profile.

    Coordinate convention for the output cloud:
      - Column 0 (X): scan-plane horizontal axis
      - Column 1 (Y): scan-plane vertical axis (height)
      - Column 2 (Z): along-track position computed from velocity integration

    Args:
        min_scan_lines: Minimum scan lines required to emit a valid profile.
        max_gap_s:      Maximum time gap between consecutive scans before
                        the accumulation is considered broken (vehicle left).
    """

    def __init__(
        self,
        min_scan_lines: int = 10,
        max_gap_s: float = 2.0,
    ):
        self._min_scan_lines = min_scan_lines
        self._max_gap_s = max_gap_s
        self._reset()

    def _reset(self) -> None:
        self._scan_lines: List[np.ndarray] = []
        self._sensor_ids: set[str] = set()
        self._start_time: Optional[float] = None
        self._last_time: Optional[float] = None
        self._along_track: float = 0.0
        self._velocity_sum: float = 0.0
        self._velocity_count: int = 0
        self._active = False

    def start_vehicle(self) -> None:
        """Begin accumulating scan lines for a new vehicle."""
        self._reset()
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    @property
    def scan_count(self) -> int:
        return len(self._scan_lines)

    def add_scan_line(
        self,
        sensor_id: str,
        points: np.ndarray,
        velocity: float,
        timestamp: float,
    ) -> None:
        """Append a single 2D scan line with velocity-based along-track offset.

        Args:
            sensor_id:  ID of the side-LiDAR that produced this scan.
            points:     (N, 2+) array — scan-plane X and Y coordinates.
            velocity:   Current vehicle velocity (m/s) from the velocity estimator.
            timestamp:  Unix timestamp of this scan.
        """
        if not self._active:
            return

        if points is None or len(points) < 2:
            return

        # Check for stale gap
        if self._last_time is not None:
            gap = timestamp - self._last_time
            if gap > self._max_gap_s:
                self._reset()
                return

        # Integrate along-track position
        if self._last_time is not None:
            dt = timestamp - self._last_time
            self._along_track += abs(velocity) * dt

        if self._start_time is None:
            self._start_time = timestamp

        self._last_time = timestamp
        self._sensor_ids.add(sensor_id)
        self._velocity_sum += abs(velocity)
        self._velocity_count += 1

        # Build 3D points: (scan_x, scan_y, along_track)
        n = len(points)
        along_track_col = np.full((n, 1), self._along_track)
        scan_xy = points[:, :2]
        points_3d = np.hstack([scan_xy, along_track_col])
        self._scan_lines.append(points_3d)

    def finish_vehicle(self) -> Optional[VehicleProfile]:
        """Finalize the current vehicle profile and return the assembled cloud.

        Returns:
            VehicleProfile if enough scan lines were accumulated, None otherwise.
        """
        if not self._active:
            return None

        self._active = False

        if len(self._scan_lines) < self._min_scan_lines:
            self._reset()
            return None

        all_points = np.concatenate(self._scan_lines, axis=0)
        mean_vel = self._velocity_sum / self._velocity_count if self._velocity_count > 0 else 0.0

        profile = VehicleProfile(
            points=all_points,
            start_time=self._start_time or 0.0,
            end_time=self._last_time or 0.0,
            scan_count=len(self._scan_lines),
            sensor_ids=sorted(self._sensor_ids),
            mean_velocity=mean_vel,
        )
        self._reset()
        return profile

    def abort(self) -> None:
        """Discard the current accumulation without emitting a profile."""
        self._reset()
