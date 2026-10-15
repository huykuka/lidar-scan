"""
BinDetector — finds the open-top cargo bin in a fused LiDAR point cloud.

Works by collapsing the 3-D scan into a 1-D side-view height profile
(height vs. position along the truck's travel direction), grouping the tall
cells into wall slabs, and pairing a rear wall with a front wall that bound
an open, floored cavity of plausible length.

Pure helper functions and shared types live in profile_helpers.py.
"""
import logging

import numpy as np
import open3d as o3d

from .profile_helpers import BinDetectionResult, build_height_profile, miss

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
            min_bed_cells: int = 3,
            max_wall_thickness: float = 0.5,
            wall_height_match_tol: float = 0.04,
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
        self._min_bed_cells = min_bed_cells
        self._max_wall_thickness = max_wall_thickness
        self._wall_height_match_tol = wall_height_match_tol

    # ------------------------------------------------------------------
    # Private: wall / bin search on the raw height profile
    # ------------------------------------------------------------------

    def _wall_runs(self, hp: np.ndarray) -> list[tuple[int, int, float]]:
        """Group cells at wall height into slabs: (first_cell, last_cell, top_z).

        Works on the raw profile only.  Empty cells are never "tall", so a
        tall object far behind the truck cannot bleed into the wall through
        forward-filled gaps.  A 1-cell slab is valid: seen from above, a bin
        rim is only a few centimetres thick.
        """
        tall = np.concatenate(([0], hp >= self._z_wall_threshold, [0])).astype(np.int8)
        d = np.diff(tall)
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1) - 1
        return [(int(s), int(e), float(np.median(hp[s:e + 1]))) for s, e in zip(starts, ends)]

    def _find_bin(self, hp: np.ndarray) -> tuple[int, int] | str:
        """Pair a rear wall with a front wall around a floored cavity.

        Returns (rear_inner_cell, front_inner_cell) for the first valid pair,
        or a short reason string naming the furthest check any pair reached.

        A pair is valid when:
          1. the rear slab is thin enough to be a wall (not a cab or solid block),
          2. the front wall is the NEXT slab of the same top height (within
             wall_height_match_tol) — taller/shorter slabs such as cab roofs,
             cranes and crossbars are skipped, but a matching wall in between
             means the candidate is behind another wall,
          3. the gap between the inner faces is within
             [min_bin_length, max_bin_length] — rejects a short stray wall,
          4. the gap holds real returns at cargo-bed height — rejects an empty
             gap between trailers and a low drawbar.
        """
        cs = self._cellsize
        max_wall_cells = int(np.ceil(self._max_wall_thickness / cs)) + 1
        runs = self._wall_runs(hp)
        reached = "NO WALL"
        for k, (_, rear_end, rear_top) in enumerate(runs):
            if rear_end - runs[k][0] + 1 > max_wall_cells:
                if reached == "NO WALL":
                    reached = "WALL TOO THICK"
                continue
            for front_start, _, front_top in runs[k + 1:]:
                if abs(front_top - rear_top) > self._wall_height_match_tol:
                    # Different height: crossbar, cargo or cab, not a wall of
                    # this bin — look past it.
                    if reached in ("NO WALL", "WALL TOO THICK"):
                        reached = "HEIGHT MISMATCH"
                    continue
                # First height-matched slab ahead is the only front-wall
                # candidate: anything further is behind another wall.
                length = (front_start - rear_end) * cs
                if not self._min_bin_length <= length <= self._max_bin_length:
                    reached = "BAD LENGTH"
                    break
                cav = hp[rear_end + 1:front_start]
                n_bed = np.count_nonzero((cav >= self._z_cavity_min) & (cav < self._z_wall_threshold))
                if n_bed < self._min_bed_cells:
                    reached = "NO BED"
                    break
                return rear_end, front_start
        return reached

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

        # Keep a 3-D copy for the bed-plane fit later (step 4).
        # All profile work uses a flattened XZ version (Y set to 0) so the
        # 1-D height profile is purely longitudinal.
        pts_3d = np.asarray(points[:, :3], dtype=np.float64)
        pts = pts_3d.copy()
        pts[:, 1] = 0.0

        x_min = float(pts[:, 0].min())
        x_max = float(pts[:, 0].max())

        # --- Step 1: sanity-check the scan range ----------------------------
        # The scan must span at least 2 m to contain any meaningful structure.
        if x_max - x_min < 2.0:
            return miss("SEARCH / INSUFFICIENT SCAN RANGE")

        # If the tallest point is below wall height there is no bin wall at all.
        if float(pts[:, 2].max()) < self._z_wall_threshold:
            return miss("SEARCH / NO WALL HEIGHT DETECTED")

        # --- Step 2: height profile ------------------------------------------
        # Slice X into cells; each cell holds a high percentile of Z (clipped
        # to z_max).  Cells with no return stay 0 and are never treated as tall.
        num_bins = int(np.ceil((x_max - x_min) / self._cellsize))
        if num_bins < 10:
            return miss("SEARCH / INSUFFICIENT CELL COUNT")
        hp = build_height_profile(pts, x_min, num_bins, self._cellsize, self._z_max)

        # --- Step 3: pair rear and front wall --------------------------------
        found = self._find_bin(hp)
        if isinstance(found, str):
            logger.info("Bin not found: %s", found)
            return miss(f"SEARCH / REAR EDGE NOT FOUND ({found})")
        rear_bin_idx, front_bin_idx = found
        x_rear_internal = x_min + rear_bin_idx * self._cellsize
        x_front_internal = x_min + front_bin_idx * self._cellsize
        length = x_front_internal - x_rear_internal

        # --- Step 4: bed-plane confirmation ---------------------------------
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

        # --- Step 5: output --------------------------------------------------
        # Emit only the inner-edge slice of each wall — a thin band of ±cell_size
        # around the exact inner-face X coordinate.  This gives the viewer a clear
        # two-line marker (rear edge + front edge) without the full wall slab.
        x_center = (x_rear_internal + x_front_internal) / 2.0

        rear_mask  = np.abs(pts[:, 0] - x_rear_internal)  <= eh
        front_mask = np.abs(pts[:, 0] - x_front_internal) <= eh

        # Per-edge fallback: widen to ±3×cell_size if the tight slice is empty
        # (very sparse scan at that exact X position).
        if not np.any(rear_mask):
            rear_mask = np.abs(pts[:, 0] - x_rear_internal) <= 6 * eh
        if not np.any(front_mask):
            front_mask = np.abs(pts[:, 0] - x_front_internal) <= 6 * eh

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
