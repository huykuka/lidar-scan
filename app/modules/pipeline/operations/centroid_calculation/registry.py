"""
Node registry for the centroid calculation operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry,
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="centroid_calculation",
    display_name="Centroid Calculation",
    category="operation",
    description="Computes the geometric centroid (mean XYZ) of the point cloud and optionally centres it at the origin",
    icon="adjust",
    websocket_enabled=True,
    properties=[
        PropertySchema(
            name="throttle_ms",
            label="Throttle (ms)",
            type="number",
            default=0,
            min=0,
            step=10,
            help_text="Minimum wait time between frames. 0 = process every frame.",
        ),
        PropertySchema(
            name="center_cloud",
            label="Centre Cloud at Origin",
            type="boolean",
            default=False,
            help_text="Translate the point cloud so its centroid is at (0, 0, 0). "
                      "Turn off to compute the centroid without moving the data.",
        ),
        PropertySchema(
            name="compute_per_axis_stats",
            label="Per-Axis Statistics",
            type="boolean",
            default=False,
            help_text="Also report per-axis min, max, and standard deviation "
                      "in the node metadata.",
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")],
))


# --- Factory Builder ---
@NodeFactory.register("centroid_calculation")
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
        op_type="centroid_calculation",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
