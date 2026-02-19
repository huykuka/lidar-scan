"""
Point Cloud Pipeline Operations.

This module provides various operations for point cloud processing, including
cropping, downsampling, outlier removal, and clustering.

Example:
    >>> from app.pipeline.operations import PipelineBuilder
    >>> pipeline = (PipelineBuilder()
    ...             .downsample(voxel_size=0.05)
    ...             .remove_outliers(nb_neighbors=20, std_ratio=2.0)
    ...             .build())
    >>> results = pipeline.process(my_points_numpy_array)
"""
import json
import os
from typing import List, Any, Callable

import numpy as np
import open3d as o3d

from .base import PipelineOperation, PointCloudPipeline, _tensor_map_keys


class Crop(PipelineOperation):
    """
    Crops the point cloud using an axis-aligned bounding box.
    
    Args:
        min_bound (List[float]): Minimum coordinates [x, y, z].
        max_bound (List[float]): Maximum coordinates [x, y, z].
    """

    def __init__(self, min_bound: List[float], max_bound: List[float]):
        self.min_bound = np.array(min_bound)
        self.max_bound = np.array(max_bound)

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            bbox = o3d.t.geometry.AxisAlignedBoundingBox(self.min_bound, self.max_bound)
            pcd = pcd.crop(bbox)
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
            return pcd, {"cropped_count": count}
        else:
            bbox = o3d.geometry.AxisAlignedBoundingBox(min_bound=self.min_bound, max_bound=self.max_bound)
            pcd = pcd.crop(bbox)
            return pcd, {"cropped_count": len(pcd.points)}


class Downsample(PipelineOperation):
    """
    Downsamples the point cloud using a voxel grid filter.
    
    Args:
        voxel_size (float): The size of the voxel to use for downsampling. 
                           Values <= 0 will bypass downsampling.
    """

    def __init__(self, voxel_size: float):
        self.voxel_size = voxel_size

    def apply(self, pcd: Any):
        if self.voxel_size > 0:
            pcd = pcd.voxel_down_sample(voxel_size=self.voxel_size)
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)
        return pcd, {"downsampled_count": count}


class StatisticalOutlierRemoval(PipelineOperation):
    """
    Removes points that are further away from their neighbors compared to the average for the point cloud.
    
    Args:
        nb_neighbors (int): Number of neighbors to consider for each point.
        std_ratio (float): Standard deviation ratio. Lower values are more aggressive.
        
    Note: Tensor API implementation currently falls back to legacy API.
    """

    def __init__(self, nb_neighbors: int = 20, std_ratio: float = 2.0):
        self.nb_neighbors = nb_neighbors
        self.std_ratio = std_ratio

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)
            
        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                # Fallback to legacy
                pcd_legacy = pcd.to_legacy()
                pcd_filtered, _ = pcd_legacy.remove_statistical_outlier(
                    nb_neighbors=self.nb_neighbors,
                    std_ratio=self.std_ratio
                )
                # Re-box as Tensor
                pcd = o3d.t.geometry.PointCloud.from_legacy(pcd_filtered, device=pcd.device)
            else:
                pcd, _ = pcd.remove_statistical_outlier(
                    nb_neighbors=self.nb_neighbors,
                    std_ratio=self.std_ratio
                )

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            final_count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            final_count = len(pcd.points)
        return pcd, {"filtered_count": final_count}


class RadiusOutlierRemoval(PipelineOperation):
    """
    Removes points that have fewer than 'nb_points' in a sphere of a given 'radius'.
    
    Args:
        nb_points (int): Minimum number of points required within the radius.
        radius (float): Radius of the sphere to search for neighbors.
        
    Note: Tensor API implementation currently falls back to legacy API.
    """

    def __init__(self, nb_points: int = 16, radius: float = 0.05):
        self.nb_points = nb_points
        self.radius = radius

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)
            
        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                # Fallback to legacy
                pcd_legacy = pcd.to_legacy()
                pcd_filtered, _ = pcd_legacy.remove_radius_outlier(
                    nb_points=self.nb_points,
                    radius=self.radius
                )
                pcd = o3d.t.geometry.PointCloud.from_legacy(pcd_filtered, device=pcd.device)
            else:
                pcd, _ = pcd.remove_radius_outlier(
                    nb_points=self.nb_points,
                    radius=self.radius
                )
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            final_count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            final_count = len(pcd.points)
        return pcd, {"filtered_count": final_count}


