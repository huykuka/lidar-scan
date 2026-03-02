from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation, _tensor_map_keys

class Downsample(PipelineOperation):
    """
    Downsamples the point cloud using a voxel grid filter.
    
    Args:
        voxel_size (float): The size of the voxel to use for downsampling. 
                           Values <= 0 will bypass downsampling.
    """

    def __init__(self, voxel_size: float):
        self.voxel_size = voxel_size

    def apply(self, pcd: Any):
        if self.voxel_size > 0:
            pcd = pcd.voxel_down_sample(voxel_size=self.voxel_size)
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)
        return pcd, {"downsampled_count": count}

class UniformDownsample(PipelineOperation):
    """
    Downsamples the point cloud by collecting every n-th point.
    
    Args:
        every_k_points (int): The interval at which points are collected (e.g., every 5th point).
    """

    def __init__(self, every_k_points: int = 5):
        self.every_k_points = every_k_points

    def apply(self, pcd: Any):
        if self.every_k_points > 1:
            pcd = pcd.uniform_down_sample(every_k_points=self.every_k_points)
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)
        return pcd, {"downsampled_count": count}

