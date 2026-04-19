"""
Node registry for the outlier removal operations.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definitions ---

node_schema_registry.register(NodeDefinition(
    type="outlier_removal",
    display_name="Stat. Outlier Removal",
    category="operation",
    description="Removes noise from the point cloud using statistic",
    icon="auto_fix_normal",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="nb_neighbors", label="Neighbors", type="number", default=20, min=1,
                       help_text="Number of neighbors to analyze for each point"),
        PropertySchema(name="std_ratio", label="Std Ratio", type="number", default=2.0, step=0.1, min=0.1,
                       help_text="Std dev multiplier for outlier threshold"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

node_schema_registry.register(NodeDefinition(
    type="radius_outlier_removal",
    display_name="Radius Outlier Removal",
    category="operation",
    description="Removes points with too few neighbors in a sphere",
    icon="blur_on",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="nb_points", label="Min Points", type="number", default=16, min=1,
                       help_text="Minimum neighbors required within radius"),
        PropertySchema(name="radius", label="Search Radius (m)", type="number", default=0.05, step=0.01, min=0.01,
                       help_text="Neighborhood radius in meters"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builders ---

@NodeFactory.register("outlier_removal")
def build_outlier_removal(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
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
        op_type="outlier_removal",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )


@NodeFactory.register("radius_outlier_removal")
def build_radius_outlier_removal(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
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
        op_type="radius_outlier_removal",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
