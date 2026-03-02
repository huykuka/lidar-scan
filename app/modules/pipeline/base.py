from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

import numpy as np
import open3d as o3d

# Standard 16-column schema mapping (we use 14 in the TensorMap)
FIELD_MAP = {
    "positions": {"idx": slice(0, 3), "dtype": np.float32},
    "lidar_nsec": {"idx": 3, "dtype": np.uint32},
    "lidar_sec": {"idx": 4, "dtype": np.uint32},
    "t": {"idx": 5, "dtype": np.uint32},
    "layer": {"idx": 6, "dtype": np.int32},
    "elevation": {"idx": 7, "dtype": np.float32},
    "ts": {"idx": 8, "dtype": np.float32},
    "azimuth": {"idx": 9, "dtype": np.float32},
    "range": {"idx": 10, "dtype": np.float32},
    "reflector": {"idx": 11, "dtype": np.uint8},
    "echo": {"idx": 12, "dtype": np.int32},
    "intensity": {"idx": 13, "dtype": np.float32},
}

def _tensor_map_keys(tensor_map: Any) -> List[str]:
    """Return TensorMap keys across Open3D versions without triggering key lookups."""
    try:
        return list(tensor_map.keys())
    except Exception:
        try:
            return list(tensor_map)
        except Exception:
            return []

class PipelineOperation(ABC):
    """Base class for all atomic point cloud operations"""

    @abstractmethod
    def apply(self, pcd: Any) -> Any:
        """
        Processes the point cloud.
        Must return the updated PointCloud object and an optional metadata dictionary.
        return pcd, {"some": "info"}
        """
        pass

class PointConverter:
    """Utility for converting between Numpy arrays and Open3D PointClouds."""
    
    @staticmethod
    def to_pcd(points: np.ndarray, device: str = "CPU:0") -> o3d.t.geometry.PointCloud:
        """Converts interleaved numpy points (N, M) to Tensor-based Open3D PointCloud."""
        o3d_device = o3d.core.Device(device)
        pcd = o3d.t.geometry.PointCloud(o3d_device)
        
        if points.size == 0:
            return pcd

        num_cols = points.shape[1]
        
        # Always set positions
        pos = points[:, 0:3].astype(np.float32)
        pcd.point.positions = o3d.core.Tensor(pos, device=o3d_device)

        # Map additional channels if they exist in the input array
        for attr, info in FIELD_MAP.items():
            if attr == "positions":
                continue
            idx = info["idx"]
            if idx < num_cols:
                data = points[:, idx].reshape(-1, 1).astype(info["dtype"])
                pcd.point[attr] = o3d.core.Tensor(data, device=o3d_device)
            
        return pcd

    @staticmethod
    def to_points(pcd: Any) -> np.ndarray:
        """Converts Open3D PointCloud back to structured interleaved numpy points (N, 14)."""
        if not hasattr(pcd, 'point') or 'positions' not in pcd.point:
            return np.zeros((0, 3), dtype=np.float32)
            
        try:
            # Get base positions and determine N
            pos_tensor = pcd.point.positions
            N = pos_tensor.shape[0]
            if N == 0:
                return np.zeros((0, 14), dtype=np.float32)

            # Pre-allocate output array (14 columns)
            out = np.zeros((N, 14), dtype=np.float32)
            out[:, 0:3] = pos_tensor.cpu().numpy()

            # Fill in other channels if they exist in the TensorMap
            available_keys = _tensor_map_keys(pcd.point)
            
            for attr, info in FIELD_MAP.items():
                if attr == "positions":
                    continue
                if attr in available_keys:
                    idx = info["idx"]
                    data = pcd.point[attr].cpu().numpy().flatten()
                    out[:, idx] = data.astype(np.float32) # Standardize to float32 for downstream

            return out
        except Exception as e:
            # Fallback to just positions if reconstruction fails
            try:
                return pcd.point.positions.cpu().numpy()
            except:
                return np.zeros((0, 3), dtype=np.float32)
