import open3d as o3d
import numpy as np
from typing import Dict, Any
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

def create_pipeline():
    """Pipeline with custom stats and segmentation"""
    return (PipelineBuilder()
            .crop(min_bound=[-10, -10, -2], max_bound=[10, 10, 3])
            .downsample(voxel_size=0.05)
            .add_custom(CustomStatisticsOperation())
            .segment_plane(distance_threshold=0.1)
            .cluster(eps=0.2, min_points=10)
            .build())
