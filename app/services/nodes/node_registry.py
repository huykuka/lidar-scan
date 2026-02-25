from typing import Any, Dict, List
from .node_factory import NodeFactory
from .schema import NodeDefinition, PropertySchema, PortSchema, node_schema_registry

# --- Schema Definitions ---

# Sensor Schema
node_schema_registry.register(NodeDefinition(
    type="sensor",
    display_name="LiDAR Sensor",
    category="sensor",
    description="Interface for physical SICK sensors or PCD file simulations",
    icon="sensors",
    properties=[
        PropertySchema(name="topic_prefix", label="Topic Prefix", type="string", default="sensor", help_text="Prefix for ROS topics"),
        PropertySchema(name="mode", label="Mode", type="select", default="real", options=[
            {"label": "Hardware (Real)", "value": "real"},
            {"label": "Simulation (PCD)", "value": "sim"}
        ]),
        PropertySchema(name="hostname", label="Hostname", type="string", default="192.168.100.124", help_text="Lidar IP address"),
        PropertySchema(name="udp_receiver_ip", label="UDP Receiver IP", type="string", default="192.168.100.10", help_text="Host IP address receiving data"),
        PropertySchema(name="udp_port", label="UDP Port", type="number", default=2667),
        PropertySchema(name="imu_udp_port", label="IMU UDP Port", type="number", default=7511),
        PropertySchema(name="pcd_path", label="PCD Path", type="string", default="", help_text="Path to .pcd file (simulation only)"),
        PropertySchema(name="x", label="Pos X", type="number", default=0.0, step=0.01),
        PropertySchema(name="y", label="Pos Y", type="number", default=0.0, step=0.01),
        PropertySchema(name="z", label="Pos Z", type="number", default=0.0, step=0.01),
        PropertySchema(name="roll", label="Roll", type="number", default=0.0, step=0.1),
        PropertySchema(name="pitch", label="Pitch", type="number", default=0.0, step=0.1),
        PropertySchema(name="yaw", label="Yaw", type="number", default=0.0, step=0.1),
    ],
    outputs=[
        PortSchema(id="raw_points", label="Raw Points"),
        PortSchema(id="processed_points", label="Processed Points")
    ]
))

# Fusion Schema
node_schema_registry.register(NodeDefinition(
    type="fusion",
    display_name="Multi-Sensor Fusion",
    category="fusion",
    description="Merges multiple point cloud streams into a unified coordinate system",
    icon="hub",
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="fused_points"),
    ],
    inputs=[
        PortSchema(id="sensor_inputs", label="Inputs", multiple=True)
    ],
    outputs=[
        PortSchema(id="fused_output", label="Fused")
    ]
))

# Crop Operation Schema
node_schema_registry.register(NodeDefinition(
    type="crop",
    display_name="Crop Filter",
    category="operation",
    description="Filter points within/outside bounding box",
    icon="crop",
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="crop_out"),
        PropertySchema(name="min_bound", label="Min Bounds [X, Y, Z]", type="vec3", default=[-10.0, -10.0, -2.0]),
        PropertySchema(name="max_bound", label="Max Bounds [X, Y, Z]", type="vec3", default=[10.0, 10.0, 2.0]),
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
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="downsampled"),
        PropertySchema(name="voxel_size", label="Voxel Size (m)", type="number", default=0.05, step=0.01, min=0.001),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))

