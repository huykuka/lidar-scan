"""
Bin detector for the Hopper Discharge Station.

Reads a fused point cloud from two 16-layer LiDARs and finds the open-top
cargo bin on the truck by building a side-view height profile along the
travel direction, then locating the rear and front walls of the bin cavity.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import open3d as o3d

logger = logging.getLogger(__name__)


@dataclass
class BinDetectionResult:
    """Everything the system needs to know about a detected bin."""

    detected: bool
    x_rear_internal: float = 0.0   # inner face of rear wall (m)
    x_front_internal: float = 0.0  # inner face of front wall (m)
    x_center: float = 0.0          # midpoint between the two walls (m)
    length: float = 0.0            # internal cavity length (m)
    confidence: float = 0.0        # 0–1, fraction of bed points on a flat plane
    status: str = "SEARCH"
    bin_points: Optional[np.ndarray] = None  # wall edge point clouds (rear + front)

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
    """Finds the open-top cargo bin in a LiDAR point cloud.

    Works by collapsing the 3-D scan into a 2-D side-view height profile
    (height vs. position along the truck's travel direction), then searching
    that profile for the characteristic shape of a bin: a tall rear wall,
    a low open cavity, and a tall front wall.
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
            min_bin_length: float = 3.0,
            max_bin_length: float = 8.5,
            bed_normal_z_min: float = 0.8,
            min_bed_inliers: int = 5,
            rear_forward_lookup: int = 30,
            front_backward_lookup: int = 5,
            rear_peak_back_window: int = 7,
            min_cavity_run_ratio: float = 0.6,
            min_bed_cells: int = 3,
            max_wall_thickness: float = 0.5,
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
        self._min_bin_length = min_bin_length
        self._max_bin_length = max_bin_length
        self._bed_normal_z_min = bed_normal_z_min
        self._min_bed_inliers = min_bed_inliers
        self._rear_forward_lookup = rear_forward_lookup
        self._front_backward_lookup = front_backward_lookup
        self._rear_peak_back_window = rear_peak_back_window
        self._min_cavity_run_ratio = min_cavity_run_ratio
        self._min_bed_cells = min_bed_cells
        self._max_wall_thickness = max_wall_thickness

    # ------------------------------------------------------------------
    # Helper: confirm rear wall orientation (step 5a)
    # ------------------------------------------------------------------

    def _rear_peak_back_ok(
        self,
        peak_idx: int,
        filled_profile: np.ndarray,
    ) -> bool:
        """Confirm a peak is a rear wall (RW), not a front wall (FW) seen in reverse.

        A real rear wall has open space behind it (approach floor, air) — nothing
        tall. A front wall of a following bin (FW2) also has open space behind it,
        BUT the key difference is: the region immediately behind FW2 is the gap/
        drawbar between trailers, which is well below wall height.

        How it works:
          1. From the peak, walk LEFT (backwards) through the wall slab itself —
             these cells are part of the same wall, not a separate structure.
          2. From the first cell outside the slab, look back ``rear_peak_back_window``
             cells (~50 cm). Nothing in that window should be at wall height.
             - RW1: only approach floor (~1 m) behind it → passes ✓
             - FW2 (stray): only approach floor behind it too → also passes.
             NOTE: back_ok alone cannot distinguish FW2 from RW1 in all cases.
             Its job is specifically to reject peaks that sit INSIDE a bin cavity
             (e.g. the rear face of the front wall seen from inside), where the
             cells immediately behind the peak are at wall height. The cavity check
             in step 5b handles the FW2-vs-RW1 distinction.

        Args:
            peak_idx: profile cell index of the candidate peak.
            filled_profile: interpolated height profile.

        Returns:
            True if nothing tall is immediately behind this peak (after the slab).
        """
        # Walk back through the wall slab (cells belonging to this same wall).
        j = peak_idx
        while j > 0 and filled_profile[j] >= self._z_wall_threshold:
            j -= 1
        # j is now the first cell to the LEFT of the wall slab.

        # Step 2: skip an extra ~50 cm safety buffer.
        safety_cells = int(0.2 / self._cellsize)
        j = max(0, j - safety_cells)

        # Step 3: look back rear_peak_back_window cells from here.
        back_start = max(0, j - self._rear_peak_back_window)
        if j <= back_start:
            return True  # not enough cells to check — accept
        back_slice = filled_profile[back_start:j]
        return bool(np.max(back_slice) < self._z_wall_threshold)

    # ------------------------------------------------------------------
    # Helper: validate the cavity ahead of the inner rear edge (step 5b)
    # ------------------------------------------------------------------

    def _rear_internal_cavity_ok(
        self,
        internal_idx: int,
        filled_profile: np.ndarray,
        height_profile: np.ndarray,
        num_bins: int,
    ) -> bool:
        """Early check that the space AHEAD of the inner rear wall is a real cavity.

        Once we find the inner face of the rear wall (where the profile drops
        into the bin), we quickly verify that what follows is actually a bin
        cavity — not a short gap between two separate trailers.

        Two things must be true:
          1. The low region must be long enough — at least
             ``min_cavity_run_ratio`` × ``min_bin_length``.  A gap between
             trailers is much shorter than a real bin.
          2. The floor of that region must carry real LiDAR returns at cargo
             bed height (between ``z_cavity_min`` and ``z_wall_threshold``).
             A drawbar/coupling sits lower than the cargo bed; an open gap
             between trailers returns almost no points at all.

        Note: if this check passes, step 6 still does a precise length and
        bed-plane check.  This is just a fast early-exit to save time.

        Args:
            internal_idx: profile cell index of the inner rear wall face.
            filled_profile: interpolated height profile (gaps filled in).
            height_profile: raw height profile (0.0 where no point landed).
            num_bins: total number of profile cells.

        Returns:
            True if a valid cavity is found ahead.
        """
        min_run_cells = int(
            (self._min_bin_length * self._min_cavity_run_ratio) / self._cellsize
        )

        # The inner edge cell itself may still be on the wall slope.
        # Skip forward until the profile drops below wall height.
        j = internal_idx + 1
        while j < num_bins and filled_profile[j] >= self._z_wall_threshold:
            j += 1
        cavity_start = j

        # Walk forward through the low region until the next wall.
        while j < num_bins and filled_profile[j] < self._z_wall_threshold:
            j += 1
        cavity_end = j  # exclusive — first cell of the next wall (or end)

        # Check 1: cavity long enough?
        if cavity_end - cavity_start < min_run_cells:
            return False

        # Check 2: real cargo bed present?
        # Use raw height_profile — a gap with no returns stays 0.0 even after
        # interpolation, so it cannot fake a bed here.
        cavity_heights = height_profile[cavity_start:cavity_end]
        bed_cells = np.count_nonzero(
            (cavity_heights >= self._z_cavity_min)
            & (cavity_heights < self._z_wall_threshold)
        )
        return bool(bed_cells >= self._min_bed_cells)

    # ------------------------------------------------------------------
    # Main detection
    # ------------------------------------------------------------------

    def detect(self, points: np.ndarray) -> BinDetectionResult:
        """Find the bin in a fused LiDAR point cloud.

        Args:
            points: Nx3 or Nx4 array of XYZ(intensity) points.

        Returns:
            BinDetectionResult with wall positions and cavity length.
        """
        if points is None or len(points) < 20:
            return BinDetectionResult(detected=False, status="SEARCH / NO VEHICLE")

        # Work with XYZ only, in float64.
        pts_3d = np.asarray(points[:, :3], dtype=np.float64)

        # Flatten to the XZ plane (side view) for the 1-D profile algorithm.
        # The original 3-D cloud (pts_3d) is kept for the bed-plane fit later.
        pts = pts_3d.copy()
        pts[:, 1] = 0.0

        # --- Step 1: check that the scan covers a useful range ---------------
        x_min = float(np.min(pts[:, 0]))
        x_max = float(np.max(pts[:, 0]))

        if x_max - x_min < 2.0:
            return BinDetectionResult(
                detected=False, status="SEARCH / INSUFFICIENT SCAN RANGE"
            )

        # --- Step 2: divide the scan range into equal-width cells -------------
        # Each cell will hold the highest point seen at that position.
        num_bins = int(np.ceil((x_max - x_min) / self._cellsize))
        if num_bins < 10:
            return BinDetectionResult(
                detected=False, status="SEARCH / INSUFFICIENT CELL COUNT"
            )

        bin_indices = np.clip(
            ((pts[:, 0] - x_min) / self._cellsize).astype(np.intp),
            0,
            num_bins - 1,
        )

        # --- Step 3: build the height profile --------------------------------
        # For each cell take the 90th-percentile height.  Using the 90th
        # percentile instead of the maximum suppresses rain drops and dust
        # that occasionally appear above the real structure.
        height_profile = np.zeros(num_bins)
        sort_order = np.argsort(bin_indices, kind="stable")
        sorted_bins = bin_indices[sort_order]
        sorted_z = pts[sort_order, 2]

        unique_bins, first_occurrence = np.unique(sorted_bins, return_index=True)
        groups = np.split(sorted_z, first_occurrence[1:])

        for bin_id, z_vals in zip(unique_bins, groups):
            n = len(z_vals)
            if n == 1:
                height_profile[bin_id] = z_vals[0]
            else:
                k = max(0, int(np.ceil(0.90 * n)) - 1)
                height_profile[bin_id] = np.partition(z_vals, k)[k]

        # --- Step 4: fill gaps in the profile --------------------------------
        # Some cells have no LiDAR return (e.g. open air inside the bin).
        # Forward-fill then backward-fill so the profile is continuous for
        # gradient and threshold comparisons.  The raw height_profile (with
        # its zeros) is kept for occupancy checks later.
        filled_profile = height_profile.copy()
        last_valid = 0.0
        for i in range(num_bins):
            if filled_profile[i] > 0.0:
                last_valid = filled_profile[i]
            elif last_valid > 0.0:
                filled_profile[i] = last_valid
        last_valid = 0.0
        for i in range(num_bins - 1, -1, -1):
            if filled_profile[i] > 0.0:
                last_valid = filled_profile[i]
            elif last_valid > 0.0:
                filled_profile[i] = last_valid

        # Gradient of the filled profile — used to detect rising/falling edges.
        profile_gradient = np.gradient(filled_profile)

        x_rear_internal = None
        x_front_internal = None
        rear_bin_idx = None
        front_bin_idx = None

        # --- Steps 5a + 5b: find the rear wall (outer peak → inner edge) -------
        #
        # These two steps are combined into one loop so that if a peak fails
        # the inner-edge search, we automatically try the next peak rather than
        # giving up entirely.
        #
        # For each candidate peak (left-to-right):
        #   5a) Must be the tallest point in the next rear_forward_lookup cells.
        #       _rear_peak_back_ok() checks that nothing tall sits behind it.
        #   5b) Walk forward from that peak to find the inner face (where the
        #       profile drops into the cavity).  _rear_internal_cavity_ok()
        #       confirms a real cavity — not a short inter-trailer gap.
        #       If no valid inner edge is found, move on to the next peak.
        #
        # This means a stray front wall of a following bin (FW2) that slips
        # past the 5a back-check will be rejected in 5b (no real cavity ahead),
        # and the loop continues to find the true rear wall behind it.
        rear_peak_idx = None
        rear_bin_idx = None
        x_rear_internal = None

        for i in range(num_bins - 1):
            # --- 5a: peak candidate check ------------------------------------
            end_idx = min(i + self._rear_forward_lookup, num_bins)
            if not (
                    filled_profile[i] >= self._z_wall_threshold
                    and filled_profile[i] >= np.max(filled_profile[i + 1:end_idx])
            ):
                continue

            # Back-check: nothing tall should sit immediately behind the wall
            # slab — confirms this is a rear face (RW), not a front face seen
            # from behind. The 5b cavity check handles FW2-vs-RW1 distinction.
            if not self._rear_peak_back_ok(i, filled_profile):
                logger.debug(
                    "Skipping peak at cell %d (x=%.2fm): tall structure found "
                    "right behind the wall slab — not a rear-facing wall.",
                    i,
                    x_min + i * self._cellsize,
                )
                continue

            # --- 5b: inner edge search — bounded to max_wall_thickness ----------
            # A real bin wall is a thin steel plate. The inner face must appear
            # within max_wall_thickness of the outer peak. If nothing is found
            # inside that window, this peak is not a real rear wall — move on.
            found_inner = False
            max_wall_cells = int(np.ceil(self._max_wall_thickness / self._cellsize)) + 1
            inner_search_end = min(i + max_wall_cells + 1, num_bins - 1)

            for j in range(i + 1, inner_search_end):
                if profile_gradient[j] < 0:
                    end_idx_j = min(j + 30, len(filled_profile))
                    if filled_profile[j] >= np.max(filled_profile[j + 1:end_idx_j]):
                        if not self._rear_internal_cavity_ok(
                            j, filled_profile, height_profile, num_bins
                        ):
                            logger.debug(
                                "Skipping inner rear candidate at cell %d (x=%.2fm): "
                                "no valid cavity ahead — too short or no cargo bed.",
                                j,
                                x_min + j * self._cellsize,
                            )
                            continue
                        rear_peak_idx = i
                        rear_bin_idx = j
                        x_rear_internal = x_min + j * self._cellsize
                        found_inner = True
                        break

            if found_inner:
                break
            # Inner edge not found for this peak — try the next peak candidate.
            logger.debug(
                "No valid inner edge found from peak at cell %d (x=%.2fm) — "
                "trying next peak.",
                i,
                x_min + i * self._cellsize,
            )

        if x_rear_internal is None or rear_bin_idx is None:
            logger.debug("Could not find a valid rear wall in the scan.")
            return BinDetectionResult(
                detected=False, status="SEARCH / REAR EDGE NOT FOUND"
            )

        # --- Step 5c: find the inner face of the front wall ------------------
        # Starting at least 1.5 m past the rear inner edge, scan forward for
        # the first rising edge that reaches wall height.  That is the inner
        # face of the front wall (the bin cavity ends here).
        #
        # Strategy A — vertical front wall:
        #   Profile is already at wall height and still rising, AND higher than
        #   the previous front_backward_lookup cells (confirms we are at the
        #   start of the rise, not somewhere in the middle of the slope).
        #
        # Strategy B (commented out) — sloped front wall:
        #   Profile is rising but not yet at wall height; wall height is
        #   reached within front_backward_lookup cells ahead.
        start_front_search = rear_bin_idx + int(1.5 / self._cellsize)
        for i in range(start_front_search, num_bins - 1):
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

            # Strategy B: sloped front wall (disabled — enable if needed)
            # if (
            #     profile_gradient[i] > 0
            #     and filled_profile[i] < self._z_wall_threshold
            #     and np.max(filled_profile[i:min(i + self._front_backward_lookup, num_bins)]) >= self._z_wall_threshold
            # ):
            #     front_bin_idx = i
            #     x_front_internal = x_min + i * self._cellsize
            #     break

        if x_front_internal is None or front_bin_idx is None:
            logger.debug("Could not find the inner face of the front wall.")
            return BinDetectionResult(
                detected=False, status="SEARCH / FRONT EDGE NOT FOUND"
            )

        # --- Step 6: check the measured cavity length ------------------------
        length = x_front_internal - x_rear_internal
        if not (self._min_bin_length <= length <= self._max_bin_length):
            logger.debug(
                "Rejected: measured length %.2f m is outside the allowed "
                "range [%.2f, %.2f] m.",
                length,
                self._min_bin_length,
                self._max_bin_length,
            )
            return BinDetectionResult(
                detected=False, status=f"SEARCH / INVALID LENGTH ({length:.1f}m)"
            )

        # --- Step 6b: confirm a flat cargo bed exists inside the cavity ------
        # Crop the 3-D cloud to the interior of the detected cavity and fit a
        # plane to it.  A real open-top bin has a flat, roughly horizontal
        # floor.  We reject detections where the fitted surface is tilted
        # (could be a coupling bar, wall remnant, or random structure) or
        # where too few points land on it (almost-empty cavity).
        #
        # If enable_area_check is False, skip the 3-D fit and use a simpler
        # check on the 1-D profile instead.
        _edge_half = self._cellsize
        interior_mask = (pts_3d[:, 0] > x_rear_internal + _edge_half) & (
                pts_3d[:, 0] < x_front_internal - _edge_half
        )
        interior_pts_3d = pts_3d[interior_mask]

        if self._enable_area_check:
            if len(interior_pts_3d) < 3:
                logger.debug("Rejected: fewer than 3 points inside the cavity.")
                return BinDetectionResult(
                    detected=False, status="SEARCH / NO INTERIOR POINTS"
                )

            # Fit a plane with RANSAC — robust against a few outliers (rain,
            # cargo material, wall remnants) as long as the flat bed makes up
            # more than half the interior points.
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
                    "Rejected: fitted surface is not flat enough "
                    "(|n_z|=%.3f, need >= %.3f). Not a horizontal cargo bed.",
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
                    "Rejected: only %d points fit the bed plane (need %d). "
                    "Cavity may be empty or blocked.",
                    inlier_count,
                    self._min_bed_inliers,
                )
                return BinDetectionResult(
                    detected=False,
                    status=f"SEARCH / SPARSE BED ({inlier_count} inliers)",
                )

            confidence = round(min(inlier_count / len(interior_pts_3d), 1.0), 2)

        else:
            # Simplified check: look at the lowest return inside the cavity.
            # A real bin cavity has a floor well below wall height.
            cavity_slice = height_profile[rear_bin_idx + 1:front_bin_idx]
            if len(cavity_slice) == 0:
                logger.debug("Rejected: no profile cells between the two walls.")
                return BinDetectionResult(
                    detected=False, status="SEARCH / NO CAVITY"
                )

            non_zero = cavity_slice[cavity_slice > 0]
            cavity_z = float(np.min(non_zero)) if len(non_zero) > 0 else 0.0
            if cavity_z > self._z_cavity_max:
                logger.debug(
                    "Rejected: lowest return inside cavity is %.3f m — "
                    "too high (max allowed %.3f m). No clear open cavity.",
                    cavity_z,
                    self._z_cavity_max,
                )
                return BinDetectionResult(
                    detected=False,
                    status=f"SEARCH / SHALLOW CAVITY ({cavity_z:.2f}m)",
                )

            confidence = 1.0

        # --- Step 7: compute final bin position ------------------------------
        x_center = (x_rear_internal + x_front_internal) / 2.0

        # Collect the wall-face point clouds for visualisation.
        # A narrow window around each wall position captures the wall slab
        # without pulling in cavity floor or truck-frame returns.
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
