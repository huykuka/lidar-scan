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
   the tracker.
4. **Registration** — `small_gicp` Generalised ICP aligns the previous
   cluster to the current one and returns the SE(3) transformation.
   Travel-axis translation extracted from the result = displacement.
5. **Position / velocity** — cumulative displacement and per-frame velocity.
   Dead-reckoning from last valid velocity on registration failure.
6. **Departure** — no valid cluster in the cropped zone → vehicle absent
   immediately.
"""
import logging
import contextlib
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Tuple

import numpy as np
import open3d as o3d
import small_gicp

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _suppress_c_stderr():
    """Redirect C-level stderr to /dev/null for the duration of the block.

    ``small_gicp`` emits harmless "voxel coord is out of range" warnings
    straight to C stderr when ``downsampling_resolution=0.0``.  Python's
    ``logging`` and ``sys.stderr`` redirects cannot silence them — only an
    ``os.dup2`` swap at the file-descriptor level works.
    """
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd = os.dup(2)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    try:
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)


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
    icp_valid: bool = True  # False when registration failed (dead-reckoned)


# ──────────────────────────────────────────────────────────────────────────────
# Cluster tracker — small_gicp GICP
# ──────────────────────────────────────────────────────────────────────────────


class ClusterTracker:
    """Per-frame displacement estimation via small_gicp GICP.

    `small_gicp` Generalised ICP fits a 3-D local covariance around each
    point and solves the covariance-weighted alignment using analytic
    gradients and a KD-tree.  ~0.3 ms/frame on a 200-point cluster.

    Args:
        travel_axis:                   Axis index for travel direction (0=X).
        max_correspondence_distance:   Max correspondence distance (m).
        min_fitness:                   Unused — kept for API compatibility.
                                       GICP acceptance uses ``converged`` flag.
        max_displacement:              Outlier gate (m).
        min_displacement:              Dead-zone (m).
        gicp_max_iter:                 Max GICP iterations (default 20).
    """

    def __init__(
        self,
        travel_axis: int = 0,
        max_correspondence_distance: float = 0.5,
        min_fitness: float = 0.3,
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
        gicp_max_iter: int = 20,
    ) -> None:
        self._travel_axis = travel_axis
        self._max_corr_dist = max_correspondence_distance
        self._min_fitness = min_fitness
        self._max_displacement = max_displacement
        self._min_displacement = min_displacement
        self._gicp_max_iter = gicp_max_iter

        self._prev_pts3d: Optional[np.ndarray] = None
        self._last_displacement: float = 0.0
        self._last_frame_ts: Optional[float] = None   # sensor timestamp of last frame

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_3d(points: np.ndarray) -> np.ndarray:
        """Return contiguous float64 (N, 3) array.

        For Nx2 input (X, Z) pads a zero Y column.
        For Nx3+ input passes through as-is (Y≈0 from sensor is fine).
        """
        if points.shape[1] == 2:
            pts = np.zeros((len(points), 3), dtype=np.float64)
            pts[:, 0] = points[:, 0]
            pts[:, 2] = points[:, 1]
            return pts
        return np.ascontiguousarray(points[:, :3], dtype=np.float64)

    # ── GICP (small_gicp) ─────────────────────────────────────────────────

    def _update_gicp(self, points: np.ndarray, timestamp: float) -> Optional[float]:
        """Align with small_gicp GICP; return travel-axis displacement or None."""
        pts3d = self._to_3d(points)

        if self._prev_pts3d is None or len(self._prev_pts3d) < 3:
            self._prev_pts3d = pts3d
            self._last_frame_ts = timestamp
            return 0.0

        # Numpy overload: align(target_points, source_points, ...)
        # source = prev frame, target = current frame → T_target_source
        # downsampling_resolution=0.0 collapses all points into one voxel and
        # causes voxel-coord overflow in C++; 0.001 (1 mm) keeps all points
        # for typical LiDAR clusters while avoiding the degenerate case.
        t0 = time.perf_counter()
        with _suppress_c_stderr():
            result = small_gicp.align(
                pts3d,                   # target (current frame)
                self._prev_pts3d,        # source (previous frame)
                registration_type="ICP",
                downsampling_resolution=0.001,
                max_correspondence_distance=self._max_corr_dist,
                max_iterations=self._gicp_max_iter,
                num_threads=1,
            )
        proc_ms = (time.perf_counter() - t0) * 1000.0

        # Frame-drop detection: warn if GICP took longer than the sensor interval
        if self._last_frame_ts is not None:
            frame_dt = timestamp - self._last_frame_ts
            if frame_dt > 0 and proc_ms > frame_dt * 1000.0:
                logger.warning(
                    "icp %.1f ms > frame interval %.1f ms — system may drop frames",
                    proc_ms, frame_dt * 1000.0,
                )
            else:
                logger.debug("icp %.2f ms (frame interval %.1f ms)", proc_ms, frame_dt * 1000.0)
        else:
            logger.debug("icp %.2f ms", proc_ms)

        self._prev_pts3d = pts3d
        self._last_frame_ts = timestamp

        if not result.converged:
            logger.info("icp did not converge — rejected")
            return None

        # T_target_source: 4×4 SE(3); translation at column 3
        raw = float(result.T_target_source[self._travel_axis, 3])
        return self._gate(raw, "icp")

    # ── Public API ────────────────────────────────────────────────────────

    def update(self, points: np.ndarray, timestamp: float) -> Optional[float]:
        """Return displacement (m, forward-positive), or None on failure."""
        return self._update_gicp(points, timestamp)

    def reset(self) -> None:
        self._prev_pts3d = None
        self._last_displacement = 0.0
        self._last_frame_ts = None

    @property
    def last_displacement(self) -> float:
        return self._last_displacement

    @property
    def initialized(self) -> bool:
        return self._prev_pts3d is not None

    # ── Gate helper ───────────────────────────────────────────────────────

    def _gate(self, raw: float, method: str) -> Optional[float]:
        """Apply dead-zone and outlier gate; return None if rejected."""
        if abs(raw) < self._min_displacement:
            raw = 0.0
        if abs(raw) > self._max_displacement + 1e-6:
            logger.info(
                "%s displacement %.4fm > max (%.4fm) — rejected",
                method, raw, self._max_displacement,
            )
            return None
        self._last_displacement = raw
        logger.info("%s displacement=%.4fm", method, raw)
        return raw


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
        max_correspondence_distance: Correspondence distance (m).
        min_fitness:                 Unused — kept for API compatibility.
                                     GICP acceptance uses convergence flag.
        max_displacement:            Max per-frame displacement (m).
        min_displacement:            Dead-zone (m).
        gicp_max_iter:               Max GICP iterations.
    """

    def __init__(
        self,
        travel_axis: int = 0,
        movement_direction: int = 1,
        reverse_tolerance: float = 0.05,
        min_vehicle_points: int = 10,
        dbscan_eps: float = 0.3,
        dbscan_min_samples: int = 5,
        trigger_distance: Optional[float] = None,
        max_correspondence_distance: float = 0.1,
        min_fitness: float = 0.3,
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
        gicp_max_iter: int = 20,
    ) -> None:
        self._travel_axis = travel_axis
        self._movement_direction = movement_direction  # +1 or -1
        self._reverse_tolerance = reverse_tolerance    # metres
        self._min_vehicle_points = min_vehicle_points
        self._dbscan_eps = dbscan_eps
        self._dbscan_min_samples = dbscan_min_samples
        self._trigger_distance = trigger_distance

        self._tracker = ClusterTracker(
            travel_axis=travel_axis,
            max_correspondence_distance=max_correspondence_distance,
            min_fitness=min_fitness,
            max_displacement=max_displacement,
            min_displacement=min_displacement,
            gicp_max_iter=gicp_max_iter,
        )

        # Position / velocity
        self._position: float = 0.0
        self._velocity: float = 0.0
        self._last_t: Optional[float] = None
        self._position_history: Deque[Tuple[float, float]] = deque(maxlen=512)

        # Tracking state
        self._vehicle_present: bool = False

    # ── Helpers ───────────────────────────────────────────────────────────

    def _crop_to_trigger_window(self, points: np.ndarray) -> np.ndarray:
        """Return only points inside the trigger window.

        Keeps points where the travel-axis coordinate is within
        ``[-trigger_distance, +trigger_distance]`` of the gantry at X=0.
        When trigger_distance is None the full scan is returned unchanged.
        """
        if self._trigger_distance is None:
            return points
        mask = (points[:, self._travel_axis] >= -self._trigger_distance) & (
            points[:, self._travel_axis] <= self._trigger_distance
        )
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
            # Guard: cluster must be approaching from the correct entry side.
            # For movement_direction=+1 (+X) the vehicle enters from X<0.
            # For movement_direction=-1 (−X) the vehicle enters from X>0.
            # In both cases: centroid * movement_direction <= 0 means correct side.
            centroid_axis = float(np.mean(spatial_pts[:, self._travel_axis]))
            if centroid_axis * self._movement_direction > 0:
                logger.debug(
                    "First-detection rejected — cluster centroid %.3f is on the wrong "
                    "side for movement_direction=%+d",
                    centroid_axis, self._movement_direction,
                )
                self._last_t = timestamp
                return self._result(timestamp, present=False)

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
            # Reverse-motion guard with inertia tolerance.
            # Small backward creep (|displacement| <= reverse_tolerance) is
            # accepted — this covers the inevitable inertia movement when the
            # truck pauses inside the gantry.  Larger reverse displacement
            # (deliberate backing-up or sensor artefact) is clamped to zero.
            if displacement * self._movement_direction < 0:
                if abs(displacement) <= self._reverse_tolerance:
                    logger.debug(
                        "Reverse displacement %.4fm within tolerance (%.4fm) — accepted",
                        displacement, self._reverse_tolerance,
                    )
                else:
                    logger.debug(
                        "Reverse displacement %.4fm exceeds tolerance (%.4fm) — ignored",
                        displacement, self._reverse_tolerance,
                    )
                    displacement = 0.0

            self._position += displacement
            self._velocity = (displacement / dt) if dt > 0 else 0.0
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
        """Return interpolated position at the given timestamp.

        Profile-sensor scan lines may arrive at timestamps that fall between
        two velocity-sensor frames.  This method linearly interpolates between
        the two bracketing history entries so that each scan line gets a unique,
        correctly-spaced X position rather than being snapped to the nearest
        velocity frame (which causes the "comb" artefact when the profile sensor
        runs faster than the velocity sensor).

        For timestamps ahead of the last history entry the position is
        extrapolated forward using the last known velocity.

        Args:
            timestamp:  The scan line's hardware timestamp (seconds).
            max_age:    Maximum gap (s) allowed between *timestamp* and the
                        nearest history boundary.  Returns None if exceeded.
        """
        if not self._position_history:
            return None

        # history is kept in insertion (= chronological) order
        last_t, last_pos = self._position_history[-1]
        first_t, first_pos = self._position_history[0]

        # ── Forward extrapolation (profile sensor ahead of velocity sensor) ──
        if timestamp >= last_t:
            dt = timestamp - last_t
            if dt > max_age:
                logger.warning(
                    "get_position_at %.4f: %.3f s ahead of last velocity sample "
                    "(max_age=%.2f s) — discarding scan line",
                    timestamp, dt, max_age,
                )
                return None
            return last_pos + self._velocity * dt

        # ── Before the first history entry ────────────────────────────────────
        if timestamp <= first_t:
            dt = first_t - timestamp
            if dt > max_age:
                logger.warning(
                    "get_position_at %.4f: %.3f s before first velocity sample "
                    "(max_age=%.2f s) — discarding scan line",
                    timestamp, dt, max_age,
                )
                return None
            return first_pos

        # ── Linear interpolation between bracketing entries ───────────────────
        # Scan from the end of the deque (most queries are for recent times).
        prev_t, prev_pos = last_t, last_pos
        for t, pos in reversed(self._position_history):
            if t <= timestamp:
                alpha = (timestamp - t) / (prev_t - t)
                return pos + alpha * (prev_pos - pos)
            prev_t, prev_pos = t, pos

        return first_pos  # fallback (should not reach)

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
