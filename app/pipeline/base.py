from abc import ABC, abstractmethod
from typing import List, Dict, Any

import numpy as np
import open3d as o3d


class PipelineOperation(ABC):
    """Base class for all point cloud operations"""

    @abstractmethod
    def apply(self, pcd: Any) -> Dict[str, Any]:
        """Supports both o3d.geometry.PointCloud and o3d.t.geometry.PointCloud"""
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

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)

        results = {}
        for op in self.operations:
            op_result = op.apply(pcd)
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
        pcd.point.positions = o3d.core.Tensor(points.astype(np.float32), device=self.device)

        results = {}
        for op in self.operations:
            op_result = op.apply(pcd)
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
