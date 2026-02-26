from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation, _tensor_map_keys

class PlaneSegmentation(PipelineOperation):
    """
    Segments a plane from the point cloud using RANSAC.
    
    Args:
        distance_threshold (float): Max distance a point can be from the plane to be considered an inlier.
        ransac_n (int): Number of points sampled to estimate the plane.
        num_iterations (int): Maximum number of iterations for RANSAC.
    """

    def __init__(self, distance_threshold: float = 0.1, ransac_n: int = 3, num_iterations: int = 1000):
        self.distance_threshold = distance_threshold
        self.ransac_n = ransac_n
        self.num_iterations = num_iterations

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)

        if count >= self.ransac_n:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                plane_model, inliers = pcd.segment_plane(
                    distance_threshold=self.distance_threshold,
                    ransac_n=self.ransac_n,
                    num_iterations=self.num_iterations,
                    probability=0.9999
                )
                pcd = pcd.select_by_index(inliers)

                return pcd, {
                    "plane_model": plane_model.cpu().numpy().tolist(),
                    "inlier_count": len(inliers)
                }
            else:
                plane_model, inliers = pcd.segment_plane(
                    distance_threshold=self.distance_threshold,
                    ransac_n=self.ransac_n,
                    num_iterations=self.num_iterations,
                    probability=0.9999
                )
                pcd = pcd.select_by_index(inliers)

                return pcd, {
                    "plane_model": plane_model.tolist(),
                    "inlier_count": len(inliers)
                }
        return pcd, {}

