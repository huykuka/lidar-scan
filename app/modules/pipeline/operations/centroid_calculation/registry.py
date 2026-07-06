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
    use_case="Find the centre of mass of a detected object — e.g. locate the midpoint of a cluster to anchor a pick-and-place coordinate, or normalise a segmented pallet to origin before pose estimation.",
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
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("centroid_calculation", node, service_context)
