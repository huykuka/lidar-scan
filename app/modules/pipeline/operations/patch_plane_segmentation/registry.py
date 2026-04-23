"""
Node registry for the patch_plane_segmentation operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="patch_plane_segmentation",
    display_name="Planar Patch Detection",
    category="operation",
    description="Detects multiple planar patches using robust statistics-based approach",
    icon="layers",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="normal_variance_threshold_deg", label="Normal Variance (deg)", type="number",
                       default=60.0, step=1.0, min=1.0, max=90.0,
                       help_text="Max spread of point normals vs plane normal. Smaller = fewer, higher quality planes"),
        PropertySchema(name="coplanarity_deg", label="Coplanarity (deg)", type="number",
                       default=75.0, step=1.0, min=1.0, max=90.0,
                       help_text="Max spread of point-to-plane distances. Larger = tighter fit"),
        PropertySchema(name="outlier_ratio", label="Outlier Ratio", type="number",
                       default=0.75, step=0.05, min=0.0, max=1.0,
                       help_text="Max fraction of outliers before rejecting a plane"),
        PropertySchema(name="min_plane_edge_length", label="Min Edge Length (m)", type="number",
                       default=0.0, step=0.01, min=0.0,
                       help_text="Min largest-edge for a patch. 0 = 1% of cloud dimension"),
        PropertySchema(name="min_num_points", label="Min Points", type="number",
                       default=0, min=0,
                       help_text="Min points for plane fitting. 0 = 0.1% of total points"),
        PropertySchema(name="max_nn", label="Max Neighbors", type="number",
                       default=30, min=5, max=100,
                       help_text="Max nearest neighbours within search_radius for growing/merging. Larger = better quality, slower"),
        PropertySchema(name="search_radius", label="Search Radius (m)", type="number",
                       default=0.1, min=0.01, max=1.0, step=0.01,
                       help_text="KDTree hybrid search radius in metres. Only neighbours within this distance AND up to max_nn count are used"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("patch_plane_segmentation")
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
        op_type="patch_plane_segmentation",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
