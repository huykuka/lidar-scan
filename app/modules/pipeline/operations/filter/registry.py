"""
Node registry for the filter_by_key operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="filter_by_key",
    display_name="Attribute Filter",
    category="operation",
    description="Filter points based on attribute values",
    icon="filter_alt",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="key", label="Attribute (e.g. intensity)", type="string", default="intensity",
                       help_text="Attribute name to filter on"),
        PropertySchema(name="operator", label="Operator", type="select", default=">", options=[
            {"label": "Greater Than (>)", "value": ">"},
            {"label": "Less Than (<)", "value": "<"},
            {"label": "Equals (==)", "value": "=="},
            {"label": "Not Equals (!=)", "value": "!="},
            {"label": "Greater/Eq (>=)", "value": ">="},
            {"label": "Less/Eq (<=)", "value": "<="}
        ],
                       help_text="Comparison operator for the filter"),
        PropertySchema(name="value", label="Threshold Value", type="number", default=100.0, step=1.0,
                       help_text="Value to compare against the attribute"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("filter_by_key")
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

    # Translate operator setting to array format expected by FilterByKey
    operator = op_config.pop("operator", "==")
    val = op_config.get("value")
    if operator != "==":
        op_config["value"] = [operator, val]

    return OperationNode(
        manager=service_context,
        node_id=node["id"],
        op_type="filter_by_key",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
