import pytest
import numpy as np
import open3d as o3d
from app.modules.pipeline.operations.outliers import StatisticalOutlierRemoval, RadiusOutlierRemoval

def test_statistical_outlier_removal_legacy():
    pcd = o3d.geometry.PointCloud()
    points = np.random.rand(50, 3)
    # Add an outlier
    points = np.vstack((points, [100.0, 100.0, 100.0]))
    pcd.points = o3d.utility.Vector3dVector(points)
    
    op = StatisticalOutlierRemoval(nb_neighbors=10, std_ratio=1.0)
    res_pcd, meta = op.apply(pcd)
    
    assert "filtered_count" in meta
    assert meta["filtered_count"] > 0
    assert meta["filtered_count"] < 51

def test_radius_outlier_removal_legacy():
    pcd = o3d.geometry.PointCloud()
    points = np.random.rand(50, 3)
    pcd.points = o3d.utility.Vector3dVector(points)
    
    op = RadiusOutlierRemoval(nb_points=5, radius=0.5)
    res_pcd, meta = op.apply(pcd)
    
    assert "filtered_count" in meta
