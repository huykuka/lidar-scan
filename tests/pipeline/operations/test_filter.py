import pytest
import numpy as np
import open3d as o3d
from app.pipeline.operations.filter import Filter, FilterByKey

def test_filter_legacy():
    pcd = o3d.geometry.PointCloud()
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0]
    ])
    pcd.points = o3d.utility.Vector3dVector(points)
    
    # Filter by x value > 0.5
    op = Filter(filter_fn=lambda p: np.asarray(p.points)[:, 0] > 0.5)
    res_pcd, meta = op.apply(pcd)
    
    assert meta["filtered_count"] == 1

def test_filter_by_key_legacy():
    pcd = o3d.geometry.PointCloud()
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0]
    ])
    pcd.points = o3d.utility.Vector3dVector(points)
    # Using 'colors' as intensity in legacy
    colors = np.array([
        [0.1, 0.0, 0.0],
        [0.8, 0.0, 0.0]
    ])
    pcd.colors = o3d.utility.Vector3dVector(colors)
    
    op = FilterByKey(key="intensity", value=lambda c: c[:,0] > 0.5)
    res_pcd, meta = op.apply(pcd)
    
    assert meta["filtered_count"] == 1
