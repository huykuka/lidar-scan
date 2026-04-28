"""
Profile accumulator — converts time-domain side-LiDAR scans into a spatial
vehicle profile using Kalman-filtered position.

Each side-mounted 2D LiDAR produces a scan line at each timestamp.  If the
sensor nodes have their pose configured, the incoming points are already
transformed to world space (rotation + translation applied by LidarSensor).
The accumulator uses the Kalman-filtered position directly as the along-track
coordinate, avoiding velocity-integration drift.

This means multiple side LiDARs at different mounting positions automatically
merge into a unified profile — their points are already aligned by their
respective pose transforms before reaching this accumulator.

Usage:
    acc = ProfileAccumulator(travel_axis=0)  # 0=X, 1=Y, 2=Z
    acc.start_vehicle()
    for frame in side_frames:
        acc.add_scan_line(sensor_id, points, position, timestamp)
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
    travel_axis: int = 2          # which column holds the along-track position

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def estimated_length(self) -> float:
        if len(self.points) == 0:
            return 0.0
        travel = self.points[:, self.travel_axis]
        return float(np.ptp(travel))


class ProfileAccumulator:
    """Accumulates scan lines into a 3D vehicle profile.

    Points arriving from each side LiDAR may already be in world space
    (transformed by LidarSensor using the sensor's pose).  The accumulator
    preserves all 3 spatial dimensions and uses the Kalman-filtered position
    directly as the along-track coordinate on the configured ``travel_axis``,
    avoiding velocity-integration drift.

    When multiple side sensors are mounted at different positions, their
    pose transforms place their points into the same coordinate frame,
    so the merged profile is spatially consistent.

    Args:
        min_scan_lines:     Minimum scan lines required to emit a valid profile.
        max_gap_s:          Maximum time gap between consecutive scans before
                            the accumulation is considered broken (vehicle left).
        travel_axis:        Which 3D axis corresponds to the vehicle travel
                            direction (0=X, 1=Y, 2=Z).  The Kalman-filtered
                            position is placed on this axis.
        min_position_delta: Minimum position change (m) required between
                            consecutive scan lines.  Scans where the vehicle
                            has moved less than this since the last accepted
                            scan are skipped.  Prevents redundant overlapping
                            lines at low speeds.  Set to 0 to accept every
                            scan regardless of position change.
    """

    def __init__(
        self,
        min_scan_lines: int = 10,
        max_gap_s: float = 2.0,
        travel_axis: int = 2,
        min_position_delta: float = 0.0,
    ):
        self._min_scan_lines = min_scan_lines
        self._max_gap_s = max_gap_s
        self._travel_axis = travel_axis
        self._min_position_delta = min_position_delta
        self._reset()

    def _clear_accumulation(self) -> None:
        """Clear accumulated scan data without changing activation state."""
        self._scan_lines: List[np.ndarray] = []
        self._sensor_ids: set[str] = set()
        self._start_time: Optional[float] = None
        self._last_time: Optional[float] = None
        self._last_position: float = 0.0
        self._last_accepted_position: Optional[float] = None

    def _reset(self) -> None:
        self._clear_accumulation()
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

    def touch_timestamp(self, timestamp: float) -> None:
        """Update the gap timer without adding a scan line.

        Call this when a frame is intentionally skipped (e.g. due to the
        velocity filter) so that the gap timeout does not falsely expire
        and clear accumulated data.
        """
        if self._active and self._last_time is not None:
            self._last_time = timestamp

    def add_scan_line(
        self,
        sensor_id: str,
        points: np.ndarray,
        position: float,
        timestamp: float,
    ) -> None:
        """Append a scan line using Kalman-filtered position directly.

        Accepts both 2D ``(N, 2)`` and 3D ``(N, 3+)`` point arrays.
        3D points (already pose-transformed by LidarSensor) keep their
        existing coordinates and get the position added to the configured
        ``travel_axis``.
        2D points are promoted to 3D with the position placed on the
        ``travel_axis`` and the 2D coordinates filling the other two axes.

        Using position directly (instead of integrating velocity) avoids
        drift and gives more accurate spatial alignment.

        Args:
            sensor_id:  ID of the side-LiDAR that produced this scan.
            points:     (N, 2+) or (N, 3+) array of scan points.
            position:   Current Kalman-filtered along-track position (m).
            timestamp:  Unix timestamp of this scan.
        """
        if not self._active:
            return

        if points is None or len(points) < 2:
            return

        # # Check for stale gap — clear data but stay active so new
        # # scan lines can still be accumulated for this vehicle pass.
        if self._last_time is not None:
            gap = timestamp - self._last_time
            if gap > self._max_gap_s:
                self._clear_accumulation()
                return

        # Skip if position hasn't changed enough since last accepted scan.
        # This prevents redundant overlapping lines at low vehicle speeds.
        if (
            self._min_position_delta > 0
            and self._last_accepted_position is not None
            and abs(position - self._last_accepted_position) < self._min_position_delta
        ):
            return

        if self._start_time is None:
            self._start_time = timestamp
        self._last_time = timestamp
        self._last_position = position
        self._last_accepted_position = position
        self._sensor_ids.add(sensor_id)

        ta = self._travel_axis
        n = len(points)
        if points.shape[1] >= 3:
            # 3D points already in world space (pose-transformed by LidarSensor).
            # Replace the travel-axis value with the detector's position so
            # that each scan slice is placed at the correct along-track
            # coordinate.  The other two axes keep their pose-transformed
            # values (the actual cross-section shape).
            points_3d = np.array(points[:, :3], dtype=np.float64)
            points_3d[:, ta] = position
        else:
            # Raw 2D scan — promote to 3D, placing position on travel axis.
            # The two non-travel axes get the 2D scan coordinates.
            points_3d = np.empty((n, 3), dtype=np.float64)
            non_travel = [i for i in range(3) if i != ta]
            points_3d[:, non_travel[0]] = points[:, 0]
            points_3d[:, non_travel[1]] = points[:, 1]
            points_3d[:, ta] = position
        self._scan_lines.append(points_3d)

    def get_accumulated_cloud(self) -> Optional[np.ndarray]:
        """Return the current accumulated point cloud without finalizing.

        Returns the concatenated points accumulated so far, or None if
        there are no scan lines yet.  Used for streaming partial profiles
        to the UI while the vehicle is still being measured.
        """
        if not self._scan_lines:
            return None
        return np.concatenate(self._scan_lines, axis=0)

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

        profile = VehicleProfile(
            points=all_points,
            start_time=self._start_time or 0.0,
            end_time=self._last_time or 0.0,
            scan_count=len(self._scan_lines),
            sensor_ids=sorted(self._sensor_ids),
            travel_axis=self._travel_axis,
        )
        self._reset()
        return profile

    def abort(self) -> None:
        """Discard the current accumulation without emitting a profile."""
        self._reset()
