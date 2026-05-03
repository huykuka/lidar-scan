"""
Alpha Shape surface reconstruction algorithm.

Creates a triangle mesh from a point cloud using the alpha shape method.
The alpha parameter controls the level of detail — smaller values produce
finer meshes that better conform to the point cloud, while larger values
produce coarser hulls.
"""
from __future__ import annotations

import logging
from typing import Optional

import open3d as o3d

from .reconstruction_base import AlphaShapeParams, ReconstructionAlgorithmBase

logger = logging.getLogger(__name__)


class AlphaShapeReconstruction(ReconstructionAlgorithmBase):
    """Alpha shape surface reconstruction.

    Args:
        params: AlphaShapeParams with the alpha radius value.
    """

    def __init__(self, params: Optional[AlphaShapeParams] = None) -> None:
        self.params = params or AlphaShapeParams()

    def reconstruct(self, pcd: o3d.geometry.PointCloud) -> o3d.geometry.TriangleMesh:
        alpha = self.params.alpha
        logger.debug("AlphaShape: alpha=%.4f, points=%d", alpha, len(pcd.points))

        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(pcd, alpha)
        mesh.compute_vertex_normals()
        return mesh
