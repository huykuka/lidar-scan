"""
Vehicle detection and displacement-based profiling from a vertical 2D LiDAR.

Physical setup:
    The vertical LiDAR scans a plane along the travel direction, covering the
    full gantry width so both the leading and trailing edges of the truck are
    visible throughout the entire pass.

    A single cluster (the truck cross-section) is extracted each frame by
    background subtraction.  To measure how far the cluster moved between
    frames, the two consecutive cluster point clouds are aligned with an
    Open3D Point-to-Point ICP registration.  The travel-axis component of
    the resulting rigid-body translation is the per-frame displacement.

    Position is accumulated directly from ICP displacements — no velocity
    computation or temporal integration needed.  This avoids noise
    amplification from dividing by dt and subsequent re-integration.

Algorithm:
    1. Background learning  — per-beam median from empty scene.
    2. Vehicle detection    — background subtraction; cluster = foreground points.
    3. ICP registration     — align previous cluster to current cluster cloud.
    4. Displacement extract — travel-axis translation from ICP transform.
    5. Position accumulate  — position += displacement (no velocity/dt).
    6. Stop                 — cluster absent for > gap_debounce_s → finalize.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.signal import correlate

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Output of a single detector update."""
    position: float           # integrated travel distance (metres)
    centroid_position: float  # cluster centroid on travel axis (metres), 0 if unavailable
    velocity: float           # current velocity estimate (m/s)
    timestamp: float
    vehicle_present: bool
    icp_valid: bool = True    # False when ICP failed — caller should skip this frame


