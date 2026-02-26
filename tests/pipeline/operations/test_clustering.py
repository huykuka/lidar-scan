import pytest
import numpy as np
import open3d as o3d
from app.modules.pipeline.operations.clustering import Clustering

def test_clustering_legacy():
    pcd = o3d.geometry.PointCloud()
    # Two clusters
    c1 = np.random.rand(20, 3) * 0.1
    c2 = np.random.rand(20, 3) * 0.1 + np.array([5.0, 5.0, 5.0])
    points = np.vstack((c1, c2))
    pcd.points = o3d.utility.Vector3dVector(points)
    
    op = Clustering(eps=0.5, min_points=5)
    res_pcd, meta = op.apply(pcd)
    
    assert meta["cluster_count"] > 0
