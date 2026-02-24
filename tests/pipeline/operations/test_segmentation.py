import pytest
import numpy as np
import open3d as o3d
from app.pipeline.operations.segmentation import PlaneSegmentation

def test_plane_segmentation_legacy():
    pcd = o3d.geometry.PointCloud()
    # Create points on a plane z=0
    x = np.random.rand(100)
    y = np.random.rand(100)
    z = np.zeros(100)
    points = np.column_stack((x, y, z))
    
    # Add noise
    noise = np.random.rand(10, 3)
    points = np.vstack((points, noise))
    pcd.points = o3d.utility.Vector3dVector(points)
    
    op = PlaneSegmentation(distance_threshold=0.01, ransac_n=3, num_iterations=100)
    res_pcd, meta = op.apply(pcd)
    
    assert meta["inlier_count"] >= 100
    assert "plane_model" in meta
