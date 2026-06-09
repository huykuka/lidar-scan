"""
Node registry for the Truck Bin Detection application module.

Registers the ``truck_bin_detection`` node type with the DAG orchestrator.
Loaded automatically when :mod:`app.modules.application.registry` is imported.
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
            "Detects and measures open-top dump truck cargo bins and aligns them "
            "with a discharging target under a hopper. Crops points along spatial "
            "Y and Z boundaries, projects to a 1D elevation profile, and tracks "
            "rear and front internal walls to output real-time alignment errors."
        ),
        icon="local_shipping",
        websocket_enabled=True,
        properties=[
            # ── Spatial Filtering & Projection ──────────────────────────────────
            PropertySchema(
                name="z_min",
                label="Min Z Height (m)",
                type="number",
                default=2.0,
                min=0.0,
                max=5.0,
                step=0.1,
                help_text=(
                    "Minimum height at the bin rim level. Filters out wheels, axles, and ground returns."
                ),
            ),
            PropertySchema(
                name="z_max",
                label="Max Z Height (m)",
                type="number",
                default=3.8,
                min=1.0,
                max=10.0,
                step=0.1,
                help_text=(
                    "Maximum height at the bin rim level. Removes returns from overhead structures."
                ),
            ),
            PropertySchema(
                name="cell_size",
                label="Longitudinal Bin Size (m)",
                type="number",
                default=0.07,
                min=0.002,
                max=0.5,
                step=0.001,
                help_text=(
                    "Cell width along the longitudinal travel axis. Smaller values improve "
                    "resolution; larger values reduce empty cells for sparse sensor data."
                ),
            ),
            # ── Height Thresholds ───────────────────────────────────────────
            PropertySchema(
                name="z_wall_threshold",
                label="Wall Height Threshold (m)",
                type="number",
                default=2.2,
                min=0.5,
                max=5.0,
                step=0.1,
                help_text=(
                    "Minimum height that characterises a bin wall (front or rear wall top edge)."
                ),
            ),
            PropertySchema(
                name="z_cavity_max",
                label="Cavity Max Height (m)",
                type="number",
                default=1.8,
                min=0.0,
                max=4.0,
                step=0.1,
                help_text=(
                    "Maximum height that characterises the interior cavity floor of the bin."
                ),
            ),
            PropertySchema(
                name="z_cavity_min",
                label="Cavity Min Height (m)",
                type="number",
                default=0.5,
                min=0.0,
                max=3.0,
                step=0.1,
                help_text=(
                    "Minimum height for a valid cavity floor return. "
                    "Rejects ground-level returns from open gaps between separate trucks."
                ),
            ),
            PropertySchema(
                name="enable_area_check",
                label="Enable Interior Area Check",
                type="boolean",
                default=True,
                help_text=(
                    "When enabled, confirms the bin by measuring the 3D XY area of points "
                    "inside the cavity. Rejects inter-truck gaps and drawbars. "
                    "Disable for single-sensor setups where Y-spread is not available — "
                    "wall line coherence checks are used instead."
                ),
            ),
            PropertySchema(
                name="min_bin_area",
                label="Min Interior Area (m²)",
                type="number",
                default=2.0,
                min=0.1,
                max=20.0,
                step=0.1,
                depends_on={"enable_area_check": [True]},
                help_text=(
                    "Minimum XY bounding-box area of the 3D points found between the two "
                    "detected walls. A real open-top bin covers length × lane width. "
                    "Rejects inter-truck gaps (near-zero points) and drawbars (narrow Y-span)."
                ),
            ),
            PropertySchema(
                name="min_wall_points",
                label="Min Wall Points",
                type="number",
                default=3,
                min=1,
                max=50,
                step=1,
                depends_on={"enable_area_check": [False]},
                help_text=(
                    "Minimum number of raw LiDAR points that must be present in each "
                    "wall slab window to accept it as a real wall. "
                    "Handles partially hidden or segmented walls."
                ),
            ),
            PropertySchema(
                name="max_wall_x_std",
                label="Max Wall X Std Dev (m)",
                type="number",
                default=0.15,
                min=0.01,
                max=1.0,
                step=0.01,
                depends_on={"enable_area_check": [False]},
                help_text=(
                    "Maximum allowed standard deviation of X-coordinates within each "
                    "wall slab. A real vertical wall face has very low X-spread. "
                    "High spread indicates scattered noise or an angled structure."
                ),
            ),
            # ── Geometric Verification ──────────────────────────────────────
            PropertySchema(
                name="min_bin_length",
                label="Min Bin Length (m)",
                type="number",
                default=3.0,
                min=1.0,
                max=10.0,
                step=0.1,
                help_text=(
                    "Minimum accepted internal cavity length. Rejects false positives from cabin structures."
                ),
            ),
            PropertySchema(
                name="max_bin_length",
                label="Max Bin Length (m)",
                type="number",
                default=8.5,
                min=3.0,
                max=20.0,
                step=0.1,
                help_text=(
                    "Maximum accepted internal cavity length. Prevents merging edges across separate trailers."
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
            PortSchema(id="bin_cloud", label="Bin Edge Points"),
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
    """Build a TruckBinDetectionNode from persisted node configuration."""
    from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode

    config: Dict[str, Any] = node.get("config") or {}

    try:
        from app.api.v1.results.router import _get_service as _get_results_svc

        results_svc = _get_results_svc()
    except Exception:
        results_svc = None

    return TruckBinDetectionNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Truck Bin Detection",
        config=config,
        results_service=results_svc,
    )
