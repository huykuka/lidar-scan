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
            name="webhook_enabled",
            label="Enable Webhook",
            type="boolean",
            default=False,
        ),
        PropertySchema(
            name="webhook_url",
            label="Webhook POST URL",
            type="string",
            default="",
            help_text="HTTPS endpoint to receive metadata payloads",
            depends_on={"webhook_enabled": [True]},
        ),
        PropertySchema(
            name="webhook_auth_type",
            label="Authentication Type",
            type="select",
            default="none",
            options=[
                {"label": "None", "value": "none"},
                {"label": "Bearer Token", "value": "bearer"},
                {"label": "Basic Auth", "value": "basic"},
                {"label": "API Key", "value": "api_key"},
            ],
            depends_on={"webhook_enabled": [True]},
        ),
        PropertySchema(
            name="webhook_auth_token",
            label="Bearer Token",
            type="string",
            default="",
            help_text="Bearer token value (stored plaintext in MVP)",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["bearer"]},
        ),
        PropertySchema(
            name="webhook_auth_username",
            label="Username",
            type="string",
            default="",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["basic"]},
        ),
        PropertySchema(
            name="webhook_auth_password",
            label="Password",
            type="string",
            default="",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["basic"]},
        ),
        PropertySchema(
            name="webhook_auth_key_name",
            label="Header Name",
            type="string",
            default="X-API-Key",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["api_key"]},
        ),
        PropertySchema(
            name="webhook_auth_key_value",
            label="Key Value",
            type="string",
            default="",
            depends_on={"webhook_enabled": [True], "webhook_auth_type": ["api_key"]},
        ),
        PropertySchema(
            name="webhook_custom_headers",
            label="Custom Headers (JSON)",
            type="string",
            default="{}",
            help_text='JSON object of extra headers, e.g. {"X-Source": "lidar"}',
            depends_on={"webhook_enabled": [True]},
        ),
    ],
    inputs=[PortSchema(id="in", label="Input", data_type="pointcloud", multiple=False)],
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
