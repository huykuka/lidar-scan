"""
Node registry for the fusion module.

This module registers the fusion node type with the DAG orchestrator.
Loaded automatically via discover_modules() at application startup.
"""
from typing import Any, Dict, List
from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)


# --- Schema Definition ---
# Defines how the fusion node appears in the Angular flow-canvas UI

node_schema_registry.register(NodeDefinition(
    type="fusion",
    display_name="Multi-Sensor Fusion",
    category="fusion",
    description="Merges multiple point cloud streams into a unified coordinate system",
    icon="hub",
    properties=[
        # Topic is now auto-generated as {node_name}_{node_id[:8]} by NodeManager
    ],
    inputs=[
        PortSchema(id="sensor_inputs", label="Inputs", multiple=True)
    ],
    outputs=[
        PortSchema(id="fused_output", label="Fused")
    ]
))


# --- Factory Builder ---

@NodeFactory.register("fusion")
def build_fusion(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build a FusionService instance from persisted node configuration."""
    from app.modules.lidar.sensor import LidarSensor  # lazy import
    from .service import FusionService  # lazy import
    
    config = node.get("config", {})

    incoming_edges = [e for e in edges if e["target_node"] == node["id"]]
    sensor_ids = []
    for e in incoming_edges:
        source_id = e["source_node"]
        source_node = service_context.nodes.get(source_id)
        if isinstance(source_node, LidarSensor):
            sensor_ids.append(source_id)

    return FusionService(
        service_context,
        sensor_ids=sensor_ids,
        fusion_id=node["id"]
    )
