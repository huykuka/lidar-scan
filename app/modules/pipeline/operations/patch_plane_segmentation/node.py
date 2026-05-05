from typing import Any

import numpy as np
import open3d as o3d

from ...base import PipelineOperation


class PatchPlaneSegmentation(PipelineOperation):
    """
    Detects multiple planar patches using robust statistics-based approach.

    Uses octree subdivision and robust planarity tests (normal variance + coplanarity)
    to find, grow, and merge planar patches. Points belonging to detected patches are
    colored by patch membership; non-patch points are discarded (similar to DBSCAN
    noise removal).

    Args:
        normal_variance_threshold_deg (float): Max spread of point normals vs fitted
            plane normal. Smaller = fewer, higher-quality planes.
        coplanarity_deg (float): Max spread of point-to-plane distances. Larger =
            tighter distribution around the fitted plane.
        outlier_ratio (float): Max fraction of outliers before a fitted plane is rejected.
        min_plane_edge_length (float): Minimum largest-edge length for a patch.
            0 defaults to 1% of the point cloud's largest dimension.
        min_num_points (int): Minimum points when fitting a plane / octree depth control.
            0 defaults to 0.1% of the total point count.
        max_nn (int): Maximum nearest neighbours within search_radius used when
            growing/merging planes. Larger = higher quality patches but slower.
        search_radius (float): KDTree hybrid search radius in metres. Only neighbours
            within this distance AND up to max_nn count are used.
    """

    def __init__(
        self,
        normal_variance_threshold_deg: float = 60.0,
        coplanarity_deg: float = 75.0,
        outlier_ratio: float = 0.75,
        min_plane_edge_length: float = 0.0,
        min_num_points: int = 0,
        max_nn: int = 30,
        search_radius: float = 0.1,
        invert: bool = False,
    ):
        self.normal_variance_threshold_deg = float(normal_variance_threshold_deg)
        self.coplanarity_deg = float(coplanarity_deg)
        self.outlier_ratio = float(outlier_ratio)
        self.min_plane_edge_length = float(min_plane_edge_length)
        self.min_num_points = int(min_num_points)
        self.max_nn = int(max_nn)
        self.search_radius = float(search_radius)
        self.invert = bool(invert)

    def apply(self, pcd: Any):
        is_tensor = isinstance(pcd, o3d.t.geometry.PointCloud)

        # detect_planar_patches only exists on legacy geometry
        if is_tensor:
            legacy_pcd = pcd.to_legacy()
        else:
            legacy_pcd = pcd

        count = len(legacy_pcd.points)
        if count == 0:
            return pcd, {"plane_count": 0, "inlier_count": 0, "original_count": 0}

        if not legacy_pcd.has_normals():
            legacy_pcd.estimate_normals(
                search_param=o3d.geometry.KDTreeSearchParamHybrid(
                    radius=self.search_radius, max_nn=self.max_nn
                )
            )

        oboxes = legacy_pcd.detect_planar_patches(
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
            return pcd, {"plane_count": 0, "inlier_count": 0, "original_count": count}

        # Assign each point to a patch via the oriented bounding boxes.
        # Points may fall in multiple boxes — last patch wins (same as clustering).
        points = np.asarray(legacy_pcd.points)
        labels = np.full(count, -1, dtype=np.int32)

        for i, obox in enumerate(oboxes):
            indices = obox.get_point_indices_within_bounding_box(
                o3d.utility.Vector3dVector(points)
            )
            labels[np.array(indices, dtype=np.int64)] = i

        # Keep only points belonging to a patch (label >= 0), like DBSCAN noise removal
        inlier_mask = labels >= 0
        if self.invert:
            selected_indices = np.where(~inlier_mask)[0]
        else:
            selected_indices = np.where(inlier_mask)[0]

        result = legacy_pcd.select_by_index(selected_indices.tolist())

        if not self.invert:
            # Color by patch membership using deterministic palette
            rng = np.random.default_rng(42)
            palette = rng.random((len(oboxes), 3))
            inlier_colors = palette[labels[inlier_mask]]
            result.colors = o3d.utility.Vector3dVector(inlier_colors)

        if is_tensor:
            result = o3d.t.geometry.PointCloud.from_legacy(result)

        return result, {
            "plane_count": len(oboxes),
            "inlier_count": int(np.sum(inlier_mask)),
            "original_count": count,
        }
