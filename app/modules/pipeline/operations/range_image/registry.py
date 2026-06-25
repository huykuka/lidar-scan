"""
Node registry for the BEV range image operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="range_image",
    display_name="Range Image (BEV)",
    category="operation",
    description="Generate a Bird's-Eye View range image from the point cloud and stream it as PNG over WebSocket",
    use_case="Derived representation for downstream algorithms — converts the point cloud into a structured 2D grid that classical image processing and neural networks can consume directly. Use as the final stage before feeding height, density, or intensity maps into a CNN for object detection, as input to a 2D occupancy-grid planner, or to produce a live monitoring image. The raw point cloud is passed through unchanged so geometric pipeline stages can continue in parallel.",
    icon="image",
    websocket_enabled=True,
    properties=[
        PropertySchema(
            name="throttle_ms",
            label="Throttle (ms)",
            type="number",
            default=100,
            min=0,
            step=10,
            help_text="Minimum time between image frames in milliseconds (0 = no limit)",
        ),
        PropertySchema(
            name="resolution",
            label="Resolution (m/pixel)",
            type="number",
            default=0.1,
            min=0.01,
            step=0.01,
            help_text="Grid cell size in metres. Smaller = higher detail, more compute",
        ),
        PropertySchema(
            name="x_min",
            label="X Min (m)",
            type="number",
            default=-25.0,
            step=1.0,
            help_text="Left edge of the BEV area in metres",
        ),
        PropertySchema(
            name="x_max",
            label="X Max (m)",
            type="number",
            default=25.0,
            step=1.0,
            help_text="Right edge of the BEV area in metres",
        ),
        PropertySchema(
            name="y_min",
            label="Y Min (m)",
            type="number",
            default=-25.0,
            step=1.0,
            help_text="Bottom edge of the BEV area in metres",
        ),
        PropertySchema(
            name="y_max",
            label="Y Max (m)",
            type="number",
            default=25.0,
            step=1.0,
            help_text="Top edge of the BEV area in metres",
        ),
        PropertySchema(
            name="channel",
            label="Channel",
            type="select",
            default="height",
            options=[
                {"value": "height", "label": "Height (max Z per cell)"},
                {"value": "density", "label": "Density (point count per cell)"},
                {"value": "intensity", "label": "Intensity (mean per cell)"},
            ],
            help_text="Which signal to encode as brightness in the output image",
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output (pass-through)")],
))


# --- Factory Builder ---
@NodeFactory.register("range_image")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import OperationNode

    config = node.get("config", {})
    op_config = config.copy()
    op_config.pop("op_type", None)
    throttle_ms = op_config.pop("throttle_ms", 100)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 100.0

    return OperationNode(
        manager=service_context,
        node_id=node["id"],
        op_type="range_image",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
