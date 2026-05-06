"""
Node registry for the Truck Bin Detection application module.

Registers the ``truck_bin_detection`` node type with the DAG orchestrator.
Loaded automatically when :mod:`app.modules.application.registry` is imported.

Side-effects executed at import time:

* :data:`~app.services.nodes.schema.node_schema_registry` receives the
  ``NodeDefinition`` for the ``truck_bin_detection`` type.
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
        type="truck_bin_detection",
        display_name="Truck Bin Detection",
        category="application",
        description=(
            "Detects and measures the cargo bin of open-top dump trucks from "
            "3D point cloud data. Accepts completed vehicle profiles or direct "
            "sensor input. Outputs bin dimensions (L×W×H), volume, and the "
            "segmented bin point cloud for visualization."
        ),
        icon="local_shipping",
        websocket_enabled=True,
        properties=[
            # ── Bin Size Constraints ───────────────────────────────────────
            PropertySchema(
                name="min_bin_length",
                label="Min Bin Length (m)",
                type="number",
                default=2.0,
                min=0.5,
                max=20.0,
                step=0.1,
                help_text=(
                    "Minimum expected bin length (metres) along the travel axis. "
                    "Candidates shorter than this are rejected as false positives. "
                    "Typical dump truck bins are 4–8 m."
                ),
            ),
            PropertySchema(
                name="min_bin_width",
                label="Min Bin Width (m)",
                type="number",
                default=1.5,
                min=0.5,
                max=10.0,
                step=0.1,
                help_text=(
                    "Minimum expected bin width (metres) perpendicular to travel. "
                    "Typical dump truck bins are 2.2–2.5 m wide."
                ),
            ),
            PropertySchema(
                name="min_bin_height",
                label="Min Bin Wall Height (m)",
                type="number",
                default=0.5,
                min=0.1,
                max=5.0,
                step=0.1,
                help_text=(
                    "Minimum wall height (metres) for a valid bin detection. "
                    "Typical dump truck bin walls are 1.0–2.0 m tall."
                ),
            ),
            # ── Detection Parameters ──────────────────────────────────────
            PropertySchema(
                name="floor_distance_threshold",
                label="Floor Distance Threshold (m)",
                type="number",
                default=0.05,
                min=0.01,
                max=0.5,
                step=0.01,
                help_text=(
                    "RANSAC inlier distance threshold for bin floor plane fitting. "
                    "Points within this distance of the fitted plane are considered "
                    "floor inliers. Increase for noisy or uneven bin floors."
                ),
            ),
            PropertySchema(
                name="wall_distance_threshold",
                label="Wall Distance Threshold (m)",
                type="number",
                default=0.05,
                min=0.01,
                max=0.5,
                step=0.01,
                help_text=(
                    "RANSAC inlier distance threshold for wall plane fitting. "
                    "Points within this distance of the fitted plane are considered "
                    "wall inliers. Increase for corrugated or dented bin walls."
                ),
            ),
            PropertySchema(
                name="floor_ransac_n",
                label="Floor RANSAC Sample Size",
                type="number",
                default=3,
                min=3,
                max=10,
                step=1,
                help_text=(
                    "Number of points sampled per RANSAC iteration for floor "
                    "plane fitting. 3 is standard for plane fitting."
                ),
            ),
            PropertySchema(
                name="floor_ransac_iterations",
                label="Floor RANSAC Iterations",
                type="number",
                default=1000,
                min=100,
                max=10000,
                step=100,
                help_text=(
                    "Maximum RANSAC iterations for floor plane detection. "
                    "More iterations = better fit but slower. 1000 is a good "
                    "balance for real-time processing."
                ),
            ),
            PropertySchema(
                name="wall_min_points",
                label="Min Wall Points",
                type="number",
                default=50,
                min=10,
                max=1000,
                step=10,
                help_text=(
                    "Minimum number of inlier points for a vertical plane to "
                    "be considered a valid bin wall. Increase to reject small "
                    "noise planes; decrease for sparse scans."
                ),
            ),
            # ── Performance ───────────────────────────────────────────────
            PropertySchema(
                name="voxel_size",
                label="Voxel Downsample Size (m)",
                type="number",
                default=0.02,
                min=0.0,
                max=0.5,
                step=0.005,
                help_text=(
                    "Downsample the input cloud before analysis for performance. "
                    "Smaller = higher precision but slower. Set to 0 to disable. "
                    "Recommended: 0.02 m for dense scans (50k+ points)."
                ),
            ),
            PropertySchema(
                name="vertical_tolerance_deg",
                label="Wall Angle Tolerance (deg)",
                type="number",
                default=30.0,
                min=1.0,
                max=60.0,
                step=1.0,
                help_text=(
                    "Angular tolerance (degrees) from vertical for wall plane "
                    "normal classification. A plane with its normal within this "
                    "angle of horizontal is classified as a wall. 30° handles "
                    "tapered/angled bin walls that are not perpendicular to the "
                    "floor (e.g. V-shaped or trapezoidal cross-sections). "
                    "Increase for more heavily tapered bins."
                ),
            ),
            PropertySchema(
                name="horizontal_tolerance_deg",
                label="Horizontal Tolerance (deg)",
                type="number",
                default=15.0,
                min=1.0,
                max=45.0,
                step=1.0,
                help_text=(
                    "Angular tolerance (degrees) from horizontal for floor plane "
                    "normal classification. A plane with its normal within this "
                    "angle of vertical is classified as a floor. 15° covers "
                    "tilted or uneven bin floors."
                ),
            ),
            # ── Intersection Constraint ───────────────────────────────────
            PropertySchema(
                name="intersection_tolerance",
                label="Plane Intersection Tolerance (m)",
                type="number",
                default=0.5,
                min=0.05,
                max=2.0,
                step=0.05,
                help_text=(
                    "Maximum signed distance (metres) from the floor plane for "
                    "a wall to be considered intersecting. Uses the floor plane "
                    "equation (not raw Z) so it handles tilted floors correctly. "
                    "LiDAR scans have vertical gaps between layers — set this "
                    "above the expected layer spacing at your scan distance "
                    "(e.g. 0.5 m for 16-beam LiDAR at ~10 m). Walls that do "
                    "not intersect the floor or any neighbouring wall are "
                    "rejected as false positives."
                ),
            ),
        ],
        inputs=[
            PortSchema(
                id="cloud_input",
                label="Point Cloud Input",
                data_type="pointcloud",
            ),
        ],
        outputs=[
            PortSchema(id="bin_cloud", label="Bin Point Cloud"),
        ],
    )
)


# ─────────────────────────────────────────────────────────────────────────────
# Factory Builder
# ─────────────────────────────────────────────────────────────────────────────


@NodeFactory.register("truck_bin_detection")
def build_truck_bin_detection(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build a TruckBinDetectionNode from persisted node configuration.

    Called by NodeFactory.create() when the orchestrator instantiates a node
    of type ``"truck_bin_detection"``.
    """
    from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode

    config: Dict[str, Any] = node.get("config") or {}

    return TruckBinDetectionNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Truck Bin Detection",
        config=config,
    )
