import pytest
import numpy as np
import open3d as o3d
from app.pipeline.operations.crop import Crop

def test_crop_legacy():
    pcd = o3d.geometry.PointCloud()
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        [5.0, 5.0, 5.0]
    ])
    pcd.points = o3d.utility.Vector3dVector(points)
    
    op = Crop(min_bound=[-1, -1, -1], max_bound=[2, 2, 2])
    res_pcd, meta = op.apply(pcd)
    
    assert meta["cropped_count"] == 2
