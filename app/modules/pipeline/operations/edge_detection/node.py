"""
edge_detection/node.py — Centroid-gradient edge detection.

Uses scipy.spatial.cKDTree for neighbour queries instead of Open3D's
KDTreeFlann, eliminating the Open3D dependency for this node.
The detection algorithm (Xia & Wang 2017) is otherwise unchanged.
"""
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.spatial import cKDTree

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

    # Heavy CPU loop — OperationNode will use a dedicated single-thread executor.
    PREFERS_LEGACY = False

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
    # Core algorithm (pure numpy + scipy)
    # ------------------------------------------------------------------

    def _detect_edges_numpy(
        self, points: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Run centroid-gradient edge detection on an (N, 3) float64 array."""
        n = len(points)
        if n == 0:
            return points, {"edge_count": 0, "original_count": 0}

        tree = cKDTree(points)

        # --- Step 1: per-point edge index ---------------------------------
        # query_ball_point returns variable-length lists; cap at max_nn
        all_neighbours: List[np.ndarray] = tree.query_ball_point(
            points, r=self.radius, workers=-1
        )

        edge_index = np.zeros(n, dtype=np.float64)

        for i in range(n):
            idx = np.asarray(all_neighbours[i], dtype=np.int64)
            if len(idx) <= 1:
                continue
            # Enforce max_nn cap (query_ball_point has no built-in limit)
            if len(idx) > self.max_nn:
                # Keep closest max_nn neighbours
                dists = np.linalg.norm(points[idx] - points[i], axis=1)
                idx = idx[np.argpartition(dists, self.max_nn)[:self.max_nn]]
                all_neighbours[i] = idx

            nb_pts = points[idx]
            centroid = nb_pts.mean(axis=0)
            dist_to_centroid = np.linalg.norm(points[i] - centroid)
            max_dist = np.linalg.norm(nb_pts - points[i], axis=1).max()
            if max_dist < 1e-8:
                continue
            edge_index[i] = dist_to_centroid / max_dist

        # --- Step 2: threshold --------------------------------------------
        edge_mask = edge_index >= self.threshold

        # --- Step 3 (optional): gradient-guided NMS -----------------------
        if self.nms:
            gradient_dir = np.zeros((n, 3), dtype=np.float64)
            for i in range(n):
                idx = np.asarray(all_neighbours[i])
                if len(idx) <= 1:
                    continue
                diffs = np.abs(edge_index[i] - edge_index[idx])
                max_id = np.argmax(diffs)
                direction = points[idx[max_id]] - points[i]
                norm = np.linalg.norm(direction)
                if norm > 1e-8:
                    gradient_dir[i] = direction / norm

            suppressed = edge_index.copy()
            for i in range(n):
                if not edge_mask[i]:
                    continue
                idx = np.asarray(all_neighbours[i])
                if len(idx) <= 1:
                    continue
                deltas = points[idx] - points[i]
                norms = np.linalg.norm(deltas, axis=1)
                norms[norms < 1e-8] = 1e-8
                orientations = deltas / norms[:, np.newaxis]
                cos_sim = np.abs((orientations * gradient_dir[i]).sum(axis=1))
                along_grad = idx[cos_sim > self.nms_cos_threshold]
                if len(along_grad) > 0 and (edge_index[along_grad] > edge_index[i]).any():
                    suppressed[i] = 0.0

            edge_mask = suppressed >= self.threshold

        edge_indices = np.where(edge_mask)[0]

        if self.invert:
            result = points[~edge_mask]
        else:
            result = points[edge_indices]

        return result, {
            "edge_count": int(len(edge_indices)),
            "original_count": int(n),
            "inverted": self.invert,
        }

    # ------------------------------------------------------------------
    # PipelineOperation interface
    # ------------------------------------------------------------------

    def apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]:
        import open3d as o3d
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            pts = pcd.point.positions.cpu().numpy().astype(np.float64)
            result_pts, meta = self._detect_edges_numpy(pts)
            # Wrap back into a minimal tensor PCD (positions only)
            out = o3d.t.geometry.PointCloud()
            if result_pts.shape[0] > 0:
                out.point.positions = o3d.core.Tensor(
                    result_pts.astype(np.float32)
                )
            return out, meta

        if isinstance(pcd, o3d.geometry.PointCloud):
            pts = np.asarray(pcd.points, dtype=np.float64)
            result_pts, meta = self._detect_edges_numpy(pts)
            out = o3d.geometry.PointCloud()
            out.points = o3d.utility.Vector3dVector(result_pts)
            return out, meta

        raise TypeError(f"EdgeDetection: unsupported pcd type {type(pcd)}")
