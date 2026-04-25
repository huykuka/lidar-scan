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
            options=[{"label": p.display_name, "value": p.model_id} for p in get_all_profiles()]
        ),
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="hostname", label="Hostname", type="string", default="192.168.100.124",
                       help_text="Lidar IP address"),
        PropertySchema(name="port", label="Port", type="number", default=2112, help_text="Device communication port",
                       depends_on={"lidar_type": _port_capable_models}),
        PropertySchema(name="udp_receiver_ip", label="UDP Receiver IP", type="string", default="192.168.100.10",
                       help_text="Host IP address receiving data",
                       depends_on={"lidar_type": _udp_receiver_models}),
        PropertySchema(name="imu_udp_port", label="IMU UDP Port", type="number", default=7503,
                       help_text="UDP port for IMU data",
                       depends_on={"lidar_type": _imu_capable_models}),
        PropertySchema(name="pose", label="Sensor Pose", type="pose",
                       help_text="6-DOF sensor pose: position (mm) and orientation (degrees)"),
    ],
    outputs=[
        PortSchema(id="out", label="Output")
    ]
))


# --- Factory Builder ---

@NodeFactory.register("sensor")
def build_sensor(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build a LidarSensor instance from persisted node configuration."""
    from .sensor import LidarSensor  # lazy import avoids circular dep

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

    # Build launch arguments using profile system
    try:
        profile = get_profile(lidar_type)
        launch_args = build_launch_args(
            model_id=lidar_type,
            hostname=hostname,
            port=port,
            udp_receiver_ip=udp_receiver_ip,
            imu_udp_port=imu_udp_port,
            add_transform_xyz_rpy=add_transform_xyz_rpy
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

    sensor = LidarSensor(
        manager=service_context,
        sensor_id=sensor_id,
        name=sensor_name,
        topic_prefix=final_topic_prefix,
        launch_args=launch_args,
        throttle_ms=throttle_ms
    )

    # Apply canonical pose (already parsed from node["pose"] above)
    sensor.set_pose(Pose(x=p_x, y=p_y, z=p_z, roll=p_roll, pitch=p_pitch, yaw=p_yaw))

    # Set LiDAR type information on the sensor instance
    sensor.lidar_type = profile.model_id
    sensor.lidar_display_name = profile.display_name

    return sensor
