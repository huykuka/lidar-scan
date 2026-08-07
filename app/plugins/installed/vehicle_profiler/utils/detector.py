"""
Vehicle detection and position tracking from a vertical 2D LiDAR.

Pipeline (per frame)
--------------------
1. **Trigger crop** — keep only points within ``trigger_distance`` metres of
   the gantry.  Skipped when ``trigger_distance`` is None.
2. **DBSCAN clustering** — largest cluster with >= ``min_vehicle_points`` is
   selected; noise and small clusters are discarded.
3. **ICP registration** — ``small_gicp`` point-to-point ICP aligns the
   previous cluster to the current one.  Result is accepted when
   ``converged=True``.
4. **Position / velocity** — cumulative displacement and per-frame velocity.
   Dead-reckoning from last valid velocity on registration failure.
5. **Departure** — no valid cluster in the trigger window → vehicle absent.
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
# Cluster tracker — small_gicp ICP
# ──────────────────────────────────────────────────────────────────────────────


class ClusterTracker:
    """Per-frame displacement estimation via small_gicp point-to-point ICP.

    ~0.5 ms/frame on a 200-point cluster (single thread, 1 mm voxel grid).

    Args:
        travel_axis:                   Axis index for travel direction (0=X).
        max_correspondence_distance:   Max point-pair distance for ICP (m).
        max_displacement:              Outlier gate (m).
        min_displacement:              Dead-zone below which displacement is
                                       zeroed (m).
        icp_max_iter:                  Maximum ICP iterations per frame.
    """

    def __init__(
        self,
        travel_axis: int = 0,
        max_correspondence_distance: float = 0.5,
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
        icp_max_iter: int = 20,
    ) -> None:
        self._travel_axis = travel_axis
        self._max_corr_dist = max_correspondence_distance
        self._max_displacement = max_displacement
        self._min_displacement = min_displacement
        self._icp_max_iter = icp_max_iter

        self._prev_pts3d: Optional[np.ndarray] = None
        self._last_displacement: float = 0.0
        self._last_velocity: float = 0.0   # m/s — used to predict next displacement
        self._last_frame_ts: Optional[float] = None

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_3d(points: np.ndarray) -> np.ndarray:
        """Return contiguous float64 (N, 3) array.

        Nx2 input (X, Z) → pad a zero Y column.
        Nx3+ input → pass through (Y≈0 from sensor is fine).
        """
        if points.shape[1] == 2:
            pts = np.zeros((len(points), 3), dtype=np.float64)
            pts[:, 0] = points[:, 0]
            pts[:, 2] = points[:, 1]
            return pts
        return np.ascontiguousarray(points[:, :3], dtype=np.float64)

    # ── ICP (small_gicp) ──────────────────────────────────────────────────

    def _update_icp(self, points: np.ndarray, timestamp: float) -> Optional[float]:
        """Align with small_gicp ICP; return travel-axis displacement or None."""
        pts3d = self._to_3d(points)

        if self._prev_pts3d is None or len(self._prev_pts3d) < 3:
            self._prev_pts3d = pts3d
            self._last_frame_ts = timestamp
            return 0.0

        dt = timestamp - self._last_frame_ts if self._last_frame_ts is not None else 0.0

        # ── Motion-predicted initial guess ───────────────────────────────────
        # Seed ICP with the displacement we expect from the last known velocity.
        # Without this, ICP starts from identity every frame; a sudden speed
        # change can push the actual displacement past max_correspondence_distance
        # so ICP finds zero correspondences and diverges.
        predicted_dx = self._last_velocity * dt
        init_T = np.eye(4)
        init_T[self._travel_axis, 3] = predicted_dx

        # ── Adaptive correspondence distance ─────────────────────────────────
        # At the predicted displacement the clouds are already aligned by init_T,
        # so residual error should be small — keep a tight window.  But add a
        # safety margin of 50% of the predicted step so small velocity
        # estimation errors don't cause misses.
        corr_dist = max(self._max_corr_dist, abs(predicted_dx) * 0.5 + self._max_corr_dist)

        t0 = time.perf_counter()
        result = small_gicp.align(
                pts3d,                   # target (current frame)
                self._prev_pts3d,        # source (previous frame)
                init_T,                  # init_T_target_source (positional)
                registration_type="ICP",
                downsampling_resolution=0.001,
                max_correspondence_distance=corr_dist,
                max_iterations=self._icp_max_iter,
        )
        proc_ms = (time.perf_counter() - t0) * 1000.0

        if dt > 0 and proc_ms > dt * 1000.0:
            logger.warning("icp %.1f ms > frame interval %.1f ms — may drop frames", proc_ms, dt * 1000.0)
        else:
            logger.debug("icp %.2f ms (pred=%.4fm corr_dist=%.3fm)", proc_ms, predicted_dx, corr_dist)

        self._prev_pts3d = pts3d
        self._last_frame_ts = timestamp

        if not result.converged:
            logger.debug("icp did not converge — rejected (error=%.4f, pred=%.4fm)", result.error, predicted_dx)
            return None

        raw = float(result.T_target_source[self._travel_axis, 3])
        return self._gate(raw, dt)

    # ── Public API ────────────────────────────────────────────────────────

    def update(self, points: np.ndarray, timestamp: float) -> Optional[float]:
        """Return displacement (m, forward-positive), or None on failure."""
        return self._update_icp(points, timestamp)

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

    def _gate(self, raw: float, dt: float) -> Optional[float]:
        """Apply dead-zone and outlier gate; update velocity on success."""
        if abs(raw) < self._min_displacement:
            raw = 0.0
        if abs(raw) > self._max_displacement + 1e-6:
            logger.debug("icp displacement %.4fm > max %.4fm — rejected", raw, self._max_displacement)
            return None
        self._last_displacement = raw
        self._last_velocity = (raw / dt) if dt > 0 else self._last_velocity
        return raw


# ──────────────────────────────────────────────────────────────────────────────
# Vehicle detector (DBSCAN-based, no background model)
# ──────────────────────────────────────────────────────────────────────────────


class VehicleDetector:
    """Detect vehicles via DBSCAN clustering on a trigger-cropped 2D scan.

    Args:
        travel_axis:                 Axis index for the truck travel direction
                                     (0=X, 1=Y).
        movement_direction:          Expected travel direction (+1 or -1).
        reverse_tolerance:           Backward creep allowed before clamping (m).
        min_vehicle_points:          Min points in a DBSCAN cluster to count
                                     as a vehicle.
        dbscan_eps:                  DBSCAN neighbourhood radius (m).
        dbscan_min_samples:          DBSCAN min samples per core point.
        trigger_distance:            Crop window half-width (m).  None = full scan.
        max_correspondence_distance: ICP point-pair distance limit (m).
        max_displacement:            Max per-frame displacement outlier gate (m).
        min_displacement:            Dead-zone below which displacement is zeroed (m).
        icp_max_iter:                Maximum ICP iterations per frame.
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
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
        icp_max_iter: int = 20,
    ) -> None:
        self._travel_axis = travel_axis
        self._movement_direction = movement_direction
        self._reverse_tolerance = reverse_tolerance
        self._min_vehicle_points = min_vehicle_points
        self._dbscan_eps = dbscan_eps
        self._dbscan_min_samples = dbscan_min_samples
        self._trigger_distance = trigger_distance

        self._tracker = ClusterTracker(
            travel_axis=travel_axis,
            max_correspondence_distance=max_correspondence_distance,
            max_displacement=max_displacement,
            min_displacement=min_displacement,
            icp_max_iter=icp_max_iter,
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

        # 1. Crop to trigger window (presence detection only)
        cropped = self._crop_to_trigger_window(points)

        # 2. Cluster on full scan — trigger crop only gates presence,
        #    ICP needs the widest possible geometric context.
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
                    "First-detection rejected — centroid %.3f on wrong side for direction=%+d",
                    centroid_axis, self._movement_direction,
                )
                self._last_t = timestamp
                return self._result(timestamp, present=False)

            self._tracker.update(points, timestamp)
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

        displacement = self._tracker.update(points, timestamp)

        if displacement is not None:
            # Reverse-motion guard with inertia tolerance.
            # Small backward creep (|displacement| <= reverse_tolerance) is
            # accepted — this covers the inevitable inertia movement when the
            # truck pauses inside the gantry.  Larger reverse displacement
            # (deliberate backing-up or sensor artefact) is clamped to zero.
            if displacement * self._movement_direction < 0:
                if abs(displacement) <= self._reverse_tolerance:
                    logger.debug("reverse %.4fm within tolerance — accepted", displacement)
                else:
                    logger.debug("reverse %.4fm exceeds tolerance — clamped to zero", displacement)
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
