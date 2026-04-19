"""
Node registry for the plane segmentation operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="plane_segmentation",
    display_name="Plane Segmentation",
    category="operation",
    description="Segments a plane from the point cloud using RANSAC",
    icon="layers",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="distance_threshold", label="Distance Threshold", type="number", default=0.1, step=0.01,
                       help_text="Max distance from plane to be considered an inlier"),
        PropertySchema(name="ransac_n", label="RANSAC N", type="number", default=3, min=3,
                       help_text="Number of points sampled per RANSAC iteration"),
        PropertySchema(name="num_iterations", label="Max Iterations", type="number", default=1000, step=10,
                       help_text="Maximum RANSAC iterations"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("plane_segmentation")
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
        op_type="plane_segmentation",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
