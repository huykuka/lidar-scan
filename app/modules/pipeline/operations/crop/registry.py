"""
Node registry for the crop operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="crop",
    display_name="Crop Filter",
    category="operation",
    description="Filter points within/outside bounding box",
    icon="crop",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="min_bound", label="Min Bounds [X, Y, Z]", type="vec3", default=[-10.0, -10.0, -2.0],
                       help_text="Lower XYZ bounds of the crop box"),
        PropertySchema(name="max_bound", label="Max Bounds [X, Y, Z]", type="vec3", default=[10.0, 10.0, 2.0],
                       help_text="Upper XYZ bounds of the crop box"),
        PropertySchema(name="invert", label="Inverted", type="boolean", default=False,
                       help_text="Keep points outside the bounds instead of inside"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("crop")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import OperationNode
    config = node.get("config", {})
    op_config = config.copy()
    op_config.pop("op_type", None)
    throttle_ms = op_config.pop("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    return OperationNode(
        manager=service_context,
        node_id=node["id"],
        op_type="crop",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
