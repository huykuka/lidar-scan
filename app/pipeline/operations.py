import json
import os
from typing import List, Dict, Any, Callable

import numpy as np
import open3d as o3d

from .base import PipelineOperation, PointCloudPipeline


class Crop(PipelineOperation):
    def __init__(self, min_bound: List[float], max_bound: List[float]):
        self.min_bound = np.array(min_bound)
        self.max_bound = np.array(max_bound)

    def apply(self, pcd: Any) -> Dict[str, Any]:
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            bbox = o3d.t.geometry.AxisAlignedBoundingBox(self.min_bound, self.max_bound)
            cropped_pcd = pcd.crop(bbox)
            pcd.point.positions = cropped_pcd.point.positions
            return {"cropped_count": len(pcd.point.positions)}
        else:
            bbox = o3d.geometry.AxisAlignedBoundingBox(min_bound=self.min_bound, max_bound=self.max_bound)
            cropped_pcd = pcd.crop(bbox)
            pcd.points = cropped_pcd.points
            return {"cropped_count": len(pcd.points)}


class Downsample(PipelineOperation):
    def __init__(self, voxel_size: float):
        self.voxel_size = voxel_size

    def apply(self, pcd: Any) -> Dict[str, Any]:
        if self.voxel_size > 0:
            down_pcd = pcd.voxel_down_sample(voxel_size=self.voxel_size)
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                pcd.point.positions = down_pcd.point.positions
                return {"downsampled_count": len(pcd.point.positions)}
            else:
                pcd.points = down_pcd.points
                return {"downsampled_count": len(pcd.points)}
        return {
            "downsampled_count": len(pcd.point.positions if isinstance(pcd, o3d.t.geometry.PointCloud) else pcd.points)}


class OutlierRemoval(PipelineOperation):
    def __init__(self, nb_neighbors: int = 20, std_ratio: float = 2.0):
        self.nb_neighbors = nb_neighbors
        self.std_ratio = std_ratio

    def apply(self, pcd: Any) -> Dict[str, Any]:
        count = len(pcd.point.positions) if isinstance(pcd, o3d.t.geometry.PointCloud) else len(pcd.points)
        if count > self.nb_neighbors:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                # Tensor API for outlier removal might differ or use legacy fallback
                pcd_legacy = pcd.to_legacy()
                pcd_filtered, _ = pcd_legacy.remove_statistical_outlier(
                    nb_neighbors=self.nb_neighbors,
                    std_ratio=self.std_ratio
                )
                pcd.point.positions = o3d.core.Tensor(np.asarray(pcd_filtered.points).astype(np.float32),
                                                      device=pcd.device)
            else:
                pcd_filtered, _ = pcd.remove_statistical_outlier(
                    nb_neighbors=self.nb_neighbors,
                    std_ratio=self.std_ratio
                )
                pcd.points = pcd_filtered.points

        final_count = len(pcd.point.positions) if isinstance(pcd, o3d.t.geometry.PointCloud) else len(pcd.points)
        return {"filtered_count": final_count}


class PlaneSegmentation(PipelineOperation):
    def __init__(self, distance_threshold: float = 0.1, ransac_n: int = 3, num_iterations: int = 1000):
        self.distance_threshold = distance_threshold
        self.ransac_n = ransac_n
        self.num_iterations = num_iterations

    def apply(self, pcd: Any) -> Dict[str, Any]:
        count = len(pcd.point.positions) if isinstance(pcd, o3d.t.geometry.PointCloud) else len(pcd.points)
        if count > self.ransac_n:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                plane_model, inliers = pcd.segment_plane(
                    distance_threshold=self.distance_threshold,
                    ransac_n=self.ransac_n,
                    num_iterations=self.num_iterations
                )
                return {
                    "plane_model": plane_model.cpu().numpy().tolist(),
                    "inlier_count": len(inliers)
                }
            else:
                plane_model, inliers = pcd.segment_plane(
                    distance_threshold=self.distance_threshold,
                    ransac_n=self.ransac_n,
                    num_iterations=self.num_iterations
                )
                return {
                    "plane_model": plane_model.tolist(),
                    "inlier_count": len(inliers)
                }
        return {}