class ClusterTracker:
    """Estimate per-frame displacement via 1-D cross-correlation of height profile.

    The vertical LiDAR produces a 2-D scan in the XZ plane (X = travel, Z = height).
    Between consecutive frames the entire profile shifts by δx along the travel axis.

    Cross-correlation directly finds the lag δx that best aligns the two 1-D
    height signals.  It is immune to the rotation-translation degeneracy that
    breaks ICP on small per-frame displacements (δx ≈ mm at 50 Hz), regardless
    of whether the surface is flat (bin) or curved (cabin).

    Algorithm per frame:
        1. Bin cluster points onto a regular X grid (bin_size).
        2. For each bin take the maximum height (robust to outliers, captures top surface).
        3. Cross-correlate the current and previous height arrays.
        4. argmax of cross-correlation in [-max_lag_bins, +max_lag_bins] → shift.
        5. displacement = shift × bin_size.

    Args:
        travel_axis:     Axis index for travel direction (0 = X).
        height_axis:     Axis index for height / range (1 = Y for a XY 2-D scan).
        bin_size:        Grid resolution in metres (default 5 mm).
        max_displacement: Outlier gate — reject if shift exceeds this (m).
        min_displacement: Dead-zone — return 0 if below this (m).
        grid_min / grid_max: Fixed scan extent in metres along travel axis.
                             If None, inferred from first frame.
    """

    def __init__(
        self,
        travel_axis: int = 0,
        height_axis: int = 1,
        bin_size: float = 0.005,
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
        grid_min: Optional[float] = None,
        grid_max: Optional[float] = None,
        # kept for API compatibility
        max_correspondence_distance: float = 0.5,
        min_icp_fitness: float = 0.3,
        voxel_size: float = 0.0,
        dead_reckon_frames: int = 0,
    ) -> None:
        self._travel_axis = travel_axis
        self._height_axis = height_axis
        self._bin_size = bin_size
        self._max_displacement = max_displacement
        self._min_displacement = min_displacement
        self._grid_min = grid_min
        self._grid_max = grid_max

        self._prev_profile: Optional[np.ndarray] = None
        self._last_displacement: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_profile(self, points: np.ndarray) -> np.ndarray:
        """Project cluster points onto a 1-D height array indexed by travel position."""
        x = points[:, self._travel_axis]
        z = points[:, self._height_axis]

        g_min = self._grid_min if self._grid_min is not None else float(x.min())
        g_max = self._grid_max if self._grid_max is not None else float(x.max())

        n_bins = max(int(np.ceil((g_max - g_min) / self._bin_size)), 1)
        profile = np.full(n_bins, np.nan)

        indices = np.clip(
            ((x - g_min) / self._bin_size).astype(int), 0, n_bins - 1
        )
        for i, h in zip(indices, z):
            # Minimum range per bin = closest point = highest truck surface.
            # For a top-down sensor, smaller range means taller feature.
            if np.isnan(profile[i]) or h < profile[i]:
                profile[i] = h

        # Fill NaN bins with linear interpolation so correlation is well-defined
        nans = np.isnan(profile)
        if nans.all():
            return profile
        xs = np.arange(n_bins)
        profile[nans] = np.interp(xs[nans], xs[~nans], profile[~nans])
        return profile

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, points: np.ndarray, timestamp: float) -> Optional[float]:
        """Cross-correlate current height profile with previous; return displacement.

        Returns:
            Displacement in metres (forward positive), or None if rejected.
        """
        profile = self._to_profile(points)

        if self._prev_profile is None or len(profile) != len(self._prev_profile):
            self._prev_profile = profile
            return 0.0

        # correlate(current, prev) peaks at +lag when current is shifted
        # forward by lag bins relative to prev (forward truck motion).
        # Mean-subtract each profile so the flat background (DC component)
        # does not dominate the correlation and wash out the truck-feature peak.
        p_curr = profile - profile.mean()
        p_prev = self._prev_profile - self._prev_profile.mean()
        max_lag_bins = max(1, int(self._max_displacement / self._bin_size))
        corr = correlate(p_curr, p_prev, mode="full")
        center = len(corr) // 2
        lo = max(0, center - max_lag_bins)
        hi = min(len(corr), center + max_lag_bins + 1)
        shift_bins = int(np.argmax(corr[lo:hi])) - (center - lo)
        displacement = float(shift_bins * self._bin_size)

        self._prev_profile = profile

        # Forward-only
        displacement = max(0.0, displacement)

        # Outlier gate
        if displacement > self._max_displacement:
            logger.info(f"xcorr displacement {displacement:.4f}m > max — rejected")
            return None

        # Dead-zone
        if displacement < self._min_displacement:
            displacement = 0.0

        self._last_displacement = displacement
        logger.info(
            f"xcorr shift={shift_bins} bins  displacement={displacement:.4f}m"
        )
        return displacement

    def reset(self) -> None:
        self._prev_profile = None
        self._last_displacement = 0.0

    @property
    def last_displacement(self) -> float:
        return self._last_displacement

    @property
    def initialized(self) -> bool:
        return self._prev_profile is not None


