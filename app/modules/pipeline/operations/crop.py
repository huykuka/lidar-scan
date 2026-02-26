from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation

class Crop(PipelineOperation):
    """
    Crops the point cloud using an axis-aligned bounding box.
    
    Args:
        min_bound (List[float]): Minimum coordinates [x, y, z].
        max_bound (List[float]): Maximum coordinates [x, y, z].
    """

    def __init__(self, min_bound: List[float], max_bound: List[float]):
        self.min_bound = np.array(min_bound, dtype=np.float64)
        self.max_bound = np.array(max_bound, dtype=np.float64)

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            bbox = o3d.t.geometry.AxisAlignedBoundingBox(self.min_bound, self.max_bound)
            pcd = pcd.crop(bbox)
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
            return pcd, {"cropped_count": count}
        else:
            bbox = o3d.geometry.AxisAlignedBoundingBox(min_bound=self.min_bound, max_bound=self.max_bound)
            pcd = pcd.crop(bbox)
            return pcd, {"cropped_count": len(pcd.points)}

