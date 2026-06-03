"""
Node registry for the LiDAR sensor module.

This module registers the sensor node type with the DAG orchestrator.
Loaded automatically via discover_modules() at application startup.
"""
from typing import Any, Dict, List

from app.modules.lidar.profiles import get_all_profiles, get_profile, build_launch_args
from app.schemas.pose import Pose
from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# Compute helper lists at module load time
_port_capable_models = [p.model_id for p in get_all_profiles() if p.port_arg]
# Result: ["tim_240", "tim_5xx", "tim_7xx", "tim_7xxs"] - TiM series with configurable ports

_udp_receiver_models = [p.model_id for p in get_all_profiles() if p.has_udp_receiver]
# Result: ["multiscan", "picoscan_120", "picoscan_150"] - Models requiring UDP receiver

_imu_capable_models = [p.model_id for p in get_all_profiles() if p.has_imu_udp_port]
# Result: ["multiscan"] - Only multiScan supports IMU data currently

_multi_layer_udp_models = [p.model_id for p in get_all_profiles() if p.has_udp_receiver and p.scan_layers > 1]
# Result: ["multiscan"] - UDP segment scanners with multiple layers

_picoscan_models = [p.model_id for p in get_all_profiles() if p.model_id.startswith("picoscan")]
# Result: ["picoscan_120", "picoscan_150"]


# --- Schema Definition ---
# Defines how the sensor node appears in the Angular flow-canvas UI

node_schema_registry.register(NodeDefinition(
    type="sensor",
    display_name="LiDAR Sensor",
    category="sensor",
    description="Interface for physical SICK LiDAR sensors",
    icon="sensors",
    websocket_enabled=True,  # Streams raw point cloud data via LIDR protocol
    properties=[
        PropertySchema(
            name="lidar_type",
            label="LiDAR Model",
            type="select",
            default="multiscan",
            required=True,
            help_text="Select the SICK LiDAR hardware model for this node",
            options=[
                {
                    "label": p.display_name,
                    "value": p.model_id,
                    "launch_file": p.launch_file,
                    "default_hostname": p.default_hostname,
                    "port_arg": p.port_arg,
                    "default_port": p.default_port,
                    "has_udp_receiver": p.has_udp_receiver,
                    "has_imu_udp_port": p.has_imu_udp_port,
                    "scan_layers": p.scan_layers,
                    "thumbnail_url": p.thumbnail_url,
                    "icon_name": p.icon_name,
                    "icon_color": p.icon_color,
                    "disabled": p.disabled,
                }
                for p in get_all_profiles()
            ],
        ),
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="hostname", label="Hostname", type="string", default="192.168.100.124",
                       help_text="LiDAR sensor IP address or hostname"),
        PropertySchema(name="port", label="Port", type="number", default=2112, help_text="Device communication port",
                       depends_on={"lidar_type": _port_capable_models}),
        PropertySchema(name="udp_receiver_ip", label="UDP Receiver IP", type="string", default="192.168.100.10",
                       help_text="Host IP address receiving data",
                       depends_on={"lidar_type": _udp_receiver_models}),
        PropertySchema(name="imu_udp_port", label="IMU UDP Port", type="number", default=7503,
                       help_text="UDP port for IMU data",
                       depends_on={"lidar_type": _imu_capable_models}),
        PropertySchema(name="imu_auto_level", label="IMU Auto-Level", type="boolean", default=False,
                       help_text="Continuously compensate point clouds for sensor tilt using the IMU gravity vector. "
                                 "Disable for dynamic mounting where raw IMU data should flow through for calibration.",
                       depends_on={"lidar_type": _imu_capable_models}),
        PropertySchema(name="pose", label="Sensor Pose", type="pose",
                       help_text="6-DOF sensor pose: position (mm) and orientation (degrees)"),

        # --- Scan Configuration (segment-based scanners) ---
        PropertySchema(name="scandataformat", label="Scan Data Format", type="select", default=2,
                       options=[{"label": "Msgpack", "value": 1}, {"label": "Compact (recommended)", "value": 2}],
                       help_text="Wire format for scan data. Compact format is recommended for lower bandwidth.",
                       depends_on={"lidar_type": _udp_receiver_models}),
        PropertySchema(name="host_FREchoFilter", label="Echo Filter", type="select", default=2,
                       options=[
                           {"label": "First Echo", "value": 0},
                           {"label": "All Echoes", "value": 1},
                           {"label": "Last Echo", "value": 2},
                       ],
                       help_text="Select which echo to use. Last Echo is default and recommended for most applications.",
                       depends_on={"lidar_type": _picoscan_models}),
        PropertySchema(name="add_transform_check_dynamic_updates", label="Dynamic Transform Updates",
                       type="boolean", default=False,
                       help_text="Allow runtime updates to the sensor transform. May decrease performance."),

        # --- Angle Range Filter (segment-based scanners) ---
        PropertySchema(name="host_set_LFPangleRangeFilter", label="Enable Angle Range Filter",
                       type="boolean", default=False,
                       help_text="Filter points by azimuth and elevation angle.",
                       depends_on={"lidar_type": _udp_receiver_models}),
        PropertySchema(name="host_LFPangleRangeFilter", label="Angle Range Filter",
                       type="string", default="0 -180.0 +179.0 -90.0 +90.0 1",
                       help_text="Format: \"<enabled> <azimuth_start> <azimuth_stop> <elevation_start> <elevation_stop> <beam_increment>\" (degrees)",
                       depends_on={"lidar_type": _udp_receiver_models}),

        # --- Interval Filter (segment-based scanners) ---
        PropertySchema(name="host_set_LFPintervalFilter", label="Enable Interval Filter",
                       type="boolean", default=False,
                       help_text="Reduce output to every N-th scan.",
                       depends_on={"lidar_type": _udp_receiver_models}),
        PropertySchema(name="host_LFPintervalFilter", label="Interval Filter",
                       type="string", default="0 1",
                       help_text="Format: \"<enabled> <N>\" where N reduces output to every N-th scan",
                       depends_on={"lidar_type": _udp_receiver_models}),

        # --- Layer Filter (multiScan only) ---
        PropertySchema(name="host_set_LFPlayerFilter", label="Enable Layer Filter",
                       type="boolean", default=False,
                       help_text="Enable/disable individual scan layers.",
                       depends_on={"lidar_type": _multi_layer_udp_models}),
        PropertySchema(name="host_LFPlayerFilter", label="Layer Filter",
                       type="string", default="0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1",
                       help_text="Format: \"<enabled> <layer0> <layer1> ... <layer15>\" (1=enabled, 0=disabled)",
                       depends_on={"lidar_type": _multi_layer_udp_models}),
        PropertySchema(name="laserscan_layer_filter", label="LaserScan Layer Filter",
                       type="string", default="0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0",
                       help_text="Select which layers emit LaserScan messages (16 values, 1=emit). Default: layer 5 only (hires).",
                       depends_on={"lidar_type": _multi_layer_udp_models}),

        # --- picoScan-specific settings ---
        PropertySchema(name="performanceprofilenumber", label="Performance Profile", type="number",
                       default=-1, min=-1, max=10, step=1,
                       help_text="picoScan performance profile (1–10). Set -1 to use device default.",
                       depends_on={"lidar_type": _picoscan_models}),
        PropertySchema(name="all_segments_min_deg", label="Fullscan Min Angle (°)", type="number",
                       default=-138.0, min=-180.0, max=180.0, step=1.0,
                       help_text="Minimum azimuth angle for fullframe assembly (degrees).",
                       depends_on={"lidar_type": _picoscan_models}),
        PropertySchema(name="all_segments_max_deg", label="Fullscan Max Angle (°)", type="number",
                       default=138.0, min=-180.0, max=180.0, step=1.0,
                       help_text="Maximum azimuth angle for fullframe assembly (degrees).",
                       depends_on={"lidar_type": _picoscan_models}),
    ],
    outputs=[
        PortSchema(id="out", label="Output")
    ]
))


