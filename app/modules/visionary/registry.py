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

# acquisition_method: "sdk" uses sick_visionary_python_base (CX models),
#                     "harvester" uses GigE Vision via harvesters + GenTL (AP models).
VISIONARY_MODELS = [
    # --- CX models (SDK streaming) ---
    {
        "model_id": "visionary_t_mini_cx",
        "display_name": "Visionary-T Mini CX (V3S105)",
        "is_stereo": False,
        "acquisition_method": "sdk",
        "default_hostname": "192.168.1.10",
        "cola_protocol": "Cola2",
        "default_control_port": 2122,
        "default_streaming_port": 2114,
    },
    {
        "model_id": "visionary_s_cx",
        "display_name": "Visionary-S CX (V3S102)",
        "is_stereo": True,
        "acquisition_method": "sdk",
        "default_hostname": "192.168.1.10",
        "cola_protocol": "Cola2",
        "default_control_port": 2122,
        "default_streaming_port": 2114,
    },
    # --- AP models (GigE Vision / Harvester) ---
    {
        "model_id": "visionary_t_mini_ap",
        "display_name": "Visionary-T Mini AP (V3S145)",
        "is_stereo": False,
        "acquisition_method": "harvester",
        "default_hostname": "192.168.1.10",
        "cola_protocol": "Cola2",
        "default_control_port": 2122,
        "default_streaming_port": 2114,
    },
    {
        "model_id": "visionary_s_ap",
        "display_name": "Visionary-S AP (V3S142)",
        "is_stereo": True,
        "acquisition_method": "harvester",
        "default_hostname": "192.168.1.10",
        "cola_protocol": "Cola2",
        "default_control_port": 2122,
        "default_streaming_port": 2114,
    },
    {
        "model_id": "visionary_b_two",
        "display_name": "Visionary-B Two (V3S146)",
        "is_stereo": True,
        "acquisition_method": "harvester",
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
                default="visionary_t_mini_cx",
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
                help_text="TCP/UDP port for BLOB data streaming (SDK mode)",
                depends_on={"camera_model": [m["model_id"] for m in VISIONARY_MODELS if m["acquisition_method"] == "sdk"]},
            ),
            PropertySchema(
                name="control_port",
                label="Control Port",
                type="number",
                default=2122,
                help_text="CoLa control channel port (SDK mode)",
                depends_on={"camera_model": [m["model_id"] for m in VISIONARY_MODELS if m["acquisition_method"] == "sdk"]},
            ),
            PropertySchema(
                name="streaming_protocol",
                label="Streaming Protocol",
                type="select",
                default="UDP",
                options=[
                    {"label": "UDP", "value": "UDP"},
                    {"label": "TCP", "value": "TCP"},
                ],
                help_text="UDP is faster (lower latency); TCP is more reliable on lossy networks",
                depends_on={"camera_model": [m["model_id"] for m in VISIONARY_MODELS if m["acquisition_method"] == "sdk"]},
            ),
            PropertySchema(
                name="cti_path",
                label="GenTL Producer (.cti)",
                type="string",
                default="",
                help_text="Path to the GenIStreamC .cti file from sick_visionary_gev_base (Harvester mode)",
                depends_on={"camera_model": [m["model_id"] for m in VISIONARY_MODELS if m["acquisition_method"] == "harvester"]},
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
    from .node import VisionarySensor

    config = node.get("config", {})

    # Throttle
    throttle_ms = config.get("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    camera_model_id = config.get("camera_model", "visionary_t_mini_cx")
    model_info = _MODEL_LOOKUP.get(camera_model_id)
    if model_info is None:
        raise ValueError(f"Unknown camera_model: '{camera_model_id}'")

    hostname = config.get("hostname", model_info["default_hostname"])
    streaming_port = int(config.get("streaming_port", model_info["default_streaming_port"]))
    control_port = int(config.get("control_port", model_info["default_control_port"]))
    protocol = config.get("streaming_protocol", "UDP")
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

    acquisition_method = model_info["acquisition_method"]
    cti_path = config.get("cti_path", "") or ""

    sensor = VisionarySensor(
        manager=service_context,
        sensor_id=sensor_id,
        hostname=hostname,
        streaming_port=streaming_port,
        protocol=protocol,
        cola_protocol=cola_protocol,
        control_port=control_port,
        is_stereo=is_stereo,
        acquisition_method=acquisition_method,
        cti_path=cti_path or None,
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
