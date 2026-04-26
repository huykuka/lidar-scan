"""
Profile accumulator — converts time-domain side-LiDAR scans into a spatial
vehicle profile using Kalman-filtered velocity.

Each side-mounted 2D LiDAR produces a scan line at each timestamp.  If the
sensor nodes have their pose configured, the incoming points are already
transformed to world space (rotation + translation applied by LidarSensor).
The accumulator adds velocity-based along-track offsets to stitch consecutive
scans into a coherent 3D vehicle shape.

This means multiple side LiDARs at different mounting positions automatically
merge into a unified profile — their points are already aligned by their
respective pose transforms before reaching this accumulator.

Usage:
    acc = ProfileAccumulator(travel_axis=0)
    acc.start_vehicle()
    for frame in side_frames:
        acc.add_scan_line(sensor_id, points, velocity, timestamp)
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
    """Accumulates scan lines into a 3D vehicle profile.

    Points arriving from each side LiDAR may already be in world space
    (transformed by LidarSensor using the sensor's pose).  The accumulator
    preserves all 3 spatial dimensions and adds a velocity-integrated
    along-track offset to the Z column, stitching scan lines into a
    contiguous 3D shape.

    When multiple side sensors are mounted at different positions, their
    pose transforms place their points into the same coordinate frame,
    so the merged profile is spatially consistent.

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

    def _clear_accumulation(self) -> None:
        """Clear accumulated scan data without changing activation state."""
        self._scan_lines: List[np.ndarray] = []
        self._sensor_ids: set[str] = set()
        self._start_time: Optional[float] = None
        self._last_time: Optional[float] = None
        self._along_track: float = 0.0
        self._velocity_sum: float = 0.0
        self._velocity_count: int = 0

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

    def add_scan_line(
        self,
        sensor_id: str,
        points: np.ndarray,
        velocity: float,
        timestamp: float,
    ) -> None:
        """Append a scan line with velocity-based along-track offset.

        Accepts both 2D ``(N, 2)`` and 3D ``(N, 3+)`` point arrays.
        3D points (already pose-transformed by LidarSensor) keep their
        X/Y coordinates and get the along-track offset added to Z.
        2D points get a Z column synthesised from the along-track position.

        Args:
            sensor_id:  ID of the side-LiDAR that produced this scan.
            points:     (N, 2+) or (N, 3+) array of scan points.
            velocity:   Current vehicle velocity (m/s) from the velocity estimator.
            timestamp:  Unix timestamp of this scan.
        """
        if not self._active:
            return

        if points is None or len(points) < 2:
            return

        # Check for stale gap — clear data but stay active so new
        # scan lines can still be accumulated for this vehicle pass.
        if self._last_time is not None:
            gap = timestamp - self._last_time
            if gap > self._max_gap_s:
                self._clear_accumulation()
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

        n = len(points)
        if points.shape[1] >= 3:
            # 3D points already in world space (pose-transformed by LidarSensor).
            # Keep X/Y from the pose transform, add along-track offset to Z.
            points_3d = np.empty((n, 3), dtype=np.float64)
            points_3d[:, 0] = points[:, 0]
            points_3d[:, 1] = points[:, 1]
            points_3d[:, 2] = points[:, 2] + self._along_track
        else:
            # Raw 2D scan — synthesise Z from along-track position
            points_3d = np.empty((n, 3), dtype=np.float64)
            points_3d[:, 0] = points[:, 0]
            points_3d[:, 1] = points[:, 1]
            points_3d[:, 2] = self._along_track
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
