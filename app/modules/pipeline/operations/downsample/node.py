from typing import Any

import numpy as np
import open3d as o3d

from ...base import PipelineOperation


class Downsample(PipelineOperation):
    """
    Downsamples the point cloud using a voxel grid filter (Open3D).

    Voxel downsampling aggregates all points in each spatial voxel into a
    single representative point — non-trivial spatial binning that justifies
    the Open3D dependency.

    Args:
        voxel_size (float): Voxel edge length in metres. Values <= 0 bypass downsampling.
    """

    def __init__(self, voxel_size: float):
        self.voxel_size = float(voxel_size)

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
    Downsamples the point cloud by keeping every k-th point.

    NUMPY_ONLY: apply() receives and returns a raw (N, M) numpy array.
    No Open3D allocation, no thread hop — just a stride slice.

    Args:
        every_k_points (int): Keep one point for every k points (e.g. 5 → keep 20%).
    """

    NUMPY_ONLY = True

    def __init__(self, every_k_points: int = 5):
        self.every_k_points = max(1, int(every_k_points))

    def apply(self, pts: np.ndarray):
        out = pts[::self.every_k_points] if self.every_k_points > 1 else pts
        return out, {"downsampled_count": int(out.shape[0])}

