"""
Node registry for the LiDAR sensor module.

This module registers the sensor node type with the DAG orchestrator.
Loaded automatically via discover_modules() at application startup.
"""
from typing import Any, Dict, List
import os
from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)
from app.modules.lidar.profiles import get_all_profiles, get_profile, build_launch_args

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
    description="Interface for physical SICK sensors or PCD file simulations",
    icon="sensors",
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
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10, help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(name="mode", label="Mode", type="select", default="real", options=[
            {"label": "Hardware (Real)", "value": "real"},
            {"label": "Simulation (PCD)", "value": "sim"}
        ]),
        PropertySchema(name="hostname", label="Hostname", type="string", default="192.168.100.124", help_text="Lidar IP address", depends_on={"mode": ["real"]}),
        PropertySchema(name="port", label="Port", type="number", default=2112, help_text="Device communication port", depends_on={"mode": ["real"], "lidar_type": _port_capable_models}),
        PropertySchema(name="udp_receiver_ip", label="UDP Receiver IP", type="string", default="192.168.100.10", help_text="Host IP address receiving data", depends_on={"mode": ["real"], "lidar_type": _udp_receiver_models}),
        PropertySchema(name="imu_udp_port", label="IMU UDP Port", type="number", default=7503, help_text="UDP port for IMU data", depends_on={"mode": ["real"], "lidar_type": _imu_capable_models}),
        PropertySchema(name="pcd_path", label="PCD Path", type="string", default="", help_text="Path to .pcd file (simulation only)", depends_on={"mode": ["sim"]}),
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


# --- Factory Builder ---

@NodeFactory.register("sensor")
def build_sensor(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build a LidarSensor instance from persisted node configuration."""
    from .sensor import LidarSensor  # lazy import avoids circular dep
    from app.services.websocket.manager import manager
    
    config = node.get("config", {})
    mode = config.get("mode", "real")
    
    # Ensure throttle_ms is numeric
    throttle_ms = config.get("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    # Resolve pcd_path for sim mode: fall back to env var, then make absolute
    pcd_path = config.get("pcd_path") or ""
    if mode == "sim" and not pcd_path:
        pcd_path = os.environ.get("LIDAR_PCD_PATH", "")
    if pcd_path and not os.path.isabs(pcd_path):
        # Resolve relative to the project root (two levels above this package)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        pcd_path = os.path.join(project_root, pcd_path.lstrip("./"))

    # Read multi-model configuration
    lidar_type = config.get("lidar_type", "multiscan")
    hostname = config.get("hostname", "192.168.100.124")
    port = config.get("port")  # replaces udp_port
    udp_receiver_ip = config.get("udp_receiver_ip")
    imu_udp_port = config.get("imu_udp_port")
    
    # Build transformation string
    x = config.get("x", 0)
    y = config.get("y", 0)
    z = config.get("z", 0)
    roll = config.get("roll", 0)
    pitch = config.get("pitch", 0)
    yaw = config.get("yaw", 0)
    add_transform_xyz_rpy = f"{x},{y},{z},{roll},{pitch},{yaw}"
    
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
        mode=mode,
        pcd_path=pcd_path or None,
        throttle_ms=throttle_ms
    )
    sensor.set_pose(x, y, z, roll, pitch, yaw)
    
    # Set LiDAR type information on the sensor instance
    sensor.lidar_type = profile.model_id
    sensor.lidar_display_name = profile.display_name
    
    return sensor
