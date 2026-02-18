from abc import ABC, abstractmethod
from typing import List, Dict, Any

import numpy as np
import open3d as o3d


def _tensor_map_keys(tensor_map: Any) -> List[str]:
    """Return TensorMap keys across Open3D versions without triggering key lookups."""
    try:
        # In some versions, tensor_map.keys() works
        return list(tensor_map.keys())
    except Exception:
        try:
            # In others, it's iterable
            return list(tensor_map)
        except Exception:
            return []


class PipelineOperation(ABC):
    """Base class for all point cloud operations"""

    @abstractmethod
    def apply(self, pcd: Any) -> Any:
        """
        Processes the point cloud.
        Must return the updated PointCloud object (can be the same or a new one) 
        and an optional metadata dictionary: return pcd, {"some": "info"}
        """
        pass


class PointCloudPipeline(ABC):
    """Base class for point cloud pipelines"""

    def __init__(self):
        self.operations: List[PipelineOperation] = []

    def add_operation(self, operation: PipelineOperation):
        self.operations.append(operation)
        return self

    @abstractmethod
    def process(self, points: np.ndarray) -> Dict[str, Any]:
        """Process points and return results"""
        pass


class LegacyPointCloudPipeline(PointCloudPipeline):
    """Legacy Open3D Pipeline using o3d.geometry.PointCloud"""

    def process(self, points: np.ndarray) -> Dict[str, Any]:
        if points.size == 0:
            return {"points": [], "metadata": {"count": 0}}

        positions = points[:, :3]
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(positions)

        results = {}
        for op in self.operations:
            # Capturing the returned pcd ensures replacements work correctly
            outcome = op.apply(pcd)
            if isinstance(outcome, tuple):
                pcd, op_result = outcome
            else:
                pcd, op_result = outcome, {}

            if op_result:
                results.update(op_result)

        processed_points = np.asarray(pcd.points)

        return {
            "points": processed_points,
            "metadata": {
                "count": len(processed_points),
                "original_count": len(points)
            },
            "algorithms": results
        }


class TensorPointCloudPipeline(PointCloudPipeline):
    """Modern Open3D Pipeline using o3d.t.geometry.PointCloud"""

    def __init__(self, device: str = "CPU:0"):
        super().__init__()
        # Use CPU by default, can be 'CUDA:0' if available
        self.device = o3d.core.Device(device)

    def process(self, points: np.ndarray) -> Dict[str, Any]:
        if points.size == 0:
            return {"points": [], "metadata": {"count": 0}}

        # Create Tensor-based PointCloud
        pcd = o3d.t.geometry.PointCloud(self.device)
        positions = points[:, :3].astype(np.float32)  # Strictly float32 for positions
        pcd.point.positions = o3d.core.Tensor(positions, device=self.device)

        # Map additional columns to attributes based on PCD structure:
        # x, y, z, lidar_nsec, lidar_sec, t, layer, elevation, ts, azimuth, range, reflector, echo, intensity
        if points.shape[1] > 3:
            pcd.point["lidar_nsec"] = o3d.core.Tensor(points[:, 3].reshape(-1, 1).astype(np.uint32), device=self.device)
        if points.shape[1] > 4:
            pcd.point["lidar_sec"] = o3d.core.Tensor(points[:, 4].reshape(-1, 1).astype(np.uint32), device=self.device)
        if points.shape[1] > 5:
            pcd.point["t"] = o3d.core.Tensor(points[:, 5].reshape(-1, 1).astype(np.uint32), device=self.device)
        if points.shape[1] > 6:
            pcd.point["layer"] = o3d.core.Tensor(points[:, 6].reshape(-1, 1).astype(np.int32), device=self.device)
        if points.shape[1] > 7:
            pcd.point["elevation"] = o3d.core.Tensor(points[:, 7].reshape(-1, 1).astype(np.float32), device=self.device)
        if points.shape[1] > 8:
            pcd.point["ts"] = o3d.core.Tensor(points[:, 8].reshape(-1, 1).astype(np.float32), device=self.device)
        if points.shape[1] > 9:
            pcd.point["azimuth"] = o3d.core.Tensor(points[:, 9].reshape(-1, 1).astype(np.float32), device=self.device)
        if points.shape[1] > 10:
            pcd.point["range"] = o3d.core.Tensor(points[:, 10].reshape(-1, 1).astype(np.float32), device=self.device)
        if points.shape[1] > 11:
            pcd.point["reflector"] = o3d.core.Tensor(points[:, 11].reshape(-1, 1).astype(np.uint8), device=self.device)
        if points.shape[1] > 12:
            pcd.point["echo"] = o3d.core.Tensor(points[:, 12].reshape(-1, 1).astype(np.int32), device=self.device)
        if points.shape[1] > 13:
            pcd.point["intensity"] = o3d.core.Tensor(points[:, 13].reshape(-1, 1).astype(np.float32),
                                                     device=self.device)

        results = {}
        for op in self.operations:
            outcome = op.apply(pcd)
            if isinstance(outcome, tuple):
                pcd, op_result = outcome
            else:
                pcd, op_result = outcome, {}

            if op_result:
                results.update(op_result)

        # Retrieve results back to CPU/Numpy
        processed_points = pcd.point.positions.cpu().numpy()

        return {
            "points": processed_points,
            "metadata": {
                "count": len(processed_points),
                "original_count": len(points)
            },
            "algorithms": results
        }
