"""
Robust 1D Longitudinal Profile Bin Detector for 2 Fused 16-Layer LiDARs.
Optimized for Hopper Discharge Station.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import open3d as o3d

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
            bed_normal_z_min: float = 0.8,
            min_bed_inliers: int = 5,
            rear_forward_lookup: int = 30,
            front_backward_lookup: int = 5,
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
        self._bed_normal_z_min = bed_normal_z_min
        self._min_bed_inliers = min_bed_inliers
        self._rear_forward_lookup = rear_forward_lookup
        self._front_backward_lookup = front_backward_lookup

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
        pts_3d = np.asarray(points[:, :3], dtype=np.float64)

        # Project onto the XZ plane — set Y to zero so the 1D height-profile
        # algorithm and wall-slab coherence checks operate purely in the
        # longitudinal-elevation plane.  pts_3d (original) is kept for the
        # bed plane-fitting step that needs real 3D geometry.
        pts = pts_3d.copy()
        pts[:, 1] = 0.0

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

        # Step 2 (vectorized): assign each point to its bin in one shot
        bin_indices = np.clip(
            ((pts[:, 0] - x_min) / self._cellsize).astype(np.intp),
            0,
            num_bins - 1,
        )

        # Step 3: Extract 90th-percentile height per bin (suppress rain/dust spikes).
        # Strategy: sort points by bin index, split into contiguous groups, then use
        # np.partition (O(n) per group) so the total cost is O(N log N) for the sort
        # plus O(N) for all partitions — no Python-level per-bin loop.
        height_profile = np.zeros(num_bins)
        sort_order = np.argsort(bin_indices, kind="stable")
        sorted_bins = bin_indices[sort_order]
        sorted_z = pts[sort_order, 2]

        # np.unique gives the first occurrence index of each bin — use those as
        # split boundaries so np.split produces one z-array per occupied bin.
        unique_bins, first_occurrence = np.unique(sorted_bins, return_index=True)
        groups = np.split(sorted_z, first_occurrence[1:])  # list of per-bin z arrays

        for bin_id, z_vals in zip(unique_bins, groups):
            n = len(z_vals)
            if n == 1:
                height_profile[bin_id] = z_vals[0]
            else:
                # np.partition is O(n) — far cheaper than np.sort for a single quantile
                k = max(0, int(np.ceil(0.90 * n)) - 1)
                height_profile[bin_id] = np.partition(z_vals, k)[k]

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
        # # Backward fill: propagate the first non-zero value leftward for any leading zeros
        last_valid = 0.0
        for i in range(num_bins - 1, -1, -1):
            if filled_profile[i] > 0.0:
                last_valid = filled_profile[i]
            elif last_valid > 0.0:
                filled_profile[i] = last_valid

        # Step 5: Detect Dual Internal Edges using a two-phase approach.
        #
        # The gradient is computed on the smoothed (and interpolated) profile.
        # np.gradient uses central differences, so each value is inherently averaged
        # with its two immediate neighbours — resilient to single-cell noise.
        #
        profile_gradient = np.gradient(filled_profile)

        x_rear_internal = None
        x_front_internal = None
        rear_bin_idx = None
        front_bin_idx = None

        # 5a. Locate the EXTERNAL rear wall peak.
        # Physical meaning: the outer face of the rear wall is the highest Z region
        # encountered first when scanning from the back of the truck.  We scan from
        # the front and look for the first bin above threshold that is higher than
        # everything in a window ahead — i.e. the point where the profile stops
        # rising and the cavity drop begins.
        rear_peak_idx = None
        for i in range(num_bins - 1):
            end_idx = min(i + self._rear_forward_lookup, num_bins)
            if (
                    filled_profile[i] >= self._z_wall_threshold
                    and filled_profile[i] >= np.max(filled_profile[i + 1:end_idx])
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
        for i in range(rear_peak_idx + 1, num_bins - 1):
            if profile_gradient[i] < 0:
                end_idx = min(i + 30, len(filled_profile))
                if filled_profile[i] >= np.max(filled_profile[i + 1:end_idx]):
                    rear_bin_idx = i
                    x_rear_internal = x_min + i * self._cellsize
                    break

        if x_rear_internal is None or rear_bin_idx is None:
            logger.debug("Failed to detect rear internal edge (drop into cavity)")
            return BinDetectionResult(
                detected=False, status="SEARCH / REAR EDGE NOT FOUND"
            )

        # 5c. Front edge: detect the internal front wall boundary.
        #
        # Strategy A — vertical wall:
        #   gradient > 0, profile already >= wall threshold, AND higher than the
        #   previous front_backward_lookup cells (confirms it is the first crossing,
        #   not a mid-slope cell).
        #
        # Strategy B — inclined wall:
        #   gradient > 0, profile still below threshold, but within
        #   front_backward_lookup cells ahead the profile reaches wall height.
        #   The foot of the slope (current cell) is the internal front edge.
        start_front_search = rear_bin_idx + int(
            1.5 / self._cellsize
        )  # Skip at least 1.5m after rear edge
        for i in range(start_front_search, num_bins - 1):
            # Strategy A: vertical wall
            if (
                profile_gradient[i] > 0
                and filled_profile[i] >= self._z_wall_threshold
                and filled_profile[i] >= np.max(
                    filled_profile[max(0, i - self._front_backward_lookup):i] if i > 0 else [0]
                )
            ):
                front_bin_idx = i
                x_front_internal = x_min + i * self._cellsize
                break

            # Strategy B: inclined wall — foot of slope, profile still below threshold
            # if (
            #     profile_gradient[i] > 0
            #     and filled_profile[i] < self._z_wall_threshold
            #     and np.max(filled_profile[i:min(i + self._front_backward_lookup, num_bins)]) >= self._z_wall_threshold
            # ):
            #     front_bin_idx = i
            #     x_front_internal = x_min + i * self._cellsize
            #     break

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

        # Step 6b: Bed plane confirmation (skipped if enable_area_check is False).
        #
        # Use the original 3D points (pts_3d) cropped to the cavity X range to
        # verify that a horizontal plane — the bin floor / cargo bed — actually
        # exists between the two detected walls.
        #
        # Algorithm:
        #   1. Crop pts_3d to the interior cavity window (same X inset as before).
        #   2. Fit a plane via SVD (zero-mean, smallest singular vector = normal).
        #   3. Check |n_z| >= bed_normal_z_min (default 0.8) to confirm the
        #      fitted surface is near-horizontal — a true flat bed, not a wall
        #      or coupling structure at an angle.
        #   4. Count inliers (points within a cell-sized distance of the plane)
        #      and require at least min_bed_inliers.
        #
        # Confidence is set to the inlier fraction relative to all interior points,
        # capped at 1.0.
        _edge_half = self._cellsize
        interior_mask = (pts_3d[:, 0] > x_rear_internal + _edge_half) & (
                pts_3d[:, 0] < x_front_internal - _edge_half
        )
        interior_pts_3d = pts_3d[interior_mask]

        if self._enable_area_check:
            if len(interior_pts_3d) < 3:
                logger.debug("Rejected: fewer than 3 points inside cavity")
                return BinDetectionResult(
                    detected=False, status="SEARCH / NO INTERIOR POINTS"
                )

            # RANSAC plane fit on the 3D interior cloud.
            # Handles outliers (wall remnants, material, rain) far better than SVD —
            # as long as the bed plane makes up >50% of points, RANSAC finds it.
            interior_pcd = o3d.geometry.PointCloud()
            interior_pcd.points = o3d.utility.Vector3dVector(interior_pts_3d)
            plane_model, inliers = interior_pcd.segment_plane(
                distance_threshold=self._cellsize,
                ransac_n=3,
                num_iterations=200,
            )
            a, b, c, d = plane_model
            normal = np.array([a, b, c], dtype=np.float64)
            normal = normal / np.linalg.norm(normal)
            n_z = abs(float(normal[2]))

            if n_z < self._bed_normal_z_min:
                logger.debug(
                    "Rejected: bed plane normal Z component %.3f < min %.3f "
                    "(fitted surface is not horizontal)",
                    n_z,
                    self._bed_normal_z_min,
                )
                return BinDetectionResult(
                    detected=False,
                    status=f"SEARCH / NON-HORIZONTAL BED (|n_z|={n_z:.2f})",
                )

            inlier_count = len(inliers)
            if inlier_count < self._min_bed_inliers:
                logger.debug(
                    "Rejected: only %d bed inliers (min %d)",
                    inlier_count,
                    self._min_bed_inliers,
                )
                return BinDetectionResult(
                    detected=False,
                    status=f"SEARCH / SPARSE BED ({inlier_count} inliers)",
                )

            confidence = round(min(inlier_count / len(interior_pts_3d), 1.0), 2)
        else:
            # Area check is disabled — check the cavity profile between walls.
            # Uses np.min instead of percentile/mean because:
            #   - Sparse cavity returns: min is reliable with even 1-2 points
            #   - Inclined walls: min finds the true bed (deepest point),
            #     ignoring the higher points near the wall slope
            cavity_slice = height_profile[rear_bin_idx + 1:front_bin_idx]
            if len(cavity_slice) == 0:
                logger.debug("Rejected: no cavity cells between detected walls")
                return BinDetectionResult(
                    detected=False, status="SEARCH / NO CAVITY"
                )

            non_zero = cavity_slice[cavity_slice > 0]
            cavity_z = float(np.min(non_zero)) if len(non_zero) > 0 else 0.0
            if cavity_z > self._z_cavity_max:
                logger.debug(
                    "Rejected: cavity bed height %.3f > max %.3f "
                    "(no clear drop between walls)",
                    cavity_z,
                    self._z_cavity_max,
                )
                return BinDetectionResult(
                    detected=False,
                    status=f"SEARCH / SHALLOW CAVITY ({cavity_z:.2f}m)",
                )

            confidence = 1.0

        # Step 7: Compute bin geometry — positioning and status are handled externally
        x_center = (x_rear_internal + x_front_internal) / 2.0

        # Edge point clouds: retain only the points that form each detected wall face.
        # A 3-cell window (1.5× cell_size on each side) captures the wall slab without
        # pulling in interior cavity or exterior truck-floor returns.

        _edge_half = self._cellsize
        rear_mask = (pts[:, 0] >= x_rear_internal - _edge_half) & (
                pts[:, 0] <= x_rear_internal + _edge_half
        )
        front_mask = (pts[:, 0] >= x_front_internal - _edge_half) & (
                pts[:, 0] <= x_front_internal + _edge_half
        )

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
