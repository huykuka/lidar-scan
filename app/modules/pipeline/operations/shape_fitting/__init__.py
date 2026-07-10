"""
Shape fitting operation package.
Fits geometric primitives (circle, plane, etc.) to point clouds and outputs
a downsampled point cloud sampled on the fitted shape.
"""
from app.modules.pipeline.operations.shape_fitting.node import ShapeFitting

__all__ = ["ShapeFitting"]
