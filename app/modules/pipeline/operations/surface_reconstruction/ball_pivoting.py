"""
Ball Pivoting Algorithm (BPA) surface reconstruction.

Rolls a ball of varying radii over the point cloud; when the ball rests on
exactly three points it creates a triangle.  Multiple radii let the algorithm
handle point clouds with varying local densities.

Note: Requires normals on the input PointCloud.
"""
from __future__ import annotations

import logging
from typing import Optional

import open3d as o3d

from .reconstruction_base import BallPivotingParams, ReconstructionAlgorithmBase

logger = logging.getLogger(__name__)


class BallPivotingReconstruction(ReconstructionAlgorithmBase):
    """Ball Pivoting surface reconstruction.

    Args:
        params: BallPivotingParams with the radii string.
    """

    def __init__(self, params: Optional[BallPivotingParams] = None) -> None:
        self.params = params or BallPivotingParams()

    def reconstruct(self, pcd: o3d.geometry.PointCloud) -> o3d.geometry.TriangleMesh:
        radii = self.params.get_radii_list()
        logger.debug("BallPivoting: radii=%s, points=%d", radii, len(pcd.points))

        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, o3d.utility.DoubleVector(radii)
        )
        mesh.compute_vertex_normals()
        return mesh
