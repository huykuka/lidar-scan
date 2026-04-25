"""
Node registry for the SICK Visionary 3D camera module.

Registers the ``visionary_sensor`` node type with the DAG orchestrator.
Loaded automatically via ``discover_modules()`` at application startup.
"""
from typing import Any, Dict, List

from app.schemas.pose import Pose
from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition,
    PropertySchema,
    PortSchema,
    node_schema_registry,
)

# ---------------------------------------------------------------------------
# Camera model definitions
# ---------------------------------------------------------------------------

VISIONARY_MODELS = [
    {
        "model_id": "visionary_t_mini",
        "display_name": "SICK Visionary-T Mini",
        "is_stereo": False,
        "default_hostname": "192.168.1.10",
        "cola_protocol": "Cola2",
        "default_control_port": 2122,
        "default_streaming_port": 2114,
    },
    {
        "model_id": "visionary_s",
        "display_name": "SICK Visionary-S",
        "is_stereo": True,
        "default_hostname": "192.168.1.10",
        "cola_protocol": "Cola2",
        "default_control_port": 2122,
        "default_streaming_port": 2114,
    },
    {
        "model_id": "visionary_b_two",
        "display_name": "SICK Visionary-B Two",
        "is_stereo": True,
        "default_hostname": "192.168.1.10",
        "cola_protocol": "Cola2",
        "default_control_port": 2122,
        "default_streaming_port": 2114,
    },
]

_MODEL_LOOKUP: Dict[str, Dict[str, Any]] = {m["model_id"]: m for m in VISIONARY_MODELS}

# ---------------------------------------------------------------------------
# Schema registration — defines how the node appears in the Angular UI
# ---------------------------------------------------------------------------

node_schema_registry.register(
    NodeDefinition(
        type="visionary_sensor",
        display_name="Visionary 3D Camera",
        category="sensor",
        description="Interface for SICK Visionary 3D cameras (ToF and Stereo)",
        icon="videocam",
        websocket_enabled=True,
        properties=[
            PropertySchema(
                name="camera_model",
                label="Camera Model",
                type="select",
                default="visionary_t_mini",
                required=True,
                help_text="Select the SICK Visionary camera model",
                options=[
                    {"label": m["display_name"], "value": m["model_id"]}
                    for m in VISIONARY_MODELS
                ],
            ),
            PropertySchema(
                name="throttle_ms",
                label="Throttle (ms)",
                type="number",
                default=0,
                min=0,
                step=10,
                help_text="Minimum time between processing frames (0 = no limit)",
            ),
            PropertySchema(
                name="hostname",
                label="Hostname",
                type="string",
                default="192.168.1.10",
                help_text="Camera IP address",
            ),
            PropertySchema(
                name="streaming_port",
                label="Streaming Port",
                type="number",
                default=2114,
                help_text="TCP/UDP port for BLOB data streaming",
            ),
            PropertySchema(
                name="control_port",
                label="Control Port",
                type="number",
                default=2122,
                help_text="CoLa control channel port",
            ),
            PropertySchema(
                name="streaming_protocol",
                label="Streaming Protocol",
                type="select",
                default="TCP",
                options=[
                    {"label": "TCP", "value": "TCP"},
                    {"label": "UDP", "value": "UDP"},
                ],
                help_text="Transport protocol for the streaming channel",
            ),
            PropertySchema(
                name="pose",
                label="Sensor Pose",
                type="pose",
                help_text="6-DOF sensor pose: position (mm) and orientation (degrees)",
            ),
        ],
        outputs=[PortSchema(id="out", label="Output")],
    )
)


# ---------------------------------------------------------------------------
# Factory builder
# ---------------------------------------------------------------------------


@NodeFactory.register("visionary_sensor")
def build_visionary_sensor(
    node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]
) -> Any:
    """Build a ``VisionarySensor`` instance from persisted node configuration."""
    from .sensor import VisionarySensor

    config = node.get("config", {})

    # Throttle
    throttle_ms = config.get("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    camera_model_id = config.get("camera_model", "visionary_t_mini")
    model_info = _MODEL_LOOKUP.get(camera_model_id)
    if model_info is None:
        raise ValueError(f"Unknown camera_model: '{camera_model_id}'")

    hostname = config.get("hostname", model_info["default_hostname"])
    streaming_port = int(config.get("streaming_port", model_info["default_streaming_port"]))
    control_port = int(config.get("control_port", model_info["default_control_port"]))
    protocol = config.get("streaming_protocol", "TCP")
    cola_protocol = model_info["cola_protocol"]
    is_stereo = model_info["is_stereo"]

    # Pose
    raw_pose = node.get("pose") or {}
    p_x = float(raw_pose.get("x", 0) or 0)
    p_y = float(raw_pose.get("y", 0) or 0)
    p_z = float(raw_pose.get("z", 0) or 0)
    p_roll = float(raw_pose.get("roll", 0) or 0)
    p_pitch = float(raw_pose.get("pitch", 0) or 0)
    p_yaw = float(raw_pose.get("yaw", 0) or 0)

    sensor_id = node["id"]
    name = node.get("name")
    topic_prefix = config.get("topic_prefix")

    sensor_name = name or sensor_id
    desired_prefix = topic_prefix or sensor_name

    final_topic_prefix = service_context._topic_registry.register(
        desired_prefix, sensor_id[:8]
    )

    sensor = VisionarySensor(
        manager=service_context,
        sensor_id=sensor_id,
        hostname=hostname,
        streaming_port=streaming_port,
        protocol=protocol,
        cola_protocol=cola_protocol,
        control_port=control_port,
        is_stereo=is_stereo,
        name=sensor_name,
        topic_prefix=final_topic_prefix,
        throttle_ms=throttle_ms,
    )

    sensor.set_pose(
        Pose(x=p_x, y=p_y, z=p_z, roll=p_roll, pitch=p_pitch, yaw=p_yaw)
    )
    sensor.camera_model = model_info["model_id"]
    sensor.camera_display_name = model_info["display_name"]

    return sensor
