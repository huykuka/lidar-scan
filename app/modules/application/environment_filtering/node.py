"""
EnvironmentFilteringNode — Application-level DAG node for floor/ceiling removal.

Simplified strategy: detect all horizontal planar patches, then pick the plane
with the lowest centroid Z as the floor and the plane with the highest centroid Z
as the ceiling. Removes those two planes from the original full-resolution cloud.

Removal strategy — perpendicular plane sweep:
  For each selected plane (normal n, centroid c), every original-cloud point p
  is removed when  |dot(p - c, n)| <= plane_thickness.
  This sweeps the full infinite plane along its normal — it is NOT a Z-slab, so
  it handles tilted floors/ramps correctly and does not touch points that happen
  to share the same Z height but lie off the plane.

Architecture:
  - Heavy CPU-bound logic (_sync_filter) runs in asyncio.to_thread() (threadpool)
  - Downsampled cloud is temporary; released after segmentation
  - Output is always at original cloud resolution
  - All parameters validated at construction (ValueError on bad inputs)
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import open3d as o3d

from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)


@dataclass
class PlaneInfo:
    """Metadata for a detected floor/ceiling plane."""

    plane_id: int
    plane_type: str        # "floor" | "ceiling"
    normal: List[float]    # unit normal (3,)
    centroid: List[float]  # 3D centroid (x, y, z)
    area: float
    point_count: int
    # 99th-percentile perpendicular distance of inlier points from the fitted plane.
    # Used as the adaptive thickness floor so tilted or uneven surfaces are fully removed
    # even when the configured plane_thickness would be too tight.
    inlier_thickness: float = 0.0

    @property
    def centroid_z(self) -> float:
        return self.centroid[2]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plane_id": self.plane_id,
            "plane_type": self.plane_type,
            "normal": self.normal,
            "centroid": self.centroid,
            "centroid_z": self.centroid_z,
            "area": self.area,
            "point_count": self.point_count,
            "inlier_thickness": self.inlier_thickness,
        }


class EnvironmentFilteringNode(ModuleNode):
    """
    Removes floor and ceiling planes from real-time indoor LiDAR scans.

    Processing pipeline (all heavy ops run in threadpool):
    1. Single to_legacy() conversion of the incoming tensor cloud
    2. Optional voxel downsampling
    3. Planar patch detection (open3d detect_planar_patches)
    4. Filter to approximately-horizontal planes only
    5. Pick lowest-Z plane as floor, highest-Z plane as ceiling
    6. Map plane points back to original cloud via cKDTree (when downsampled)
    7. Remove floor + ceiling points; forward the rest downstream

    Output is ALWAYS at original cloud resolution.
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        config: Dict[str, Any],
        throttle_ms: float = 0,
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self.config = config
        self.throttle_ms = throttle_ms

        # ── Performance parameters ─────────────────────────────────────────
        _vds = config.get("voxel_downsample_size", 0.01)
        self.voxel_downsample_size: float = float(_vds if _vds is not None else 0.01)

        # ── Plane detection parameters ─────────────────────────────────────
        self.normal_variance_threshold_deg: float = float(config.get("normal_variance_threshold_deg", 60.0))
        self.coplanarity_deg: float = float(config.get("coplanarity_deg", 75.0))
        self.outlier_ratio: float = float(config.get("outlier_ratio", 0.75))
        self.min_plane_edge_length: float = float(config.get("min_plane_edge_length", 0.0))
        self.min_num_points: int = int(config.get("min_num_points", 0))
        self.max_nn: int = int(config.get("max_nn", 30))
        self.search_radius: float = float(config.get("search_radius", 0.2))

        # ── Validation parameters ──────────────────────────────────────────
        self.vertical_tolerance_deg: float = float(config.get("vertical_tolerance_deg", 15.0))
        # Pre-compute cosine threshold so _is_horizontal avoids arccos per call
        self._cos_vertical_threshold: float = float(
            np.cos(np.radians(self.vertical_tolerance_deg))
        )
        self.min_plane_area: float = float(config.get("min_plane_area", 1.0))

        # ── Filtering targets ──────────────────────────────────────────────
        self.remove_floor: bool = bool(config.get("remove_floor", True))
        self.remove_ceiling: bool = bool(config.get("remove_ceiling", True))
        # Half-thickness of the perpendicular slab swept around each plane.
        # Points with |dot(p - centroid, normal)| <= plane_thickness are removed.
        self.plane_thickness: float = float(config.get("plane_thickness", 0.1))

        self._validate_params()

        # ── Plane cache ────────────────────────────────────────────────────
        # After first successful detection, cache each plane's normal + centroid
        # so subsequent frames can skip detect_planar_patches entirely and apply
        # the perpendicular-distance sweep directly.
        # miss_confirm_frames consecutive detection failures are required before
        # the cache is invalidated.
        self.cache_refresh_frames: int = int(config.get("cache_refresh_frames", 30))
        self.miss_confirm_frames: int = int(config.get("miss_confirm_frames", 3))
        self._cached_floor: Optional[PlaneInfo] = None
        self._cached_ceiling: Optional[PlaneInfo] = None
        self._frames_since_detection: int = 0
        self._consecutive_misses: int = 0

        # ── Runtime state ──────────────────────────────────────────────────
        self.input_count: int = 0
        self.last_input_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.last_metadata: Dict[str, Any] = {}
        self.processing_time_ms: float = 0.0
        self._processing: bool = False

    # ── Parameter validation ──────────────────────────────────────────────────

    def _validate_params(self) -> None:
        if not (0.0 <= self.voxel_downsample_size <= 1.0):
            raise ValueError("voxel_downsample_size must be between 0.0 and 1.0 meters")
        if not (1 <= self.vertical_tolerance_deg <= 45):
            raise ValueError("vertical_tolerance_deg must be between 1 and 45 degrees")
        if self.min_plane_area < 0.1:
            raise ValueError("min_plane_area must be >= 0.1 square meters")

    # ── Downsampling ──────────────────────────────────────────────────────────

    def _voxel_downsample(
        self, pcd_legacy: o3d.geometry.PointCloud, n_orig: int
    ) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        if self.voxel_downsample_size <= 0:
            return pcd_legacy, {
                "downsampling_enabled": False,
                "voxel_size": 0.0,
                "points_before_downsample": n_orig,
                "points_after_downsample": n_orig,
            }

        pcd_ds = pcd_legacy.voxel_down_sample(self.voxel_downsample_size)
        n_ds = len(np.asarray(pcd_ds.points))

        if n_ds < 100:
            logger.warning(
                f"[{self.id}] Voxel size {self.voxel_downsample_size}m too large — "
                f"downsampled to {n_ds} points. Consider reducing voxel_downsample_size."
            )

        return pcd_ds, {
            "downsampling_enabled": True,
            "voxel_size": self.voxel_downsample_size,
            "points_before_downsample": n_orig,
            "points_after_downsample": n_ds,
        }

    # ── Plane detection ───────────────────────────────────────────────────────

    def _detect_horizontal_planes(
        self, pcd_legacy: o3d.geometry.PointCloud
    ) -> List[PlaneInfo]:
        """
        Detect planar patches and return only approximately-horizontal ones
        that meet the minimum area threshold.
        """
        if len(pcd_legacy.points) == 0:
            return []

        if not pcd_legacy.has_normals():
            pcd_legacy.estimate_normals(
                search_param=o3d.geometry.KDTreeSearchParamHybrid(
                    radius=self.search_radius, max_nn=self.max_nn
                )
            )

        oboxes = pcd_legacy.detect_planar_patches(
            normal_variance_threshold_deg=self.normal_variance_threshold_deg,
            coplanarity_deg=self.coplanarity_deg,
            outlier_ratio=self.outlier_ratio,
            min_plane_edge_length=self.min_plane_edge_length,
            min_num_points=self.min_num_points,
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.search_radius, max_nn=self.max_nn
            ),
        )

        if not oboxes:
            return []

        # Assign point labels via OBB containment
        points_np = np.asarray(pcd_legacy.points, dtype=np.float32)
        labels = np.full(len(points_np), -1, dtype=np.int32)
        pts_vec = o3d.utility.Vector3dVector(points_np)
        for i, obox in enumerate(oboxes):
            idx = obox.get_point_indices_within_bounding_box(pts_vec)
            if idx:
                labels[np.array(idx, dtype=np.int64)] = i

        planes: List[PlaneInfo] = []
        for i, obox in enumerate(oboxes):
            # Must be approximately horizontal (normal ≈ vertical)
            normal = obox.R[:, 2]
            normal = normal / (np.linalg.norm(normal) + 1e-9)
            if abs(float(normal[2])) < self._cos_vertical_threshold:
                continue

            # Must meet minimum footprint area
            area = float(obox.extent[0]) * float(obox.extent[1])
            if area < self.min_plane_area:
                continue

            # Compute p99 perpendicular spread of inlier points from the fitted plane.
            # This becomes the adaptive thickness: a tilted or uneven surface will have
            # a naturally larger spread, ensuring all inliers are captured even when
            # the configured plane_thickness would be too tight.
            centroid = obox.center
            inlier_mask = labels == i
            inlier_count = int(np.sum(inlier_mask))
            if inlier_count > 0:
                inlier_pts = points_np[inlier_mask]
                perp_dists = np.abs((inlier_pts - centroid.astype(np.float32)) @ normal.astype(np.float32))
                inlier_thickness = float(np.percentile(perp_dists, 99))
            else:
                inlier_thickness = 0.0

            planes.append(PlaneInfo(
                plane_id=i,
                plane_type="",  # assigned below
                normal=normal.tolist(),
                centroid=centroid.tolist(),
                area=area,
                point_count=inlier_count,
                inlier_thickness=inlier_thickness,
            ))

        return planes

    # ── Perpendicular plane sweep ─────────────────────────────────────────────

    @staticmethod
    def _plane_removal_mask(
        pts: np.ndarray,
        plane: PlaneInfo,
        thickness: float,
    ) -> np.ndarray:
        """
        Return a boolean mask of points within `thickness` of the infinite plane.

        Uses the signed perpendicular distance formula:
            distance = |dot(p - centroid, normal)|

        This sweeps the full plane along its normal regardless of orientation —
        a tilted floor or ramp is handled correctly, unlike a Z-slab.

        Args:
            pts:       (N, 3) float32 point positions
            plane:     PlaneInfo with unit normal and 3D centroid
            thickness: half-thickness of the slab in metres

        Returns:
            Boolean mask (N,), True = point is on the plane and should be removed
        """
        n = np.array(plane.normal, dtype=np.float32)
        c = np.array(plane.centroid, dtype=np.float32)
        # dot product broadcasted over all points: (N,)
        dist = np.abs((pts - c) @ n)
        return dist <= thickness

    def _effective_thickness(self, plane: PlaneInfo) -> float:
        """
        Return the removal half-thickness for a plane.

        Uses the larger of the configured plane_thickness and the plane's measured
        inlier_thickness (p99 perpendicular spread of its detection-phase inliers).
        This keeps the slab tight on flat scans and automatically expands it for
        tilted sensors or uneven surfaces where the fitted plane centroid sits further
        from some real floor/ceiling points than the fixed threshold would allow.
        """
        return max(self.plane_thickness, plane.inlier_thickness)

    # ── Core filtering (CPU-bound, runs in threadpool) ────────────────────────

    def _sync_filter(
        self, pcd_in: o3d.t.geometry.PointCloud
    ) -> Tuple[o3d.t.geometry.PointCloud, Dict[str, Any]]:
        """
        Remove floor and ceiling points using a perpendicular plane sweep.

        Fast path (cache hit): apply cached plane normal + centroid directly —
        pure numpy, no Open3D cost.
        Slow path (cache miss / refresh): run detect_planar_patches, pick
        extremes, update cache.
        """
        n_orig = len(pcd_in.point["positions"])

        _empty_meta: Dict[str, Any] = {
            "downsampling_enabled": False,
            "voxel_size": 0.0,
            "points_before_downsample": n_orig,
            "points_after_downsample": n_orig,
        }

        if n_orig == 0:
            logger.warning(f"[{self.id}] Received empty point cloud, skipping filtering")
            return pcd_in, {
                **_empty_meta,
                "input_point_count": 0,
                "output_point_count": 0,
                "removed_point_count": 0,
                "planes_detected": 0,
                "planes_filtered": 0,
                "plane_details": [],
                "status": "warning_pass_through",
            }

        pcd_legacy = pcd_in.to_legacy()
        pts_orig_np = np.asarray(pcd_legacy.points, dtype=np.float32)

        cache_hit = (
            self._cached_floor is not None
            and self._frames_since_detection < self.cache_refresh_frames
        )

        if cache_hit:
            # ── Fast path: perpendicular sweep from cached planes ─────────
            self._frames_since_detection += 1
            removal_mask = np.zeros(n_orig, dtype=bool)
            if self.remove_floor:
                removal_mask |= self._plane_removal_mask(
                    pts_orig_np, self._cached_floor, self._effective_thickness(self._cached_floor)
                )
            if self.remove_ceiling and self._cached_ceiling is not None:
                removal_mask |= self._plane_removal_mask(
                    pts_orig_np, self._cached_ceiling, self._effective_thickness(self._cached_ceiling)
                )

            keep_indices = np.where(~removal_mask)[0]
            pcd_out = pcd_in.select_by_index(keep_indices)
            n_removed = int(np.sum(removal_mask))

            cached_planes = [self._cached_floor]
            if self._cached_ceiling is not None:
                cached_planes.append(self._cached_ceiling)

            return pcd_out, {
                **_empty_meta,
                "input_point_count": n_orig,
                "output_point_count": n_orig - n_removed,
                "removed_point_count": n_removed,
                "planes_detected": len(cached_planes),
                "planes_filtered": len(cached_planes),
                "plane_details": [p.to_dict() for p in cached_planes],
                "cache_hit": True,
                "status": "success",
            }

        # ── Slow path: full detection ─────────────────────────────────────
        pcd_ds_legacy, ds_meta = self._voxel_downsample(pcd_legacy, n_orig)

        try:
            planes = self._detect_horizontal_planes(pcd_ds_legacy)
        except Exception as exc:
            logger.warning(f"[{self.id}] Plane detection failed: {exc}")
            return pcd_in, {
                **ds_meta,
                "input_point_count": n_orig,
                "output_point_count": n_orig,
                "removed_point_count": 0,
                "planes_detected": 0,
                "planes_filtered": 0,
                "plane_details": [],
                "cache_hit": False,
                "status": "no_planes_detected",
            }

        if not planes:
            self._consecutive_misses += 1
            if self._consecutive_misses < self.miss_confirm_frames:
                logger.debug(
                    f"[{self.id}] No planes detected "
                    f"({self._consecutive_misses}/{self.miss_confirm_frames} consecutive misses)"
                )
                if self._cached_floor is not None:
                    # Still within confirmation window — apply cached planes
                    removal_mask = np.zeros(n_orig, dtype=bool)
                    if self.remove_floor:
                        removal_mask |= self._plane_removal_mask(
                            pts_orig_np, self._cached_floor, self._effective_thickness(self._cached_floor)
                        )
                    if self.remove_ceiling and self._cached_ceiling is not None:
                        removal_mask |= self._plane_removal_mask(
                            pts_orig_np, self._cached_ceiling, self._effective_thickness(self._cached_ceiling)
                        )
                    keep_indices = np.where(~removal_mask)[0]
                    pcd_out = pcd_in.select_by_index(keep_indices)
                    n_removed = int(np.sum(removal_mask))
                    cached_planes = [self._cached_floor]
                    if self._cached_ceiling is not None:
                        cached_planes.append(self._cached_ceiling)
                    return pcd_out, {
                        **ds_meta,
                        "input_point_count": n_orig,
                        "output_point_count": n_orig - n_removed,
                        "removed_point_count": n_removed,
                        "planes_detected": 0,
                        "planes_filtered": len(cached_planes),
                        "plane_details": [p.to_dict() for p in cached_planes],
                        "cache_hit": True,
                        "status": "success",
                    }
            else:
                logger.info(
                    f"[{self.id}] No planes detected for {self._consecutive_misses} "
                    "consecutive frames — invalidating cache."
                )
                self._cached_floor = None
                self._cached_ceiling = None
                self._frames_since_detection = 0
                self._consecutive_misses = 0

            return pcd_in, {
                **ds_meta,
                "input_point_count": n_orig,
                "output_point_count": n_orig,
                "removed_point_count": 0,
                "planes_detected": 0,
                "planes_filtered": 0,
                "plane_details": [],
                "cache_hit": False,
                "status": "no_planes_detected",
            }

        # Pick lowest Z → floor, highest Z → ceiling
        planes_sorted = sorted(planes, key=lambda p: p.centroid_z)
        floor_plane = planes_sorted[0]
        floor_plane.plane_type = "floor"

        selected: List[PlaneInfo]
        if len(planes_sorted) == 1:
            selected = [floor_plane]
            ceiling_plane = None
        else:
            ceiling_plane = planes_sorted[-1]
            ceiling_plane.plane_type = "ceiling"
            selected = [floor_plane, ceiling_plane]

        # Update cache with full PlaneInfo (normal + centroid)
        self._cached_floor = floor_plane
        self._cached_ceiling = ceiling_plane
        self._frames_since_detection = 1
        self._consecutive_misses = 0

        logger.info(
            f"[{self.id}] Cache refreshed — "
            f"floor z={floor_plane.centroid_z:.2f}  normal={[round(x,2) for x in floor_plane.normal]}"
            + (f"  ceiling z={ceiling_plane.centroid_z:.2f}" if ceiling_plane else "")
        )

        # Build removal mask using perpendicular sweep
        removal_mask = np.zeros(n_orig, dtype=bool)
        if self.remove_floor:
            removal_mask |= self._plane_removal_mask(
                pts_orig_np, floor_plane, self._effective_thickness(floor_plane)
            )
        if self.remove_ceiling and ceiling_plane is not None:
            removal_mask |= self._plane_removal_mask(
                pts_orig_np, ceiling_plane, self._effective_thickness(ceiling_plane)
            )

        keep_indices = np.where(~removal_mask)[0]
        pcd_out = pcd_in.select_by_index(keep_indices)
        n_removed = int(np.sum(removal_mask))

        return pcd_out, {
            **ds_meta,
            "input_point_count": n_orig,
            "output_point_count": n_orig - n_removed,
            "removed_point_count": n_removed,
            "planes_detected": len(planes),
            "planes_filtered": len(selected),
            "plane_details": [p.to_dict() for p in selected],
            "cache_hit": False,
            "status": "success",
        }

    # ── Async data flow ───────────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """Receive point cloud payload, filter floor/ceiling, and forward downstream."""
        from app.modules.pipeline.base import PointConverter  # noqa: PLC0415

        self.last_input_at = time.time()
        start_t = self.last_input_at
        self.input_count += 1

        if self._processing:
            logger.debug(f"[{self.id}] Dropping frame — still processing")
            return

        points = payload.get("points")
        if points is None:
            logger.warning(f"[{self.id}] Received payload with no 'points' key, skipping")
            return

        self._processing = True
        try:
            pcd_in = PointConverter.to_pcd(points)
            pcd_out, metadata = await asyncio.to_thread(self._sync_filter, pcd_in)

            self.last_metadata = metadata
            self.processing_time_ms = (time.time() - start_t) * 1000
            self.last_error = None

            new_payload = payload.copy()
            new_payload["points"] = PointConverter.to_points(pcd_out)
            new_payload["node_id"] = self.id
            new_payload["processed_by"] = self.id
            new_payload["metadata"] = metadata
            new_payload.update(metadata)

            notify_status_change(self.id)
            asyncio.create_task(self.manager.forward_data(self.id, new_payload))

        except Exception as exc:
            self.last_error = str(exc)
            notify_status_change(self.id)
            logger.error(f"[{self.id}] {exc}", exc_info=True)
        finally:
            self._processing = False

    # ── Status reporting ──────────────────────────────────────────────────────

    def emit_status(self) -> NodeStatusUpdate:
        """Return standardised node status for DAG status API."""
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="error",
                    value=self.last_error,
                    color="red",
                ),
                error_message=self.last_error,
            )

        recently_active = (
            self.last_input_at is not None
            and time.time() - self.last_input_at < 5.0
        )

        if recently_active and self.last_metadata:
            status = self.last_metadata.get("status", "success")
            planes_filtered = self.last_metadata.get("planes_filtered", 0)
            color = "blue" if status == "success" else "orange"
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="planes_filtered",
                    value=planes_filtered,
                    color=color,
                ),
            )

        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="processing",
                value=False,
                color="gray",
            ),
        )
