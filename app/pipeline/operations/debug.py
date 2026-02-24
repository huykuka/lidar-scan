from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation, PointCloudPipeline, _tensor_map_keys

class DebugSave(PipelineOperation):
    """
    Saves the current state of the point cloud to a PCD file for debugging.
    
    Args:
        output_dir (str): Directory where files will be saved.
        prefix (str): Prefix for the saved PCD files.
        max_keeps (int): Maximum number of recent files to keep. Older files are deleted.
    """

    def __init__(self, output_dir: str = "debug_output", prefix: str = "pcd", max_keeps: int = 10):
        self.output_dir = output_dir
        self.prefix = prefix
        self.max_keeps = max_keeps
        self.counter = 0
        self.saved_files = []
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

    def apply(self, pcd: Any):
        filename = os.path.join(self.output_dir, f"{self.prefix}_{self.counter:04d}.pcd")
        self.counter += 1

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            o3d.t.io.write_point_cloud(filename, pcd, write_ascii=True)
        else:
            o3d.io.write_point_cloud(filename, pcd, write_ascii=True)

        self.saved_files.append(filename)
        while len(self.saved_files) > self.max_keeps:
            oldest = self.saved_files.pop(0)
            if os.path.exists(oldest):
                os.remove(oldest)

        return pcd, {"debug_file": filename}

class SaveDataStructure(PipelineOperation):
    """
    Saves the structural information of the point cloud (attributes, count, etc.) to a JSON file.
    
    Args:
        output_file (str): Path to the output JSON file.
    """

    def __init__(self, output_file: str = "debug_structure.json"):
        self.output_file = output_file

    def apply(self, pcd: Any):
        # Ensure directory exists
        dir_name = os.path.dirname(self.output_file)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            attr_keys = list(_tensor_map_keys(pcd.point))
            
            # Robustly determine count even if attributes are missing
            try:
                count = int(pcd.point.positions.shape[0])
            except Exception:
                count = 0
                
            structure = {
                "device": str(pcd.device),
                "point_attributes": {k: str(pcd.point[k].dtype) for k in attr_keys},
                "count": count,
                "sample_data": {}
            }
            sample_count = min(5, count)
            for k in attr_keys:
                try:
                    data = pcd.point[k][:sample_count].cpu().numpy()
                    structure["sample_data"][k] = data.tolist()
                except Exception:
                    pass
        else:
            structure = {
                "type": "legacy",
                "count": len(pcd.points),
                "has_colors": pcd.has_colors(),
                "has_normals": pcd.has_normals(),
                "sample_data": {
                    "positions": np.asarray(pcd.points)[:5].tolist()
                }
            }
            if pcd.has_colors():
                structure["sample_data"]["colors"] = np.asarray(pcd.colors)[:5].tolist()
            if pcd.has_normals():
                structure["sample_data"]["normals"] = np.asarray(pcd.normals)[:5].tolist()

        with open(self.output_file, "w") as f:
            json.dump(structure, f, indent=2)

        return pcd, {"structure_file": self.output_file}

