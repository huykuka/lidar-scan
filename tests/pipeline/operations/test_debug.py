import pytest
import numpy as np
import open3d as o3d
import os
from app.pipeline.operations.debug import DebugSave, SaveDataStructure

def test_debug_save_legacy(tmp_path):
    pcd = o3d.geometry.PointCloud()
    points = np.random.rand(10, 3)
    pcd.points = o3d.utility.Vector3dVector(points)
    
    out_dir = str(tmp_path / "debug_output")
    op = DebugSave(output_dir=out_dir, prefix="testpcd", max_keeps=2)
    
    op.apply(pcd)
    op.apply(pcd)
    res_pcd, meta = op.apply(pcd)
    
    assert "debug_file" in meta
    assert os.path.exists(meta["debug_file"])
    # should only keep 2 files
    files = os.listdir(out_dir)
    assert len(files) == 2

def test_save_structure_legacy(tmp_path):
    pcd = o3d.geometry.PointCloud()
    points = np.random.rand(10, 3)
    pcd.points = o3d.utility.Vector3dVector(points)
    
    out_file = str(tmp_path / "structure.json")
    op = SaveDataStructure(output_file=out_file)
    res_pcd, meta = op.apply(pcd)
    
    assert "structure_file" in meta
    assert os.path.exists(out_file)
