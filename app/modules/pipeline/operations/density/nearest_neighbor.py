"""
nearest_neighbor.py — Nearest Neighbour densification algorithm.
=================================================================

NearestNeighborDensify generates synthetic points by adding uniformly-random
3-D displacement vectors from randomly-selected source points, scaled by a
fraction of the **global** mean nearest-neighbour distance.

Global search guarantee
-----------------------
Mean NN distance is computed via a full-cloud scipy KDTree query over all N
points — no scanline sub-sampling, no ring grouping.  Displacement direction is
uniformly random in all three spatial axes, so both horizontal and vertical gaps
are filled.

Performance target: <100ms for 50k–100k pts (fast-mode SLA).
"""
from __future__ import annotations

import logging
import math

import numpy as np
import open3d as o3d

from .density_base import DensityAlgorithmBase, DensifyNNParams

logger = logging.getLogger(__name__)


class NearestNeighborDensify(DensityAlgorithmBase):
    """
    Nearest-neighbour densification — volumetric, sensor-agnostic.

    Args:
        params:    DensifyNNParams instance, or None to use production defaults.
    """

    def __init__(
        self,
        params: DensifyNNParams | None = None,
    ) -> None:
        self.params: DensifyNNParams = params if params is not None else DensifyNNParams()

    def apply(
        self,
        pcd: o3d.t.geometry.PointCloud,
        n_new: int,
    ) -> o3d.t.geometry.PointCloud:
        """
        Generate n_new synthetic points by 3-D jittered displacement from source
        points, using a global mean NN distance computed on the full cloud.

        Args:
            pcd:   Input tensor PointCloud.
            n_new: Number of synthetic points to generate.

        Returns:
            New tensor PointCloud containing original + n_new synthetic points.
        """
        p = self.params
        pts = pcd.point.positions.numpy().astype(np.float64)  # (N, 3)
        n_orig = len(pts)

        # Compute mean NN distance using a global scipy KDTree over ALL points.
        mean_nn_dist = self._compute_mean_nn_dist_global(pts)

        logger.debug(
            "Densify[nn]: n_orig=%d, n_new=%d, mean_nn_dist=%.4f, "
            "disp=[%.3f, %.3f]×mean_nn",
            n_orig, n_new, mean_nn_dist, p.displacement_min, p.displacement_max,
        )

        rng = np.random.default_rng()
        synthetic = np.empty((n_new, 3), dtype=np.float32)

        points_per_source = max(1, math.ceil(n_new / n_orig))
        idx = 0
        while idx < n_new:
            # Pick a random source point from the GLOBAL cloud
            src_idx = rng.integers(0, n_orig)
            src_pt = pts[src_idx]

            for _ in range(points_per_source):
                if idx >= n_new:
                    break
                # Uniformly random 3-D unit direction — no axis restriction
                direction = rng.standard_normal(3)
                norm = np.linalg.norm(direction)
                if norm < 1e-8:
                    direction = np.array([1.0, 0.0, 0.0], dtype=np.float64)
                else:
                    direction /= norm

                radius = rng.uniform(p.displacement_min, p.displacement_max) * mean_nn_dist
                synthetic[idx] = (src_pt + radius * direction).astype(np.float32)
                idx += 1

        orig_f32 = pts.astype(np.float32)
        all_pts = np.vstack([orig_f32, synthetic])  # (N + n_new, 3)
        return self._make_tensor_pcd_from_positions(all_pts)
