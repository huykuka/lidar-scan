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
            "LiDAR (full gantry FOV) to measure vehicle velocity via cluster centroid "
            "NN tracking, and one or more side-mounted LiDARs to reconstruct the "
            "vehicle's cross-section profile. Outputs a 3D point cloud of the vehicle shape."
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
            # ── Cluster Tracker (ICP) ─────────────────────────────────────
            PropertySchema(
                name="max_correspondence_distance",
                label="ICP Max Correspondence Distance (m)",
                type="number",
                default=0.5,
                min=0.05,
                max=5.0,
                step=0.05,
                help_text=(
                    "Maximum point-to-point distance (metres) for ICP "
                    "correspondences. Set to roughly 2× the expected distance "
                    "the vehicle travels per scan frame — e.g. 0.5 m for a "
                    "vehicle moving at 5 m/s scanned at 20 Hz."
                ),
            ),
            PropertySchema(
                name="min_icp_fitness",
                label="Min ICP Fitness",
                type="number",
                default=0.3,
                min=0.05,
                max=1.0,
                step=0.0001,
                help_text=(
                    "Minimum ICP fitness score [0–1] to accept a registration "
                    "result as a valid velocity measurement. Below this threshold "
                    "the Kalman filter runs a predict-only step (dead-reckoning "
                    "at last velocity)."
                ),
            ),
            PropertySchema(
                name="voxel_size",
                label="Voxel Down-sample Size (m)",
                type="number",
                default=0.0,
                min=0.0,
                max=0.5,
                step=0.01,
                help_text=(
                    "Voxel size (metres) for down-sampling cluster clouds before "
                    "ICP. Reduces computation on dense point clouds. 0 = disabled."
                ),
            ),
            PropertySchema(
                name="max_displacement",
                label="Max Displacement per Frame (m)",
                type="number",
                default=0.5,
                min=0.01,
                max=5.0,
                step=0.01,
                help_text=(
                    "Maximum ICP displacement per frame (metres). Any result "
                    "exceeding this is rejected as noise. Set to roughly the "
                    "maximum expected travel per scan frame (max_speed / scan_rate)."
                ),
            ),
            PropertySchema(
                name="min_displacement",
                label="Min Displacement (Dead-zone) (m)",
                type="number",
                default=0.005,
                min=0.0,
                max=0.1,
                step=0.001,
                help_text=(
                    "Dead-zone threshold (metres). ICP displacements below this "
                    "are treated as zero (truck static). Prevents noise accumulation "
                    "from ICP jitter on stationary vehicles. Set above ICP noise "
                    "floor (~0.003–0.005 m for typical 2D LiDAR)."
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
                step=0.001,
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
                name="min_vehicle_points",
                label="Min Vehicle Points",
                type="number",
                default=5,
                min=1,
                max=100,
                step=1,
                help_text=(
                    "Minimum number of vehicle points required in a frame to "
                    "accept it as a valid position measurement. Frames with "
                    "fewer points (e.g. bin walls, trailer gaps) are treated "
                    "as absence and the position is predicted forward instead. "
                    "Increase if bin interiors are pulling the position back to zero."
                ),
            ),
            PropertySchema(
                name="travel_axis",
                label="Travel Axis",
                type="select",
                default=0,
                options=[
                    {"label": "X", "value": 0},
                    {"label": "Y", "value": 1},
                ],
                help_text=(
                    "Which axis corresponds to the vehicle travel direction. "
                    "Used by both the detector (leading-edge tracking in the "
                    "2D scan plane) and the profile accumulator (stacking "
                    "scan lines along this axis in 3D). Typically X or Y "
                    "depending on your sensor mounting orientation."
                ),
            ),
           
            # ── Profile Accumulation ──────────────────────────────────────
            PropertySchema(
                name="stream_partial",
                label="Stream Partial Profile",
                type="boolean",
                default=False,
                help_text=(
                    "When enabled, the accumulated point cloud is streamed to "
                    "connected outputs after every side-sensor scan line. This "
                    "lets the UI show the profile building up in real-time. "
                    "Disable to only emit the final complete profile when the "
                    "vehicle leaves — reduces WebSocket traffic on slow connections."
                ),
            ),
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
