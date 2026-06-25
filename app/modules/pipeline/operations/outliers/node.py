from typing import Any, Optional, Tuple

import numpy as np
import open3d as o3d

from ...base import PipelineOperation


class StatisticalOutlierRemoval(PipelineOperation):
    """
    Removes points that are further away from their neighbors compared to the average for the point cloud.
    
    Args:
        nb_neighbors (int): Number of neighbors to consider for each point.
        std_ratio (float): Standard deviation ratio. Lower values are more aggressive.
    """

    PREFERS_LEGACY = True

    def __init__(self, nb_neighbors: int = 20, std_ratio: float = 2.0):
        self.nb_neighbors = int(nb_neighbors)
        self.std_ratio = float(std_ratio)

    def apply_filter(self, pcd: o3d.geometry.PointCloud) -> Tuple[Optional[np.ndarray], dict]:
        """Index-based fast path: returns (inlier_indices, metadata).

        Called by OperationNode._sync_compute when PREFERS_LEGACY is True.
        The caller uses the indices to select rows from the original numpy
        array, preserving all 14 channels without any Tensor conversion.
        """
        count = len(pcd.points)
        if count > 0:
            _, indices = pcd.remove_statistical_outlier(
                nb_neighbors=self.nb_neighbors,
                std_ratio=self.std_ratio
            )
            return np.asarray(indices, dtype=np.intp), {"filtered_count": len(indices)}
        return None, {"filtered_count": 0}

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)

        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                pcd_legacy = pcd.to_legacy()
                pcd_filtered, _ = pcd_legacy.remove_statistical_outlier(
                    nb_neighbors=self.nb_neighbors,
                    std_ratio=self.std_ratio
                )
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
    """

    PREFERS_LEGACY = True

    def __init__(self, nb_points: int = 16, radius: float = 0.05):
        self.nb_points = int(nb_points)
        self.radius = float(radius)

    def apply_filter(self, pcd: o3d.geometry.PointCloud) -> Tuple[Optional[np.ndarray], dict]:
        """Index-based fast path — see StatisticalOutlierRemoval.apply_filter."""
        count = len(pcd.points)
        if count > 0:
            _, indices = pcd.remove_radius_outlier(
                nb_points=self.nb_points,
                radius=self.radius
            )
            return np.asarray(indices, dtype=np.intp), {"filtered_count": len(indices)}
        return None, {"filtered_count": 0}

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)

        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
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
