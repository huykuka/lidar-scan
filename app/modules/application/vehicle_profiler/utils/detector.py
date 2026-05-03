"""
Vehicle detection and position tracking from a vertical 2D LiDAR.

Physical setup
--------------
The vertical LiDAR scans a plane along the travel direction, covering the
full gantry width so both the leading and trailing edges of the truck are
visible throughout the entire pass.

Pipeline (per frame)
--------------------
1. **Background learning** — per-beam median from the first N empty-scene frames.
2. **Vehicle detection** — background subtraction; foreground = vehicle cluster.
3. **ICP registration** — Open3D Point-to-Point ICP aligns previous cluster to
   current cluster.  Travel-axis translation = displacement for this frame.
4. **Position / velocity** — position is the cumulative ICP displacement;
   velocity is displacement / dt.  On ICP failure the last valid velocity is
   used to dead-reckon position until ICP recovers.
5. **Stop** — cluster absent for > ``gap_debounce_s`` → vehicle departed.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import open3d as o3d

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class DetectionResult:
    """Output of a single detector update."""

    position: float               # Cumulative travel distance (m)
    velocity: float
    velocity: float           # Estimated velocity (m/s)
    timestamp: float
    vehicle_present: bool
    icp_valid: bool = True    # False when ICP failed (dead-reckoned)


# ──────────────────────────────────────────────────────────────────────────────
# ICP-based cluster tracker
# ──────────────────────────────────────────────────────────────────────────────


class ClusterTracker:
    """Per-frame displacement via Open3D Point-to-Point ICP.

    Aligns the previous cluster cloud to the current one and returns the
    travel-axis component of the resulting translation.

    Args:
        travel_axis:                   Axis index for travel direction (0=X).
        max_correspondence_distance:   ICP max correspondence distance (m).
        min_icp_fitness:               Minimum fitness to accept ICP result.
        max_displacement:              Outlier gate (m).
        min_displacement:              Dead-zone (m).
        voxel_size:                    Downsample voxel size (0 = disabled).
    """

    def __init__(
        self,
        travel_axis: int = 0,
        max_correspondence_distance: float = 0.5,
        min_icp_fitness: float = 0.3,
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
        voxel_size: float = 0.0,
    ) -> None:
        self._travel_axis = travel_axis
        self._max_corr_dist = max_correspondence_distance
        self._min_fitness = min_icp_fitness
        self._max_displacement = max_displacement
        self._min_displacement = min_displacement
        self._voxel_size = voxel_size

        self._prev_cloud: Optional[o3d.geometry.PointCloud] = None
        self._last_displacement: float = 0.0

    # ── Helpers ───────────────────────────────────────────────────────────

    def _to_cloud(self, points: np.ndarray) -> o3d.geometry.PointCloud:
        """Convert Nx2 or Nx3 array → Open3D PointCloud (pads to 3D)."""
        if points.shape[1] == 2:
            pts3d = np.zeros((len(points), 3), dtype=np.float64)
            pts3d[:, :2] = points
        else:
            pts3d = np.asarray(points[:, :3], dtype=np.float64)
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(pts3d)
        return cloud

    # ── Public API ────────────────────────────────────────────────────────

    def update(self, points: np.ndarray, timestamp: float) -> Optional[float]:
        """Return displacement (m, forward-positive), or None on failure."""
        cloud = self._to_cloud(points)

        if self._prev_cloud is None or len(self._prev_cloud.points) < 3:
            self._prev_cloud = cloud
            return 0.0

        reg = o3d.pipelines.registration.registration_icp(
            self._prev_cloud,
            cloud,
            self._max_corr_dist,
            np.eye(4),
            o3d.pipelines.registration.TransformationEstimationPointToPoint(),
        )
        self._prev_cloud = cloud
   

        if reg.fitness < self._min_fitness:
            logger.info("ICP fitness %.3f < min — rejected", reg.fitness)
            return None

        displacement = max(0.0, float(reg.transformation[self._travel_axis, 3]))

        if displacement > self._max_displacement:
            logger.debug("ICP displacement %.4fm > max (%.4fm) — rejected", displacement, self._max_displacement)
            return None

        if displacement < self._min_displacement:
            displacement = 0.0

        self._last_displacement = displacement
        logger.debug("ICP displacement=%.4fm  fitness=%.3f", displacement, reg.fitness)
        return displacement

    def reset(self) -> None:
        self._prev_cloud = None
        self._last_displacement = 0.0

    @property
    def last_displacement(self) -> float:
        return self._last_displacement

    @property
    def initialized(self) -> bool:
        return self._prev_cloud is not None


# ──────────────────────────────────────────────────────────────────────────────
# Vehicle detector (orchestrates tracker + direct position/velocity)
# ──────────────────────────────────────────────────────────────────────────────


class VehicleDetector:
    """Detect vehicles via background subtraction and track position directly
    from ICP displacement.

    Position is the cumulative sum of accepted ICP displacements.
    Velocity is displacement / dt for the current frame.  When ICP fails the
    last valid velocity is used to dead-reckon position until ICP recovers.

    Vehicle travel direction is assumed to be positive-X.  Frames where ICP
    reports negative displacement (truck reversing) are suppressed — the
    detector returns vehicle_present=False until forward motion resumes.

    Args:
        bg_threshold:                Delta (m) above background → vehicle.
        bg_learning_frames:          Frames for background model.
        travel_axis:                 Travel direction axis (0=X, 1=Y).
        gap_debounce_s:              Seconds of absence before departure.
        min_vehicle_points:          Min foreground points per frame.
        max_correspondence_distance: ICP correspondence distance (m).
        min_icp_fitness:             Minimum ICP fitness to accept.
        voxel_size:                  ICP voxel down-sample (0 = disabled).
        max_displacement:            Max per-frame displacement (m).
        min_displacement:            Dead-zone (m).
        trigger_distance:            How far before the gantry (m, positive
                                     value) the leading edge must be to trigger
                                     detection.  E.g. 0.1 fires when the truck
                                     front is within 10 cm of X=0.
                                     None = trigger anywhere.
    """

    def __init__(
        self,
        bg_threshold: float = 0.3,
        bg_learning_frames: int = 20,
        travel_axis: int = 0,
        gap_debounce_s: float = 3.0,
        min_vehicle_points: int = 5,
        max_correspondence_distance: float = 0.5,
        min_icp_fitness: float = 0.3,
        voxel_size: float = 0.0,
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
        trigger_distance: Optional[float] = None,
    ) -> None:
        self._bg_threshold = bg_threshold
        self._bg_learning_frames = bg_learning_frames
        self._travel_axis = travel_axis
        # trigger_distance crops the scan to X >= -trigger_distance before any
        # background subtraction — points outside that window are invisible to
        # the detector.  None = no crop (full scan used).
        self._trigger_distance = trigger_distance
        self._gap_debounce_s = gap_debounce_s
        self._min_vehicle_points = min_vehicle_points

        self._tracker = ClusterTracker(
            travel_axis=travel_axis,
            max_correspondence_distance=max_correspondence_distance,
            min_icp_fitness=min_icp_fitness,
            voxel_size=voxel_size,
            max_displacement=max_displacement,
            min_displacement=min_displacement,
        )

        # Background model
        self._bg_accumulator: list[np.ndarray] = []
        self._bg_distances: Optional[np.ndarray] = None

        # Position / velocity (direct from ICP, no filter)
        self._position: float = 0.0
        self._velocity: float = 0.0
        self._last_t: Optional[float] = None

        # Tracking state
        self._vehicle_present: bool = False
        self._absence_since: Optional[float] = None

    # ── Helpers ───────────────────────────────────────────────────────────

    def _result(
        self,
        timestamp: float,
        present: bool = True,
        icp_valid: bool = True,
    ) -> DetectionResult:
        return DetectionResult(
            position=self._position,
            velocity=self._velocity,
            timestamp=timestamp,
            vehicle_present=present,
            icp_valid=icp_valid,
        )

    def _stop(self, timestamp: float) -> DetectionResult:
        self._vehicle_present = False
        self._absence_since = None
        self._last_t = timestamp
        return self._result(timestamp, present=False)

    # ── Main update ───────────────────────────────────────────────────────

    def update(self, points: np.ndarray, timestamp: float) -> Optional[DetectionResult]:
        """Process one scan frame.  Returns None during background learning."""
        if points is None or len(points) < 2:
            return None

        # Always compute distances from the full scan so the background model
        # and ICP stay aligned on the same beam indices.
        distances = np.linalg.norm(points[:, :2], axis=1)

        # Background learning — full scan
        if self._bg_distances is None:
            self._bg_accumulator.append(distances)
            if len(self._bg_accumulator) >= self._bg_learning_frames:
                max_len = max(len(d) for d in self._bg_accumulator)
                padded = np.full((len(self._bg_accumulator), max_len), np.nan)
                for i, d in enumerate(self._bg_accumulator):
                    padded[i, : len(d)] = d
                self._bg_distances = np.nanmedian(padded, axis=0)
                self._bg_accumulator.clear()
            return None

        # Vehicle detection — full-scan mask
        n = min(len(distances), len(self._bg_distances))
        delta = self._bg_distances[:n] - distances[:n]
        vehicle_mask = delta > self._bg_threshold

        # Trigger gate: for the initial trigger only, count vehicle points
        # inside the crop window so the truck must be near the gantry before
        # detection starts.  Once tracking is active use the full count so
        # structural gaps in the far zone don't cause a false departure.
        if self._trigger_distance is not None :
            crop_mask = points[:n, self._travel_axis] >= -self._trigger_distance
            n_vehicle = int((vehicle_mask & crop_mask).sum())
        else:
            n_vehicle = int(vehicle_mask.sum())

        # No cluster
        if n_vehicle < self._min_vehicle_points:
            if self._vehicle_present:
                if self._absence_since is None:
                    self._absence_since = timestamp
                if (timestamp - self._absence_since) < self._gap_debounce_s:
                    return self._result(timestamp, present=True)
                return self._stop(timestamp)
            self._last_t = timestamp
            return self._result(timestamp, present=False)

        # Cluster present — ICP uses full scan
        self._absence_since = None
        spatial_pts = points[:, :3] if points.shape[1] >= 3 else points[:, :2]

        # First detection — seed tracker, no displacement yet
        if not self._vehicle_present:
            self._tracker.update(spatial_pts, timestamp)
            self._last_t = timestamp
            self._vehicle_present = True
            return self._result(timestamp, present=True)

        # Normal tracking — ICP displacement → position / velocity
        dt = (timestamp - self._last_t) if self._last_t is not None else 0.0
        self._last_t = timestamp

        displacement = self._tracker.update(spatial_pts, timestamp)

        if displacement is not None:
            self._position += displacement
            self._velocity = (displacement / dt) if dt > 0 else 0.0
            return self._result(timestamp, present=True)

        return self._result(timestamp, present=True, icp_valid=False)

    # ── Reset ─────────────────────────────────────────────────────────────

    def reset_tracking(self) -> None:
        """Reset tracking state, preserve background model."""
        self._tracker.reset()
        self._position = 0.0
        self._velocity = 0.0
        self._last_t = None
        self._vehicle_present = False
        self._absence_since = None

    def reset(self) -> None:
        """Full reset including background model."""
        self.reset_tracking()
        self._bg_accumulator.clear()
        self._bg_distances = None

    # ── Accessors ─────────────────────────────────────────────────────────

    @property
    def vehicle_present(self) -> bool:
        return self._vehicle_present

    @property
    def current_position(self) -> float:
        """Cumulative ICP travel distance (m)."""
        return self._position

    @property
    def current_velocity(self) -> float:
        """Last valid ICP velocity (m/s)."""
        return self._velocity
