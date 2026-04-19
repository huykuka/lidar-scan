"""
Downsample operation package.
Re-exports Downsample and UniformDownsample for backwards-compatible imports.
"""
from app.modules.pipeline.operations.downsample.node import Downsample, UniformDownsample

__all__ = ["Downsample", "UniformDownsample"]
