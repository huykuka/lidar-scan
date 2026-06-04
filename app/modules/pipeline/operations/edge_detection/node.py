from typing import Any, Dict, Tuple

import numpy as np
import open3d as o3d

from ...base import PipelineOperation


class EdgeDetection(PipelineOperation):
    """
    Centroid-gradient edge detection for 3D point clouds.

    Based on Xia & Wang (2017) "A fast edge extraction method for mobile
    LiDAR point clouds".  For each point the *edge index* is computed as
    the normalised distance between the point and the centroid of its
    neighbourhood — points on sharp geometric features (ridges, corners,
    object edges) have high edge indices because the centroid shifts away
    from them.

    An optional gradient-guided non-maximum suppression (NMS) step thins
    the detected edges to single-point-wide ridges.

    Args:
        radius: Neighbour search radius in metres.
        max_nn: Maximum neighbours per point.
        threshold: Edge-index threshold (0-1).  Higher values yield
            fewer, more prominent edges.
        invert: When False (default) output edge points; when True
            output the inlier (non-edge) points instead.
        nms: Enable gradient-guided non-maximum suppression.
        nms_cos_threshold: Cosine similarity threshold for the NMS
            gradient direction test (0-1).
    """

    def __init__(
        self,
        radius: float = 0.12,
        max_nn: int = 200,
        threshold: float = 0.15,
        invert: bool = False,
        nms: bool = True,
        nms_cos_threshold: float = 0.95,
    ) -> None:
        self.radius = float(radius)
        self.max_nn = int(max_nn)
        self.threshold = float(threshold)
        self.invert = bool(invert)
        self.nms = bool(nms)
        self.nms_cos_threshold = float(nms_cos_threshold)

    # ------------------------------------------------------------------
    # Core algorithm
    # ------------------------------------------------------------------

    def _detect_edges(
        self, pcd: o3d.geometry.PointCloud
    ) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """Run centroid-gradient edge detection on a *legacy* PointCloud."""
        points = np.asarray(pcd.points)
        n_points = len(points)
        if n_points == 0:
            return pcd, {"edge_count": 0, "original_count": 0}

        tree = o3d.geometry.KDTreeFlann(pcd)

        # --- Step 1: compute per-point edge index ----------------------
        edge_index = np.zeros(n_points, dtype=np.float64)

        # Pre-build neighbour lists (reused in NMS)
        neighbours: list[np.ndarray] = []

        for i in range(n_points):
            k, idx, _ = tree.search_hybrid_vector_3d(
                points[i], self.radius, self.max_nn
            )
            idx_arr = np.asarray(idx)
            neighbours.append(idx_arr)

            if k <= 1:
                continue

            nb_pts = points[idx_arr]
            centroid = nb_pts.mean(axis=0)

            # Distance from the point to its neighbourhood centroid
            dist_to_centroid = np.linalg.norm(points[i] - centroid)

            # Normalise by farthest neighbour distance
            dists_to_nbs = np.linalg.norm(nb_pts - points[i], axis=1)
            max_dist = dists_to_nbs.max()
            if max_dist < 1e-8:
                continue

            edge_index[i] = dist_to_centroid / max_dist

        # --- Step 2: threshold -----------------------------------------
        edge_mask = edge_index >= self.threshold

        # --- Step 3 (optional): gradient-guided NMS --------------------
        if self.nms:
            # Compute gradient orientation for every point
            gradient_dir = np.zeros((n_points, 3), dtype=np.float64)
            for i in range(n_points):
                idx_arr = neighbours[i]
                if len(idx_arr) <= 1:
                    continue
                diffs = np.abs(edge_index[i] - edge_index[idx_arr])
                max_id = np.argmax(diffs)
                direction = points[idx_arr[max_id]] - points[i]
                norm = np.linalg.norm(direction)
                if norm > 1e-8:
                    gradient_dir[i] = direction / norm

            # Suppress non-maxima along the gradient direction
            suppressed = edge_index.copy()
            for i in range(n_points):
                if not edge_mask[i]:
                    continue
                idx_arr = neighbours[i]
                if len(idx_arr) <= 1:
                    continue

                nb_pts = points[idx_arr]
                deltas = nb_pts - points[i]
                norms = np.linalg.norm(deltas, axis=1)
                norms[norms < 1e-8] = 1e-8
                orientations = deltas / norms[:, np.newaxis]

                cos_sim = np.abs((orientations * gradient_dir[i]).sum(axis=1))
                along_grad = idx_arr[cos_sim > self.nms_cos_threshold]

                if len(along_grad) > 0 and (edge_index[along_grad] > edge_index[i]).any():
                    suppressed[i] = 0.0

            edge_mask = suppressed >= self.threshold

        edge_indices = np.where(edge_mask)[0]
        result_pcd = pcd.select_by_index(edge_indices.tolist(), invert=self.invert)

        return result_pcd, {
            "edge_count": int(len(edge_indices)),
            "original_count": int(n_points),
            "inverted": self.invert,
        }

    # ------------------------------------------------------------------
    # PipelineOperation interface
    # ------------------------------------------------------------------

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            legacy = pcd.to_legacy()
            edge_legacy, meta = self._detect_edges(legacy)
            edge_tensor = o3d.t.geometry.PointCloud.from_legacy(edge_legacy)
            return edge_tensor, meta

        return self._detect_edges(pcd)
