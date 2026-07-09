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
    use_case="Restrict the scan to a region of interest — e.g. keep only points inside a truck loading bay or remove the floor and ceiling of a warehouse scan.",
    icon="crop",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="min_bound", label="Min Bounds [X, Y, Z] (m)", type="vec3", default=[-10.0, -10.0, -2.0],
                       help_text="Lower XYZ bounds of the crop box in meters"),
        PropertySchema(name="max_bound", label="Max Bounds [X, Y, Z] (m)", type="vec3", default=[10.0, 10.0, 2.0],
                       help_text="Upper XYZ bounds of the crop box in meters"),
        PropertySchema(name="invert", label="Inverted", type="boolean", default=False,
                       help_text="Keep points outside the bounds instead of inside"),
    ],
    inputs=[PortSchema(id="in", label="Input", multiple=True)],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("crop")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("crop", node, service_context)
