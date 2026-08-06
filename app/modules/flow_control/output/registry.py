"""
Node registry for the Output Node flow control module.

Registers the output_node type with the DAG orchestrator.
Follows the same pattern as if_condition/registry.py.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry,
)

# --- Schema Definition ---

node_schema_registry.register(NodeDefinition(
    type="output_node",
    display_name="Output",
    category="flow_control",
    description="Displays metadata from upstream node on a dedicated page",
    icon="dashboard",
    websocket_enabled=False,  # Metadata goes via system_status topic, not a node-specific WS topic
    properties=[
        PropertySchema(
            name="tcp_enabled",
            label="Enable TCP Stream",
            type="boolean",
            default=False,
            help_text="Expose a raw TCP server that fans out NDJSON frames to all connected clients",
        ),
        PropertySchema(
            name="tcp_port",
            label="TCP Port",
            type="integer",
            default=9000,
            help_text="Port the TCP stream server listens on (0.0.0.0). Requires restart to take effect.",
            depends_on={"tcp_enabled": [True]},
        ),
    ],
    inputs=[PortSchema(id="in", label="Input", data_type="pointcloud", multiple=True)],
    outputs=[],  # Terminal node — no downstream forwarding
))


# --- Factory Builder ---

@NodeFactory.register("output_node")
def build(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """
    Build an OutputNode instance from persisted node configuration.

    Args:
        node: Node configuration dictionary
        service_context: NodeManager reference
        edges: List of edge configurations (unused — terminal node has no outputs)

    Returns:
        OutputNode instance
    """
    from app.modules.flow_control.output.node import OutputNode  # Lazy import

    config = node.get("config", {})
    return OutputNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", node["id"]),
        config=config,
    )
