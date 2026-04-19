from typing import Any

import open3d as o3d

from ...base import PipelineOperation


class BoundaryDetection(PipelineOperation):
    """
    Detects boundary points in the point cloud.
    
    Args:
        radius (float): Radius for neighbor search.
        max_nn (int): Maximum number of neighbors to consider.
        angle_threshold (float): Angle threshold (in degrees) for boundary detection.
    """

    def __init__(self, radius: float = 0.02, max_nn: int = 30, angle_threshold: float = 90.0):
        self.radius = float(radius)
        self.max_nn = int(max_nn)
        self.angle_threshold = float(angle_threshold)

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            # Boundary detection requires normals
            if 'normals' not in pcd.point:
                pcd.estimate_normals(max_nn=self.max_nn, radius=self.radius)

            boundary_pcd, mask = pcd.compute_boundary_points(self.radius, self.max_nn, self.angle_threshold)

            count = boundary_pcd.point.positions.shape[0] if 'positions' in boundary_pcd.point else 0
            original_count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0

            return boundary_pcd, {
                "boundary_count": int(count),
                "original_count": int(original_count)
            }
        else:
            # Fallback for Legacy API
            pcd_tensor = o3d.t.geometry.PointCloud.from_legacy(pcd)
            if 'normals' not in pcd_tensor.point:
                pcd_tensor.estimate_normals(max_nn=self.max_nn, radius=self.radius)

            boundary_pcd, mask = pcd_tensor.compute_boundary_points(self.radius, self.max_nn, self.angle_threshold)
            pcd_legacy = boundary_pcd.to_legacy()

            return pcd_legacy, {
                "boundary_count": len(pcd_legacy.points),
                "original_count": len(pcd.points)
            }
