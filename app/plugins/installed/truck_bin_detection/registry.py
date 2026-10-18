"""
Node registry for the Truck Bin Detection module.

Registers the truck_bin_detection node so it is available in the pipeline
editor and can be wired up inside a processing graph.
"""

from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.plugins.installed.truck_bin_detection import __version__
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
        version=__version__,
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
                name="wall_height_match_tol",
                label="Wall Height Match Tolerance (m)",
                type="number",
                default=0.04,
                min=0.01,
                max=0.20,
                step=0.005,
                help_text=(
                    "Maximum allowed height difference (m) between the rear and front wall "
                    "top cells. Real bin walls have the same nominal height; a larger gap "
                    "means the candidate front wall is actually a cab roof, crane, or the "
                    "next trailer. Default 4 cm. Increase if walls are noisy or sloped."
                ),
            ),
            PropertySchema(
                name="front_step_min",
                label="Front Step Min Rise (m)",
                type="number",
                default=0.3,
                min=0.05,
                max=3.0,
                step=0.05,
                help_text=(
                    "Smallest single-cell height jump that counts as the front wall rising "
                    "vertically from the cargo bed."
                ),
            ),
            PropertySchema(
                name="front_plateau_tol",
                label="Front Plateau Tolerance (m)",
                type="number",
                default=0.15,
                min=0.01,
                max=1.0,
                step=0.01,
                help_text="How close in height the cells ahead of the jump must be to count as level.",
            ),
            PropertySchema(
                name="min_wall_cells",
                label="Min Wall Width (cells)",
                type="number",
                default=3,
                min=1,
                max=20,
                step=1,
                help_text=(
                    "A rear or front wall must be at least this many adjacent cells wide at "
                    "wall height. Narrower slabs (1-2 cells) are treated as a crossbar, frame "
                    "member or noise between the edges and skipped; the search continues to "
                    "the next slab. 1 accepts any slab."
                ),
            ),
            PropertySchema(
                name="rear_confirm_skip",
                label="Rear Confirm Skip (cells)",
                type="number",
                default=2,
                min=0,
                max=20,
                step=1,
                help_text="While tracking, cells to jump past a rear wall candidate before checking for returns.",
            ),
            PropertySchema(
                name="edge_confirm_cells",
                label="Edge Confirm Cells",
                type="number",
                default=5,
                min=0,
                max=30,
                step=1,
                help_text=(
                    "Cells checked just past a wall edge. Rear: after the skip, all must carry "
                    "a return (no empty space). Front: the jump must be followed by a level "
                    "top within this window. Rejects stray slabs, slopes, piles and noise. "
                    "0 disables both checks."
                ),
            ),
            PropertySchema(
                name="max_rear_x",
                label="Max Rear Edge Position (m)",
                type="number",
                default=50.0,
                step=0.1,
                help_text=(
                    "Maximum X position of the rear edge, in the same frame as the input "
                    "cloud. A rear edge beyond this is a wrong detection and the frame is "
                    "reported as a miss. Tracking also searches for the rear wall starting at "
                    "this position and walking backward. Default 50 m is "
                    "effectively off; set it to the farthest point a rear wall can reach."
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
            PropertySchema(
                name="max_bed_structure_cells",
                label="Max Vertical Structure Cells",
                type="number",
                default=0,
                min=0,
                max=20,
                step=1,
                help_text=(
                    "A real cargo bed is flat: no cell between the rear and front walls may "
                    "reach wall height. If more than this many cells in the cavity are at "
                    "wall height (another wall, post, frame standing on the bed) the pair is "
                    "rejected. Raise it to tolerate a thin cross frame inside the bin."
                ),
            ),

            # ── Length stabilisation ─────────────────────────────────────────
            PropertySchema(
                name="stabilize_window_s",
                label="Stabilize Window (s)",
                type="number",
                default=2.0,
                min=0.0,
                max=60.0,
                step=0.1,
                help_text=(
                    "The detected bin length is tracked over this many seconds. Once it "
                    "stays within the tolerance for the whole window, the length is locked: "
                    "from then on only the rear wall is searched and the front wall is placed "
                    "that length ahead of it, which removes flicker. 0 disables locking."
                ),
            ),
            PropertySchema(
                name="stabilize_tolerance",
                label="Stabilize Tolerance (m)",
                type="number",
                default=0.15,
                min=0.01,
                max=1.0,
                step=0.01,
                help_text=(
                    "Maximum spread (max - min) of the bin length inside the stabilize "
                    "window for the length to count as stable."
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
    from app.plugins.installed.truck_bin_detection.node import TruckBinDetectionNode

    config: Dict[str, Any] = node.get("config") or {}

    return TruckBinDetectionNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Truck Bin Detection",
        config=config,
    )
