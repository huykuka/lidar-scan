"""
statistical.py — Statistical upsampling densification algorithm.
=================================================================

StatisticalDensify computes per-point local density using a **global** KDTree query,
identifies sparse 3-D regions, and interpolates new points along edges to existing
neighbours with alpha in [0.3, 0.7].

Global search guarantee
-----------------------
KDTree is built on *all* points; no axis-specific neighbourhood restriction.

Performance target: 100–300ms (medium-mode SLA).
"""
from __future__ import annotations

import logging
import math

import numpy as np
import open3d as o3d

from .density_base import DensityAlgorithmBase, DensifyStatisticalParams

logger = logging.getLogger(__name__)


class StatisticalDensify(DensityAlgorithmBase):
    """
    Statistical upsampling densification — volumetric, sensor-agnostic.

    Args:
        params:    DensifyStatisticalParams instance, or None for production defaults.
    """

    def __init__(
        self,
        params: DensifyStatisticalParams | None = None,
    ) -> None:
        self.params: DensifyStatisticalParams = (
            params if params is not None else DensifyStatisticalParams()
        )

    def apply(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Generate n_new synthetic points by statistical sparse-region interpolation.

        Falls back to nearest-neighbour if statistical produces nothing.

        Args:
            pcd:   Input tensor PointCloud.
            n_new: Number of synthetic points to generate.

        Returns:
            New tensor PointCloud containing original + synthetic points.
        """
        from scipy.spatial import KDTree  # lazy import

        p = self.params
        pts = pcd.point.positions.numpy().astype(np.float64)
        n_orig = len(pts)

        # Global KDTree — full cloud, no per-ring or per-scanline restriction
        kd_tree = KDTree(pts)
        k_total = min(p.k_neighbors + 1, n_orig)  # +1 for self
        dists, idxs = kd_tree.query(pts, k=k_total)

        # Exclude self (col 0)
        dists = dists[:, 1:]    # (N, k_neighbors)
        idxs = idxs[:, 1:]      # (N, k_neighbors)

        # Local density: k / volume_of_sphere(radius = max_dist)
        max_dist = dists[:, -1]
        max_dist = np.where(max_dist < 1e-8, 1e-8, max_dist)
        local_density = (k_total - 1) / ((4.0 / 3.0) * math.pi * (max_dist ** 3))

        # Mean NN dist for min_dist filter (global, all directions)
        mean_nn_dist = float(dists[:, 0].mean()) if dists.size > 0 else 0.01
        min_dist = mean_nn_dist * p.min_dist_factor

        # Sparse-region points: bottom sparse_percentile of volumetric density
        percentile_val = float(np.percentile(local_density, p.sparse_percentile))
        sparse_mask = local_density < percentile_val
        sparse_indices = np.where(sparse_mask)[0]

        logger.debug(
            "Densify[statistical]: n_orig=%d, n_new=%d, k=%d, "
            "sparse_pct=%.0f, n_sparse=%d, min_dist=%.4f",
            n_orig, n_new, p.k_neighbors, p.sparse_percentile,
            len(sparse_indices), min_dist,
        )

        rng = np.random.default_rng()
        synthetic_list = []
        budget = n_new

        if len(sparse_indices) > 0:
            n_neighbors = dists.shape[1]
            pts_per_sparse = max(1, math.ceil(budget / (len(sparse_indices) * n_neighbors)))

            for src_i in sparse_indices:
                if budget <= 0:
                    break
                p_i = pts[src_i]
                for j in range(n_neighbors):
                    if budget <= 0:
                        break
                    p_j = pts[idxs[src_i, j]]
                    for _ in range(pts_per_sparse):
                        if budget <= 0:
                            break
                        alpha = rng.uniform(0.3, 0.7)
                        # Interpolation in full 3-D space — no axis clamping
                        new_pt = (1.0 - alpha) * p_i + alpha * p_j
                        synthetic_list.append(new_pt)
                        budget -= 1

        if len(synthetic_list) == 0:
            # Fallback to NN if statistical produced nothing
            from .nearest_neighbor import NearestNeighborDensify

            nn_algo = NearestNeighborDensify()
            return nn_algo.apply(pcd, n_new)

        synthetic = np.array(synthetic_list, dtype=np.float32)

        # Post-filter: remove points too close to existing (global KDTree)
        if min_dist > 0:
            synthetic = self._filter_too_close(synthetic, kd_tree, min_dist)

        # Trim or pad to n_new
        if len(synthetic) > n_new:
            synthetic = synthetic[:n_new]

        orig_f32 = pts.astype(np.float32)
        all_pts = np.vstack([orig_f32, synthetic])
        return self._make_tensor_pcd_from_positions(all_pts)
