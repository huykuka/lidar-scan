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

# Patch Plane Segmentation Schema
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
        PropertySchema(name="knn", label="KNN", type="number",
                       default=30, min=5, max=100,
                       help_text="Nearest neighbors for growing/merging. Larger = better quality, slower"),
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
        PropertySchema(name="emit_shapes", label="Emit Bounding Boxes", type="boolean", default=False,
                       help_text="When enabled, emits a wireframe bounding box and label for each detected cluster on the shapes topic"),
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
    websocket_enabled=False,  # Saves to disk only, no WebSocket streaming
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

# Generate Plane Schema
node_schema_registry.register(NodeDefinition(
    type="generate_plane",
    display_name="Generate Plane Mesh",
    category="operation",
    description="Generates a planar triangle mesh from segmented point cloud",
    icon="grid_on",
    websocket_enabled=True,   # Streams mesh vertices as point positions
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between frames (0 = no limit)"),
        PropertySchema(name="mode", label="Mode", type="select", default="square",
                       options=[
                           {"label": "Square (origin-centered)", "value": "square"},
                           {"label": "Boundary-Fitted", "value": "boundary"},
                       ],
                       help_text="Mesh generation mode"),
        PropertySchema(name="size", label="Size (m)", type="number", default=1.0, step=0.1, min=0.01,
                       help_text="Side length in meters (square mode only)"),
        PropertySchema(name="voxel_size", label="Vertex Spacing (m)", type="number",
                       default=0.05, step=0.005, min=0.001,
                       help_text="Grid vertex spacing in meters"),
        PropertySchema(name="plane_model", label="Plane Model [a,b,c,d]", type="vec4", default=None,
                       help_text="Optional override: plane coefficients. If None, auto-fitted via RANSAC."),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Vertices (as points)")]
))

# Densify Point Cloud Schema
node_schema_registry.register(NodeDefinition(
    type="densify",
    display_name="Point Cloud Densify",
    category="operation",
    description="Increases point cloud density by interpolating synthetic points",
    icon="blur_circular",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Wait time between updates. 0 means as fast as possible."),
        PropertySchema(
            name="algorithm", label="Algorithm", type="select",
            default="nearest_neighbor",
            options=[
                {"label": "Nearest Neighbor (Fast)",        "value": "nearest_neighbor"},
                {"label": "Statistical (Balanced)",         "value": "statistical"},
                {"label": "Moving Least Squares (Smooth)",  "value": "mls"},
                {"label": "Poisson (Best, Slow)",           "value": "poisson"},
            ],
            help_text="Pick how new points are created. Top options are faster, bottom ones look better."
        ),
        PropertySchema(
            name="density_multiplier", label="Multiply By", type="number",
            default=2.0, min=1.0, max=8.0, step=0.5,
            help_text="How many times more points you want. 2 = twice as many, 4 = four times as many."
        ),
        PropertySchema(
            name="preserve_normals", label="Keep Normals", type="boolean",
            default=True,
            help_text="Keep lighting and shading correct on new points. Turn off to speed things up."
        ),
        # ── Nearest Neighbor params ──────────────────────────────────────────
        PropertySchema(
            name="nn_params.displacement_min", label="Min Spread", type="number",
            default=0.05, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["nearest_neighbor"]},
            help_text="New points won't be placed closer than this. Lower = tighter clusters."
        ),
        PropertySchema(
            name="nn_params.displacement_max", label="Max Spread", type="number",
            default=0.50, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["nearest_neighbor"]},
            help_text="New points won't be placed farther than this. Higher = fills bigger gaps but may look rougher."
        ),
        # ── MLS params ───────────────────────────────────────────────────────
        PropertySchema(
            name="mls_params.k_neighbors", label="Smoothness", type="number",
            default=20, min=3, max=100, step=1,
            depends_on={"algorithm": ["mls"]},
            help_text="How many nearby points to look at when fitting the surface. Higher = smoother but slower."
        ),
        PropertySchema(
            name="mls_params.projection_radius_factor", label="Spread", type="number",
            default=0.5, min=0.01, max=2.0, step=0.05,
            depends_on={"algorithm": ["mls"]},
            help_text="How far from each point new ones can appear. Bigger = wider coverage."
        ),
        PropertySchema(
            name="mls_params.min_dist_factor", label="Min Gap", type="number",
            default=0.05, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["mls"]},
            help_text="Keeps new points from piling up on top of existing ones."
        ),
        # ── Statistical params ───────────────────────────────────────────────
        PropertySchema(
            name="statistical_params.k_neighbors", label="Scan Range", type="number",
            default=10, min=2, max=100, step=1,
            depends_on={"algorithm": ["statistical"]},
            help_text="How many nearby points to check when looking for thin areas. Higher = more thorough but slower."
        ),
        PropertySchema(
            name="statistical_params.sparse_percentile", label="Fill Amount (%)", type="number",
            default=50.0, min=1.0, max=100.0, step=1.0,
            depends_on={"algorithm": ["statistical"]},
            help_text="What portion of thin areas to fill. 50 = fill half, 80 = fill most gaps."
        ),
        PropertySchema(
            name="statistical_params.min_dist_factor", label="Min Gap", type="number",
            default=0.3, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["statistical"]},
            help_text="Keeps new points from piling up on top of existing ones."
        ),
        # ── Poisson params ───────────────────────────────────────────────────
        PropertySchema(
            name="poisson_params.depth", label="Detail", type="number",
            default=8, min=4, max=12, step=1,
            depends_on={"algorithm": ["poisson"]},
            help_text="How much detail to capture. Higher = sharper edges but much slower."
        ),
        PropertySchema(
            name="poisson_params.density_threshold_quantile", label="Edge Cleanup", type="number",
            default=0.1, min=0.0, max=0.5, step=0.01,
            depends_on={"algorithm": ["poisson"]},
            help_text="Trims stray points around the edges. Higher = cleaner edges, but may cut into the shape."
        ),
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
    "clustering", "boundary_detection", "debug_save", "filter_by_key", "generate_plane",
    "densify", "patch_plane_segmentation"
]
for _op in _OPERATION_TYPES:
    NodeFactory._registry[_op] = NodeFactory._registry["operation"]
