"""
Node registry for the pipeline operations module.

Auto-imports all sub-module registries for point cloud operation nodes.
Loaded automatically via discover_modules() at application startup.
"""

from .operations.crop import registry as crop_registry
from .operations.downsample import registry as downsample_registry
from .operations.outliers import registry as outliers_registry
from .operations.segmentation import registry as segmentation_registry
from .operations.clustering import registry as clustering_registry
from .operations.filter import registry as filter_registry
from .operations.boundary import registry as boundary_registry
from .operations.debug import registry as debug_registry
from .operations.generate_plane import registry as generate_plane_registry
from .operations.density import registry as density_registry
from .operations.patch_plane_segmentation import registry as patch_plane_segmentation_registry
from .operations.surface_reconstruction import registry as surface_reconstruction_registry
from .operations.coordinate_transform import registry as coordinate_transform_registry
from .operations.edge_detection import registry as edge_detection_registry
from .operations.plane_projection import registry as plane_projection_registry
from .operations.range_image import registry as range_image_registry
from .operations.centroid_calculation import registry as centroid_calculation_registry

__all__ = [
    "crop_registry",
    "downsample_registry",
    "outliers_registry",
    "segmentation_registry",
    "clustering_registry",
    "filter_registry",
    "boundary_registry",
    "debug_registry",
    "generate_plane_registry",
    "density_registry",
    "patch_plane_segmentation_registry",
    "surface_reconstruction_registry",
    "coordinate_transform_registry",
    "edge_detection_registry",
    "plane_projection_registry",
    "range_image_registry",
    "centroid_calculation_registry",
]
