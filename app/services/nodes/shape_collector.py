"""
ShapeCollectorMixin — opt-in mixin for DAG nodes that emit 3D shapes per frame.

Any DAG node that wants to emit shapes inherits this mixin alongside ModuleNode.
Shapes are buffered in _pending_shapes during on_input(), then collected by
NodeManager after on_input() returns (via DataRouter.publish_shapes()).
"""
from __future__ import annotations

from typing import List

from app.services.nodes.shapes import ShapePayload


class ShapeCollectorMixin:
    """Opt-in mixin for nodes that emit 3D shapes per frame."""

    def __init__(self):
        self._pending_shapes: List[ShapePayload] = []

    def emit_shape(self, shape: ShapePayload) -> None:
        """Buffer one shape for this processing frame."""
        self._pending_shapes.append(shape)

    def collect_and_clear_shapes(self) -> List[ShapePayload]:
        """
        Return all buffered shapes and clear the buffer.

        Called by NodeManager (DataRouter.publish_shapes()) after on_input() returns.
        No locking needed — called from the asyncio event loop after
        asyncio.to_thread() returns.
        """
        shapes = list(self._pending_shapes)
        self._pending_shapes.clear()
        return shapes
