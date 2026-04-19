"""
BoundingBoxEmitterNode — Example application node that emits 3D bounding boxes
as shapes over the 'shapes' WebSocket topic.

This node demonstrates how to use ShapeCollectorMixin alongside ModuleNode to
emit CubeShape (axis-aligned bounding box) and LabelShape overlays derived from
Open3D AxisAlignedBoundingBox computations.

Usage in DAG:
    Connect this node downstream of any point-cloud emitting node.
    It will compute an AABB for the incoming point cloud and emit it as a
    CubeShape (wireframe green box) plus a LabelShape annotation.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.core.logging import get_logger
from app.modules.application.base_node import ApplicationNode
from app.services.nodes.shape_collector import ShapeCollectorMixin
from app.services.nodes.shapes import CubeShape, LabelShape

logger = get_logger(__name__)


class BoundingBoxEmitterNode(ApplicationNode, ShapeCollectorMixin):
    """
    DAG node that computes axis-aligned bounding boxes from point cloud data
    and emits them as 3D shapes for the shape overlay layer.

    Inherits from both ApplicationNode and ShapeCollectorMixin so it can
    participate in normal DAG data routing AND emit shapes collected by
    NodeManager's DataRouter.publish_shapes().
    """

    def __init__(self, node_id: str, name: str, manager: Any, config: Dict[str, Any] = None):
        ApplicationNode.__init__(self)
        ShapeCollectorMixin.__init__(self)
        self.id = node_id
        self.name = name
        self.manager = manager
        self.config = config or {}

        # Visual style config (can be overridden via node config)
        self.color: str = self.config.get("color", "#00ff00")
        self.opacity: float = float(self.config.get("opacity", 0.4))
        self.wireframe: bool = bool(self.config.get("wireframe", True))

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """
        Receive point cloud data, compute AABB via Open3D, and emit a CubeShape + LabelShape.

        The heavy Open3D computation runs on a thread to avoid blocking the event loop.
        """
        points = payload.get("points")
        if points is None or len(points) == 0:
            # Forward downstream with no shapes emitted
            await self.manager.forward_data(self.id, payload)
            return

        try:
            center, size, point_count = await asyncio.to_thread(
                self._compute_bbox, points
            )

            # Emit bounding box as a CubeShape
            self.emit_shape(CubeShape(
                center=center,
                size=size,
                color=self.color,
                opacity=self.opacity,
                wireframe=self.wireframe,
                label=f"{self.name} ({point_count} pts)",
            ))

            # Emit a label at the top of the bounding box
            label_position = [center[0], center[1], center[2] + size[2] / 2.0]
            self.emit_shape(LabelShape(
                position=label_position,
                text=f"{self.name}  ({point_count} pts)",
            ))

        except Exception as e:
            logger.error(f"BoundingBoxEmitterNode '{self.name}': bbox computation failed: {e}")

        # Forward unchanged data downstream
        await self.manager.forward_data(self.id, payload)

    @staticmethod
    def _compute_bbox(points) -> tuple[list[float], list[float], int]:
        """
        Compute axis-aligned bounding box from a numpy point array.

        Runs on a thread (called via asyncio.to_thread).

        Returns:
            center: [x, y, z] in world units
            size: [sx, sy, sz] full extents in world units
            point_count: number of points in the cloud
        """
        import numpy as np

        pts = np.asarray(points)
        if pts.ndim != 2 or pts.shape[1] < 3:
            raise ValueError(f"Expected Nx3+ array, got shape {pts.shape}")

        xyz = pts[:, :3]

        try:
            import open3d as o3d
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(xyz)
            bbox = pcd.get_axis_aligned_bounding_box()
            center = bbox.get_center().tolist()
            size = bbox.get_extent().tolist()
        except ImportError:
            # Fallback when Open3D is not available (e.g., in testing)
            min_coords = xyz.min(axis=0)
            max_coords = xyz.max(axis=0)
            center = ((min_coords + max_coords) / 2.0).tolist()
            size = (max_coords - min_coords).tolist()

        return center, size, len(xyz)
