from ..operations import PipelineBuilder


def create_pipeline(lidar_id: str = "default"):
    return (PipelineBuilder()
            .build())
