import os

from ..operations import PipelineBuilder


def create_pipeline(lidar_id: str = "default"):
    """Pipeline with custom stats and segmentation"""
    debug_dir = os.path.join("debug_data", lidar_id)
    return (PipelineBuilder()
            .filter(
                reflector=1,                   # Match specific value
                # intensity=('>', 42000),        # Use picklable comparison tuple
            )        
            # .remove_outliers(nb_neighbors=3,std_ratio=1)  
            # .remove_radius_outliers(nb_points=3, radius=0.02)
            # .cluster(eps=0.05, min_points=6)
            # .segment_plane(distance_threshold=0.01,num_iterations=200)
            # .compute_boundary(radius=0.02,max_nn=30,angle_threshold=90.0)
            # .add_custom(CreatePointPlane(size=1.0, resolution=0.1, noise=0.01))
            .debug_save(output_dir=debug_dir, prefix="advanced", max_keeps=10)
            .save_structure(output_file=os.path.join(debug_dir, "data_structure.json"))
            .build())