class UniformDownsample(PipelineOperation):
    """
    Downsamples the point cloud by collecting every n-th point.
    
    Args:
        every_k_points (int): The interval at which points are collected (e.g., every 5th point).
    """

    def __init__(self, every_k_points: int = 5):
        self.every_k_points = every_k_points

    def apply(self, pcd: Any):
        if self.every_k_points > 1:
            pcd = pcd.uniform_down_sample(every_k_points=self.every_k_points)
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)
        return pcd, {"downsampled_count": count}


class OutlierRemoval(StatisticalOutlierRemoval):
    """Legacy wrapper for StatisticalOutlierRemoval"""
    pass


class PlaneSegmentation(PipelineOperation):
    """
    Segments a plane from the point cloud using RANSAC.
    
    Args:
        distance_threshold (float): Max distance a point can be from the plane to be considered an inlier.
        ransac_n (int): Number of points sampled to estimate the plane.
        num_iterations (int): Maximum number of iterations for RANSAC.
    """

    def __init__(self, distance_threshold: float = 0.1, ransac_n: int = 3, num_iterations: int = 1000):
        self.distance_threshold = distance_threshold
        self.ransac_n = ransac_n
        self.num_iterations = num_iterations

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)

        if count >= self.ransac_n:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                plane_model, inliers = pcd.segment_plane(
                    distance_threshold=self.distance_threshold,
                    ransac_n=self.ransac_n,
                    num_iterations=self.num_iterations,
                    probability=0.9999
                )
                pcd = pcd.select_by_index(inliers)

                return pcd, {
                    "plane_model": plane_model.cpu().numpy().tolist(),
                    "inlier_count": len(inliers)
                }
            else:
                plane_model, inliers = pcd.segment_plane(
                    distance_threshold=self.distance_threshold,
                    ransac_n=self.ransac_n,
                    num_iterations=self.num_iterations,
                    probability=0.9999
                )
                pcd = pcd.select_by_index(inliers)

                return pcd, {
                    "plane_model": plane_model.tolist(),
                    "inlier_count": len(inliers)
                }
        return pcd, {}


class Clustering(PipelineOperation):
    """
    Clusters points using the DBSCAN algorithm and removes outliers (noise).
    
    Args:
        eps (float): Distance to neighbors in a cluster.
        min_points (int): Minimum number of points required to form a cluster.
    """

    def __init__(self, eps: float = 0.2, min_points: int = 10):
        self.eps = eps
        self.min_points = min_points

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)

        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                labels = pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points, print_progress=True)
                mask = labels >= 0
                pcd = pcd.select_by_mask(mask)
                cluster_count = int(labels.max().item() + 1) if labels.shape[0] > 0 else 0
            else:
                labels = np.array(pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points))
                indices = np.where(labels >= 0)[0]
                pcd = pcd.select_by_index(indices)
                cluster_count = int(labels.max() + 1) if labels.size > 0 else 0
            return pcd, {"cluster_count": cluster_count}
        return pcd, {"cluster_count": 0}


class Filter(PipelineOperation):
    """
    Generic point cloud filter that uses a custom filter function.
    
    Args:
        filter_fn (Callable): A function that takes a PointCloud and returns a boolean mask or indices.
                             - Tensor API: filter_fn(pcd) -> o3d.core.Tensor (bool or int64)
                             - Legacy API: filter_fn(pcd) -> np.ndarray (bool or int) or List[int]
    """

    def __init__(self, filter_fn: Callable[[Any], Any]):
        """
        filter_fn should take a PointCloud and return a boolean mask or indices.
        For Tensor API: filter_fn(pcd) -> o3d.core.Tensor (bool or int64)
        For Legacy API: filter_fn(pcd) -> np.ndarray (bool or int) or List[int]
        """
        self.filter_fn = filter_fn

    def apply(self, pcd: Any):
        result = self.filter_fn(pcd)

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            if hasattr(result, 'shape') and len(result.shape) > 1:
                result = result.reshape([-1])

            if hasattr(result, 'dtype') and str(result.dtype).lower().startswith('bool'):
                pcd = pcd.select_by_mask(result)
            else:
                pcd = pcd.select_by_index(result)
            if 'positions' in pcd.point:
                final_count = pcd.point.positions.shape[0]
            else:
                final_count = 0
        else:
            if isinstance(result, np.ndarray) and result.dtype == bool:
                result = np.where(result)[0]
            pcd = pcd.select_by_index(result)
            final_count = len(pcd.points)

        return pcd, {"filtered_count": final_count}


