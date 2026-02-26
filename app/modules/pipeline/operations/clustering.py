from sqlalchemy import false
from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation, _tensor_map_keys

class Clustering(PipelineOperation):
    """
    Clusters points using the DBSCAN algorithm and removes outliers (noise).
    
    Args:
        eps (float): Distance to neighbors in a cluster.
        min_points (int): Minimum number of points required to form a cluster.
    """

    def __init__(self, eps: float = 0.2, min_points: int = 10):
        self.eps = eps
        self.min_points = min_points

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)

        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                labels = pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points, print_progress=False)
                mask = labels >= 0
                pcd = pcd.select_by_mask(mask)
                cluster_count = int(labels.max().item() + 1) if labels.shape[0] > 0 else 0
            else:
                labels = np.array(pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points))
                indices = np.where(labels >= 0)[0]
                pcd = pcd.select_by_index(indices)
                cluster_count = int(labels.max() + 1) if labels.size > 0 else 0
            return pcd, {"cluster_count": cluster_count}
        return pcd, {"cluster_count": 0}

