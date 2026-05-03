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
                name="max_displacement",
                label="Max Displacement per Frame (m)",
                type="number",
                default=0.5,
                min=0.001,
                max=5.0,
                step=0.001,
                help_text=(
                    "Maximum displacement accepted per frame (metres). Results "
                    "above this are rejected as outliers. Rule of thumb: "
                    "max_speed (m/s) / scan_rate (Hz). E.g. 3 m/s at 10 Hz → 0.3 m."
                ),
            ),
            PropertySchema(
                name="min_displacement",
                label="Min Displacement (Dead-zone) (m)",
                type="number",
                default=0.001,
                min=0.0,
                max=0.05,
                step=0.001,
                help_text=(
                    "Dead-zone threshold (metres). Displacements below this are treated as "
                    "zero (truck static). Prevents noise accumulation from ICP jitter on "
                    "a stationary vehicle. Typical noise floor is 0.001–0.003 m"
                ),
            ),
            # ── Vehicle Detection ─────────────────────────────────────────
            PropertySchema(
                name="dbscan_eps",
                label="Detection Sensitivity (m)",
                type="number",
                default=0.3,
                min=0.05,
                max=2.0,
                step=0.05,
                help_text=(
                    "Maximum distance between two points for them to be considered "
                    "part of the same cluster (DBSCAN ε). Lower values → tighter "
                    "clusters, less sensitive. Higher values → merge spread-out "
                    "returns into one cluster. Set to roughly 2× the expected "
                    "point spacing at the sensor's typical detection range."
                ),
            ),
            PropertySchema(
                name="min_vehicle_points",
                label="Min Cluster Points",
                type="number",
                default=10,
                min=3,
                max=200,
                step=1,
                help_text=(
                    "Minimum number of points a cluster must contain to be treated "
                    "as a vehicle. Rejects small noise clusters and debris. Increase "
                    "if spurious detections occur; decrease if the truck cross-section "
                    "is partially occluded."
                ),
            ),
            PropertySchema(
                name="travel_axis",
                label="Travel Axis",
                type="select",
                default=0,
                options=[
                    {"label": "+X", "value": 0},
                    {"label": "+Y", "value": 1},
                ],
                help_text=(
                    "Which axis corresponds to the vehicle travel direction. "
                    "Used by both the detector (leading-edge tracking in the "
                    "2D scan plane) and the profile accumulator (stacking "
                    "scan lines along this axis in 3D). Typically X or Y "
                    "depending on your sensor mounting orientation."
                ),
            ),
            PropertySchema(
                name="trigger_distance",
                label="Trigger Distance (m)",
                type="number",
                default=None,
                min=0.0,
                max=20.0,
                step=0.1,
                help_text=(
                    "How far before the gantry (X=0) the truck's leading edge "
                    "must be to start detection. E.g. 0.1 fires only when the "
                    "truck front is within 10 cm of the gantry. "
                    "Leave empty to trigger anywhere in the scan zone."
                ),
            ),
            PropertySchema(
                name="min_scan_lines",
                label="Min Scan Lines",
                type="number",
                default=10,
                min=1,
                max=500,
                step=1,
                help_text=(
                    "Minimum number of side-sensor scan lines required to emit "
                    "a valid profile. Profiles with fewer lines are discarded. "
                    "Set based on truck length and scan rate."
                ),
            ),
            PropertySchema(
                name="min_height",
                label="Min Point Height (m)",
                type="number",
                default=0.0,
                min=0.0,
                max=5.0,
                step=0.05,
                help_text=(
                    "Minimum height (metres) a point must be above the ground "
                    "to be included in the profile. Use this to remove ground "
                    "noise when the LiDAR FOV is extended and beams reach the "
                    "road surface ahead of or behind the truck. Set to 0 to "
                    "keep all points. Typical value: 0.1–0.3 m."
                ),
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