class FilterByKey(PipelineOperation):
    """
    Filters the point cloud based on a specific attribute key.
    
    Args:
        key (str): The attribute key to filter by (e.g., 'intensity', 'reflector').
        value (Any): The value to match, or a callable condition (e.g., lambda x: x > 0.5).
    """

    def __init__(self, key: str, value: Any):
        """
        Filters the point cloud based on a specific attribute (key).
        'value' can be a direct value (e.g., True, 0.5) for equality matching,
        or a condition function (e.g., lambda x: x > 0.5).
        """
        self.key = key
        self.value = value

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            if self.key not in pcd.point:
                count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
                return pcd, {"filtered_count": count, "warning": f"Key '{self.key}' not found"}

            data = pcd.point[self.key]
            if callable(self.value):
                result = self.value(data)
            elif isinstance(self.value, (tuple, list)) and len(self.value) == 2:
                op, val = self.value
                if op == '>':
                    result = (data > val)
                elif op == '>=':
                    result = (data >= val)
                elif op == '<':
                    result = (data < val)
                elif op == '<=':
                    result = (data <= val)
                elif op == '!=':
                    result = (data != val)
                elif op == '==':
                    result = (data == val)
                else:
                    result = (data == self.value)
            else:
                result = (data == self.value)

            if hasattr(result, 'shape') and len(result.shape) > 1:
                result = result.reshape([-1])

            if hasattr(result, 'dtype') and str(result.dtype).lower().startswith('bool'):
                pcd = pcd.select_by_mask(result)
            else:
                pcd = pcd.select_by_index(result)
            
            if 'positions' in pcd.point:
                final_count = pcd.point.positions.shape[0]
            else:
                final_count = 0
        else:
            attr_name = self.key
            if self.key == "intensity": attr_name = "colors"

            if hasattr(pcd, attr_name):
                data = np.asarray(getattr(pcd, attr_name))
                if callable(self.value):
                    mask = self.value(data)
                elif isinstance(self.value, (tuple, list)) and len(self.value) == 2:
                    op, val = self.value
                    if op == '>':
                        mask = (data > val)
                    elif op == '>=':
                        mask = (data >= val)
                    elif op == '<':
                        mask = (data < val)
                    elif op == '<=':
                        mask = (data <= val)
                    elif op == '!=':
                        mask = (data != val)
                    elif op == '==':
                        mask = (data == val)
                    else:
                        mask = (data == self.value)
                else:
                    mask = (data == self.value)

                if isinstance(mask, np.ndarray) and mask.dtype == bool:
                    indices = np.where(mask)[0]
                else:
                    indices = mask

                pcd = pcd.select_by_index(indices)
                final_count = len(pcd.points)
            else:
                return pcd, {"filtered_count": len(pcd.points),
                             "warning": f"Attribute '{self.key}' not found on legacy PointCloud"}

        return pcd, {"filtered_count": final_count, "filter_key": self.key}


