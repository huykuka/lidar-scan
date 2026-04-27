"""
Node registry for the Vehicle Profiler application module.

Registers the ``vehicle_profiler`` node type with the DAG orchestrator.
Loaded automatically when :mod:`app.modules.application.registry` is imported.

Side-effects executed at import time:

* :data:`~app.services.nodes.schema.node_schema_registry` receives the
  ``NodeDefinition`` for the ``vehicle_profiler`` type.
* :class:`~app.services.nodes.node_factory.NodeFactory` receives the
  builder function via the
  :meth:`~app.services.nodes.node_factory.NodeFactory.register` decorator.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition,
    PortSchema,
    PropertySchema,
    node_schema_registry,
)

# ─────────────────────────────────────────────────────────────────────────────
# Schema Definition
# ─────────────────────────────────────────────────────────────────────────────

node_schema_registry.register(
    NodeDefinition(
        type="vehicle_profiler",
        display_name="Vehicle Profiler",
        category="application",
        description=(
            "Multi-2D-LiDAR vehicle profiling node. Uses one vertically-mounted "
            "LiDAR to measure vehicle velocity (Kalman-filtered) and one or more "
            "side-mounted LiDARs to reconstruct the vehicle's cross-section profile. "
            "Outputs a 3D point cloud of the vehicle shape."
        ),
        icon="directions_car",
        websocket_enabled=True,
        properties=[
            # ── Sensor Assignment ─────────────────────────────────────────
            PropertySchema(
                name="velocity_sensor_id",
                label="Velocity Sensor",
                type="select",
                default="",
                required=False,
                options_source="sensor_nodes",
                help_text=(
                    "Which connected sensor is the vertically-mounted LiDAR "
                    "used for velocity measurement. All other connected inputs "
                    "are treated as profile (side) sensors. Leave empty to "
                    "auto-select the first connected sensor."
                ),
            ),
            # ── Kalman Filter ─────────────────────────────────────────────
            PropertySchema(
                name="process_noise",
                label="Process Noise (Q)",
                type="number",
                default=0.1,
                min=0.001,
                max=10.0,
                step=0.01,
                help_text=(
                    "Kalman filter process noise. Higher values make the filter "
                    "trust measurements more (faster response, more jitter). "
                    "Lower values trust the constant-velocity model more "
                    "(smoother but slower to react)."
                ),
            ),
            PropertySchema(
                name="measurement_noise",
                label="Measurement Noise (R)",
                type="number",
                default=0.5,
                min=0.01,
                max=50.0,
                step=0.1,
                help_text=(
                    "Kalman filter measurement noise. Higher values mean noisier "
                    "edge-position measurements — the filter will smooth more "
                    "aggressively. Increase for noisy or reflective environments."
                ),
            ),
            # ── Vehicle Detection ─────────────────────────────────────────
            PropertySchema(
                name="bg_threshold",
                label="Background Threshold (m)",
                type="number",
                default=0.3,
                min=0.05,
                max=5.0,
                step=0.05,
                help_text=(
                    "Distance (metres) closer than the learned background to "
                    "classify a point as belonging to a vehicle. Increase for "
                    "farther sensor mounting positions."
                ),
            ),
            PropertySchema(
                name="bg_learning_frames",
                label="Background Learning Frames",
                type="number",
                default=20,
                min=5,
                max=200,
                step=1,
                help_text=(
                    "Number of initial frames used to learn the background "
                    "distance model (median). No vehicles should be present "
                    "during this phase."
                ),
            ),
            PropertySchema(
                name="travel_axis",
                label="Detector Travel Axis",
                type="select",
                default=0,
                options=[
                    {"label": "X", "value": 0},
                    {"label": "Y", "value": 1},
                ],
                help_text=(
                    "Which axis of the vertical LiDAR's 2D scan plane "
                    "corresponds to the vehicle travel direction. Used by "
                    "the detector to find the leading edge. X or Y only "
                    "(2D scan data)."
                ),
            ),
            PropertySchema(
                name="profile_travel_axis",
                label="Profile Travel Axis",
                type="select",
                default=2,
                options=[
                    {"label": "X", "value": 0},
                    {"label": "Y", "value": 1},
                    {"label": "Z", "value": 2},
                ],
                help_text=(
                    "Which 3D axis the profile scan lines are stacked along "
                    "(the vehicle's movement direction in world space). The "
                    "Kalman-filtered position is placed on this axis."
                ),
            ),
            PropertySchema(
                name="min_velocity",
                label="Min Velocity (m/s)",
                type="number",
                default=0.0,
                min=0.0,
                max=10.0,
                step=0.01,
                help_text=(
                    "Minimum forward velocity (m/s) required to accept profile "
                    "scan lines. Scans captured while the vehicle is stationary "
                    "or moving backwards are discarded to prevent duplicate or "
                    "reversed profile data. Set to 0 to accept all scans."
                ),
            ),
            # ── Profile Accumulation ──────────────────────────────────────
            PropertySchema(
                name="min_scan_lines",
                label="Min Scan Lines",
                type="number",
                default=10,
                min=2,
                max=1000,
                step=1,
                help_text=(
                    "Minimum number of scan lines required from side sensors "
                    "to emit a valid vehicle profile. Profiles with fewer "
                    "scan lines are discarded."
                ),
            ),
            PropertySchema(
                name="max_gap_s",
                label="Max Scan Gap (s)",
                type="number",
                default=2.0,
                min=0.1,
                max=30.0,
                step=0.1,
                help_text=(
                    "Maximum allowed time gap (seconds) between consecutive "
                    "side-sensor scans. If exceeded, the current accumulation "
                    "is discarded (assumes the vehicle left or sensor stalled)."
                ),
            ),
            PropertySchema(
                name="min_position_delta",
                label="Min Position Delta (m)",
                type="number",
                default=0.0,
                min=0.0,
                max=1.0,
                step=0.001,
                help_text=(
                    "Minimum position change (metres) required between "
                    "consecutive scan lines. At low vehicle speeds, many "
                    "scans may land at nearly the same position — this "
                    "deduplicates them for a cleaner profile. Set to 0 to "
                    "keep every scan. Try 0.005–0.02 for slow miniature setups."
                ),
            ),
            # ── Performance ───────────────────────────────────────────────
            PropertySchema(
                name="throttle_ms",
                label="Throttle (ms)",
                type="number",
                default=0,
                min=0,
                step=10,
                help_text="Minimum time between processing frames (0 = no limit).",
            ),
        ],
        inputs=[
            PortSchema(
                id="sensor_inputs",
                label="LiDAR Inputs",
                multiple=True,
            ),
        ],
        outputs=[
            PortSchema(id="profile_output", label="Vehicle Profile"),
        ],
    )
)


# ─────────────────────────────────────────────────────────────────────────────
# Factory Builder
# ─────────────────────────────────────────────────────────────────────────────


@NodeFactory.register("vehicle_profiler")
def build_vehicle_profiler(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build a VehicleProfilerNode from persisted node configuration.

    Called by NodeFactory.create() when the orchestrator instantiates a node
    of type ``"vehicle_profiler"``.
    """
    from app.modules.application.vehicle_profiler.node import VehicleProfilerNode

    config: Dict[str, Any] = node.get("config") or {}

    velocity_sensor_id = config.get("velocity_sensor_id", "") or ""

    # Auto-detect: if the user left the field empty, pick the first connected
    # upstream sensor as the velocity sensor.
    if not velocity_sensor_id:
        incoming_edges = [e for e in edges if e["target_node"] == node["id"]]
        if incoming_edges:
            velocity_sensor_id = incoming_edges[0]["source_node"]

    return VehicleProfilerNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Vehicle Profiler",
        velocity_sensor_id=velocity_sensor_id,
        config=config,
    )
