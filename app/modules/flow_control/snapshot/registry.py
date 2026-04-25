"""
Node registry for the Snapshot flow-control module.

Registers the 'snapshot' node type with the DAG orchestrator's schema registry
and NodeFactory.  Mirrors the pattern established by if_condition/registry.py.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition,
    PortSchema,
    PropertySchema,
    node_schema_registry,
)

# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

node_schema_registry.register(NodeDefinition(
    type="snapshot",
    display_name="Snapshot",
    category="flow_control",
    description="Captures latest upstream point cloud on HTTP trigger",
    icon="camera",
    websocket_enabled=False,
    properties=[
        PropertySchema(
            name="throttle_ms",
            label="Throttle (ms)",
            type="number",
            default=0,
            min=0,
            step=10,
            help_text="Min ms between successful triggers (0 = no limit)",
        ),
    ],
    inputs=[
        PortSchema(id="in", label="Input", data_type="pointcloud"),
    ],
    outputs=[
        PortSchema(id="out", label="Output", data_type="pointcloud"),
    ],
))


# ---------------------------------------------------------------------------
# Factory builder
# ---------------------------------------------------------------------------

@NodeFactory.register("snapshot")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """
    Build a SnapshotNode from persisted node configuration.

    Args:
        node: Node configuration dict (id, name, config, …).
        service_context: NodeManager reference.
        edges: DAG edge list (unused).

    Returns:
        SnapshotNode instance.
    """
    from .node import SnapshotNode  # lazy import — avoids circular dependency

    config = node.get("config", {})
    throttle_ms = float(config.get("throttle_ms", 0))

    return SnapshotNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", "Snapshot"),
        throttle_ms=throttle_ms,
    )
