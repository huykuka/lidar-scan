import os

from ..operations import PipelineBuilder


def create_pipeline(lidar_id: str = "default"):
    """
    Pipeline for detecting reflectors.
    Filters by the 'reflector' field and removes outliers.
    Skips downsampling to preserve point density.
    """
    debug_dir = os.path.join("debug_data", lidar_id, "reflector")

    return (PipelineBuilder()
            .filter(reflector=1)
            # .remove_outliers(nb_neighbors=10, std_ratio=1.0)
            # .cluster(eps=0.2, min_points=10)
            # .segment_plane(distance_threshold=0.05)
            .build())
