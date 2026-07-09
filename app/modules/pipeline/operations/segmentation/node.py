from typing import Any, Optional
import open3d as o3d
import numpy as np
from scipy.spatial import ConvexHull, QhullError
from ...base import PipelineOperation

class PlaneSegmentation(PipelineOperation):
    """
    Segments a plane from the point cloud using RANSAC.
    
    Args:
        distance_threshold (float): Max distance a point can be from the plane to be considered an inlier.
        ransac_n (int): Number of points sampled to estimate the plane.
        num_iterations (int): Maximum number of iterations for RANSAC.
    """

    def __init__(
        self,
        distance_threshold: float = 0.1,
        ransac_n: int = 3,
        num_iterations: int = 1000,
        invert: bool = False,
        min_area: float = 0.0,
        max_area: float = 0.0,
    ):
        self.distance_threshold = float(distance_threshold)
        self.ransac_n = int(ransac_n)
        self.num_iterations = int(num_iterations)
        self.invert = bool(invert)
        self.min_area = float(min_area)
        self.max_area = float(max_area)

    @staticmethod
    def _compute_plane_area(points_3d: np.ndarray, normal: np.ndarray) -> float:
        """Project *points_3d* onto the plane and return the 2-D convex-hull area."""
        if len(points_3d) < 3:
            return 0.0
        # Build an orthonormal basis on the plane
        n = normal / np.linalg.norm(normal)
        ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = np.cross(n, ref)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        # Project to 2-D
        centered = points_3d - points_3d.mean(axis=0)
        uv = np.column_stack([centered @ u, centered @ v])
        try:
            return float(ConvexHull(uv).volume)  # 2-D "volume" == area
        except QhullError:
            return 0.0

    def _area_ok(self, area: float) -> bool:
        """Return *True* when *area* satisfies the configured thresholds."""
        if self.min_area > 0 and area < self.min_area:
            return False
        if self.max_area > 0 and area > self.max_area:
            return False
        return True

    @staticmethod
    def _get_inlier_points(pcd: Any, inliers: Any) -> np.ndarray:
        """Extract inlier XYZ positions as a numpy array from tensor or legacy PCD."""
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            return pcd.select_by_index(inliers).point.positions.cpu().numpy()
        return np.asarray(pcd.select_by_index(inliers).points)

    @staticmethod
    def _plane_model_list(plane_model: Any, is_tensor: bool) -> list:
        """Normalise plane model to a plain Python list."""
        if is_tensor:
            return plane_model.cpu().numpy().tolist()
        return plane_model.tolist()

    def apply(self, pcd: Any):
        is_tensor = isinstance(pcd, o3d.t.geometry.PointCloud)
        count = (
            pcd.point.positions.shape[0] if (is_tensor and 'positions' in pcd.point)
            else len(pcd.points)
        )

        has_area_filter = self.min_area > 0 or self.max_area > 0

        if count < self.ransac_n:
            return pcd, {}

        plane_model_raw, inliers = pcd.segment_plane(
            distance_threshold=self.distance_threshold,
            ransac_n=self.ransac_n,
            num_iterations=self.num_iterations,
            probability=0.9999,
        )
        plane_model_list = self._plane_model_list(plane_model_raw, is_tensor)

        area: Optional[float] = None
        if has_area_filter:
            inlier_pts = self._get_inlier_points(pcd, inliers)
            normal = np.array(plane_model_list[:3])
            area = self._compute_plane_area(inlier_pts, normal)
            if not self._area_ok(area):
                return pcd, {
                    "plane_model": plane_model_list,
                    "inlier_count": len(inliers),
                    "inverted": self.invert,
                    "area": area,
                    "area_rejected": True,
                }

        pcd = pcd.select_by_index(inliers, invert=self.invert)
        meta = {
            "plane_model": plane_model_list,
            "inlier_count": len(inliers),
            "inverted": self.invert,
        }
        if area is not None:
            meta["area"] = area
            meta["area_rejected"] = False
        return pcd, meta