# --- Factory Builder ---

@NodeFactory.register("sensor")
def build_sensor(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build a LidarSensor instance from persisted node configuration."""
    from .node import LidarSensor  # lazy import avoids circular dep

    config = node.get("config", {})

    # Ensure throttle_ms is numeric
    throttle_ms = config.get("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    # Read multi-model configuration
    lidar_type = config.get("lidar_type", "multiscan")
    hostname = config.get("hostname", "192.168.100.124")
    port = config.get("port")  # replaces udp_port
    udp_receiver_ip = config.get("udp_receiver_ip")
    imu_udp_port = config.get("imu_udp_port")

    # Read pose from the canonical top-level "pose" key (B-10)
    # This is surfaced at the top level by NodeModel.to_dict()
    raw_pose = node.get("pose") or {}
    p_x = float(raw_pose.get("x", 0) or 0)
    p_y = float(raw_pose.get("y", 0) or 0)
    p_z = float(raw_pose.get("z", 0) or 0)
    p_roll = float(raw_pose.get("roll", 0) or 0)
    p_pitch = float(raw_pose.get("pitch", 0) or 0)
    p_yaw = float(raw_pose.get("yaw", 0) or 0)
    add_transform_xyz_rpy = f"{p_x},{p_y},{p_z},{p_roll},{p_pitch},{p_yaw}"

    # Read extended scan/filter configuration from node config
    scandataformat = config.get("scandataformat")
    if scandataformat is not None:
        try:
            scandataformat = int(scandataformat)
        except (ValueError, TypeError):
            scandataformat = None

    host_FREchoFilter = config.get("host_FREchoFilter")
    if host_FREchoFilter is not None:
        try:
            host_FREchoFilter = int(host_FREchoFilter)
        except (ValueError, TypeError):
            host_FREchoFilter = None

    host_set_LFPangleRangeFilter = config.get("host_set_LFPangleRangeFilter")
    if host_set_LFPangleRangeFilter is not None:
        host_set_LFPangleRangeFilter = bool(host_set_LFPangleRangeFilter)
    host_LFPangleRangeFilter = config.get("host_LFPangleRangeFilter")

    host_set_LFPintervalFilter = config.get("host_set_LFPintervalFilter")
    if host_set_LFPintervalFilter is not None:
        host_set_LFPintervalFilter = bool(host_set_LFPintervalFilter)
    host_LFPintervalFilter = config.get("host_LFPintervalFilter")

    host_set_LFPlayerFilter = config.get("host_set_LFPlayerFilter")
    if host_set_LFPlayerFilter is not None:
        host_set_LFPlayerFilter = bool(host_set_LFPlayerFilter)
    host_LFPlayerFilter = config.get("host_LFPlayerFilter")
    laserscan_layer_filter = config.get("laserscan_layer_filter")

    performanceprofilenumber = config.get("performanceprofilenumber")
    if performanceprofilenumber is not None:
        try:
            performanceprofilenumber = int(performanceprofilenumber)
        except (ValueError, TypeError):
            performanceprofilenumber = None

    all_segments_min_deg = config.get("all_segments_min_deg")
    if all_segments_min_deg is not None:
        try:
            all_segments_min_deg = float(all_segments_min_deg)
        except (ValueError, TypeError):
            all_segments_min_deg = None

    all_segments_max_deg = config.get("all_segments_max_deg")
    if all_segments_max_deg is not None:
        try:
            all_segments_max_deg = float(all_segments_max_deg)
        except (ValueError, TypeError):
            all_segments_max_deg = None

    add_transform_check_dynamic_updates = config.get("add_transform_check_dynamic_updates")
    if add_transform_check_dynamic_updates is not None:
        add_transform_check_dynamic_updates = bool(add_transform_check_dynamic_updates)

    # Build launch arguments using profile system
    try:
        profile = get_profile(lidar_type)
        launch_args = build_launch_args(
            model_id=lidar_type,
            hostname=hostname,
            port=port,
            udp_receiver_ip=udp_receiver_ip,
            imu_udp_port=imu_udp_port,
            add_transform_xyz_rpy=add_transform_xyz_rpy,
            scandataformat=scandataformat,
            host_FREchoFilter=host_FREchoFilter,
            host_set_LFPangleRangeFilter=host_set_LFPangleRangeFilter,
            host_LFPangleRangeFilter=host_LFPangleRangeFilter,
            host_set_LFPintervalFilter=host_set_LFPintervalFilter,
            host_LFPintervalFilter=host_LFPintervalFilter,
            host_set_LFPlayerFilter=host_set_LFPlayerFilter,
            host_LFPlayerFilter=host_LFPlayerFilter,
            laserscan_layer_filter=laserscan_layer_filter,
            performanceprofilenumber=performanceprofilenumber,
            all_segments_min_deg=all_segments_min_deg,
            all_segments_max_deg=all_segments_max_deg,
            add_transform_check_dynamic_updates=add_transform_check_dynamic_updates,
        )
    except KeyError:
        raise ValueError(f"Unknown lidar_type: '{lidar_type}'")

    sensor_id = node["id"]
    name = node.get("name")
    topic_prefix = config.get("topic_prefix")

    sensor_name = name or sensor_id
    desired_prefix = topic_prefix or sensor_name

    # Register unique topic prefix using same format as orchestrator (8 chars of ID)
    # The TopicRegistry will automatically slugify and ensure uniqueness
    final_topic_prefix = service_context._topic_registry.register(desired_prefix, sensor_id[:8])

    imu_auto_level = bool(config.get("imu_auto_level", False))

    sensor = LidarSensor(
        manager=service_context,
        sensor_id=sensor_id,
        name=sensor_name,
        topic_prefix=final_topic_prefix,
        launch_args=launch_args,
        throttle_ms=throttle_ms,
        imu_auto_level=imu_auto_level,
    )

    # Apply canonical pose (already parsed from node["pose"] above)
    sensor.set_pose(Pose(x=p_x, y=p_y, z=p_z, roll=p_roll, pitch=p_pitch, yaw=p_yaw))

    # Set LiDAR type information on the sensor instance
    sensor.lidar_type = profile.model_id
    sensor.lidar_display_name = profile.display_name

    return sensor
