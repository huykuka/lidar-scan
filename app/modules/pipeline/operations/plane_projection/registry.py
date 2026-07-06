"""
Node registry for the plane projection operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="plane_projection",
    display_name="Plane Projection",
    category="operation",
    description="Project the point cloud onto an axis-aligned plane (XY, XZ, or YZ) by zeroing the chosen axis",
    use_case="Geometric processing step — collapses one spatial dimension to simplify subsequent measurements. Use before boundary detection to trace a 2D footprint, before area or width calculations that only require two axes, or to normalise scan data to a reference plane before comparing frames. The projected cloud remains a point cloud and flows to the next node unchanged in all other attributes.",
    icon="layers",
    websocket_enabled=True,
    properties=[
        PropertySchema(
            name="throttle_ms",
            label="Throttle (ms)",
            type="number",
            default=0,
            min=0,
            step=10,
            help_text="Minimum time between processing frames (0 = no limit)",
        ),
        PropertySchema(
            name="axis",
            label="Drop Axis",
            type="select",
            default="z",
            options=[
                {"value": "z", "label": "Z → project onto XY plane (top-down)"},
                {"value": "y", "label": "Y → project onto XZ plane (front)"},
                {"value": "x", "label": "X → project onto YZ plane (side)"},
            ],
            help_text="The axis whose coordinate is set to 0. "
                      "'z' gives a bird's-eye / floor projection.",
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")],
))


# --- Factory Builder ---
@NodeFactory.register("plane_projection")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("plane_projection", node, service_context)
