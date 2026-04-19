from typing import Any, Dict, List

import numpy as np
import open3d as o3d

from ..base import PipelineOperation


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
    """

    def __init__(self, eps: float = 0.2, min_points: int = 10, emit_shapes: bool = False):
        self.eps = float(eps)
        self.min_points = int(min_points)
        self.emit_shapes = bool(emit_shapes)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cluster_bbox_legacy(
        pcd_legacy: "o3d.geometry.PointCloud",
        labels: np.ndarray,
        cluster_idx: int,
    ):
        """Return (center list, size list) for a single cluster from a legacy PointCloud."""
        mask = labels == cluster_idx
        indices = np.where(mask)[0].tolist()
        cluster_pcd = pcd_legacy.select_by_index(indices)
        bbox = cluster_pcd.get_axis_aligned_bounding_box()
        center: List[float] = bbox.get_center().tolist()
        size: List[float] = bbox.get_extent().tolist()
        point_count: int = len(indices)
        return center, size, point_count

    @staticmethod
    def _cluster_bbox_tensor(
        pcd_tensor: "o3d.t.geometry.PointCloud",
        labels: Any,
        cluster_idx: int,
    ):
        """Return (center list, size list) for a single cluster from a tensor PointCloud."""
        # labels is an o3d.core.Tensor of shape (N,)
        labels_np: np.ndarray = labels.numpy()
        mask_np = (labels_np == cluster_idx)
        indices = np.where(mask_np)[0].tolist()
        cluster_pcd = pcd_tensor.select_by_index(indices)
        # Convert to legacy for AABB computation (simpler API)
        pos = cluster_pcd.point.positions.numpy()
        legacy_pcd = o3d.geometry.PointCloud()
        legacy_pcd.points = o3d.utility.Vector3dVector(pos)
        bbox = legacy_pcd.get_axis_aligned_bounding_box()
        center: List[float] = bbox.get_center().tolist()
        size: List[float] = bbox.get_extent().tolist()
        point_count: int = len(indices)
        return center, size, point_count

    def _build_cluster_shapes(
        self, pcd: Any, labels: Any, cluster_count: int, is_tensor: bool
    ) -> List[Any]:
        """Build CubeShape + LabelShape for each detected cluster."""
        from app.services.nodes.shapes import CubeShape, LabelShape

        shapes: List[Any] = []
        for i in range(cluster_count):
            try:
                if is_tensor:
                    center, size, pt_count = self._cluster_bbox_tensor(pcd, labels, i)
                else:
                    center, size, pt_count = self._cluster_bbox_legacy(pcd, labels, i)

                # Bounding box wireframe cube
                shapes.append(CubeShape(
                    center=center,
                    size=size,
                    color="#00ff00",
                    opacity=0.35,
                    wireframe=True,
                    label=f"cluster_{i}",
                ))

                # Billboard label positioned at top centre of the bbox
                label_pos = [center[0], center[1], center[2] + size[2] / 2.0]
                shapes.append(LabelShape(
                    position=label_pos,
                    text=f"cluster_{i} ({pt_count} pts)",
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

        if count > 0:
            if isinstance(pcd, o3d.t.geometry.PointCloud):
                labels = pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points, print_progress=False)
                mask = labels >= 0
                pcd_out = pcd.select_by_mask(mask)
                cluster_count = int(labels.max().item() + 1) if labels.shape[0] > 0 else 0

                meta: Dict[str, Any] = {"cluster_count": cluster_count}
                if self.emit_shapes and cluster_count > 0:
                    meta["shapes"] = self._build_cluster_shapes(
                        pcd, labels, cluster_count, is_tensor=True
                    )
                return pcd_out, meta

            else:
                labels = np.array(pcd.cluster_dbscan(eps=self.eps, min_points=self.min_points))
                indices = np.where(labels >= 0)[0]
                pcd_out = pcd.select_by_index(indices)
                cluster_count = int(labels.max() + 1) if labels.size > 0 else 0
                meta = {"cluster_count": cluster_count}
                if self.emit_shapes and cluster_count > 0:
                    meta["shapes"] = self._build_cluster_shapes(
                        pcd, labels, cluster_count, is_tensor=False
                    )
                return pcd_out, meta

        meta = {"cluster_count": 0}
        if self.emit_shapes:
            meta["shapes"] = []
        return pcd, meta
