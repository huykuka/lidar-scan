import pytest
import numpy as np
import open3d as o3d
from app.modules.pipeline.operations.downsample import Downsample, UniformDownsample

def test_downsample_legacy():
    pcd = o3d.geometry.PointCloud()
    # 100 random points in [0, 1]
    points = np.random.rand(100, 3) 
    pcd.points = o3d.utility.Vector3dVector(points)
    
    op = Downsample(voxel_size=0.5)
    res_pcd, meta = op.apply(pcd)
    
    # Just ensure it runs and reduces points
    assert meta["downsampled_count"] > 0
    assert meta["downsampled_count"] <= 100

def test_uniform_downsample_legacy():
    pcd = o3d.geometry.PointCloud()
    points = np.random.rand(10, 3) 
    pcd.points = o3d.utility.Vector3dVector(points)
    
    op = UniformDownsample(every_k_points=2)
    res_pcd, meta = op.apply(pcd)
    
    assert meta["downsampled_count"] == 5
