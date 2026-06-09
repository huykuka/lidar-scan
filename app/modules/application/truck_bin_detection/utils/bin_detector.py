"""
Robust 1D Longitudinal Profile Bin Detector for 2 Fused 16-Layer LiDARs.
Optimized for Hopper Discharge Station.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BinDetectionResult:
    """Result of a real-time truck bin alignment analysis."""

    detected: bool
    x_rear_internal: float = 0.0
    x_front_internal: float = 0.0
    x_center: float = 0.0
    length: float = 0.0
    confidence: float = 0.0
    status: str = "SEARCH"
    bin_points: Optional[np.ndarray] = None  # rear + front edge point clouds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "x_rear_internal": round(self.x_rear_internal, 3),
            "x_front_internal": round(self.x_front_internal, 3),
            "x_center": round(self.x_center, 3),
            "length": round(self.length, 3),
            "confidence": round(self.confidence, 2),
            "status": self.status,
        }


class BinDetector:
    """Detects and registers the exact longitudinal center of an open-top cargo bin

    by projecting sparse 3D scans onto a 1D travel axis elevation profile, tracking
    the rear and front internal boundary slopes of the cavity.
    """

    def __init__(
        self,
        lane_width: float = 1.4,
        z_min: float = 2.0,
        z_max: float = 3.8,
        cell_size: float = 0.07,
        z_wall_threshold: float = 2.2,
        z_cavity_max: float = 1.8,
        z_cavity_min: float = 0.5,
        min_bin_area: float = 2.0,
        enable_area_check: bool = True,
        min_wall_points: int = 3,
        max_wall_x_std: float = 0.15,
        min_bin_length: float = 3.0,
        max_bin_length: float = 8.5,
    ) -> None:
        self._lane_width = lane_width
        self._z_min = z_min
        self._z_max = z_max
        self._cellsize = cell_size
        self._z_wall_threshold = z_wall_threshold
        self._z_cavity_max = z_cavity_max
        self._z_cavity_min = z_cavity_min
        self._min_bin_area = min_bin_area
        self._enable_area_check = enable_area_check
        self._min_wall_points = min_wall_points
        self._max_wall_x_std = max_wall_x_std
        self._min_bin_length = min_bin_length
        self._max_bin_length = max_bin_length

    def detect(self, points: np.ndarray) -> BinDetectionResult:
        """Run 1D slope-based internal edge detection on a fused point cloud.

        Args:
            points: Nx3 or Nx4 numpy array of XYZ coordinates.

        Returns:
            BinDetectionResult with center position and alignment error.
        """
        if points is None or len(points) < 20:
            return BinDetectionResult(detected=False, status="SEARCH / NO VEHICLE")

        # Convert to Nx3 float64
        pts = np.asarray(points[:, :3], dtype=np.float64)

        # Step 1: Spatial ROI Crop (Corridor + Height envelope)
        # Keeps only lane center Y-width and heights corresponding to box rims
        # Range of X traveled
        x_min = float(np.min(pts[:, 0]))
        x_max = float(np.max(pts[:, 0]))

        # Skip if scan range is too short to represent a truck
        if x_max - x_min < 2.0:
            return BinDetectionResult(
                detected=False, status="SEARCH / INSUFFICIENT SCAN RANGE"
            )

        # Step 2: 1D longitudinal projection into discrete spatial cells
        num_bins = int(np.ceil((x_max - x_min) / self._cellsize))
        if num_bins < 10:
            return BinDetectionResult(
                detected=False, status="SEARCH / INSUFFICIENT CELL COUNT"
            )

        bin_points_collect = [[] for _ in range(num_bins)]
        for p in pts:
            bin_idx = int((p[0] - x_min) / self._cellsize)
            bin_idx = min(max(bin_idx, 0), num_bins - 1)
            bin_points_collect[bin_idx].append(p[2])

        # Step 3: Extract 90th percentile height per bin (Prevent rain/dust spikes)
        height_profile = np.zeros(num_bins)
        for i in range(num_bins):
            if len(bin_points_collect[i]) > 0:
                height_profile[i] = np.percentile(bin_points_collect[i], 90)
            else:
                height_profile[i] = 0.0

        # Step 4a: Interpolate empty cells (forward + backward fill) before smoothing.
        # An empty cell is one where no LiDAR point landed (value == 0.0).
        # This prevents the median filter from being pulled down by structural zeros
        # in sparse valley regions where the open cavity floor returns few/no hits.
        filled_profile = height_profile.copy()
        # Forward fill: propagate the last non-zero value rightward
        last_valid = 0.0
        for i in range(num_bins):
            if filled_profile[i] > 0.0:
                last_valid = filled_profile[i]
            elif last_valid > 0.0:
                filled_profile[i] = last_valid
        # Backward fill: propagate the first non-zero value leftward for any leading zeros
        last_valid = 0.0
        for i in range(num_bins - 1, -1, -1):
            if filled_profile[i] > 0.0:
                last_valid = filled_profile[i]
            elif last_valid > 0.0:
                filled_profile[i] = last_valid

        # Step 4b: Apply 5-cell median filter to bridge 16-beam vertical scan gaps
        smoothed_profile = np.copy(filled_profile)
        # for i in range(2, num_bins - 2):
        #     smoothed_profile[i] = np.median(filled_profile[i - 2 : i + 3])

        # Step 5: Detect Dual Internal Edges using a two-phase approach.
        #
        # The gradient is computed on the smoothed (and interpolated) profile.
        # np.gradient uses central differences, so each value is inherently averaged
        # with its two immediate neighbours — resilient to single-cell noise.
        #
        # Minimum gradient magnitude that qualifies as a real structural edge:
        # half the total wall-to-cavity height difference per cell width.
        _min_edge_drop = (self._z_wall_threshold - self._z_cavity_max) / 2.0 / 1000

        profile_gradient = np.gradient(smoothed_profile)

        x_rear_internal = None
        x_front_internal = None
        rear_bin_idx = None
        front_bin_idx = None

        # 5a. Locate the EXTERNAL rear wall peak.
        # Physical meaning: the outer face of the rear wall is the highest Z region
        # encountered first when scanning from the back of the truck.  We look for
        # the first local maximum whose height is at or above z_wall_threshold —
        # i.e. gradient crosses zero from positive to negative (peak) at a point
        # that is above the wall threshold.
        rear_peak_idx = None
        for i in range(1, num_bins - 1):
            if (
                smoothed_profile[i] >= self._z_wall_threshold
                and profile_gradient[i - 1] > 0
                and profile_gradient[i] <= 0
            ):
                rear_peak_idx = i
                break

        if rear_peak_idx is None:
            logger.debug("Failed to detect rear external wall peak")
            return BinDetectionResult(
                detected=False, status="SEARCH / REAR PEAK NOT FOUND"
            )

        # 5b. From the peak, walk forward to find the INTERNAL rear edge.
        # Physical meaning: the inner face of the rear wall is where the profile
        # drops steeply from the peak height down into the open cavity.
        # We look for the first cell after the peak where the gradient is a
        # significant negative value (steeper than _min_edge_drop).
        for i in range(rear_peak_idx + 1, num_bins - 1):
            if profile_gradient[i] < -0.10:
                rear_bin_idx = i
                x_rear_internal = x_min + i * self._cellsize
                break

        if x_rear_internal is None or rear_bin_idx is None:
            logger.debug("Failed to detect rear internal edge (drop into cavity)")
            return BinDetectionResult(
                detected=False, status="SEARCH / REAR EDGE NOT FOUND"
            )

        # 5c. Front edge: first significant positive gradient after the deadband
        start_front_search = rear_bin_idx + int(
            0.5 / self._cellsize
        )  # Skip at least 0.5m after rear edge
        for i in range(start_front_search, num_bins - 1):
            if (
                profile_gradient[i] > 0.4
                and smoothed_profile[i] >= self._z_wall_threshold
            ):
                front_bin_idx = i
                x_front_internal = x_min + i * self._cellsize
                break

        if x_front_internal is None or front_bin_idx is None:
            logger.debug("Failed to detect front internal edge (climb out of cavity)")
            return BinDetectionResult(
                detected=False, status="SEARCH / FRONT EDGE NOT FOUND"
            )

        # Step 6: Valley & Shape Robustness checks (Big-Plane Confirmation)
        length = x_front_internal - x_rear_internal
        if not (self._min_bin_length <= length <= self._max_bin_length):
            logger.debug(
                "Rejected: length %.2f is outside [%.2f, %.2f]",
                length,
                self._min_bin_length,
                self._max_bin_length,
            )
            return BinDetectionResult(
                detected=False, status=f"SEARCH / INVALID LENGTH ({length:.1f}m)"
            )

        # Step 6b: 3D cavity area confirmation (skipped if enable_area_check is False).
        # Collect the raw points that sit strictly inside the cavity — beyond the wall
        # slabs on both sides. Using _edge_half as the inset ensures wall-face points
        # do not inflate the Y-span of the interior cloud.
        # A real open-top bin has points spread across the full lane width and cavity
        # length — its XY bounding box area is large.
        # False positives are rejected because:
        #   - Inter-truck gap: near-zero points inside → area ~ 0
        #   - Drawbar / coupling: points clustered in a narrow band → small Y-span → small area
        _edge_half = self._cellsize * 1.5
        interior_mask = (pts[:, 0] > x_rear_internal + _edge_half) & (
            pts[:, 0] < x_front_internal - _edge_half
        )
        interior_pts = pts[interior_mask]

        if self._enable_area_check:
            if len(interior_pts) < 3:
                logger.debug("Rejected: fewer than 3 points inside cavity")
                return BinDetectionResult(
                    detected=False, status="SEARCH / NO INTERIOR POINTS"
                )

            x_span = float(interior_pts[:, 0].max() - interior_pts[:, 0].min())
            y_span = float(interior_pts[:, 1].max() - interior_pts[:, 1].min())
            interior_area = x_span * y_span

            if interior_area < self._min_bin_area:
                logger.debug(
                    "Rejected: interior XY area %.2f m² < min %.2f m² "
                    "(x_span=%.2f, y_span=%.2f)",
                    interior_area,
                    self._min_bin_area,
                    x_span,
                    y_span,
                )
                return BinDetectionResult(
                    detected=False,
                    status=f"SEARCH / SMALL INTERIOR AREA ({interior_area:.1f} m²)",
                )

            # Confidence: ratio of observed area to expected bin opening (length × lane_width).
            # Capped at 1.0 — a perfectly captured bin reads close to 1.0.
            expected_area = length * self._lane_width
            confidence = round(min(interior_area / expected_area, 1.0), 2)
        else:
            # Area check is disabled — fall back to wall line coherence check.
            # Each detected wall slab should form a tight vertical line in the XZ
            # plane: real wall faces have all their points at nearly the same X
            # (low X standard deviation). Scattered noise or a drawbar coupling
            # hit at an angle produces high X spread.
            # Segmented / partially hidden walls still pass — we only need the
            # points that are present to be vertically aligned, regardless of
            # how many Z levels they span.
            _edge_half = self._cellsize * 1.5
            rear_slab = pts[
                (pts[:, 0] >= x_rear_internal - _edge_half)
                & (pts[:, 0] <= x_rear_internal + _edge_half)
            ]
            front_slab = pts[
                (pts[:, 0] >= x_front_internal - _edge_half)
                & (pts[:, 0] <= x_front_internal + _edge_half)
            ]

            for slab, label in ((rear_slab, "rear"), (front_slab, "front")):
                if len(slab) < self._min_wall_points:
                    logger.debug(
                        "Rejected: %s wall has only %d points (min %d)",
                        label,
                        len(slab),
                        self._min_wall_points,
                    )
                    return BinDetectionResult(
                        detected=False,
                        status=f"SEARCH / WEAK {label.upper()} WALL ({len(slab)} pts)",
                    )
                x_std = float(np.std(slab[:, 0]))
                if x_std > self._max_wall_x_std:
                    logger.debug(
                        "Rejected: %s wall X std=%.3f > max %.3f "
                        "(not a coherent vertical line)",
                        label,
                        x_std,
                        self._max_wall_x_std,
                    )
                    return BinDetectionResult(
                        detected=False,
                        status=f"SEARCH / SCATTERED {label.upper()} WALL (std={x_std:.2f}m)",
                    )

            confidence = 1.0

        # Step 7: Compute bin geometry — positioning and status are handled externally
        x_center = (x_rear_internal + x_front_internal) / 2.0

        # Edge point clouds: retain only the points that form each detected wall face.
        # A 3-cell window (1.5× cell_size on each side) captures the wall slab without
        # pulling in interior cavity or exterior truck-floor returns.
        rear_mask = (pts[:, 0] >= x_rear_internal) & (pts[:, 0] <= x_rear_internal)
        front_mask = (pts[:, 0] >= x_front_internal) & (pts[:, 0] <= x_front_internal)
        edge_pts = np.concatenate([pts[rear_mask], pts[front_mask]], axis=0)

        return BinDetectionResult(
            detected=True,
            x_rear_internal=x_rear_internal,
            x_front_internal=x_front_internal,
            x_center=x_center,
            length=length,
            confidence=confidence,
            status="DETECTED",
            bin_points=edge_pts if len(edge_pts) > 0 else pts,
        )
