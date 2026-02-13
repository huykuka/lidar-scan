import os
from ..operations import PipelineBuilder

def create_pipeline(lidar_id: str = "default"):
    """Simple general purpose cleaning pipeline"""
    debug_dir = os.path.join("debug_data", lidar_id)
    return (PipelineBuilder()
            .crop(min_bound=[-20, -20, -5], max_bound=[20, 20, 5])
            .downsample(voxel_size=0.1)
            .remove_outliers(nb_neighbors=20, std_ratio=2.0)
            .debug_save(output_dir=debug_dir, prefix="basic", max_keeps=10)
            .save_structure(output_file=os.path.join(debug_dir, "data_structure.json"))
            .build())
