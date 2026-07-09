"""
Node registry for the coordinate transform operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry,
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="coordinate_transform",
    display_name="Coordinate Transform",
    category="operation",
    description="Applies translation, rotation, and scaling to the point cloud",
    use_case="Align a sensor frame to a world or robot coordinate system — e.g. rotate a roof-mounted LiDAR into the vehicle frame, shift a scan to match a known origin, or mirror a point cloud for symmetric inspection.",
    icon="transform",
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
            name="translation",
            label="Translation [X, Y, Z] (m)",
            type="vec3",
            default=[0.0, 0.0, 0.0],
            help_text="Offset along each axis in metres.",
        ),
        PropertySchema(
            name="rotation",
            label="Rotation [X, Y, Z] (deg)",
            type="vec3",
            default=[0.0, 0.0, 0.0],
            help_text="Euler rotation around each axis in degrees (applied X \u2192 Y \u2192 Z).",
        ),
        PropertySchema(
            name="scale",
            label="Scale [X, Y, Z]",
            type="vec3",
            default=[1.0, 1.0, 1.0],
            help_text="Per-axis scale factors (1.0 = no change).",
        ),
        PropertySchema(
            name="order",
            label="Composition Order",
            type="select",
            default="trs",
            options=[
                {"label": "Translate \u2192 Rotate \u2192 Scale (TRS)", "value": "trs"},
                {"label": "Scale \u2192 Rotate \u2192 Translate (SRT)", "value": "srt"},
            ],
            help_text="Order in which translation, rotation, and scale are composed.",
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")],
))


# --- Factory Builder ---
@NodeFactory.register("coordinate_transform")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("coordinate_transform", node, service_context)