class VehicleDetector:
    """Detects vehicles and tracks travel distance from a vertical 2D LiDAR.

    Position is accumulated directly from ICP displacements — no velocity needed.

    Args:
        bg_threshold:                Delta (m) above background → vehicle point.
        bg_learning_frames:          Frames for background learning.
        travel_axis:                 Axis for vehicle travel (0=X, 1=Y, 2=Z).
        gap_debounce_s:              Seconds of absent cluster before departure.
        min_vehicle_points:          Min foreground points to accept a frame.
        bin_size:                    Cross-correlation grid resolution (m).
        max_displacement:            Max per-frame displacement (m). Rejects outliers.
        min_displacement:            Dead-zone (m). Below this → static.
        grid_min / grid_max:         Fixed scan extent along travel axis (m). None = infer.
    """

    def __init__(
        self,
        bg_threshold: float = 0.3,
        bg_learning_frames: int = 20,
        travel_axis: int = 0,
        gap_debounce_s: float = 3.0,
        min_vehicle_points: int = 5,
        bin_size: float = 0.005,
        max_displacement: float = 0.5,
        min_displacement: float = 0.001,
        grid_min: Optional[float] = None,
        grid_max: Optional[float] = None,
        # kept for API compatibility
        max_correspondence_distance: float = 0.5,
        min_icp_fitness: float = 0.3,
        voxel_size: float = 0.0,
    ) -> None:
        self._bg_threshold = bg_threshold
        self._bg_learning_frames = bg_learning_frames
        self._travel_axis = travel_axis
        self._gap_debounce_s = gap_debounce_s
        self._min_vehicle_points = min_vehicle_points

        self._tracker = ClusterTracker(
            travel_axis=travel_axis,
            bin_size=bin_size,
            max_displacement=max_displacement,
            min_displacement=min_displacement,
            grid_min=grid_min,
            grid_max=grid_max,
        )

        # Background model
        self._bg_accumulator: list[np.ndarray] = []
        self._bg_distances: Optional[np.ndarray] = None

        # Tracking state
        self._last_t: Optional[float] = None
        self._vehicle_present: bool = False
        self._absence_since: Optional[float] = None
        self._travel_distance: float = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _result(
        self,
        timestamp: float,
        centroid_pos: float = 0.0,
        present: bool = True,
        icp_valid: bool = True,
    ) -> DetectionResult:
        return DetectionResult(
            position=self._travel_distance,
            centroid_position=centroid_pos,
            velocity=0.0,  # no longer computed
            timestamp=timestamp,
            vehicle_present=present,
            icp_valid=icp_valid,
        )

    def _stop(self, timestamp: float) -> DetectionResult:
        self._vehicle_present = False
        self._absence_since = None
        self._last_t = timestamp
        return self._result(timestamp, present=False)

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    def update(self, points: np.ndarray, timestamp: float) -> Optional[DetectionResult]:
        """Process one scan frame.  Returns None during background learning."""
        if points is None or len(points) < 2:
            return None

        distances = np.linalg.norm(points[:, :2], axis=1)

        # --- Background learning ---
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

        # --- Vehicle detection ---
        n = min(len(distances), len(self._bg_distances))
        delta = self._bg_distances[:n] - distances[:n]
        vehicle_mask = delta > self._bg_threshold
        n_vehicle = int(vehicle_mask.sum())

        # --- No cluster (or below min points threshold) ---
        if n_vehicle < self._min_vehicle_points:
            if self._vehicle_present:
                if self._absence_since is None:
                    self._absence_since = timestamp
                if (timestamp - self._absence_since) < self._gap_debounce_s:
                    # During gap debounce, position stays frozen (no displacement)
                    return self._result(timestamp, present=True)
                return self._stop(timestamp)
            self._last_t = timestamp
            return self._result(timestamp, present=False)

        # --- Cluster present — clear gap debounce ---
        self._absence_since = None
        vehicle_pts = points[:n][vehicle_mask]
        spatial_pts = vehicle_pts[:, :3] if vehicle_pts.shape[1] >= 3 else vehicle_pts[:, :2]

        centroid_pos = float(spatial_pts[:, self._travel_axis].mean())

        self._last_t = timestamp

        # --- First detection: seed tracker ---
        if not self._vehicle_present:
            self._tracker.update(spatial_pts, timestamp)
            self._vehicle_present = True
            return self._result(timestamp, centroid_pos=centroid_pos, present=True)

        # --- Normal tracking: ICP → displacement → accumulate position ---
        displacement = self._tracker.update(spatial_pts, timestamp)

        if displacement is not None:
            self._travel_distance += displacement
            return self._result(timestamp, centroid_pos=centroid_pos, present=True)
        else:
            # ICP failed — position frozen this frame
            return self._result(timestamp, centroid_pos=centroid_pos, present=True, icp_valid=False)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_tracking(self) -> None:
        """Reset tracking state, preserve background model."""
        self._tracker.reset()
        self._last_t = None
        self._vehicle_present = False
        self._absence_since = None
        self._travel_distance = 0.0

    def reset(self) -> None:
        """Full reset including background model."""
        self.reset_tracking()
        self._bg_accumulator.clear()
        self._bg_distances = None

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def vehicle_present(self) -> bool:
        return self._vehicle_present

    @property
    def current_position(self) -> float:
        """Integrated travel distance (metres) — profile coordinate."""
        return self._travel_distance

    @property
    def current_velocity(self) -> float:
        """Deprecated — returns 0. Use position directly."""
        return 0.0
