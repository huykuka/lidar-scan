"""
Node registry for the debug_save operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="debug_save",
    display_name="Save PCD",
    category="operation",
    description="Saves point cloud to PCD files",
    icon="save",
    websocket_enabled=False,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="output_dir", label="Output Directory", type="string", default="debug_output",
                       help_text="Directory to write output PCD files"),
        PropertySchema(name="prefix", label="File Prefix", type="string", default="pcd",
                       help_text="Filename prefix for saved PCD files"),
        PropertySchema(name="max_keeps", label="Max Keeps", type="number", default=10, min=1,
                       help_text="Maximum number of files to keep"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("debug_save")
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
        op_type="debug_save",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
