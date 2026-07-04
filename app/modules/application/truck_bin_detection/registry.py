"""
Node registry for the Truck Bin Detection module.

Registers the truck_bin_detection node so it is available in the pipeline
editor and can be wired up inside a processing graph.
"""

from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition,
    PortSchema,
    PropertySchema,
    node_schema_registry,
)

node_schema_registry.register(
    NodeDefinition(
        type="truck_bin_detection",
        display_name="Truck Bin Detection",
        category="application",
        description=(
            "Finds the open-top cargo bin on a dump truck and measures its position "
            "so the hopper can discharge into it accurately. "
            "Builds a side-view height profile from the LiDAR scan, then locates "
            "the rear and front walls of the bin cavity."
        ),
        icon="local_shipping",
        websocket_enabled=True,
        properties=[

            # ── Height filter ────────────────────────────────────────────────
            # Only points inside this height band are used. This cuts out the
            # ground, wheels, and anything above the bin rim.

            PropertySchema(
                name="z_min",
                label="Min Height (m)",
                type="number",
                default=2.0,
                min=0.0,
                max=5.0,
                step=0.1,
                help_text=(
                    "Lowest height to include. Points below this (ground, wheels, axles) "
                    "are ignored. Set just below the lowest expected bin rim."
                ),
            ),
            PropertySchema(
                name="z_max",
                label="Max Height (m)",
                type="number",
                default=3.8,
                min=1.0,
                max=10.0,
                step=0.1,
                help_text=(
                    "Highest height to include. Points above this (overhead structures, "
                    "crane beams) are ignored. Set just above the tallest expected bin wall."
                ),
            ),

            # ── Profile resolution ───────────────────────────────────────────
            PropertySchema(
                name="cell_size",
                label="Profile Cell Size (m)",
                type="number",
                default=0.07,
                min=0.002,
                max=0.5,
                step=0.001,
                help_text=(
                    "Width of each slice in the side-view height profile. "
                    "Smaller = finer detail but more empty cells in sparse scans. "
                    "Larger = smoother profile but less precise wall positions. "
                    "7 cm works well for two fused 16-layer LiDARs."
                ),
            ),

            # ── Wall and cavity height thresholds ────────────────────────────
            # These tell the detector what counts as a 'wall' and what counts
            # as the open interior of the bin.

            PropertySchema(
                name="z_wall_threshold",
                label="Wall Height Threshold (m)",
                type="number",
                default=2.2,
                min=0.5,
                max=5.0,
                step=0.1,
                help_text=(
                    "A profile cell must reach at least this height to be treated as "
                    "a bin wall. Set between the cargo bed height and the wall-top height. "
                    "Too low → the detector may latch onto the truck frame. "
                    "Too high → it misses short walls."
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
                    "The open cavity inside the bin must have a floor below this height. "
                    "If the lowest return between the two walls is above this value the "
                    "detector rejects the result — no real open cavity was found."
                ),
            ),
            PropertySchema(
                name="z_cavity_min",
                label="Cavity Floor Min Height (m)",
                type="number",
                default=0.5,
                min=0.0,
                max=3.0,
                step=0.1,
                help_text=(
                    "Minimum height for a point to count as a cargo bed return. "
                    "This separates the real bin floor from a low drawbar/coupling bar "
                    "or an open gap between two separate trailers — both of which sit "
                    "lower than the actual cargo bed."
                ),
            ),

            # ── Interior area check ──────────────────────────────────────────
            # This is the most reliable way to confirm a real bin was found.
            # It checks that the space between the two walls is wide enough in
            # 3-D to be a full-width cargo bay, not a narrow coupling or gap.

            PropertySchema(
                name="enable_area_check",
                label="Enable Interior Area Check",
                type="boolean",
                default=True,
                help_text=(
                    "When ON: confirms the bin by fitting a flat plane to the 3-D points "
                    "inside the cavity. Rejects drawbars, coupling structures, and gaps "
                    "between trailers. Recommended when two LiDARs are fused. "
                    "When OFF: uses a simpler height-only check on the 1-D profile — "
                    "suitable for single-sensor setups."
                ),
            ),
            PropertySchema(
                name="min_bin_area",
                label="Min Interior Footprint (m²)",
                type="number",
                default=2.0,
                min=0.1,
                max=20.0,
                step=0.1,
                depends_on={"enable_area_check": [True]},
                help_text=(
                    "Minimum floor area of the points found between the two detected walls. "
                    "A real open-top bin covers roughly length × lane width. "
                    "A drawbar is very narrow (small area) and a gap between trailers "
                    "has almost no returns — both are rejected by this check."
                ),
            ),

            # ── Bin size limits ──────────────────────────────────────────────
            PropertySchema(
                name="min_bin_length",
                label="Min Bin Length (m)",
                type="number",
                default=3.0,
                min=1.0,
                max=10.0,
                step=0.1,
                help_text=(
                    "Shortest cavity the detector will accept. Anything shorter is likely "
                    "the truck cab, a coupling structure, or sensor noise."
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
                    "Longest cavity the detector will accept. Prevents the detector from "
                    "accidentally spanning across two separate trailers."
                ),
            ),

            # ── Wall search windows ──────────────────────────────────────────
            # These control how the detector scans the profile to find the walls.

            PropertySchema(
                name="max_wall_thickness",
                label="Max Wall Thickness (m)",
                type="number",
                default=0.5,
                min=0.05,
                max=1.0,
                step=0.01,
                help_text=(
                    "Maximum distance allowed between the outer face and inner face of "
                    "the rear wall. A bin wall is a thin steel plate — if the gap between "
                    "the detected outer peak and the inner edge exceeds this, the peak is "
                    "discarded and the search continues. Default 20 cm."
                ),
            ),
            PropertySchema(
                name="rear_forward_lookup",
                label="Rear Wall Peak Look-ahead (cells)",
                type="number",
                default=30,
                min=5,
                max=100,
                step=1,
                help_text=(
                    "When searching for the rear wall, a candidate peak is accepted only "
                    "if it is the tallest point within this many cells ahead (~2 m at "
                    "default cell size). Increase if the profile is noisy and peaks are "
                    "missed; decrease if closely-spaced structures cause false peaks."
                ),
            ),
            PropertySchema(
                name="front_backward_lookup",
                label="Front Wall Edge Look-back (cells)",
                type="number",
                default=5,
                min=1,
                max=50,
                step=1,
                help_text=(
                    "When confirming the front wall, the candidate cell must be taller "
                    "than this many cells immediately behind it — confirming we are at "
                    "the start of the rising edge, not somewhere in the middle of a slope. "
                    "Increase for wider sloped front walls."
                ),
            ),

            # ── Multi-bin protection ─────────────────────────────────────────
            # When two bins are on the truck, the front wall of the second bin
            # can be mistaken for the rear wall of the first.  These settings
            # protect against that.

            PropertySchema(
                name="rear_peak_back_window",
                label="Rear Wall Back-Check Window (cells)",
                type="number",
                default=7,
                min=1,
                max=50,
                step=1,
                help_text=(
                    "After the detector finds a wall peak, it steps back past the wall "
                    "slab itself and checks this many cells behind it (~50 cm at default "
                    "cell size). Nothing tall should be there — a real rear wall (RW) "
                    "faces open air or low approach floor. If a tall structure is found "
                    "right behind the slab, the candidate is a front face seen from the "
                    "wrong side and is skipped. Note: keep this window SHORT — shorter "
                    "than the minimum gap between two consecutive bins — so the front "
                    "wall of a following bin does not accidentally trigger this check."
                ),
            ),
            PropertySchema(
                name="min_cavity_run_ratio",
                label="Min Cavity Length Ratio",
                type="number",
                default=0.6,
                min=0.1,
                max=1.0,
                step=0.05,
                help_text=(
                    "After finding the inner face of the rear wall, the open region ahead "
                    "must be at least this fraction of Min Bin Length before hitting the "
                    "next wall. This rejects the short gap between a stray front wall of "
                    "a second bin and the true rear wall behind it. "
                    "0.6 means the cavity must be at least 60% of Min Bin Length."
                ),
            ),
            PropertySchema(
                name="min_bed_cells",
                label="Min Cargo Bed Returns",
                type="number",
                default=3,
                min=1,
                max=50,
                step=1,
                help_text=(
                    "Minimum number of profile cells inside the cavity that carry a real "
                    "LiDAR return at cargo bed height (between Cavity Floor Min and Wall "
                    "Height Threshold). A drawbar/coupling sits lower than the bed; a gap "
                    "between trailers has almost no returns — both are rejected. "
                    "Increase if false positives occur in sparse scans."
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
# Factory
# ─────────────────────────────────────────────────────────────────────────────

@NodeFactory.register("truck_bin_detection")
def build_truck_bin_detection(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build a TruckBinDetectionNode from a saved pipeline configuration."""
    from app.modules.application.truck_bin_detection.node import TruckBinDetectionNode

    config: Dict[str, Any] = node.get("config") or {}

    return TruckBinDetectionNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Truck Bin Detection",
        config=config,
    )