class Clustering(PipelineOperation):
    def __init__(self, eps: float = 0.2, min_points: int = 10):
        self.eps = eps
        self.min_points = min_points

    def apply(self, pcd: Any) -> Dict[str, Any]:
        count = pcd.point.positions.shape[0] if isinstance(pcd, o3d.t.geometry.PointCloud) else len(pcd.points)
        if count > self.min_points:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                labels = pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points)
                cluster_count = int(labels.max().item() + 1) if labels.shape[0] > 0 else 0
            else:
                labels = np.array(pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points))
                cluster_count = int(labels.max() + 1) if labels.size > 0 else 0
            return {"cluster_count": cluster_count}
        return {"cluster_count": 0}


class Filter(PipelineOperation):
    def __init__(self, filter_fn: Callable[[Any], Any]):
        """
        filter_fn should take a PointCloud and return a boolean mask or indices.
        For Tensor API: filter_fn(pcd) -> o3d.core.Tensor (bool or int64)
        For Legacy API: filter_fn(pcd) -> np.ndarray (bool or int) or List[int]
        """
        self.filter_fn = filter_fn

    def apply(self, pcd: Any) -> Dict[str, Any]:
        result = self.filter_fn(pcd)

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            # Check if result is a boolean mask or indices
            if hasattr(result, 'dtype') and str(result.dtype).lower().startswith('bool'):
                pcd_filtered = pcd.select_by_mask(result)
            else:
                pcd_filtered = pcd.select_by_index(result)

            # Sync properties
            pcd.point.positions = pcd_filtered.point.positions
            for key in pcd_filtered.point.keys():
                if key != 'positions':
                    pcd.point[key] = pcd_filtered.point[key]

            final_count = pcd.point.positions.shape[0]
        else:
            # For Legacy API
            if isinstance(result, np.ndarray) and result.dtype == bool:
                result = np.where(result)[0]

            pcd_filtered = pcd.select_by_index(result)
            pcd.points = pcd_filtered.points
            if pcd_filtered.has_colors():
                pcd.colors = pcd_filtered.colors
            if pcd_filtered.has_normals():
                pcd.normals = pcd_filtered.normals

            final_count = len(pcd.points)

        return {"filtered_count": final_count}


class FilterByKey(PipelineOperation):
    def __init__(self, key: str, value: Any):
        """
        Filters the point cloud based on a specific attribute (key).
        'value' can be a direct value (e.g., True, 0.5) for equality matching,
        or a condition function (e.g., lambda x: x > 0.5).
        """
        self.key = key
        self.value = value

    def apply(self, pcd: Any) -> Dict[str, Any]:
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            if self.key not in pcd.point:
                return {"filtered_count": pcd.point.positions.shape[0], "warning": f"Key '{self.key}' not found"}

            data = pcd.point[self.key]
            if callable(self.value):
                result = self.value(data)
            else:
                result = (data == self.value)

            # Check if result is a boolean mask or indices
            if hasattr(result, 'dtype') and str(result.dtype).lower().startswith('bool'):
                pcd_filtered = pcd.select_by_mask(result)
            else:
                pcd_filtered = pcd.select_by_index(result)

            pcd.point.positions = pcd_filtered.point.positions
            for key in pcd_filtered.point.keys():
                if key != 'positions':
                    pcd.point[key] = pcd_filtered.point[key]

            final_count = pcd.point.positions.shape[0]
        else:
            # For Legacy API, we check if it's a known attribute (colors, normals)
            # or try to access it if it was dynamically added (rare in o3d legacy)
            if hasattr(pcd, self.key):
                data = np.asarray(getattr(pcd, self.key))
                result = self.condition_fn(data)

                if isinstance(result, np.ndarray) and result.dtype == bool:
                    result = np.where(result)[0]

                pcd_filtered = pcd.select_by_index(result)
                pcd.points = pcd_filtered.points
                if pcd_filtered.has_colors():
                    pcd.colors = pcd_filtered.colors
                if pcd_filtered.has_normals():
                    pcd.normals = pcd_filtered.normals
                final_count = len(pcd.points)
            else:
                return {"filtered_count": len(pcd.points),
                        "warning": f"Attribute '{self.key}' not found on legacy PointCloud"}

        return {"filtered_count": final_count, "filter_key": self.key}


