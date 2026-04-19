"""
Patch plane segmentation operation package.
Re-exports PatchPlaneSegmentation for backwards-compatible imports.
"""
from app.modules.pipeline.operations.patch_plane_segmentation.node import PatchPlaneSegmentation

__all__ = ["PatchPlaneSegmentation"]
