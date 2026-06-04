"""
Node registry for the edge detection operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="edge_detection",
    display_name="Edge Detection",
    category="operation",
    description="Centroid-gradient edge detection (Xia & Wang 2017) with optional NMS",
    icon="border_style",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="radius", label="Radius (m)", type="number", default=0.12, step=0.01,
                       help_text="Neighbour search radius in metres"),
        PropertySchema(name="max_nn", label="Max Neighbors", type="number", default=200, min=1,
                       help_text="Maximum neighbours per point for edge-index computation"),
        PropertySchema(name="threshold", label="Edge-Index Threshold", type="number", default=0.15, step=0.01,
                       min=0.0, max=1.0,
                       help_text="Edge-index threshold (0-1). Higher = fewer, sharper edges"),
        PropertySchema(name="nms", label="Non-Maximum Suppression", type="boolean", default=True,
                       help_text="Enable gradient-guided NMS to thin edges"),
        PropertySchema(name="nms_cos_threshold", label="NMS Cosine Threshold", type="number",
                       default=0.95, step=0.01, min=0.0, max=1.0,
                       help_text="Cosine similarity for NMS gradient direction test",
                       depends_on={"nms": [True]}),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("edge_detection")
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
        op_type="edge_detection",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
