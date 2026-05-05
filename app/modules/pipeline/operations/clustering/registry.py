"""
Node registry for the clustering operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="clustering",
    display_name="DBSCAN Clustering",
    category="operation",
    description="Clusters points using the DBSCAN algorithm",
    icon="scatter_plot",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="eps", label="Eps (Radius)", type="number", default=0.2, step=0.01,
                       help_text="Neighborhood radius for clustering"),
        PropertySchema(name="min_points", label="Min Points", type="number", default=10, min=1,
                       help_text="Minimum points to form a cluster"),
        PropertySchema(name="emit_shapes", label="Emit Bounding Boxes", type="boolean", default=False,
                       help_text="When enabled, emits a wireframe bounding box and label for each detected cluster on the shapes topic"),
        PropertySchema(name="invert", label="Invert", type="boolean", default=False,
                       help_text="Keep noise (unclustered) points instead of the clustered points"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("clustering")
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
        op_type="clustering",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
