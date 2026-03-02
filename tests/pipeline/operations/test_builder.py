import pytest
import numpy as np
import open3d as o3d
from app.modules.pipeline.operations.builder import PipelineBuilder

def test_pipeline_builder_legacy():
    builder = PipelineBuilder(use_tensor=False)
    pipeline = (builder
                .downsample(voxel_size=0.1)
                .crop(min_bound=[-1, -1, -1], max_bound=[1, 1, 1])
                .build())
    
    pcd = o3d.geometry.PointCloud()
    points = np.array([
        [0.0, 0.0, 0.0],
        [2.0, 2.0, 2.0]
    ])
    pcd.points = o3d.utility.Vector3dVector(points)
    
    from app.modules.pipeline.base import LegacyPointCloudPipeline
    assert isinstance(pipeline, LegacyPointCloudPipeline)
