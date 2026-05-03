"""
Poisson surface reconstruction algorithm.

Solves a regularised optimisation to produce a smooth, watertight surface.
The ``depth`` parameter controls the octree resolution — higher values capture
finer detail at the cost of longer computation.

A ``density_quantile`` threshold removes spurious low-density vertices that
Poisson tends to create far from the actual data.

Note: Requires normals on the input PointCloud.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import open3d as o3d

from .reconstruction_base import PoissonReconstructionParams, ReconstructionAlgorithmBase

logger = logging.getLogger(__name__)


class PoissonReconstruction(ReconstructionAlgorithmBase):
    """Poisson surface reconstruction.

    Args:
        params: PoissonReconstructionParams controlling depth, scale, and density filtering.
    """

    def __init__(self, params: Optional[PoissonReconstructionParams] = None) -> None:
        self.params = params or PoissonReconstructionParams()

    def reconstruct(self, pcd: o3d.geometry.PointCloud) -> o3d.geometry.TriangleMesh:
        p = self.params
        logger.debug(
            "Poisson: depth=%d, scale=%.2f, linear_fit=%s, points=%d",
            p.depth, p.scale, p.linear_fit, len(pcd.points),
        )

        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd,
            depth=p.depth,
            width=p.width,
            scale=p.scale,
            linear_fit=p.linear_fit,
        )

        # Remove low-density vertices (spurious geometry far from data)
        if p.density_quantile > 0.0 and len(densities) > 0:
            densities_np = np.asarray(densities)
            threshold = np.quantile(densities_np, p.density_quantile)
            vertices_to_remove = densities_np < threshold
            mesh.remove_vertices_by_mask(vertices_to_remove)

        mesh.compute_vertex_normals()
        return mesh