class BoundaryDetection(PipelineOperation):
    """
    Detects boundary points in the point cloud.
    
    Args:
        radius (float): Radius for neighbor search.
        max_nn (int): Maximum number of neighbors to consider.
        angle_threshold (float): Angle threshold (in degrees) for boundary detection.
    """

    def __init__(self, radius: float = 0.02, max_nn: int = 30, angle_threshold: float = 90.0):
        self.radius = radius
        self.max_nn = max_nn
        self.angle_threshold = angle_threshold

    def apply(self, pcd: Any):
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            # Boundary detection requires normals
            if 'normals' not in pcd.point:
                pcd.estimate_normals(max_nn=self.max_nn, radius=self.radius)
            
            boundary_pcd, mask = pcd.compute_boundary_points(self.radius, self.max_nn, self.angle_threshold)
            
            count = boundary_pcd.point.positions.shape[0] if 'positions' in boundary_pcd.point else 0
            original_count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
            
            return boundary_pcd, {
                "boundary_count": int(count),
                "original_count": int(original_count)
            }
        else:
            # Fallback for Legacy API
            pcd_tensor = o3d.t.geometry.PointCloud.from_legacy(pcd)
            if 'normals' not in pcd_tensor.point:
                pcd_tensor.estimate_normals(max_nn=self.max_nn, radius=self.radius)
            
            boundary_pcd, mask = pcd_tensor.compute_boundary_points(self.radius, self.max_nn, self.angle_threshold)
            pcd_legacy = boundary_pcd.to_legacy()
            
            return pcd_legacy, {
                "boundary_count": len(pcd_legacy.points),
                "original_count": len(pcd.points)
            }


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


class PipelineBuilder:
    """
    Fluid interface for building PointCloudPipelines.
    
    Example:
        >>> # Create a pipeline with several operations
        >>> builder = PipelineBuilder(use_tensor=True)
        >>> pipeline = (builder
        ...             .downsample(voxel_size=0.05)
        ...             .remove_outliers(nb_neighbors=20, std_ratio=2.0)
        ...             .segment_plane(distance_threshold=0.1)
        ...             .build())
        >>> 
        >>> # Process points (numpy array)
        >>> import numpy as np
        >>> points = np.random.rand(1000, 3) 
        >>> result = pipeline.process(points)
        >>> print(f"Remaining points: {result['metadata']['count']}")
    """

    def __init__(self, use_tensor: bool = True, device: str = "CPU:0"):
        if use_tensor:
            from .base import TensorPointCloudPipeline
            self.pipeline = TensorPointCloudPipeline(device)
        else:
            from .base import LegacyPointCloudPipeline
            self.pipeline = LegacyPointCloudPipeline()

    def crop(self, min_bound: List[float], max_bound: List[float]):
        """Crops the point cloud within the specified bounding box."""
        self.pipeline.add_operation(Crop(min_bound, max_bound))
        return self

    def downsample(self, voxel_size: float):
        """Reduces point count using voxel downsampling."""
        self.pipeline.add_operation(Downsample(voxel_size))
        return self

    def remove_outliers(self, nb_neighbors: int = 20, std_ratio: float = 2.0):
        """Removes statistical outliers based on neighbor distances."""
        self.pipeline.add_operation(StatisticalOutlierRemoval(nb_neighbors, std_ratio))
        return self

    def remove_radius_outliers(self, nb_points: int = 16, radius: float = 0.05):
        """Removes points that have fewer than nb_points within a radius."""
        self.pipeline.add_operation(RadiusOutlierRemoval(nb_points, radius))
        return self

    def uniform_downsample(self, every_k_points: int = 5):
        """Downsamples the point cloud by selecting every k-th point."""
        self.pipeline.add_operation(UniformDownsample(every_k_points))
        return self

    def segment_plane(self, distance_threshold: float = 0.1, ransac_n: int = 3, num_iterations: int = 1000):
        """Segments and keeps ONLY the dominant plane."""
        self.pipeline.add_operation(PlaneSegmentation(distance_threshold, ransac_n, num_iterations))
        return self

    def cluster(self, eps: float = 0.2, min_points: int = 10):
        """Segments clusters and removes noise points using DBSCAN."""
        self.pipeline.add_operation(Clustering(eps, min_points))
        return self

    def compute_boundary(self, radius: float = 0.02, max_nn: int = 30, angle_threshold: float = 90.0):
        """Detects boundary points in the point cloud."""
        self.pipeline.add_operation(BoundaryDetection(radius, max_nn, angle_threshold))
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
