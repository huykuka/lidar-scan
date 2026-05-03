"""
Node registry for the PCD Injection module.

Registers:
  - NodeDefinition (schema for UI config panel)
  - @NodeFactory.register("pcd_injection") factory builder

Loaded automatically via discover_modules() at application startup.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry,
)

# ---------------------------------------------------------------------------
# Node schema definition
# ---------------------------------------------------------------------------

node_schema_registry.register(NodeDefinition(
    type="pcd_injection",
    display_name="PCD Injection",
    category="sensor",
    description="Receive PCD point cloud data via HTTP multipart upload",
    icon="cloud_upload",
    websocket_enabled=True,
    properties=[],
    outputs=[PortSchema(id="out", label="Output")],
))


# ---------------------------------------------------------------------------
# Factory builder
# ---------------------------------------------------------------------------

@NodeFactory.register("pcd_injection")
def build_pcd_injection(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build a PcdInjectionNode from persisted node configuration.

    Args:
        node: Persisted node dict (id, name, type, config, ...).
        service_context: NodeManager / orchestrator context.
        edges: DAG edges (unused by source node).

    Returns:
        A fully configured PcdInjectionNode instance.
    """
    from app.modules.pcd_injection.node import PcdInjectionNode

    node_id: str = node["id"]
    name: str = node.get("name", node_id)

    topic_prefix = service_context._topic_registry.register(name, node_id[:8])

    return PcdInjectionNode(
        manager=service_context,
        node_id=node_id,
        name=name,
        topic_prefix=topic_prefix,
    )
