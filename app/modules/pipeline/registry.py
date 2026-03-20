"""
Node registry for the pipeline operations module.

This module registers all Open3D point cloud operation node types with the
DAG orchestrator. Loaded automatically via discover_modules() at application startup.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definitions ---
# Each operation defines how it appears in the Angular flow-canvas UI

# Crop Operation Schema
node_schema_registry.register(NodeDefinition(
    type="crop",
    display_name="Crop Filter",
    category="operation",
    description="Filter points within/outside bounding box",
    icon="crop",
    websocket_enabled=True,  # Forwards transformed point clouds
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="min_bound", label="Min Bounds [X, Y, Z]", type="vec3", default=[-10.0, -10.0, -2.0],
                       help_text="Lower XYZ bounds of the crop box"),
        PropertySchema(name="max_bound", label="Max Bounds [X, Y, Z]", type="vec3", default=[10.0, 10.0, 2.0],
                       help_text="Upper XYZ bounds of the crop box"),
        PropertySchema(name="invert", label="Inverted", type="boolean", default=False,
                       help_text="Keep points outside the bounds instead of inside"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

# Voxel Downsample Schema
node_schema_registry.register(NodeDefinition(
    type="downsample",
    display_name="Voxel Downsample",
    category="operation",
    description="Subsamples points using a grid of voxels",
    icon="grid_view",
    websocket_enabled=True,  # Forwards transformed point clouds
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="voxel_size", label="Voxel Size (m)", type="number", default=0.05, step=0.01, min=0.001,
                       help_text="Voxel edge length in meters"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

# Outlier Removal Schema
node_schema_registry.register(NodeDefinition(
    type="outlier_removal",
    display_name="Stat. Outlier Removal",
    category="operation",
    description="Removes noise from the point cloud using statistic",
    icon="auto_fix_normal",
    websocket_enabled=True,  # Forwards transformed point clouds
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

# Radius Outlier Removal Schema
node_schema_registry.register(NodeDefinition(
    type="radius_outlier_removal",
    display_name="Radius Outlier Removal",
    category="operation",
    description="Removes points with too few neighbors in a sphere",
    icon="blur_on",
    websocket_enabled=True,  # Forwards transformed point clouds
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

# Plane Segmentation Schema
node_schema_registry.register(NodeDefinition(
    type="plane_segmentation",
    display_name="Plane Segmentation",
    category="operation",
    description="Segments a plane from the point cloud using RANSAC",
    icon="layers",
    websocket_enabled=True,  # Forwards transformed point clouds
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="distance_threshold", label="Distance Threshold", type="number", default=0.1, step=0.01,
                       help_text="Max distance from plane to be considered an inlier"),
        PropertySchema(name="ransac_n", label="RANSAC N", type="number", default=3, min=3,
                       help_text="Number of points sampled per RANSAC iteration"),
        PropertySchema(name="num_iterations", label="Max Iterations", type="number", default=1000, step=10,
                       help_text="Maximum RANSAC iterations"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

# Clustering Schema
node_schema_registry.register(NodeDefinition(
    type="clustering",
    display_name="DBSCAN Clustering",
    category="operation",
    description="Clusters points using the DBSCAN algorithm",
    icon="scatter_plot",
    websocket_enabled=True,  # Forwards transformed point clouds
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="eps", label="Eps (Radius)", type="number", default=0.2, step=0.01,
                       help_text="Neighborhood radius for clustering"),
        PropertySchema(name="min_points", label="Min Points", type="number", default=10, min=1,
                       help_text="Minimum points to form a cluster"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

# Boundary Detection Schema
node_schema_registry.register(NodeDefinition(
    type="boundary_detection",
    display_name="Boundary Detection",
    category="operation",
    description="Detects boundary points based on angle criteria",
    icon="timeline",
    websocket_enabled=True,  # Forwards transformed point clouds
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="radius", label="Radius", type="number", default=0.02, step=0.01,
                       help_text="Neighborhood radius for boundary analysis"),
        PropertySchema(name="max_nn", label="Max NN", type="number", default=30, min=1,
                       help_text="Maximum neighbors to consider"),
        PropertySchema(name="angle_threshold", label="Angle Threshold", type="number", default=90.0, step=1.0,
                       help_text="Boundary angle threshold in degrees"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

# Filter By Key Schema
node_schema_registry.register(NodeDefinition(
    type="filter_by_key",
    display_name="Attribute Filter",
    category="operation",
    description="Filter points based on attribute values",
    icon="filter_alt",
    websocket_enabled=True,  # Forwards transformed point clouds
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="key", label="Attribute (e.g. intensity)", type="string", default="intensity",
                       help_text="Attribute name to filter on"),
        PropertySchema(name="operator", label="Operator", type="select", default=">", options=[
            {"label": "Greater Than (>)", "value": ">"},
            {"label": "Less Than (<)", "value": "<"},
            {"label": "Equals (==)", "value": "=="},
            {"label": "Not Equals (!=)", "value": "!="},
            {"label": "Greater/Eq (>=)", "value": ">="},
            {"label": "Less/Eq (<=)", "value": "<="}
        ],
                       help_text="Comparison operator for the filter"),
        PropertySchema(name="value", label="Threshold Value", type="number", default=100.0, step=1.0,
                       help_text="Value to compare against the attribute"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

# Debug Save Schema
node_schema_registry.register(NodeDefinition(
    type="debug_save",
    display_name="Debug Save PCD",
    category="operation",
    description="Saves point cloud to PCD files",
    icon="save",
    websocket_enabled=False,  # Forwards transformed point clouds
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="output_dir", label="Output Directory", type="string", default="debug_output",
                       help_text="Directory to write output PCD files"),
        PropertySchema(name="prefix", label="File Prefix", type="string", default="pcd",
                       help_text="Filename prefix for saved PCD files"),
        PropertySchema(name="max_keeps", label="Max Keeps", type="number", default=10, min=1,
                       help_text="Maximum number of files to keep"),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---

@NodeFactory.register("operation")
def build_operation(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build an OperationNode instance from persisted node configuration."""
    from .operation_node import OperationNode  # lazy import

    config = node.get("config", {})
    # op_type can come from config.op_type or fall back to the node's own type (e.g. "crop")
    op_type = config.get("op_type") or node.get("type", "crop")

    # Remove config-level fields from op_config before passing to the operation class
    op_config = config.copy()
    op_config.pop("op_type", None)

    # Extract throttle_ms for OperationNode, don't pass it to the operation itself
    throttle_ms = op_config.pop("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    # Translate operator setting to array format for filter_by_key
    if op_type == "filter_by_key":
        operator = op_config.pop("operator", "==")
        val = op_config.get("value")
        if operator != "==":
            op_config["value"] = [operator, val]

    return OperationNode(
        manager=service_context,
        node_id=node["id"],
        op_type=op_type,
        op_config=op_config,  # pass clean config so ops only receive their expected params
        name=node.get("name"),
        throttle_ms=throttle_ms  # pass throttle directly to OperationNode
    )


# Register all specific operation types so NodeFactory can find them by node.type
_OPERATION_TYPES = [
    "crop", "downsample", "outlier_removal", "radius_outlier_removal", "plane_segmentation",
    "clustering", "boundary_detection", "debug_save", "filter_by_key"
]
for _op in _OPERATION_TYPES:
    NodeFactory._registry[_op] = NodeFactory._registry["operation"]
