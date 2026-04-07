"""
poisson.py — Hybrid Poisson reconstruction densification algorithm.
====================================================================

PoissonDensify preserves all original points and augments with uniformly-sampled
points from a Poisson-reconstructed mesh trimmed at low-density vertices.

Global search guarantee
-----------------------
Poisson reconstruction operates on the complete cloud; no row/column sub-sampling
is performed before reconstruction.

Performance target: 500ms–2s.
"""
from __future__ import annotations

import logging

import numpy as np
import open3d as o3d

from .density_base import DensityAlgorithmBase, DensifyPoissonParams

logger = logging.getLogger(__name__)


class PoissonDensify(DensityAlgorithmBase):
    """
    Hybrid Poisson reconstruction densification — volumetric.

    Args:
        params:    DensifyPoissonParams instance, or None to use production defaults.
        log_level: Logging verbosity ('minimal' | 'full' | 'none').
    """

    def __init__(
        self,
        params: DensifyPoissonParams | None = None,
        log_level: str = "minimal",
    ) -> None:
        super().__init__(log_level=log_level)
        self.params: DensifyPoissonParams = params if params is not None else DensifyPoissonParams()

    def apply(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Preserve all original points and augment with n_new uniformly-sampled
        points from a Poisson-reconstructed mesh.

        Args:
            pcd:   Input tensor PointCloud.
            n_new: Number of synthetic points to generate.

        Returns:
            New tensor PointCloud containing original + synthetic points.
        """
        p = self.params
        pcd_legacy = pcd.to_legacy()
        try:
            pts_orig = np.asarray(pcd_legacy.points, dtype=np.float32)

            # Ensure normals for Poisson — full-cloud KNN search
            if not pcd_legacy.has_normals():
                pcd_legacy.estimate_normals(
                    o3d.geometry.KDTreeSearchParamKNN(knn=30)
                )
                pcd_legacy.normalize_normals()

            if self.log_level == "full":
                logger.debug(
                    "Densify[poisson]: n_orig=%d, n_new=%d, depth=%d, q=%.2f",
                    len(pts_orig), n_new, p.depth, p.density_threshold_quantile,
                )

            # Poisson reconstruction on the complete cloud
            mesh, densities = (
                o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                    pcd_legacy,
                    depth=p.depth,
                    width=0,
                    scale=1.1,
                    linear_fit=False,
                )
            )

            # Trim low-density vertices using configurable quantile
            densities_arr = np.asarray(densities)
            threshold = float(np.quantile(densities_arr, p.density_threshold_quantile))
            vertices_to_remove = densities_arr < threshold
            mesh.remove_vertices_by_mask(vertices_to_remove)

            # Guard: n_new capped at 7x original
            max_sample = int(len(pts_orig) * 7)
            n_sample = min(n_new, max_sample)
            if n_sample <= 0:
                n_sample = 1

            # Sample uniformly from the mesh
            sampled_legacy = mesh.sample_points_uniformly(number_of_points=n_sample)
            del mesh

            sampled_pts = np.asarray(sampled_legacy.points, dtype=np.float32)

            all_pts = np.vstack([pts_orig, sampled_pts])
            return self._make_tensor_pcd_from_positions(all_pts)
        finally:
            del pcd_legacy