class DebugSave(PipelineOperation):
    def __init__(self, output_dir: str = "debug_output", prefix: str = "pcd", max_keeps: int = 10):
        self.output_dir = output_dir
        self.prefix = prefix
        self.max_keeps = max_keeps
        self.counter = 0
        self.saved_files = []
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

    def apply(self, pcd: Any) -> Dict[str, Any]:
        filename = os.path.join(self.output_dir, f"{self.prefix}_{self.counter:04d}.pcd")
        self.counter += 1

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            o3d.t.io.write_point_cloud(filename, pcd)
        else:
            o3d.io.write_point_cloud(filename, pcd)

        self.saved_files.append(filename)

        # Maintain max_keeps
        while len(self.saved_files) > self.max_keeps:
            oldest = self.saved_files.pop(0)
            if os.path.exists(oldest):
                os.remove(oldest)

        return {"debug_file": filename}


class SaveDataStructure(PipelineOperation):
    def __init__(self, output_file: str = "debug_structure.json"):
        self.output_file = output_file

    def apply(self, pcd: Any) -> Dict[str, Any]:
        # Ensure directory exists
        dir_name = os.path.dirname(self.output_file)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            structure = {
                "device": str(pcd.device),
                "point_attributes": {k: str(v.dtype) for k, v in pcd.point.items()},
                "count": pcd.point.positions.shape[0]
            }
        else:
            structure = {
                "type": "legacy",
                "count": len(pcd.points),
                "has_colors": pcd.has_colors(),
                "has_normals": pcd.has_normals()
            }

        with open(self.output_file, "w") as f:
            json.dump(structure, f, indent=2)

        return {"structure_file": self.output_file}


class PipelineBuilder:
    def __init__(self, use_tensor: bool = False, device: str = "CPU:0"):
        if use_tensor:
            from .base import TensorPointCloudPipeline
            self.pipeline = TensorPointCloudPipeline(device)
        else:
            from .base import LegacyPointCloudPipeline
            self.pipeline = LegacyPointCloudPipeline()

    def crop(self, min_bound: List[float], max_bound: List[float]):
        self.pipeline.add_operation(Crop(min_bound, max_bound))
        return self

    def downsample(self, voxel_size: float):
        self.pipeline.add_operation(Downsample(voxel_size))
        return self

    def remove_outliers(self, nb_neighbors: int = 20, std_ratio: float = 2.0):
        self.pipeline.add_operation(OutlierRemoval(nb_neighbors, std_ratio))
        return self

    def segment_plane(self, distance_threshold: float = 0.1):
        self.pipeline.add_operation(PlaneSegmentation(distance_threshold))
        return self

    def cluster(self, eps: float = 0.2, min_points: int = 10):
        self.pipeline.add_operation(Clustering(eps, min_points))
        return self

    def filter(self, condition: Callable[[Any], Any] = None, **kwargs):
        """
        Generic filter. 
        Pass a function: .filter(lambda pcd: ...)
        Pass attributes: .filter(reflector=True, intensity=lambda x: x > 0.5)
        """
        if condition:
            self.pipeline.add_operation(Filter(condition))

        for key, value in kwargs.items():
            self.pipeline.add_operation(FilterByKey(key, value))

        return self

    def add_custom(self, operation: PipelineOperation):
        self.pipeline.add_operation(operation)
        return self

    def debug_save(self, output_dir: str = "debug_output", prefix: str = "pcd", max_keeps: int = 10):
        self.pipeline.add_operation(DebugSave(output_dir, prefix, max_keeps))
        return self

    def save_structure(self, output_file: str = "debug_structure.json"):
        self.pipeline.add_operation(SaveDataStructure(output_file))
        return self

    def build(self) -> PointCloudPipeline:
        return self.pipeline
