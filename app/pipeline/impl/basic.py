import os

from ..operations import PipelineBuilder


def create_pipeline(lidar_id: str = "default"):
    """Simple general purpose cleaning pipeline"""
    return (PipelineBuilder()
            .build())
