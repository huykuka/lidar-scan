"""
Node registry for the downsample operations.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definitions ---
node_schema_registry.register(NodeDefinition(
    type="downsample",
    display_name="Voxel Downsample",
    category="operation",
    description="Subsamples points using a grid of voxels",
    use_case="Reduce point count before heavy operations like clustering or surface reconstruction — e.g. cut a 500 k-point outdoor scan to ~50 k points for real-time processing.",
    icon="grid_view",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="voxel_size", label="Voxel Size (m)", type="number", default=0.05, step=0.01, min=0.001,
                       help_text="Voxel edge length in meters"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

node_schema_registry.register(NodeDefinition(
    type="uniform_downsample",
    display_name="Uniform Downsample",
    category="operation",
    description="Subsamples points by keeping every k-th point",
    use_case="Fast deterministic decimation that preserves scan structure — e.g. halve a ring-structured LiDAR scan without spatial distortion.",
    icon="format_list_numbered",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="every_k_points", label="Keep Every K Points", type="number", default=5, min=2, step=1,
                       help_text="Retain one point for every K points in the cloud"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builders ---
@NodeFactory.register("downsample")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("downsample", node, service_context)


@NodeFactory.register("uniform_downsample")
def build_uniform(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("uniform_downsample", node, service_context)

