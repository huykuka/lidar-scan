from ..operations import PipelineBuilder

def create_pipeline():
    """Simple general purpose cleaning pipeline"""
    return (PipelineBuilder()
            .crop(min_bound=[-20, -20, -5], max_bound=[20, 20, 5])
            .downsample(voxel_size=0.1)
            .remove_outliers(nb_neighbors=20, std_ratio=2.0)
            .build())
