"""
Node registry for the plane segmentation operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="plane_segmentation",
    display_name="Plane Segmentation",
    category="operation",
    description="Segments a plane from the point cloud using RANSAC",
    use_case="Isolate or remove the dominant flat surface in a scene — e.g. extract a conveyor belt, detect the ground plane before vehicle profiling, or remove a factory floor before object detection.",
    icon="layers",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="distance_threshold", label="Distance Threshold (m)", type="number", default=0.1, step=0.01,
                       help_text="Max distance from plane in meters to be considered an inlier"),
        PropertySchema(name="ransac_n", label="RANSAC N", type="number", default=3, min=3,
                       help_text="Number of points sampled per RANSAC iteration"),
        PropertySchema(name="num_iterations", label="Max Iterations", type="number", default=1000, step=10,
                       help_text="Maximum RANSAC iterations"),
        PropertySchema(name="min_area", label="Min Area (m²)", type="number", default=0, min=0, step=0.1,
                       help_text="Minimum plane surface area in m². Planes smaller than this are ignored (0 = no limit)"),
        PropertySchema(name="max_area", label="Max Area (m²)", type="number", default=0, min=0, step=0.1,
                       help_text="Maximum plane surface area in m². Planes larger than this are ignored (0 = no limit)"),
        PropertySchema(name="invert", label="Invert", type="boolean", default=False,
                       help_text="Keep non-plane points instead of the segmented plane"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("plane_segmentation")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import build_operation_node
    return build_operation_node("plane_segmentation", node, service_context)
