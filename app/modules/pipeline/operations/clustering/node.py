from typing import Any, Dict, List

import numpy as np
import open3d as o3d

from ...base import PipelineOperation


class Clustering(PipelineOperation):
    """
    Clusters points using the DBSCAN algorithm and removes outliers (noise).

    Args:
        eps (float): Distance to neighbors in a cluster.
        min_points (int): Minimum number of points required to form a cluster.
        emit_shapes (bool): When True, compute per-cluster bounding boxes and emit
            CubeShape + LabelShape instances in the returned metadata under the key
            ``"shapes"``.  These are picked up by OperationNode and forwarded to
            NodeManager's ShapeCollectorMixin pipeline.
        min_cluster_points (int): Skip DBSCAN entirely if the input cloud has fewer
            than this many points.  Avoids paying the KD-tree construction cost on
            very sparse post-filter clouds.  Default 10.
    """

    def __init__(
        self,
        eps: float = 0.2,
        min_points: int = 10,
        emit_shapes: bool = False,
        min_cluster_points: int = 10,
    ):
        self.eps = float(eps)
        self.min_points = int(min_points)
        self.emit_shapes = bool(emit_shapes)
        self.min_cluster_points = int(min_cluster_points)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cluster_bbox(positions_np: np.ndarray, labels_np: np.ndarray, cluster_idx: int):
        """
        Compute (center, size, point_count) for one cluster directly from numpy arrays.

        This avoids the per-cluster Open3D PointCloud copy that the old implementation
        performed, which was O(clusters × N) in memory allocations per frame.
        """
        mask = labels_np == cluster_idx
        pts = positions_np[mask]
        if pts.shape[0] == 0:
            return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0
        center: List[float] = pts.mean(axis=0).tolist()
        size: List[float] = (pts.max(axis=0) - pts.min(axis=0)).tolist()
        return center, size, int(mask.sum())

    def _build_cluster_shapes(
        self, positions_np: np.ndarray, labels_np: np.ndarray, cluster_count: int
    ) -> List[Any]:
        """Build CubeShape for each detected cluster using pre-extracted numpy arrays."""
        from app.services.nodes.shapes import CubeShape

        shapes: List[Any] = []
        for i in range(cluster_count):
            try:
                center, size, _ = self._cluster_bbox(positions_np, labels_np, i)
                shapes.append(CubeShape(
                    center=center,
                    size=size,
                    color="#00ff00",
                    opacity=0.35,
                    wireframe=True,
                    label=f"cluster_{i}",
                ))
            except Exception:
                # Skip malformed individual cluster — don't abort the whole frame
                pass

        return shapes

    # ------------------------------------------------------------------
    # PipelineOperation.apply()
    # ------------------------------------------------------------------

    def apply(self, pcd: Any) -> tuple:
        if isinstance(pcd, o3d.t.geometry.PointCloud):
            count = pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
        else:
            count = len(pcd.points)

        # Early-exit guard: skip DBSCAN when the cloud is too sparse.
        # This avoids KD-tree construction cost on nearly-empty frames.
        if count < self.min_cluster_points:
            meta: Dict[str, Any] = {"cluster_count": 0}
            if self.emit_shapes:
                meta["shapes"] = []
            return pcd, meta

        if isinstance(pcd, o3d.t.geometry.PointCloud):
            labels = pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points, print_progress=False)
            mask = labels >= 0
            pcd_out = pcd.select_by_mask(mask)
            cluster_count = int(labels.max().item() + 1) if labels.shape[0] > 0 else 0

            meta = {"cluster_count": cluster_count}
            if self.emit_shapes and cluster_count > 0:
                positions_np = pcd.point.positions.numpy()
                labels_np = labels.numpy()
                meta["shapes"] = self._build_cluster_shapes(positions_np, labels_np, cluster_count)
            return pcd_out, meta

        else:
            labels_np = np.array(pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points))
            indices = np.where(labels_np >= 0)[0]
            pcd_out = pcd.select_by_index(indices)
            cluster_count = int(labels_np.max() + 1) if labels_np.size > 0 else 0
            meta = {"cluster_count": cluster_count}
            if self.emit_shapes and cluster_count > 0:
                positions_np = np.asarray(pcd.points)
                meta["shapes"] = self._build_cluster_shapes(positions_np, labels_np, cluster_count)
            return pcd_out, meta
