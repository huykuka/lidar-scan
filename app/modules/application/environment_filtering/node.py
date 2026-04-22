"""
EnvironmentFilteringNode — Application-level DAG node for floor/ceiling removal.

Receives a point cloud payload from upstream DAG nodes, applies voxel downsampling
(optional), detects planar patches using PatchPlaneSegmentation, validates each
plane against orientation/position/size criteria, and removes floor/ceiling points
from the ORIGINAL full-resolution cloud.

Architecture:
  - Heavy CPU-bound logic (_sync_filter) runs in asyncio.to_thread() (threadpool)
  - Downsampled cloud is temporary; released after segmentation
  - Output is always at original cloud resolution
  - All parameters validated at construction (ValueError on bad inputs)

References:
  - technical.md § 4, 5 (class design and algorithm)
  - api-spec.md § 5 (metadata contract)
  - requirements.md (acceptance criteria)
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import open3d as o3d

from app.core.logging import get_logger
from app.modules.pipeline.operations.patch_plane_segmentation.node import (
    PatchPlaneSegmentation,
)
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)


@dataclass
class PlaneInfo:
    """Metadata for a validated floor/ceiling plane."""

    plane_id: int
    plane_type: str  # "floor" | "ceiling"
    normal: List[float]
    centroid_z: float
    area: float
    point_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plane_id": self.plane_id,
            "plane_type": self.plane_type,
            "normal": self.normal,
            "centroid_z": self.centroid_z,
            "area": self.area,
            "point_count": self.point_count,
        }


class EnvironmentFilteringNode(ModuleNode):
    """
    Removes floor and ceiling planes from real-time indoor LiDAR scans.

    Processing pipeline (all heavy ops run in threadpool):
    1. Voxel downsampling (optional, configurable via voxel_downsample_size)
    2. Planar patch detection on downsampled cloud (PatchPlaneSegmentation)
    3. Per-plane validation: orientation + position + size (AND logic)
    4. Index mapping back to original cloud (KD-tree nearest-neighbor)
    5. Point removal: select_by_index on original full-resolution cloud

    Output is ALWAYS at original cloud resolution — downsampled cloud is temporary.

    For dense point clouds (100k+ points), automatic voxel downsampling improves
    performance while maintaining filtering accuracy. Disable (voxel_downsample_size=0)
    for high-precision requirements.
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

        # ── Plane detection parameters (PatchPlaneSegmentation) ────────────
        self._op = PatchPlaneSegmentation(
            normal_variance_threshold_deg=float(config.get("normal_variance_threshold_deg", 60.0)),
            coplanarity_deg=float(config.get("coplanarity_deg", 75.0)),
            outlier_ratio=float(config.get("outlier_ratio", 0.75)),
            min_plane_edge_length=float(config.get("min_plane_edge_length", 0.0)),
            min_num_points=int(config.get("min_num_points", 0)),
            knn=int(config.get("knn", 30)),
        )

        # ── Validation parameters ──────────────────────────────────────────
        self.vertical_tolerance_deg: float = float(config.get("vertical_tolerance_deg", 15.0))
        self.floor_height_range: Tuple[float, float] = (
            float(config.get("floor_height_min", -0.5)),
            float(config.get("floor_height_max", 0.5)),
        )
        self.ceiling_height_range: Tuple[float, float] = (
            float(config.get("ceiling_height_min", 2.0)),
            float(config.get("ceiling_height_max", 4.0)),
        )
        self.min_plane_area: float = float(config.get("min_plane_area", 1.0))

        # ── Validate all params at construction time ───────────────────────
        self._validate_params()

        # ── Runtime state ──────────────────────────────────────────────────
        self.input_count: int = 0
        self.last_input_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.last_metadata: Dict[str, Any] = {}
        self.processing_time_ms: float = 0.0
        self._processing: bool = False

    # ── Parameter validation ──────────────────────────────────────────────────

    def _validate_params(self) -> None:
        """Validate all parameters at construction. Raise ValueError on invalid ranges."""
        if not (0.0 <= self.voxel_downsample_size <= 1.0):
            raise ValueError(
                "voxel_downsample_size must be between 0.0 and 1.0 meters"
            )
        if not (1 <= self.vertical_tolerance_deg <= 45):
            raise ValueError(
                "vertical_tolerance_deg must be between 1 and 45 degrees"
            )
        if self.min_plane_area < 0.1:
            raise ValueError("min_plane_area must be >= 0.1 square meters")
        if self.floor_height_range[0] >= self.floor_height_range[1]:
            raise ValueError("floor_height_range must have max > min")
        if self.ceiling_height_range[0] >= self.ceiling_height_range[1]:
            raise ValueError("ceiling_height_range must have max > min")

    # ── Downsampling ──────────────────────────────────────────────────────────

    def _voxel_downsample(
        self, pcd_tensor: o3d.t.geometry.PointCloud
    ) -> Tuple[o3d.t.geometry.PointCloud, Dict[str, Any]]:
        """
        Apply voxel downsampling to input cloud.

        Returns (pcd_ds, downsample_meta). If voxel_downsample_size <= 0,
        returns the same object reference (no copy) with disabled meta.
        """
        n_orig = len(pcd_tensor.point["positions"])

        if self.voxel_downsample_size <= 0:
            return pcd_tensor, {
                "downsampling_enabled": False,
                "voxel_size": 0.0,
                "points_before_downsample": n_orig,
                "points_after_downsample": n_orig,
            }

        # Convert to legacy for voxel_down_sample (returns legacy)
        pcd_legacy = pcd_tensor.to_legacy()
        pcd_ds_legacy = pcd_legacy.voxel_down_sample(self.voxel_downsample_size)
        n_ds = len(np.asarray(pcd_ds_legacy.points))

        if n_ds < 100:
            logger.warning(
                f"[{self.id}] Voxel size {self.voxel_downsample_size}m too large — "
                f"downsampling reduced cloud to {n_ds} points. "
                "Consider reducing voxel_downsample_size."
            )

        pcd_ds = o3d.t.geometry.PointCloud.from_legacy(pcd_ds_legacy)
        meta = {
            "downsampling_enabled": True,
            "voxel_size": self.voxel_downsample_size,
            "points_before_downsample": n_orig,
            "points_after_downsample": n_ds,
        }
        return pcd_ds, meta

    # ── Plane detection ───────────────────────────────────────────────────────

    def _apply_with_boxes(
        self, legacy_pcd: o3d.geometry.PointCloud
    ) -> Tuple[List[Any], np.ndarray, np.ndarray]:
        """
        Detect planar patches using PatchPlaneSegmentation.

        Returns (oboxes, labels, points_np):
          - oboxes: list of OrientedBoundingBox
          - labels: (N,) int32 array; plane index per point, -1 = unassigned
          - points_np: (N, 3) float64 XYZ of the input cloud
        """
        count = len(legacy_pcd.points)
        points_np = np.asarray(legacy_pcd.points, dtype=np.float64)

        if count == 0:
            return [], np.array([], dtype=np.int32), points_np

        # Ensure normals exist for detect_planar_patches
        if not legacy_pcd.has_normals():
            legacy_pcd.estimate_normals(
                search_param=o3d.geometry.KDTreeSearchParamKNN(knn=self._op.knn)
            )

        oboxes = legacy_pcd.detect_planar_patches(
            normal_variance_threshold_deg=self._op.normal_variance_threshold_deg,
            coplanarity_deg=self._op.coplanarity_deg,
            outlier_ratio=self._op.outlier_ratio,
            min_plane_edge_length=self._op.min_plane_edge_length,
            min_num_points=self._op.min_num_points,
            search_param=o3d.geometry.KDTreeSearchParamKNN(knn=self._op.knn),
        )

        if not oboxes:
            return [], np.full(count, -1, dtype=np.int32), points_np

        # Assign each point to a plane via OBB containment
        labels = np.full(count, -1, dtype=np.int32)
        pts_vec = o3d.utility.Vector3dVector(points_np)
        for i, obox in enumerate(oboxes):
            indices = obox.get_point_indices_within_bounding_box(pts_vec)
            if indices:
                labels[np.array(indices, dtype=np.int64)] = i

        return oboxes, labels, points_np

    # ── Plane classification ──────────────────────────────────────────────────

    def _classify_plane(
        self,
        obox: Any,
        labels: np.ndarray,
        points_np: np.ndarray,
        plane_idx: int,
    ) -> Optional[PlaneInfo]:
        """
        Validate a plane against orientation, position, and size criteria (AND logic).

        Returns PlaneInfo if all checks pass, None otherwise.
        """
        # 1. Orientation — normal vector must be approximately vertical
        normal = obox.R[:, 2]
        normal = normal / (np.linalg.norm(normal) + 1e-9)
        cos_angle = abs(np.dot(normal, np.array([0.0, 0.0, 1.0])))
        # Clamp to [-1, 1] to avoid acos domain errors
        cos_angle = np.clip(cos_angle, 0.0, 1.0)
        angle_deg = np.degrees(np.arccos(cos_angle))
        if angle_deg > self.vertical_tolerance_deg:
            return None

        # 2. Position — centroid Z must be in floor OR ceiling range
        centroid_z = float(obox.center[2])
        is_floor = self.floor_height_range[0] <= centroid_z <= self.floor_height_range[1]
        is_ceiling = self.ceiling_height_range[0] <= centroid_z <= self.ceiling_height_range[1]
        if not (is_floor or is_ceiling):
            return None
        plane_type = "floor" if is_floor else "ceiling"

        # 3. Size — OBB footprint area must meet minimum
        area = float(obox.extent[0]) * float(obox.extent[1])
        if area < self.min_plane_area:
            return None

        # Collect per-plane stats
        plane_mask = labels == plane_idx
        point_count = int(np.sum(plane_mask))

        return PlaneInfo(
            plane_id=plane_idx,
            plane_type=plane_type,
            normal=normal.tolist(),
            centroid_z=centroid_z,
            area=area,
            point_count=point_count,
        )

    # ── Index mapping (downsampled → original) ────────────────────────────────

    def _map_indices_to_original(
        self,
        plane_pts_ds: np.ndarray,
        original_points: np.ndarray,
        radius: float,
    ) -> np.ndarray:
        """
        Map downsampled plane points to original cloud indices via KD-tree.

        For each original point, checks if any downsampled plane point is within
        'radius'. Returns boolean mask of length N_orig.

        Args:
            plane_pts_ds: (M, 3) float64 — downsampled plane point positions
            original_points: (N, 3) float64 — original cloud positions
            radius: search radius (voxel_downsample_size / 2)

        Returns:
            Boolean mask of shape (N,), True = belongs to this plane
        """
        if len(plane_pts_ds) == 0:
            return np.zeros(len(original_points), dtype=bool)

        pcd_plane = o3d.geometry.PointCloud()
        pcd_plane.points = o3d.utility.Vector3dVector(plane_pts_ds)
        tree = o3d.geometry.KDTreeFlann(pcd_plane)

        mask = np.zeros(len(original_points), dtype=bool)
        for i, pt in enumerate(original_points):
            k, _, _ = tree.search_radius_vector_3d(pt, radius)
            if k > 0:
                mask[i] = True
        return mask

    # ── Core filtering (CPU-bound, runs in threadpool) ────────────────────────

    def _sync_filter(
        self, pcd_in: o3d.t.geometry.PointCloud
    ) -> Tuple[o3d.t.geometry.PointCloud, Dict[str, Any]]:
        """
        Synchronous filter: detect and remove floor/ceiling planes.

        Always runs in asyncio.to_thread(). Returns (pcd_out, metadata).
        pcd_out is ALWAYS at original resolution.
        """
        n_orig = len(pcd_in.point["positions"])

        # ── Handle empty cloud ────────────────────────────────────────────
        if n_orig == 0:
            logger.warning(f"[{self.id}] Received empty point cloud, skipping filtering")
            ds_meta = {
                "downsampling_enabled": False,
                "voxel_size": 0.0,
                "points_before_downsample": 0,
                "points_after_downsample": 0,
            }
            return pcd_in, {
                **ds_meta,
                "input_point_count": 0,
                "output_point_count": 0,
                "removed_point_count": 0,
                "planes_detected": 0,
                "planes_filtered": 0,
                "plane_details": [],
                "status": "warning_pass_through",
            }

        # ── Step 1: Voxel downsampling ────────────────────────────────────
        pcd_ds, ds_meta = self._voxel_downsample(pcd_in)

        # If downsampling produced too few points, set status accordingly
        n_ds = ds_meta["points_after_downsample"]
        low_density_warning = ds_meta.get("downsampling_enabled") and n_ds < 100
        status_override = "warning_low_point_density" if low_density_warning else None

        # ── Step 2: Plane detection on downsampled cloud ──────────────────
        try:
            oboxes, labels_ds, pts_ds_np = self._apply_with_boxes(pcd_ds.to_legacy())
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
                "status": "no_planes_detected",
            }

        n_planes = len(oboxes)
        if n_planes == 0:
            logger.info(
                f"[{self.id}] No planar surfaces detected, passing through original cloud. "
                "Try reducing normal_variance_threshold_deg or min_plane_area "
                "if your scan has noisy or sparse floor/ceiling data."
            )
            return pcd_in, {
                **ds_meta,
                "input_point_count": n_orig,
                "output_point_count": n_orig,
                "removed_point_count": 0,
                "planes_detected": 0,
                "planes_filtered": 0,
                "plane_details": [],
                "status": status_override or "no_planes_detected",
            }

        # ── Step 3: Classify planes ───────────────────────────────────────
        validated_planes: List[PlaneInfo] = []
        for i in range(n_planes):
            plane_info = self._classify_plane(oboxes[i], labels_ds, pts_ds_np, i)
            if plane_info is not None:
                validated_planes.append(plane_info)

        if not validated_planes:
            logger.info(
                f"[{self.id}] Detected {n_planes} planes, but none matched "
                "floor/ceiling criteria"
            )
            return pcd_in, {
                **ds_meta,
                "input_point_count": n_orig,
                "output_point_count": n_orig,
                "removed_point_count": 0,
                "planes_detected": n_planes,
                "planes_filtered": 0,
                "plane_details": [],
                "status": status_override or "warning_pass_through",
            }

        # ── Step 4: Build removal mask ────────────────────────────────────
        if self.voxel_downsample_size > 0:
            # Map downsampled plane indices back to original cloud
            pts_orig_np = np.asarray(pcd_in.to_legacy().points, dtype=np.float64)
            removal_mask = np.zeros(len(pts_orig_np), dtype=bool)
            radius = self.voxel_downsample_size / 2.0
            for plane in validated_planes:
                plane_pts_ds = pts_ds_np[labels_ds == plane.plane_id]
                plane_mask = self._map_indices_to_original(plane_pts_ds, pts_orig_np, radius)
                removal_mask |= plane_mask
        else:
            # No downsampling: labels_ds indexes original cloud directly
            removal_mask = np.zeros(len(pts_ds_np), dtype=bool)
            for plane in validated_planes:
                removal_mask |= (labels_ds == plane.plane_id)

        # ── Step 5: Remove plane points from original cloud ───────────────
        keep_indices = np.where(~removal_mask)[0]
        pcd_out = pcd_in.select_by_index(keep_indices.tolist())

        n_removed = int(np.sum(removal_mask))
        n_out = n_orig - n_removed

        return pcd_out, {
            **ds_meta,
            "input_point_count": n_orig,
            "output_point_count": n_out,
            "removed_point_count": n_removed,
            "planes_detected": n_planes,
            "planes_filtered": len(validated_planes),
            "plane_details": [p.to_dict() for p in validated_planes],
            "status": status_override or "success",
        }

    # ── Async data flow ───────────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """Receive point cloud payload, filter, and forward downstream."""
        from app.modules.pipeline.base import PointConverter  # noqa: PLC0415 (lazy import)

        self.last_input_at = time.time()
        start_t = self.last_input_at
        first_frame = self.input_count == 0
        self.input_count += 1

        # Skip-if-busy guard
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

        # Warning states (orange)
        if recently_active and self.last_metadata:
            status = self.last_metadata.get("status", "success")
            planes_filtered = self.last_metadata.get("planes_filtered", 0)

            if status != "success":
                return NodeStatusUpdate(
                    node_id=self.id,
                    operational_state=OperationalState.RUNNING,
                    application_state=ApplicationState(
                        label="planes_filtered",
                        value=planes_filtered,
                        color="orange",
                    ),
                )

            # Success with planes filtered (blue)
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="planes_filtered",
                    value=planes_filtered,
                    color="blue",
                ),
            )

        # Idle (gray)
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="processing",
                value=False,
                color="gray",
            ),
        )
