"""
Node registry for the IF condition flow control module.

Registers the if_condition node type with the DAG orchestrator.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---

node_schema_registry.register(NodeDefinition(
    type="if_condition",
    display_name="Conditional If",
    category="flow_control",
    description="Routes data based on boolean expression",
    icon="call_split",
    properties=[
        PropertySchema(
            name="expression",
            label="Condition Expression",
            type="string",
            default="true",
            required=True,
            help_text="Boolean expression: point_count > 1000 AND external_state == True"
        ),
        PropertySchema(
            name="throttle_ms",
            label="Throttle (ms)",
            type="number",
            default=0,
            min=0,
            step=10,
            help_text="Minimum time between evaluations (0 = no limit)"
        ),
    ],
    inputs=[
        PortSchema(id="in", label="Input", data_type="pointcloud")
    ],
    outputs=[
        PortSchema(id="true", label="True", data_type="pointcloud"),
        PortSchema(id="false", label="False", data_type="pointcloud")
    ]
))


# --- Factory Builder ---

@NodeFactory.register("if_condition")
def build_if_condition(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """
    Build an IfConditionNode instance from persisted node configuration.
    
    Args:
        node: Node configuration dictionary
        service_context: NodeManager reference
        edges: List of edge configurations (unused)
        
    Returns:
        IfConditionNode instance
    """
    from .node import IfConditionNode  # Lazy import to avoid circular dependencies
    
    config = node.get("config", {})
    expression = config.get("expression", "true")
    throttle_ms = float(config.get("throttle_ms", 0))
    
    return IfConditionNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", "If Condition"),
        expression=expression,
        throttle_ms=throttle_ms
    )
