import os
from typing import Any

import numpy as np
import open3d as o3d

from ..base import PipelineOperation
from ..operations import PipelineBuilder


class CustomStatisticsOperation(PipelineOperation):
    """Example of a custom operation that calculates point cloud statistics"""

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            points = pcd.point.positions.cpu().numpy()
        else:
            points = np.asarray(pcd.points)
        if len(points) == 0:
            return pcd, {"stats": "empty"}

        center = np.mean(points, axis=0)
        return pcd, {
            "custom_stats": {
                "center": center.tolist()
            }
        }


class CreatePointPlane(PipelineOperation):
    """
    Generates a synthetic point cloud plane.
    Useful for validating the PlaneSegmentation algorithm with perfect or controlled noisy data.
    """

    def __init__(self, size: float = 10.0, resolution: float = 0.1, noise: float = 0.01):
        self.size = size
        self.resolution = resolution
        self.noise = noise

    def apply(self, pcd: Any):
        ticks = np.arange(-self.size / 2, self.size / 2, self.resolution)
        xx, yy = np.meshgrid(ticks, ticks)
        zz = np.random.normal(0, self.noise, xx.size)
        points = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=1).astype(np.float32)

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            # With the new Return style, we can just create a new PCD and return it!
            new_pcd = o3d.t.geometry.PointCloud(pcd.device)
            new_pcd.point.positions = o3d.core.Tensor(points, device=pcd.device)
            return new_pcd, {
                "plane_generated": {
                    "count": len(points),
                    "size": self.size
                }
            }
        else:
            pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
            return pcd, {
                "plane_generated": {
                    "count": len(points),
                    "size": self.size
                }
            }


def create_pipeline(lidar_id: str = "default"):
    """Pipeline with custom stats and segmentation"""
    debug_dir = os.path.join("debug_data", lidar_id)
    return (PipelineBuilder()
            # .filter(
            #     reflector=1,                   # Match specific value
            #     intensity=('>', 30000),        # Use picklable comparison tuple
            # )          
            .downsample(voxel_size=0.01)
            .remove_outliers(nb_neighbors=20, std_ratio=2.0)
            .segment_plane(distance_threshold=0.03)
            .add_custom(CreatePointPlane(size=1.0, resolution=0.1, noise=0.01))
            .downsample(voxel_size=0.05)
            .debug_save(output_dir=debug_dir, prefix="advanced", max_keeps=10)
            .save_structure(output_file=os.path.join(debug_dir, "data_structure.json"))
            .build())
