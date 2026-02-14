import os
from typing import Dict, Any

import numpy as np
import open3d as o3d

from ..base import PipelineOperation
from ..operations import PipelineBuilder


class CustomStatisticsOperation(PipelineOperation):
    """Example of a custom operation that calculates point cloud statistics"""

    def apply(self, pcd: Any) -> Dict[str, Any]:
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            points = pcd.point.positions.cpu().numpy()
        else:
            points = np.asarray(pcd.points)
        if len(points) == 0:
            return {"stats": "empty"}

        center = np.mean(points, axis=0)
        return {
            "custom_stats": {
                "center": center.tolist()
            }
        }


def create_pipeline(lidar_id: str = "default"):
    """Pipeline with custom stats and segmentation"""
    return (PipelineBuilder()
            .downsample(voxel_size=0.15)
            .remove_outliers(nb_neighbors=5,std_ratio=2.0)
            .remove_radius_outliers(nb_points=3, radius=0.5)
            .build())
