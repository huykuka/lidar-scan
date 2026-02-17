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
    debug_dir = os.path.join("debug_data", lidar_id)
    return (PipelineBuilder()
            .filter(
                reflector=1,                   # Match specific value
                intensity=('>', 40000),        # Use picklable comparison tuple
            )          
            # .debug_save(output_dir=debug_dir, prefix="advanced", max_keeps=10)
            # .save_structure(output_file=os.path.join(debug_dir, "data_structure.json"))
            .build())
