"""
Boundary detection operation package.
Re-exports BoundaryDetection for backwards-compatible imports.
"""
from app.modules.pipeline.operations.boundary.node import BoundaryDetection

__all__ = ["BoundaryDetection"]
