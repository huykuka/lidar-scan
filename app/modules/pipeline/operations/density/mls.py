"""
mls.py — Moving Least Squares (MLS) densification algorithm.
=============================================================

MLSDensify projects synthetic points onto the tangent plane of randomly-selected
source points.  Tangent planes are computed from global neighbourhood normals, so
vertical surfaces, ground planes, and diagonal structures are all treated identically.

Global search guarantee
-----------------------
All neighbour queries use a global scipy KDTree built on the complete input cloud —
no per-ring or per-scanline neighbourhood restriction.

Performance target: <500ms for 50k–100k pts (high-mode SLA).
"""
from __future__ import annotations

import logging
import math

import numpy as np
import open3d as o3d

from .density_base import DensityAlgorithmBase, DensifyMLSParams

logger = logging.getLogger(__name__)


class MLSDensify(DensityAlgorithmBase):
    """
    Moving Least Squares tangent-plane projection densification — volumetric.

    Args:
        params:    DensifyMLSParams instance, or None to use production defaults.
    """

    def __init__(
        self,
        params: DensifyMLSParams | None = None,
    ) -> None:
        self.params: DensifyMLSParams = params if params is not None else DensifyMLSParams()

    def apply(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Generate n_new synthetic points via tangent-plane projection on the
        full-cloud KDTree neighbourhood.

        Args:
            pcd:   Input tensor PointCloud.
            n_new: Number of synthetic points to generate.

        Returns:
            New tensor PointCloud containing original + synthetic points.
        """
        from scipy.spatial import KDTree  # lazy import

        p = self.params
        pcd_legacy = pcd.to_legacy()
        try:
            pts = np.asarray(pcd_legacy.points, dtype=np.float64)
            n_orig = len(pts)

            # Ensure normals for tangent plane construction.
            if not pcd_legacy.has_normals():
                pcd_legacy.estimate_normals(
                    o3d.geometry.KDTreeSearchParamKNN(knn=p.k_neighbors)
                )
                pcd_legacy.normalize_normals()
            norms = np.asarray(pcd_legacy.normals, dtype=np.float64)  # (N, 3)

            # Global mean NN distance — full-cloud scipy KDTree
            mean_nn_dist = self._compute_mean_nn_dist_global(pts)
            projection_radius = mean_nn_dist * p.projection_radius_factor
            min_dist = mean_nn_dist * p.min_dist_factor

            logger.debug(
                "Densify[mls]: n_orig=%d, n_new=%d, k=%d, "
                "proj_r=%.4f, min_dist=%.4f",
                n_orig, n_new, p.k_neighbors, projection_radius, min_dist,
            )

            # Global KDTree for duplicate filtering
            kd_tree = KDTree(pts)
            rng = np.random.default_rng()

            synthetic = np.empty((n_new, 3), dtype=np.float32)
            points_per_source = max(1, math.ceil(n_new / n_orig))
            idx = 0
            while idx < n_new:
                # Select source point from the GLOBAL cloud
                src_idx = rng.integers(0, n_orig)
                pt = pts[src_idx]
                n = norms[src_idx]

                # Build tangent plane basis {u, v}
                u, v = self._tangent_basis(n)
                sigma = projection_radius / 3.0

                for _ in range(points_per_source):
                    if idx >= n_new:
                        break
                    su = rng.uniform(-sigma, sigma)
                    sv = rng.uniform(-sigma, sigma)
                    new_pt = pt + su * u + sv * v
                    synthetic[idx] = new_pt.astype(np.float32)
                    idx += 1

            # Post-filter: remove synthetic pts within min_dist of any existing pt
            if min_dist > 0:
                synthetic = self._filter_too_close(synthetic, kd_tree, min_dist)

            orig_f32 = pts.astype(np.float32)
            all_pts = np.vstack([orig_f32, synthetic])
            return self._make_tensor_pcd_from_positions(all_pts)
        finally:
            del pcd_legacy
