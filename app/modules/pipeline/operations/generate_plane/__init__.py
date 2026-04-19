"""
Generate plane operation package.
Re-exports GeneratePlane for backwards-compatible imports.
"""
from app.modules.pipeline.operations.generate_plane.node import GeneratePlane

__all__ = ["GeneratePlane"]
