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


# --- Schema Definition ---
# Defines how the sensor node appears in the Angular flow-canvas UI

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


# --- Factory Builder ---

@NodeFactory.register("sensor")
def build_sensor(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build a LidarSensor instance from persisted node configuration."""
    from .sensor import LidarSensor  # lazy import avoids circular dep
    from app.services.websocket.manager import manager
    
    config = node.get("config", {})
    mode = config.get("mode", "real")

    # Resolve pcd_path for sim mode: fall back to env var, then make absolute
    pcd_path = config.get("pcd_path") or ""
    if mode == "sim" and not pcd_path:
        pcd_path = os.environ.get("LIDAR_PCD_PATH", "")
    if pcd_path and not os.path.isabs(pcd_path):
        # Resolve relative to the project root (two levels above this package)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
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
    
    return sensor
