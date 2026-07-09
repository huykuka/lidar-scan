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
    use_case="Map all flat structural surfaces simultaneously — e.g. detect walls, floor, and ceiling of a room in one pass, or identify all pallet faces in a warehouse without running RANSAC repeatedly.",
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
        PropertySchema(name="min_area", label="Min Area (m²)", type="number", default=0, min=0, step=0.1,
                       help_text="Minimum patch area in m². Patches smaller than this are discarded (0 = no limit)"),
        PropertySchema(name="max_area", label="Max Area (m²)", type="number", default=0, min=0, step=0.1,
                       help_text="Maximum patch area in m². Patches larger than this are discarded (0 = no limit)"),
        PropertySchema(name="invert", label="Invert", type="boolean", default=False,
                       help_text="Keep non-patch points instead of the detected planar patches"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("patch_plane_segmentation")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("patch_plane_segmentation", node, service_context)
