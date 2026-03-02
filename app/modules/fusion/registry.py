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
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10, help_text="Minimum time between processing frames (0 = no limit)"),
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
    
    # Ensure throttle_ms is numeric
    throttle_ms = config.get("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

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
        fusion_id=node["id"],
        throttle_ms=throttle_ms
    )
