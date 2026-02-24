from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation, PointCloudPipeline, _tensor_map_keys

class StatisticalOutlierRemoval(PipelineOperation):
    """
    Removes points that are further away from their neighbors compared to the average for the point cloud.
    
    Args:
        nb_neighbors (int): Number of neighbors to consider for each point.
        std_ratio (float): Standard deviation ratio. Lower values are more aggressive.
        
    Note: Tensor API implementation currently falls back to legacy API.
    """

    def __init__(self, nb_neighbors: int = 20, std_ratio: float = 2.0):
        self.nb_neighbors = nb_neighbors
        self.std_ratio = std_ratio

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)
            
        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                # Fallback to legacy
                pcd_legacy = pcd.to_legacy()
                pcd_filtered, _ = pcd_legacy.remove_statistical_outlier(
                    nb_neighbors=self.nb_neighbors,
                    std_ratio=self.std_ratio
                )
                # Re-box as Tensor
                pcd = o3d.t.geometry.PointCloud.from_legacy(pcd_filtered, device=pcd.device)
            else:
                pcd, _ = pcd.remove_statistical_outlier(
                    nb_neighbors=self.nb_neighbors,
                    std_ratio=self.std_ratio
                )

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            final_count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            final_count = len(pcd.points)
        return pcd, {"filtered_count": final_count}

class RadiusOutlierRemoval(PipelineOperation):
    """
    Removes points that have fewer than 'nb_points' in a sphere of a given 'radius'.
    
    Args:
        nb_points (int): Minimum number of points required within the radius.
        radius (float): Radius of the sphere to search for neighbors.
        
    Note: Tensor API implementation currently falls back to legacy API.
    """

    def __init__(self, nb_points: int = 16, radius: float = 0.05):
        self.nb_points = nb_points
        self.radius = radius

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)
            
        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                # Fallback to legacy
                pcd_legacy = pcd.to_legacy()
                pcd_filtered, _ = pcd_legacy.remove_radius_outlier(
                    nb_points=self.nb_points,
                    radius=self.radius
                )
                pcd = o3d.t.geometry.PointCloud.from_legacy(pcd_filtered, device=pcd.device)
            else:
                pcd, _ = pcd.remove_radius_outlier(
                    nb_points=self.nb_points,
                    radius=self.radius
                )
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            final_count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            final_count = len(pcd.points)
        return pcd, {"filtered_count": final_count}

class OutlierRemoval(StatisticalOutlierRemoval):
    """Legacy wrapper for StatisticalOutlierRemoval"""
    pass

