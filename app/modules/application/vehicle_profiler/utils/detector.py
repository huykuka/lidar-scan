"""
Vehicle detection and position tracking from a vertical 2D LiDAR.

Physical setup
--------------
The vertical LiDAR scans a plane along the travel direction.  An upstream
crop node is expected to deliver only the gantry-area scan (no far-field
noise).  The detector's own trigger crop further restricts to the window
``travel_axis >= -trigger_distance``.

Pipeline (per frame)
--------------------
1. **Trigger crop** — keep only points where the travel-axis coordinate is
   within ``trigger_distance`` metres of the gantry (X >= -trigger_distance).
   Skipped when ``trigger_distance`` is None (use full scan).
2. **DBSCAN clustering** — density-based clustering on the cropped scan.
   Noise points (label=-1) are discarded.
3. **Vehicle gate** — any cluster with at least ``min_vehicle_points`` is
   considered a vehicle cluster.  The largest such cluster is forwarded to
   the ICP tracker.
4. **ICP registration** — Open3D Point-to-Point ICP aligns the previous
   cluster to the current one.  Travel-axis translation = displacement.
5. **Position / velocity** — cumulative ICP displacement and per-frame
   velocity.  Dead-reckoning from last valid velocity on ICP failure.
6. **Departure** — no valid cluster in the cropped zone → vehicle absent
   immediately.
"""
import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple

import numpy as np
import open3d as o3d

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class DetectionResult:
    """Output of a single detector update."""

    position: float        # Cumulative travel distance (m)
    velocity: float        # Estimated velocity (m/s)
    timestamp: float
    vehicle_present: bool
    icp_valid: bool = True  # False when ICP failed (dead-reckoned)


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
            logger.debug("ICP fitness %.3f < min %.3f — rejected", reg.fitness, self._min_fitness)
            return None

        raw = float(reg.transformation[self._travel_axis, 3])

        # Dead-zone: treat sub-millimetre displacements as zero
        if abs(raw) < self._min_displacement:
            raw = 0.0

        # Outlier gate: reject implausibly large jumps
        if abs(raw) > self._max_displacement + 1e-6:
            logger.debug("ICP displacement %.4fm > max (%.4fm) — rejected", raw, self._max_displacement)
            return None

        self._last_displacement = raw
        logger.debug("ICP displacement=%.4fm  fitness=%.3f", raw, reg.fitness)
        return raw

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
# Vehicle detector (DBSCAN-based, no background model)
# ──────────────────────────────────────────────────────────────────────────────


