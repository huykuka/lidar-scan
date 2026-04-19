"""
Segmentation operation package.
Re-exports PlaneSegmentation for backwards-compatible imports.
"""
from app.modules.pipeline.operations.segmentation.node import PlaneSegmentation

__all__ = ["PlaneSegmentation"]
