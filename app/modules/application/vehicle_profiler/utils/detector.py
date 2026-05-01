"""
Vehicle detection and Kalman-filtered position tracking from a vertical 2D LiDAR.

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
   current cluster.  Travel-axis translation = raw displacement.
4. **Kalman filter** — pykalman constant-velocity filter smooths position and
   estimates velocity.  On ICP failure it dead-reckons using last velocity.
5. **Stop** — cluster absent for > ``gap_debounce_s`` → vehicle departed.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import numpy.ma as ma
import open3d as o3d
from pykalman import KalmanFilter

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class DetectionResult:
    """Output of a single detector update."""

    position: float           # Kalman-filtered travel distance (m)
    centroid_position: float  # cluster centroid on travel axis (m)
    velocity: float           # Kalman-filtered velocity (m/s)
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
        if self._voxel_size > 0:
            cloud = cloud.voxel_down_sample(self._voxel_size)
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
            logger.info("ICP displacement %.4fm > max — rejected", displacement)
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
# Kalman filter (pykalman)
# ──────────────────────────────────────────────────────────────────────────────


class PositionKalmanFilter:
    """1-D constant-velocity Kalman filter backed by pykalman.

    State: ``[position, velocity]``
    Observation: velocity implied by ICP displacement (``displacement / dt``).

    On ICP failure a masked observation triggers predict-only (dead-reckoning).
    The transition matrix is rebuilt each step with the actual ``dt`` so the
    filter handles variable frame rates correctly.

    Args:
        process_noise_pos:  Position process noise (m²/s).
        process_noise_vel:  Velocity process noise (m²/s³).
        measurement_noise:  Velocity measurement noise (m²/s²).
        initial_covariance: Diagonal of the initial covariance matrix.
    """

    def __init__(
        self,
        process_noise_pos: float = 1e-4,
        process_noise_vel: float = 1e-2,
        measurement_noise: float = 1e-4,
        initial_covariance: float = 1.0,
    ) -> None:
        self._q_pos = process_noise_pos
        self._q_vel = process_noise_vel
        self._R = measurement_noise
        self._init_cov = initial_covariance

        self._x: np.ndarray = np.array([0.0, 0.0])
        self._P: np.ndarray = np.eye(2) * initial_covariance
        self._last_t: Optional[float] = None
        self._initialized = False

    def _make_kf(self, dt: float) -> KalmanFilter:
        """Build a pykalman KalmanFilter for the given dt."""
        return KalmanFilter(
            transition_matrices=np.array([[1.0, dt], [0.0, 1.0]]),
            observation_matrices=np.array([[0.0, 1.0]]),
            transition_covariance=np.array([
                [self._q_pos * dt, 0.0],
                [0.0, self._q_vel * dt],
            ]),
            observation_covariance=np.array([[self._R]]),
        )

    @property
    def position(self) -> float:
        return float(self._x[0])

    @property
    def velocity(self) -> float:
        return float(self._x[1])

    @property
    def initialized(self) -> bool:
        return self._initialized

    def step(self, timestamp: float, displacement: Optional[float] = None) -> None:
        """Predict, then update (or dead-reckon if *displacement* is None)."""
        if not self._initialized:
            self._last_t = timestamp
            self._initialized = True
            if displacement is not None:
                self._x[0] += displacement
            return

        dt = timestamp - self._last_t if self._last_t is not None else 0.0
        self._last_t = timestamp

        if dt <= 0:
            if displacement is not None:
                self._x[0] += displacement
            return

        kf = self._make_kf(dt)

        if displacement is not None:
            obs = np.array([displacement / dt])
            self._x, self._P = kf.filter_update(self._x, self._P, observation=obs)
            # Trust ICP for position; let the KF smooth velocity only.
            self._x[0] = self._x[0] - self._x[1] * dt + displacement
        else:
            self._x, self._P = kf.filter_update(
                self._x, self._P, observation=ma.masked,
            )

        # Forward-only velocity
        if self._x[1] < 0:
            self._x[1] = 0.0

    def reset(self) -> None:
        self._x = np.array([0.0, 0.0])
        self._P = np.eye(2) * self._init_cov
        self._last_t = None
        self._initialized = False


# ──────────────────────────────────────────────────────────────────────────────
# Vehicle detector (orchestrates tracker + Kalman)
# ──────────────────────────────────────────────────────────────────────────────


class VehicleDetector:
    """Detect vehicles via background subtraction and track position with
    ICP + Kalman filtering.

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
        process_noise_pos:           Kalman position process noise (m²/s).
        process_noise_vel:           Kalman velocity process noise (m²/s³).
        measurement_noise:           Kalman velocity measurement noise (m²/s²).
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
        process_noise_pos: float = 1e-4,
        process_noise_vel: float = 1e-2,
        measurement_noise: float = 1e-4,
    ) -> None:
        self._bg_threshold = bg_threshold
        self._bg_learning_frames = bg_learning_frames
        self._travel_axis = travel_axis
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

        self._kf = PositionKalmanFilter(
            process_noise_pos=process_noise_pos,
            process_noise_vel=process_noise_vel,
            measurement_noise=measurement_noise,
        )

        # Background model
        self._bg_accumulator: list[np.ndarray] = []
        self._bg_distances: Optional[np.ndarray] = None

        # Tracking state
        self._last_t: Optional[float] = None
        self._vehicle_present: bool = False
        self._absence_since: Optional[float] = None

    # ── Helpers ───────────────────────────────────────────────────────────

    def _result(
        self,
        timestamp: float,
        centroid_pos: float = 0.0,
        present: bool = True,
        icp_valid: bool = True,
    ) -> DetectionResult:
        return DetectionResult(
            position=self._kf.position,
            centroid_position=centroid_pos,
            velocity=self._kf.velocity,
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

        distances = np.linalg.norm(points[:, :2], axis=1)

        # Background learning
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

        # Vehicle detection
        n = min(len(distances), len(self._bg_distances))
        delta = self._bg_distances[:n] - distances[:n]
        vehicle_mask = delta > self._bg_threshold
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

        # Cluster present
        self._absence_since = None
        vehicle_pts = points[:n][vehicle_mask]
        spatial_pts = vehicle_pts[:, :3] if vehicle_pts.shape[1] >= 3 else vehicle_pts[:, :2]
        centroid_pos = float(spatial_pts[:, self._travel_axis].mean())
        self._last_t = timestamp

        # First detection — seed tracker
        if not self._vehicle_present:
            self._tracker.update(spatial_pts, timestamp)
            self._kf.step(timestamp, displacement=0.0)
            self._vehicle_present = True
            return self._result(timestamp, centroid_pos=centroid_pos, present=True)

        # Normal tracking — ICP → Kalman
        displacement = self._tracker.update(spatial_pts, timestamp)

        if displacement is not None:
            self._kf.step(timestamp, displacement=displacement)
            return self._result(timestamp, centroid_pos=centroid_pos, present=True)

        # ICP failed — Kalman dead-reckons
        self._kf.step(timestamp, displacement=None)
        return self._result(
            timestamp, centroid_pos=centroid_pos, present=True, icp_valid=False,
        )

    # ── Reset ─────────────────────────────────────────────────────────────

    def reset_tracking(self) -> None:
        """Reset tracking state, preserve background model."""
        self._tracker.reset()
        self._kf.reset()
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
        """Kalman-filtered travel distance (m)."""
        return self._kf.position

    @property
    def current_velocity(self) -> float:
        """Kalman-filtered velocity (m/s)."""
        return self._kf.velocity
