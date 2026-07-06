"""
Node registry for the boundary detection operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="boundary_detection",
    display_name="Boundary Detection",
    category="operation",
    description="Detects boundary points based on angle criteria",
    use_case="Extract the outline of objects or surfaces — e.g. trace the perimeter of a pallet, detect the open edges of a truck loading bay, or find the rim of a container bin.",
    icon="timeline",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="radius", label="Radius (m)", type="number", default=0.02, step=0.01,
                       help_text="Search radius in meters for boundary point analysis"),
        PropertySchema(name="max_nn", label="Max Neighbors", type="number", default=30, min=1,
                       help_text="Maximum nearest neighbors to consider per point"),
        PropertySchema(name="angle_threshold", label="Angle Threshold (°)", type="number", default=90.0, step=1.0,
                       help_text="Boundary angle threshold in degrees"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("boundary_detection")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("boundary_detection", node, service_context)
