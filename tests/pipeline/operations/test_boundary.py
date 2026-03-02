import pytest
import numpy as np
import open3d as o3d
from app.modules.pipeline.operations.boundary import BoundaryDetection

def test_boundary_detection_legacy():
    pcd = o3d.geometry.PointCloud()
    points = np.random.rand(100, 3)
    pcd.points = o3d.utility.Vector3dVector(points)
    
    op = BoundaryDetection(radius=0.2, max_nn=30, angle_threshold=90.0)
    res_pcd, meta = op.apply(pcd)
    
    assert "boundary_count" in meta
    assert "original_count" in meta
