"""
Node registry for the generate_plane operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="generate_plane",
    display_name="Generate Plane Mesh",
    category="operation",
    description="Generates a planar triangle mesh from segmented point cloud",
    use_case="Produce a solid reference surface from a segmented plane — e.g. build a mesh of a conveyor belt or factory floor for collision checks, volume calculations, or AR overlay rendering.",
    icon="grid_on",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between frames (0 = no limit)"),
        PropertySchema(name="mode", label="Mode", type="select", default="square",
                       options=[
                           {"label": "Square (origin-centered)", "value": "square"},
                           {"label": "Boundary-Fitted", "value": "boundary"},
                       ],
                       help_text="Mesh generation mode"),
        PropertySchema(name="size", label="Size (m)", type="number", default=1.0, step=0.1, min=0.01,
                       help_text="Side length in meters (square mode only)"),
        PropertySchema(name="voxel_size", label="Vertex Spacing (m)", type="number",
                       default=0.05, step=0.005, min=0.001,
                       help_text="Grid vertex spacing in meters"),
        PropertySchema(name="plane_model", label="Plane Model [a,b,c,d]", type="vec4", default=None,
                       help_text="Optional override: plane coefficients. If None, auto-fitted via RANSAC."),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Vertices (as points)")]
))


# --- Factory Builder ---
@NodeFactory.register("generate_plane")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("generate_plane", node, service_context)
