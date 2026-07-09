"""
BinDetector — finds the open-top cargo bin in a fused LiDAR point cloud.

Works by collapsing the 3-D scan into a 2-D side-view height profile
(height vs. position along the truck's travel direction), then searching
that profile for the characteristic shape of a bin: a tall rear wall,
a low open cavity, and a tall front wall.

Pure helper functions and shared types live in profile_helpers.py.
"""
import logging

import numpy as np
import open3d as o3d

from .profile_helpers import (
    BinDetectionResult,
    build_height_profile,
    fill_profile,
    miss,
    rolling_bwd_max,
    rolling_fwd_max,
)

logger = logging.getLogger(__name__)


class BinDetector:

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
    # Private: peak / edge validators
    # ------------------------------------------------------------------

    def _rear_peak_back_ok(self, peak_idx: int, fp: np.ndarray) -> bool:
        """Confirm nothing tall sits immediately behind a candidate rear-wall peak.

        Why: the scan direction is left-to-right (increasing X).  The very
        first tall peak the scan encounters should be the outer face of the
        rear wall — open air is behind it (between the sensor and the truck).
        If a tall structure exists in the cells directly behind the peak, it
        means this peak is actually an interior wall (e.g. the front wall of
        the bin seen from inside after we have already passed the rear wall),
        not the true outer rear face.

        We skip over the wall slab cells first because those belong to the
        same wall and must not be counted as a "structure behind".  A short
        safety gap is then added to avoid triggering on the gradient overhang
        right at the slab edge.
        """
        j = peak_idx
        while j > 0 and fp[j] >= self._z_wall_threshold:
            j -= 1
        j = max(0, j - int(0.2 / self._cellsize))          # small safety gap
        back_start = max(0, j - self._rear_peak_back_window)
        return j <= back_start or bool(np.max(fp[back_start:j]) < self._z_wall_threshold)

    def _rear_internal_cavity_ok(
        self,
        internal_idx: int,
        fp: np.ndarray,
        hp: np.ndarray,
        num_bins: int,
    ) -> bool:
        """Early check that a real bin cavity follows the inner rear wall edge.

        Why: once the inner face of the rear wall is found, we quickly verify
        that what follows is actually a bin cavity and not a short gap between
        two separate trailers.  Running this check before committing to a peak
        lets the outer loop skip false positives cheaply and try the next peak,
        instead of waiting for step 6 to reject a bad detection.

        Two conditions must hold:
          1. The low region must be long enough — at least
             min_cavity_run_ratio × min_bin_length.  A gap between trailers
             is far shorter than a real bin cavity.
          2. The floor of that region must carry real LiDAR returns at cargo-
             bed height (z_cavity_min ≤ z < z_wall_threshold).  A drawbar or
             coupling bar sits lower than the cargo bed; an open gap between
             trailers returns almost no points at all.  We use the raw (un-
             interpolated) height profile so that empty cells cannot fake a bed
             through forward-fill interpolation.
        """
        min_run = int(self._min_bin_length * self._min_cavity_run_ratio / self._cellsize)
        j = internal_idx + 1
        while j < num_bins and fp[j] >= self._z_wall_threshold:
            j += 1
        cav_start = j
        while j < num_bins and fp[j] < self._z_wall_threshold:
            j += 1
        if j - cav_start < min_run:
            return False
        cav_hp = hp[cav_start:j]
        return bool(
            np.count_nonzero(
                (cav_hp >= self._z_cavity_min) & (cav_hp < self._z_wall_threshold)
            ) >= self._min_bed_cells
        )

    # ------------------------------------------------------------------
    # Public: main detection
    # ------------------------------------------------------------------

    def detect(self, points: np.ndarray) -> BinDetectionResult:
        """Find the bin in a fused LiDAR point cloud.

        Args:
            points: Nx3 or Nx4 array of XYZ(intensity) points.

        Returns:
            BinDetectionResult with wall positions and cavity length.
        """
        if points is None or len(points) < 20:
            return miss("SEARCH / NO VEHICLE")

        # Keep a 3-D copy for the bed-plane fit later (step 6b).
        # All profile work uses a flattened XZ version (Y set to 0) so the
        # 1-D height profile is purely longitudinal.
        pts_3d = np.asarray(points[:, :3], dtype=np.float64)
        pts = pts_3d.copy()
        pts[:, 1] = 0.0

        x_min = float(pts[:, 0].min())
        x_max = float(pts[:, 0].max())

        # --- Step 1: sanity-check the scan range ----------------------------
        # The scan must span at least 2 m to contain any meaningful structure.
        # A shorter range means the truck is not in the scan area yet.
        if x_max - x_min < 2.0:
            return miss("SEARCH / INSUFFICIENT SCAN RANGE")

        # Fast pre-check: if the tallest point in the entire scan is below
        # wall height, there is no bin wall at all.  Return immediately to
        # avoid the expensive profile-building steps below.
        if float(pts[:, 2].max()) < self._z_wall_threshold:
            return miss("SEARCH / NO WALL HEIGHT DETECTED")

        # --- Step 2: divide the scan into equal-width cells -----------------
        # We collapse the 3-D cloud into a 1-D height profile by slicing the
        # X axis into cells of width cell_size.  Each cell will hold the
        # maximum height seen at that longitudinal position.
        num_bins = int(np.ceil((x_max - x_min) / self._cellsize))
        if num_bins < 10:
            return miss("SEARCH / INSUFFICIENT CELL COUNT")

        # --- Step 3: build the height profile --------------------------------
        # For each cell, take the maximum Z after clipping to z_max.  Clipping
        # suppresses rain/dust returns that sit above the bin rim without the
        # cost of a full 90th-percentile sort; z_max filtering is expected to
        # be applied upstream anyway.  np.maximum.at is a single O(N) scatter —
        # much faster than the previous sort + per-bin partition loop.
        hp = build_height_profile(pts, x_min, num_bins, self._cellsize, self._z_max)

        # --- Step 4: fill empty cells ----------------------------------------
        # Some cells have no LiDAR return (open air above the bin cavity, or
        # sparse coverage).  Empty cells (value 0) would break the gradient
        # and threshold comparisons that follow.  We forward-fill then backward-
        # fill so every cell carries a plausible height value.
        # The raw profile (hp, with its zeros) is kept for the bed-presence
        # check in step 5b where we must not confuse "no return" with a bed.
        fp = fill_profile(hp)

        # Profile gradient: used to detect rising (front wall) and falling
        # (rear wall inner face) edges.  np.gradient uses central differences,
        # so each value is smoothed by its immediate neighbours — resilient to
        # single-cell noise.
        grad = np.gradient(fp)

        # --- Precompute rolling maxima ---------------------------------------
        # Steps 5a and 5b each need "what is the max height in the next W
        # cells?".  Computing that inside the loop is O(N×W); building the
        # lookup tables once here makes every per-cell check O(1).
        #
        # max_peak_cell: a rear-wall peak only makes sense if there is enough
        # room ahead to fit a full bin (min_bin_length).  Peaks beyond this
        # point are guaranteed to fail the length gate in step 6, so we stop
        # the search early.
        max_peak_cell  = int((x_max - x_min - self._min_bin_length) / self._cellsize)
        max_wall_cells = int(np.ceil(self._max_wall_thickness / self._cellsize)) + 1
        fwd_max_5a = rolling_fwd_max(fp, self._rear_forward_lookup)
        fwd_max_5b = rolling_fwd_max(fp, 30)

        # Backward rolling max for step 5c: bwd_max[i] = max(fp[i-W : i]).
        # The front-wall check requires the candidate cell to be higher than
        # the W cells immediately before it (confirms we are at the START of
        # the rising edge, not somewhere in the middle of the slope).
        bwd_max_5c = rolling_bwd_max(fp, self._front_backward_lookup)

        # --- Steps 5a + 5b: find the rear wall (outer peak → inner edge) ----
        # These two steps are combined into one loop so that if a peak fails
        # the inner-edge search we automatically try the next peak, rather than
        # giving up entirely.
        #
        # 5a — outer peak: must be the tallest point in the next
        #      rear_forward_lookup cells AND pass the back-check (nothing tall
        #      sits behind it).
        # 5b — inner edge: walk forward from that peak within max_wall_thickness.
        #      The inner face is where the gradient goes negative AND the cell
        #      is still a local maximum looking forward 30 cells.  The cavity
        #      check rejects peaks whose "cavity" is really a short inter-trailer
        #      gap or a low drawbar rather than a real bin floor.
        rear_bin_idx = x_rear_internal = None

        for i in range(min(num_bins - 1, max_peak_cell)):

            # 5a: reject cells below wall height or not a local forward maximum.
            if fp[i] < self._z_wall_threshold or fp[i] < fwd_max_5a[i]:
                continue

            # 5a: reject peaks with a tall structure immediately behind them.
            if not self._rear_peak_back_ok(i, fp):
                logger.debug("peak @%d (%.2fm): tall structure behind — skip", i, x_min + i * self._cellsize)
                continue

            # 5b: search for the inner face within max_wall_thickness.
            inner_end = min(i + max_wall_cells + 1, num_bins - 1)
            for j in range(i + 1, inner_end):
                if grad[j] < 0 and fp[j] >= fwd_max_5b[j]:
                    if not self._rear_internal_cavity_ok(j, fp, hp, num_bins):
                        logger.debug("inner @%d (%.2fm): no valid cavity — skip", j, x_min + j * self._cellsize)
                        continue
                    rear_bin_idx = j
                    x_rear_internal = x_min + j * self._cellsize
                    break

            if x_rear_internal is not None:
                break
            logger.debug("peak @%d (%.2fm): no inner edge found — try next", i, x_min + i * self._cellsize)

        if x_rear_internal is None:
            logger.debug("No valid rear wall found.")
            return miss("SEARCH / REAR EDGE NOT FOUND")

        # --- Step 5c: find the front wall inner edge -------------------------
        # Starting at least 1.5 m past the rear inner edge (to skip the cavity
        # floor returns), scan forward for the first cell that is rising,
        # above wall height, AND higher than the previous front_backward_lookup
        # cells.  That last condition confirms we are at the START of the rising
        # edge rather than somewhere in the middle of the slope.
        x_front_internal = front_bin_idx = None
        for i in range(rear_bin_idx + int(1.5 / self._cellsize), num_bins - 1):
            if grad[i] > 0 and fp[i] >= self._z_wall_threshold and fp[i] >= bwd_max_5c[i]:
                front_bin_idx = i
                x_front_internal = x_min + i * self._cellsize
                break

        if x_front_internal is None:
            logger.debug("No front wall found.")
            return miss("SEARCH / FRONT EDGE NOT FOUND")

        # --- Step 6: length gate ---------------------------------------------
        # The distance between the two inner faces must fall within the
        # configured [min_bin_length, max_bin_length] range.  Too short means
        # we latched onto a coupling structure or a cabin; too long means the
        # front edge is actually the rear wall of the next trailer.
        length = x_front_internal - x_rear_internal
        if not (self._min_bin_length <= length <= self._max_bin_length):
            logger.debug("Length %.2fm outside [%.2f, %.2f]", length, self._min_bin_length, self._max_bin_length)
            return miss(f"SEARCH / INVALID LENGTH ({length:.1f}m)")

        # --- Step 6b: bed-plane confirmation ---------------------------------
        # Crop the 3-D cloud to the interior of the cavity and verify that a
        # roughly horizontal flat plane — the cargo bed — actually exists there.
        # This rejects cases where the two detected walls happen to be the right
        # distance apart but there is no real open-top bin between them (e.g. a
        # drawbar trailer, a closed container, or a random pair of structures).
        #
        # If enable_area_check is False, use a simpler 1-D profile check
        # instead (suitable when only one LiDAR is available and Y-spread is
        # unreliable).
        eh = self._cellsize
        interior_pts = pts_3d[
            (pts_3d[:, 0] > x_rear_internal + eh) & (pts_3d[:, 0] < x_front_internal - eh)
        ]

        if self._enable_area_check:
            if len(interior_pts) < 3:
                return miss("SEARCH / NO INTERIOR POINTS")

            # RANSAC plane fit: robust against outliers (rain, cargo material,
            # wall remnants) as long as the flat bed makes up > 50 % of points.
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(interior_pts)
            plane_model, inliers = pcd.segment_plane(
                distance_threshold=self._cellsize, ransac_n=3, num_iterations=200
            )
            # The Z component of the plane normal must be close to 1 — a value
            # near 0 means the fitted surface is nearly vertical (wall remnant
            # or coupling bar), not a horizontal cargo bed.
            normal = np.array(plane_model[:3])
            n_z = abs(float(normal[2] / np.linalg.norm(normal)))

            if n_z < self._bed_normal_z_min:
                logger.debug("Bed not flat enough: |n_z|=%.3f", n_z)
                return miss(f"SEARCH / NON-HORIZONTAL BED (|n_z|={n_z:.2f})")

            inlier_count = len(inliers)
            if inlier_count < self._min_bed_inliers:
                logger.debug("Too few bed inliers: %d", inlier_count)
                return miss(f"SEARCH / SPARSE BED ({inlier_count} inliers)")

            confidence = round(min(inlier_count / len(interior_pts), 1.0), 2)

        else:
            # Simplified check: the lowest real return between the two walls
            # must be below z_cavity_max.  If the minimum is too high there is
            # no open cavity — we may have latched onto a closed container or
            # the truck chassis.
            cav = hp[rear_bin_idx + 1:front_bin_idx]
            if len(cav) == 0:
                return miss("SEARCH / NO CAVITY")
            nz = cav[cav > 0]
            cavity_z = float(nz.min()) if len(nz) else 0.0
            if cavity_z > self._z_cavity_max:
                logger.debug("Cavity too shallow: %.3fm", cavity_z)
                return miss(f"SEARCH / SHALLOW CAVITY ({cavity_z:.2f}m)")
            confidence = 1.0

        # --- Step 7: output --------------------------------------------------
        # Compute the bin centre and collect the wall-face point clouds for
        # downstream visualisation.  A window of ±cell_size around each inner
        # edge position captures the wall slab without pulling in cavity floor
        # or truck-frame returns.
        x_center = (x_rear_internal + x_front_internal) / 2.0
        rear_mask  = np.abs(pts[:, 0] - x_rear_internal)  <= eh
        front_mask = np.abs(pts[:, 0] - x_front_internal) <= eh
        edge_pts = np.concatenate([pts[rear_mask], pts[front_mask]])

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
