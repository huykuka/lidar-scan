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
            max_bed_structure_cells: int = 0,
            max_wall_thickness: float = 0.5,
            wall_height_match_tol: float = 0.04,
            front_step_min: float = 0.3,
            front_plateau_tol: float = 0.15,
            edge_cells: int = 3,
            edge_skip: int = 2,
            front_ramp_cells: int = 6,
            max_rear_x: float = 50.0,
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
        self._max_bed_structure_cells = max_bed_structure_cells
        self._max_wall_thickness = max_wall_thickness
        self._wall_height_match_tol = wall_height_match_tol
        self._front_step_min = front_step_min
        self._front_plateau_tol = front_plateau_tol
        self._edge_cells = max(1, edge_cells)
        self._edge_skip = max(0, edge_skip)
        self._front_ramp_cells = max(0, front_ramp_cells)
        self._max_rear_x = max_rear_x

    # ------------------------------------------------------------------
    # Private: wall / bin search on the raw height profile
    # ------------------------------------------------------------------

    def _wall_runs(self, hp: np.ndarray) -> list[tuple[int, int, float]]:
        """Group cells at wall height into slabs: (first_cell, last_cell, top_z).

        Works on the raw profile only.  Empty cells are never "tall", so a
        tall object far behind the truck cannot bleed into the wall through
        forward-filled gaps.  Slabs narrower than ``edge_cells`` (1-2 cells by
        default) are dropped: a lone thin return at wall height is a horizontal
        crossbar, frame member or noise lying between the edges, not a wall, so the
        search simply goes on to the next slab.
        """
        tall = np.concatenate(([0], hp >= self._z_wall_threshold, [0])).astype(np.int8)
        d = np.diff(tall)
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1) - 1
        return [
            (int(s), int(e), float(np.median(hp[s:e + 1])))
            for s, e in zip(starts, ends)
            if e - s + 1 >= self._edge_cells
        ]

    def _front_step_edge(self, hp: np.ndarray, first_tall: int) -> int | None:
        """Pin the front edge to the cell where the height suddenly jumps up.

        The front wall rises almost vertically: one cell sits at bed level and the next
        is far higher.  Starting at the first cell at wall height, look back a few cells
        for the biggest single-cell rise (>= front_step_min).  The jump is only
        confirmed when at least one of the ``edge_cells`` cells just ahead of it
        stays at a similar height (within front_plateau_tol) -- the top of the wall.
        Returns the jump cell, or None when this is not a vertical step with a level
        top (slope, pile, noise).
        """
        window = self._edge_cells
        n = len(hp)
        best_idx, best_rise = None, self._front_step_min
        for i in range(first_tall, max(first_tall - 4, 0), -1):
            # Bed level: last real return before the jump (skips empty cells).
            j = i - 1
            while j >= 0 and hp[j] <= 0 and i - j <= 3:
                j -= 1
            prev = hp[j] if j >= 0 else 0.0
            rise = hp[i] - prev
            if rise >= best_rise:
                best_idx, best_rise = i, rise
        if best_idx is None:
            return self._front_ramp_edge(hp, first_tall)
        top = hp[best_idx]
        ahead = hp[best_idx + 1:min(best_idx + 1 + window, n)]
        level = np.count_nonzero(np.abs(ahead[ahead > 0] - top) <= self._front_plateau_tol)
        if level < 1:
            return None
        return best_idx

    def _front_ramp_edge(self, hp: np.ndarray, first_tall: int) -> int | None:
        """Fallback for a front wall with an inclined plate on its bed side.

        The height climbs over several cells instead of jumping in one, so no single-cell
        rise reaches front_step_min.  Accept it when, within ``front_ramp_cells`` cells
        before the first wall-height cell, the profile rises steadily (no dip beyond
        a third of front_plateau_tol) by at least front_step_min, and the cells ahead
        hold a level top.  The edge is pinned to the first wall-height cell.
        """
        n = len(hp)
        if self._front_ramp_cells <= 0 or first_tall <= 0:
            return None
        base = hp[max(first_tall - self._front_ramp_cells, 0):first_tall]
        base = base[base > 0]
        if len(base) == 0:
            return None
        seq = np.append(base, hp[first_tall])
        if hp[first_tall] - seq.min() < self._front_step_min:
            return None
        if np.any(np.diff(seq) < -self._front_plateau_tol / 3.0):
            return None
        ahead = hp[first_tall:min(first_tall + 1 + self._edge_cells, n)]
        ahead = ahead[ahead > 0]
        if np.count_nonzero(np.abs(ahead - ahead.max()) <= self._front_plateau_tol) < 2:
            return None
        return first_tall

    def _has_bed(self, cav: np.ndarray) -> str | None:
        """Check the cells between the walls look like a cargo bed.

        Returns None when valid, else a reason: "NO BED" (too few bed-height returns) or
        "VERTICAL STRUCTURE" (more than ``max_bed_structure_cells`` cells at wall height
        between the walls: another wall, a post or a frame standing up from the bed).
        """
        if np.count_nonzero(cav >= self._z_wall_threshold) > self._max_bed_structure_cells:
            return "VERTICAL STRUCTURE"
        n_bed = np.count_nonzero((cav >= self._z_cavity_min) & (cav < self._z_wall_threshold))
        return "NO BED" if n_bed < self._min_bed_cells else None

    def _rear_reject(
            self, hp: np.ndarray, end: int, top: float, len_cells: int, wall_top: float | None
    ) -> str | None:
        """Run the rear-wall checks on one thin slab, in order.  None = accepted, else the reason.

        1. HEIGHT MISMATCH -- the slab top differs from the known ``wall_top``.
        2. EMPTY AHEAD     -- after ``edge_skip`` cells (inner face, edge noise), any of
                              the next ``edge_cells`` cells has no return: a stray slab.
        3. cargo bed       -- the ``len_cells`` cells ahead must look like a bed (``_has_bed``).
        """
        if wall_top is not None and abs(top - wall_top) > self._wall_height_match_tol:
            return "HEIGHT MISMATCH"

        first = end + 1 + self._edge_skip
        ahead = hp[first:first + self._edge_cells]
        if len(ahead) < self._edge_cells or not np.all(ahead > 0):
            return "EMPTY AHEAD"

        return self._has_bed(hp[end + 1:end + 1 + len_cells])

    def _find_rear_for_length(
            self, hp: np.ndarray, length: float, wall_top: float | None,
            max_rear_idx: int | None = None,
    ) -> tuple[int, int, float] | str:
        """Length is stable: find only the rear wall; the front is rear + length.

        Walks the thin wall slabs from ``max_rear_idx`` (the max rear edge position)
        backward and returns the first one that passes ``_rear_reject``.  No front wall
        is searched for.

        Returns (rear_inner_cell, front_cell, wall_top) or a reason string.
        """
        max_wall_cells = int(np.ceil(self._max_wall_thickness / self._cellsize)) + 1
        len_cells = int(round(length / self._cellsize))

        all_runs = self._wall_runs(hp)
        runs = all_runs
        if max_rear_idx is not None:
            runs = [r for r in runs if r[1] <= max_rear_idx]

        reached = "NO WALL"
        for start, end, top in reversed(runs):
            if end - start + 1 > max_wall_cells:
                continue
            reason = self._rear_reject(hp, end, top, len_cells, wall_top)
            if reason is None:
                # A wall slab at the expected front that is not the rear's height means
                # this rear is the wrong one - keep going.  No slab there is fine (front
                # out of view or sloped), so only a mismatch rejects.
                front = end + len_cells
                near = [t for s, e, t in all_runs if s <= front + max_wall_cells and e >= front - max_wall_cells]
                if near and all(abs(t - top) > self._wall_height_match_tol for t in near):
                    reached = "FRONT HEIGHT MISMATCH"
                    continue
                return end, front, top
            reached = reason
        return reached

    def _front_reject(
            self, hp: np.ndarray, start: int, end: int, top: float, len_cells: int,
            wall_top: float | None,
    ) -> tuple[int, int] | str:
        """Run the front-wall checks on one thin slab, in order.

        Returns (rear_cell, front_edge_cell) when accepted, else the reason string.

        1. HEIGHT MISMATCH -- the slab top differs from the known ``wall_top``.
        2. NOTHING AFTER   -- none of the ``edge_cells`` cells past the slab (after
                              ``edge_skip``) has a return: a lone frame, not a wall.
        3. NO STEP         -- no vertical jump with a level top at the slab's start.
        4. cargo bed       -- the ``len_cells`` cells behind the edge must look like a bed.
        """
        if wall_top is not None and abs(top - wall_top) > self._wall_height_match_tol:
            return "HEIGHT MISMATCH"

        first = end + 1 + self._edge_skip
        if not np.any(hp[first:first + self._edge_cells] > 0):
            return "NOTHING AFTER"

        edge = self._front_step_edge(hp, start)
        if edge is None:
            return "NO STEP"

        rear = edge - len_cells
        bad = self._has_bed(hp[max(rear + 1, 0):edge])
        return bad if bad else (rear, edge)

    def _find_front_for_length(
            self, hp: np.ndarray, length: float, wall_top: float | None
    ) -> tuple[int, int, float] | str:
        """Length is stable but the rear wall is out of view: find the front wall; rear = front - length.

        The truck drove far to the other side, so only the front wall is in the scan.  Walks
        the thin wall slabs and returns the first one that passes ``_front_reject``.

        Returns (rear_cell, front_edge_cell, wall_top) or a reason string; the rear cell may
        be before the start of the scan.
        """
        max_wall_cells = int(np.ceil(self._max_wall_thickness / self._cellsize)) + 1
        len_cells = int(round(length / self._cellsize))

        reached = "NO WALL"
        for start, end, top in self._wall_runs(hp):
            if end - start + 1 > max_wall_cells:
                continue
            result = self._front_reject(hp, start, end, top, len_cells, wall_top)
            if isinstance(result, str):
                reached = result
                continue
            return result[0], result[1], top
        return reached

    def _find_bin(self, hp: np.ndarray) -> tuple[int, int, float] | str:
        """Pair a rear wall with a front wall around a floored cavity.

        Returns (rear_inner_cell, front_inner_cell, wall_top) for the first valid pair,
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
                # The rear wall is the reference: its height picks the front.  A slab
                # that is not a vertical step with a level top (frame member, slope,
                # pile) is not the front wall - keep going forward.
                edge = self._front_step_edge(hp, front_start)
                if edge is None:
                    if reached in ("NO WALL", "WALL TOO THICK", "HEIGHT MISMATCH"):
                        reached = "NO STEP"
                    continue
                front_start = edge
                length = (front_start - rear_end) * cs
                # A height-matched, step-confirmed slab is the only front candidate:
                # anything further is behind another wall (e.g. a stray wall must not
                # pair across the next bin's rear wall).
                if not self._min_bin_length <= length <= self._max_bin_length:
                    reached = "BAD LENGTH"
                    break
                cav = hp[rear_end + 1:front_start]
                bad = self._has_bed(cav)
                if bad:
                    reached = bad
                    break
                return rear_end, front_start, rear_top
        return reached

    # ------------------------------------------------------------------
    # Public: main detection
    # ------------------------------------------------------------------

    def detect(
            self,
            points: np.ndarray,
            known_length: float | None = None,
            known_wall_top: float | None = None,
    ) -> BinDetectionResult:
        """Find the bin in a fused LiDAR point cloud.

        Args:
            points: Nx3 or Nx4 array of XYZ(intensity) points.
            known_length: stable bin length (m).  When given, only the rear wall is
                searched and the front wall is placed ``known_length`` ahead of it.
            known_wall_top: wall top height of the stable bin, to match the rear wall.

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
        inferred = known_length is not None
        rear_inferred = False
        if inferred:
            # Length locked: anchor on the rear wall and place the front at rear + length.
            # If the rear is not in view (truck drove far to the other side), anchor on
            # the front wall instead and place the rear at front - length.
            max_rear_idx = int(np.floor((self._max_rear_x - x_min) / self._cellsize))
            found = self._find_rear_for_length(hp, known_length, known_wall_top, max_rear_idx)
            if isinstance(found, str):
                rear_reason = found
                found = self._find_front_for_length(hp, known_length, known_wall_top)
                if isinstance(found, str):
                    return miss(f"TRACK / EDGE NOT FOUND (rear: {rear_reason}, front: {found})")
                rear_inferred = True
            rear_bin_idx, front_bin_idx, wall_top = found
        else:
            found = self._find_bin(hp)
            if isinstance(found, str):
                logger.info("Bin not found: %s", found)
                return miss(f"SEARCH / REAR EDGE NOT FOUND ({found})")
            rear_bin_idx, front_bin_idx, wall_top = found
        if rear_inferred:
            x_front_internal = x_min + front_bin_idx * self._cellsize
            x_rear_internal = x_front_internal - known_length
        else:
            x_rear_internal = x_min + rear_bin_idx * self._cellsize
            x_front_internal = x_rear_internal + known_length if inferred else x_min + front_bin_idx * self._cellsize
        if x_rear_internal > self._max_rear_x:
            return miss(f"{'TRACK' if inferred else 'SEARCH'} / REAR EDGE TOO FAR (x={x_rear_internal:.2f} m)")
        length = x_front_internal - x_rear_internal
        if not inferred and not self._min_bin_length <= length <= self._max_bin_length:
            return miss(f"SEARCH / BAD LENGTH ({length:.2f} m)")

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
            cav = hp[max(rear_bin_idx + 1, 0):front_bin_idx]
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
            status="TRACKING" if inferred else "DETECTED",
            bin_points=edge_pts if len(edge_pts) > 0 else pts,
            wall_top=wall_top,
            front_inferred=inferred and not rear_inferred,
            rear_inferred=rear_inferred,
        )