class VehicleDetector:
    """Detect vehicles via DBSCAN clustering on a trigger-cropped 2D scan.

    No background learning is required.  An upstream crop node should
    already restrict the scan to the gantry area; this detector further
    crops to the leading-edge trigger window before clustering.

    Args:
        travel_axis:                 Axis index for the truck travel direction
                                     (0=X, 1=Y).
        min_vehicle_points:          Min points in a DBSCAN cluster to count
                                     as a vehicle.  Acts as a size gate —
                                     rejects noise and tiny debris clusters.
        dbscan_eps:                  DBSCAN neighbourhood radius (m).  Tune
                                     to the expected point spacing in the scan.
        dbscan_min_samples:          DBSCAN min samples per core point.
        trigger_distance:            Crop window: only consider points where
                                     ``points[:, travel_axis] >= -trigger_distance``
                                     (i.e. within trigger_distance metres of the
                                     gantry).  None = use the full incoming scan.
        max_correspondence_distance: ICP correspondence distance (m).
        min_icp_fitness:             Minimum ICP fitness to accept result.
        voxel_size:                  ICP voxel down-sample (0 = disabled).
        max_displacement:            Max per-frame ICP displacement (m).
        min_displacement:            ICP dead-zone (m).
    """

    def __init__(
        self,
        travel_axis: int = 0,
        min_vehicle_points: int = 10,
        dbscan_eps: float = 0.3,
        dbscan_min_samples: int = 5,
        trigger_distance: Optional[float] = None,
        max_correspondence_distance: float = 0.5,
        min_icp_fitness: float = 0.3,
        voxel_size: float = 0.0,
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
    ) -> None:
        self._travel_axis = travel_axis
        self._min_vehicle_points = min_vehicle_points
        self._dbscan_eps = dbscan_eps
        self._dbscan_min_samples = dbscan_min_samples
        self._trigger_distance = trigger_distance

        self._tracker = ClusterTracker(
            travel_axis=travel_axis,
            max_correspondence_distance=max_correspondence_distance,
            min_icp_fitness=min_icp_fitness,
            voxel_size=voxel_size,
            max_displacement=max_displacement,
            min_displacement=min_displacement,
        )

        # Position / velocity
        self._position: float = 0.0
        self._velocity: float = 0.0
        self._last_t: Optional[float] = None

        # Timestamped position history — used by get_position_at() so that
        # side-LiDAR scan lines can look up the position nearest to their own
        # timestamp, absorbing latency and frequency differences between sensors.
        # Bounded to the last 256 entries — enough for several seconds at 50 Hz.
        self._position_history: Deque[Tuple[float, float]] = deque(maxlen=256)

        # Tracking state
        self._vehicle_present: bool = False

    # ── Helpers ───────────────────────────────────────────────────────────

    def _crop_to_trigger_window(self, points: np.ndarray) -> np.ndarray:
        """Return only points inside the trigger window.

        Keeps points where the travel-axis coordinate is >= -trigger_distance
        (i.e. within ``trigger_distance`` metres of the gantry at X=0).
        When trigger_distance is None the full scan is returned unchanged.
        """
        if self._trigger_distance is None:
            return points
        mask = points[:, self._travel_axis] >= -self._trigger_distance
        return points[mask]

    def _largest_vehicle_cluster(self, points: np.ndarray) -> Optional[np.ndarray]:
        """Run DBSCAN and return the largest cluster with >= min_vehicle_points.

        Returns None if no valid cluster is found (scene empty or only noise).
        """
        if len(points) < self._dbscan_min_samples:
            return None

        # Build Open3D cloud (pad 2D → 3D)
        if points.shape[1] == 2:
            pts3d = np.zeros((len(points), 3), dtype=np.float64)
            pts3d[:, :2] = points
        else:
            pts3d = np.asarray(points[:, :3], dtype=np.float64)

        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(pts3d)

        labels = np.asarray(
            cloud.cluster_dbscan(
                eps=self._dbscan_eps,
                min_points=self._dbscan_min_samples,
                print_progress=False,
            )
        )

        # labels == -1 → noise; valid clusters are 0, 1, 2, …
        valid_labels = labels[labels >= 0]
        if len(valid_labels) == 0:
            return None

        unique, counts = np.unique(valid_labels, return_counts=True)

        # Size gate: discard clusters smaller than min_vehicle_points
        big_mask = counts >= self._min_vehicle_points
        if not big_mask.any():
            logger.debug(
                "DBSCAN: %d cluster(s) found but none reached min_vehicle_points=%d",
                len(unique), self._min_vehicle_points,
            )
            return None

        # Pick the largest cluster among valid ones
        best_label = unique[big_mask][np.argmax(counts[big_mask])]
        cluster_pts = points[labels == best_label]

        logger.debug(
            "DBSCAN: %d cluster(s), largest valid=%d pts (label %d)",
            big_mask.sum(), len(cluster_pts), best_label,
        )
        return cluster_pts

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
        self._last_t = timestamp
        return self._result(timestamp, present=False)

    # ── Main update ───────────────────────────────────────────────────────

    def update(self, points: np.ndarray, timestamp: float) -> Optional[DetectionResult]:
        """Process one scan frame.  Always returns a DetectionResult (never None)."""
        if points is None or len(points) < 2:
            return self._result(timestamp, present=False) if self._last_t is not None else None

        # 1. Crop to trigger window
        cropped = self._crop_to_trigger_window(points)

        # 2. Cluster — find largest valid cluster
        cluster = self._largest_vehicle_cluster(cropped)

        # 3. No valid cluster → absent
        if cluster is None:
            if self._vehicle_present:
                logger.info("Vehicle departed (no cluster in trigger window)")
                return self._stop(timestamp)
            self._last_t = timestamp
            return self._result(timestamp, present=False)

        # 4. Cluster present → ICP tracking
        spatial_pts = cluster[:, :3] if cluster.shape[1] >= 3 else cluster[:, :2]

        # First detection — seed tracker
        if not self._vehicle_present:
            self._tracker.update(spatial_pts, timestamp)
            self._last_t = timestamp
            self._vehicle_present = True
            logger.info(
                "Vehicle detected — cluster size=%d trigger_distance=%s",
                len(cluster), self._trigger_distance,
            )
            return self._result(timestamp, present=True)

        # Normal tracking — ICP displacement → position / velocity
        dt = (timestamp - self._last_t) if self._last_t is not None else 0.0
        self._last_t = timestamp

        displacement = self._tracker.update(spatial_pts, timestamp)

        if displacement is not None:
            self._position += displacement
            self._velocity = (displacement / dt) if dt > 0 else 0.0
            if displacement != 0.0:
                self._position_history.append((timestamp, self._position))
            return self._result(timestamp, present=True)

        # ICP failed — dead-reckon from last velocity
        if dt > 0:
            self._position += self._velocity * dt
            self._position_history.append((timestamp, self._position))
        return self._result(timestamp, present=True, icp_valid=False)

    # ── Reset ─────────────────────────────────────────────────────────────

    def reset_tracking(self) -> None:
        """Reset tracking state only."""
        self._tracker.reset()
        self._position = 0.0
        self._velocity = 0.0
        self._last_t = None
        self._vehicle_present = False
        self._position_history.clear()

    def reset(self) -> None:
        """Full reset (alias for reset_tracking — no background model to clear)."""
        self.reset_tracking()

    # ── Accessors ─────────────────────────────────────────────────────────

    def get_position_at(self, timestamp: float, max_age: float = 0.5) -> Optional[float]:
        """Return the recorded position nearest to the given timestamp.

        Side-LiDAR scan lines arrive with their own hardware timestamp which
        may differ from the velocity sensor's timestamp due to latency or
        different scan rates.  This method finds the position sample whose
        timestamp is closest to the requested one, absorbing latency and
        frequency differences between sensors.

        Args:
            timestamp:  The scan's own hardware timestamp (seconds).
            max_age:    Maximum allowed time gap (seconds) between the
                        requested timestamp and the nearest recorded sample.
                        If the gap exceeds this, None is returned so the
                        caller can discard the scan line rather than place
                        it at an incorrect position.  Defaults to 0.5 s —
                        generous enough for mixed 10/20 Hz setups but tight
                        enough to catch clock drift or a stalled velocity
                        sensor.

        Returns:
            Nearest recorded position (m), or None if no sample is within
            max_age seconds (history empty, clock drift, or sensor stall).
        """
        if not self._position_history:
            return None

        best_t, best_pos = min(self._position_history, key=lambda tp: abs(tp[0] - timestamp))
        dt = abs(best_t - timestamp)

        if dt > max_age:
            logger.warning(
                "get_position_at %.4f: nearest sample is %.4f s away (max_age=%.2f s) "
                "— discarding scan line to avoid position drift",
                timestamp, dt, max_age,
            )
            return None

        logger.debug(
            "get_position_at %.4f → matched %.4f (Δt=%.4f s) pos=%.4f m",
            timestamp, best_t, dt, best_pos,
        )
        return best_pos

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
