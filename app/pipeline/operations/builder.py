from typing import List, Any, Callable
import time
import json
import os
import open3d as o3d
import numpy as np
from ..base import PipelineOperation, PointCloudPipeline, _tensor_map_keys
from .crop import Crop
from .downsample import Downsample, UniformDownsample
from .outliers import StatisticalOutlierRemoval, RadiusOutlierRemoval
from .segmentation import PlaneSegmentation
from .clustering import Clustering
from .filter import Filter, FilterByKey
from .boundary import BoundaryDetection
from .debug import DebugSave, SaveDataStructure
from .visualize import Visualize

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
            from ..base import TensorPointCloudPipeline
            self.pipeline = TensorPointCloudPipeline(device)
        else:
            from ..base import LegacyPointCloudPipeline
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

    def visualize(self, window_name: str = "LiDAR Viewer", point_size: float = 1.5,
                  width: int = 960, height: int = 600, blocking: bool = True,
                  stay_seconds: float = 1.0):
        """Adds a visualization step to preview the cloud inside the pipeline."""
        self.pipeline.add_operation(Visualize(window_name, point_size, width, height, blocking, stay_seconds))
        return self

    def build(self) -> PointCloudPipeline:
        return self.pipeline

