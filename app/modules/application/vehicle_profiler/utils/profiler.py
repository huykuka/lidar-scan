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
    gate = SideLidarGate(bg_threshold=0.3, bg_learning_frames=20)
    acc = ProfileAccumulator(travel_axis=0)
    acc.start_vehicle()
    for frame in side_frames:
        vehicle_pts = gate.filter(frame.points)
        if vehicle_pts is not None:
            acc.add_scan_line(sensor_id, vehicle_pts, position, timestamp)
    profile = acc.finish_vehicle()
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class SideLidarGate:
    """Self-gating filter for side LiDARs — learns background, passes only vehicle points.

    Each side LiDAR independently learns a per-beam background distance model
    during the first N frames (empty scene).  After learning, each incoming
    frame is checked: beams significantly closer than background are vehicle
    points.  If enough vehicle points are present, the filtered (vehicle-only)
    points are returned; otherwise None (skip this frame).

    This prevents accumulating empty/background slices into the profile when
    the truck hasn't reached (or has already passed) this sensor's FOV.

    Args:
        bg_threshold:        Distance delta (m) above background to be considered vehicle.
        bg_learning_frames:  Number of initial frames for background model.
        min_vehicle_points:  Minimum foreground points to accept a frame as "vehicle present".
    """

    def __init__(
        self,
        bg_threshold: float = 0.3,
        bg_learning_frames: int = 20,
        min_vehicle_points: int = 5,
    ) -> None:
        self._bg_threshold = bg_threshold
        self._bg_learning_frames = bg_learning_frames
        self._min_vehicle_points = min_vehicle_points

        self._bg_accumulator: List[np.ndarray] = []
        self._bg_distances: Optional[np.ndarray] = None

    @property
    def background_ready(self) -> bool:
        """True once background model has been learned."""
        return self._bg_distances is not None

    def filter(self, points: np.ndarray) -> Optional[np.ndarray]:
        """Process one scan frame from a side LiDAR.

        Args:
            points: (N, 2+) array of scan points (spatial coordinates).

        Returns:
            Filtered vehicle-only points if vehicle is present, None otherwise.
            During background learning, returns None (frame is consumed for learning).
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
                    padded[i, : len(d)] = d
                self._bg_distances = np.nanmedian(padded, axis=0)
                self._bg_accumulator.clear()
                logger.debug("SideLidarGate: background learned")
            return None

        # --- Gating: background subtraction ---
        n = min(len(distances), len(self._bg_distances))
        delta = self._bg_distances[:n] - distances[:n]
        vehicle_mask = delta > self._bg_threshold
        n_vehicle = int(vehicle_mask.sum())

        if n_vehicle < self._min_vehicle_points:
            return None

        return points[:n][vehicle_mask]

    def reset(self) -> None:
        """Full reset — re-learn background."""
        self._bg_accumulator.clear()
        self._bg_distances = None


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
                            direction (0=X, 1=Y, 2=Z).  The position is placed
                            on this axis.
        min_position_delta: Minimum position change (m) required between
                            consecutive scan lines.  Scans where the vehicle
                            has moved less than this since the last accepted
                            scan are skipped.  Prevents redundant overlapping
                            lines at low speeds.  Set to 0 to accept every
                            scan regardless of position change.
        min_height:         Minimum Z height (m) for a point to be kept.
                            Points at or below this threshold are ground noise
                            and are dropped before accumulation.  Set to 0.0
                            (default) to keep all points.
    """

    def __init__(
        self,
        min_scan_lines: int = 10,
        max_gap_s: float = 2.0,
        travel_axis: int = 2,
        min_position_delta: float = 0.0,
        min_height: float = 0.0,
    ):
        self._min_scan_lines = min_scan_lines
        self._max_gap_s = max_gap_s
        self._travel_axis = travel_axis
        self._min_position_delta = min_position_delta
        self._min_height = min_height
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

        # Drop ground-level points — the height axis is whichever axis is
        # not the travel axis (typically Z=2).  Points at or below min_height
        # are road surface noise from the extended LiDAR FOV.
        if self._min_height > 0.0:
            height_axis = next(i for i in range(3) if i != ta)
            points_3d = points_3d[points_3d[:, height_axis] > self._min_height]
            if len(points_3d) < 2:
                return

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