# Outlier Removal Schema
node_schema_registry.register(NodeDefinition(
    type="outlier_removal",
    display_name="Stat. Outlier Removal",
    category="operation",
    description="Removes noise from the point cloud using stats",
    icon="auto_fix_normal",
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="filtered"),
        PropertySchema(name="nb_neighbors", label="Neighbors", type="number", default=20, min=1),
        PropertySchema(name="std_ratio", label="Std Ratio", type="number", default=2.0, step=0.1, min=0.1),
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
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="radius_filtered"),
        PropertySchema(name="nb_points", label="Min Points", type="number", default=16, min=1),
        PropertySchema(name="radius", label="Search Radius (m)", type="number", default=0.05, step=0.01, min=0.01),
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
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="segmented"),
        PropertySchema(name="distance_threshold", label="Distance Threshold", type="number", default=0.1, step=0.01),
        PropertySchema(name="ransac_n", label="RANSAC N", type="number", default=3, min=3),
        PropertySchema(name="num_iterations", label="Max Iterations", type="number", default=1000, step=10),
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
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="clustered"),
        PropertySchema(name="eps", label="Eps (Radius)", type="number", default=0.2, step=0.01),
        PropertySchema(name="min_points", label="Min Points", type="number", default=10, min=1),
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
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="boundary"),
        PropertySchema(name="radius", label="Radius", type="number", default=0.02, step=0.01),
        PropertySchema(name="max_nn", label="Max NN", type="number", default=30, min=1),
        PropertySchema(name="angle_threshold", label="Angle Threshold", type="number", default=90.0, step=1.0),
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
    properties=[
        PropertySchema(name="topic", label="Output Topic", type="string", default="filtered"),
        PropertySchema(name="key", label="Attribute (e.g. intensity)", type="string", default="intensity"),
        PropertySchema(name="operator", label="Operator", type="select", default=">", options=[
            {"label": "Greater Than (>)", "value": ">"},
            {"label": "Less Than (<)", "value": "<"},
            {"label": "Equals (==)", "value": "=="},
            {"label": "Not Equals (!=)", "value": "!="},
            {"label": "Greater/Eq (>=)", "value": ">="},
            {"label": "Less/Eq (<=)", "value": "<="}
        ]),
        PropertySchema(name="value", label="Threshold Value", type="number", default=100.0, step=1.0),
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
    properties=[
        PropertySchema(name="output_dir", label="Output Directory", type="string", default="debug_output"),
        PropertySchema(name="prefix", label="File Prefix", type="string", default="pcd"),
        PropertySchema(name="max_keeps", label="Max Keeps", type="number", default=10, min=1),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


@NodeFactory.register("sensor")
def build_sensor(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.services.lidar.sensor import LidarSensor  # lazy import avoids circular dep
    from app.services.websocket.manager import manager
    import os
    config = node.get("config", {})
    mode = config.get("mode", "real")

    # Resolve pcd_path for sim mode: fall back to env var, then make absolute
    pcd_path = config.get("pcd_path") or ""
    if mode == "sim" and not pcd_path:
        pcd_path = os.environ.get("LIDAR_PCD_PATH", "")
    if pcd_path and not os.path.isabs(pcd_path):
        # Resolve relative to the project root (two levels above this package)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        pcd_path = os.path.join(project_root, pcd_path.lstrip("./"))

    hostname = config.get("hostname", "192.168.100.124")
    udp_receiver_ip = config.get("udp_receiver_ip", "192.168.100.10")
    udp_port = config.get("udp_port", 2667)
    imu_udp_port = config.get("imu_udp_port", 7511)
    
    launch_args = f"./launch/sick_multiscan.launch hostname:={hostname} udp_receiver_ip:={udp_receiver_ip} udp_port:={udp_port} imu_udp_port:={imu_udp_port}"

    sensor_id = node["id"]
    name = node.get("name")
    topic_prefix = config.get("topic_prefix")
    x = config.get("x", 0)
    y = config.get("y", 0)
    z = config.get("z", 0)
    roll = config.get("roll", 0)
    pitch = config.get("pitch", 0)
    yaw = config.get("yaw", 0)

    sensor_name = name or sensor_id
    desired_prefix = topic_prefix or sensor_name
    
    # Avoid duplicate static prefixes by concatenating name and truncated ID
    short_id = sensor_id[:6]
    if short_id not in desired_prefix:
        desired_prefix = f"{desired_prefix}_{short_id}"
        
    final_topic_prefix = service_context._topic_registry.register(desired_prefix, sensor_id)

    sensor = LidarSensor(
        manager=service_context,
        sensor_id=sensor_id,
        name=sensor_name,
        topic_prefix=final_topic_prefix,
        launch_args=launch_args,
        mode=mode,
        pcd_path=pcd_path or None
    )
    sensor.set_pose(x, y, z, roll, pitch, yaw)
    
    manager.register_topic(f"{final_topic_prefix}_raw_points")
    return sensor

@NodeFactory.register("fusion")
def build_fusion(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.services.lidar.sensor import LidarSensor  # lazy import
    from app.services.fusion.service import FusionService  # lazy import
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
        topic=config.get("topic", f"fused_{node['id'][:8]}"),
        sensor_ids=sensor_ids,
        fusion_id=node["id"]
    )

@NodeFactory.register("operation")
def build_operation(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from .operation_node import OperationNode  # lazy import
    config = node.get("config", {})
    # op_type can come from config.op_type or fall back to the node's own type (e.g. "crop")
    op_type = config.get("op_type") or node.get("type", "crop")
    
    # Remove config-level fields from op_config before passing to the operation class
    op_config = config.copy()
    op_config.pop("op_type", None)
    op_config.pop("topic", None)
    
    # Backwards compatibility and schema mapping for Crop
    if op_type == "crop":
        if "min" in op_config:
            op_config["min_bound"] = op_config.pop("min")
        if "max" in op_config:
            op_config["max_bound"] = op_config.pop("max")
        op_config.pop("invert", None)
        
    # Translate operator setting to array format for filter_by_key
    if op_type == "filter_by_key":
        operator = op_config.pop("operator", "==")
        val = op_config.get("value")
        if operator != "==":
            op_config["value"] = [operator, val]

    # Operations that shouldn't broadcast payload over WebSockets
    topic = config.get("topic")
    if op_type in ["debug_save"]:
        topic = None
    elif topic and "_" not in topic: # Prevent infinite extending suffix on reloads/renders
        topic = f"{topic}_{node['id'][:6]}"

    return OperationNode(
        manager=service_context,
        node_id=node["id"],
        op_type=op_type,
        op_config=op_config,  # pass clean config so ops only receive their expected params
        name=node.get("name"),
        topic=topic
    )

# Register all specific operation types so NodeFactory can find them by node.type
_OPERATION_TYPES = [
    "crop", "downsample", "outlier_removal", "radius_outlier_removal", "plane_segmentation",
    "clustering", "boundary_detection", "debug_save", "filter_by_key"
]
for _op in _OPERATION_TYPES:
    NodeFactory._registry[_op] = NodeFactory._registry["operation"]
