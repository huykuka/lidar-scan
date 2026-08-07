"""
Node registry for the Volume Calculation application module.

Registers the ``volume_calculation`` node type with the DAG orchestrator.
Loaded automatically when :mod:`app.modules.application.registry` is imported.
"""
from typing import Any, Dict

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition,
    PortSchema,
    PropertySchema,
    node_schema_registry,
)

# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

node_schema_registry.register(
    NodeDefinition(
        type="volume_calculation",
        display_name="Volume Calculation",
        category="application",
        description=(
            "Estimates the volume of material on a surface by comparing two "
            "point clouds: an empty baseline scan and a loaded scan. "
            "Uses Open3D multi-scale ICP alignment followed by Z-delta grid "
            "analysis with morphological filtering to isolate the loaded region."
        ),
        icon="straighten",
        websocket_enabled=False,
        properties=[
            # ── Sensor assignment ─────────────────────────────────────────
            PropertySchema(
                name="empty_sensor_id",
                label="Empty Reference Sensor",
                type="select",
                default="",
                required=False,
                options_source="sensor_nodes",
                help_text=(
                    "Which connected sensor supplies the empty baseline cloud. "
                    "All other connected inputs are treated as the loaded state. "
                    "Leave empty to auto-select the first connected sensor."
                ),
            ),
            # ── Outlier removal ───────────────────────────────────────────
            PropertySchema(
                name="outlier_nb_neighbors",
                label="Outlier: Neighbours",
                type="number",
                default=20,
                min=5,
                max=100,
                step=1,
                help_text=(
                    "K-neighbours used for statistical outlier removal. "
                    "Points whose mean distance to neighbours lies more than "
                    "std_ratio standard deviations above the mean are removed."
                ),
            ),
            PropertySchema(
                name="outlier_std_ratio",
                label="Outlier: Std-ratio",
                type="number",
                default=2.0,
                min=0.5,
                max=5.0,
                step=0.1,
                help_text=(
                    "Standard-deviation multiplier for the outlier threshold. "
                    "Lower values remove more points; typical range 1.5–3.0."
                ),
            ),
            # ── Ground removal ────────────────────────────────────────────
            PropertySchema(
                name="remove_ground",
                label="Remove Ground Plane",
                type="boolean",
                default=True,
                help_text=(
                    "Run RANSAC plane segmentation before alignment to strip "
                    "the truck bed / floor. Disable only if the input clouds "
                    "already have the ground removed upstream."
                ),
            ),
            PropertySchema(
                name="ground_distance_threshold",
                label="Ground: RANSAC Distance (m)",
                type="number",
                default=0.01,
                min=0.001,
                max=0.1,
                step=0.001,
                depends_on={"remove_ground": [True]},
                help_text=(
                    "Maximum point-to-plane distance (m) to be considered a "
                    "ground inlier. Typical value: 0.005–0.02 m."
                ),
            ),
            PropertySchema(
                name="ground_num_iterations",
                label="Ground: RANSAC Iterations",
                type="number",
                default=1000,
                min=100,
                max=5000,
                step=100,
                depends_on={"remove_ground": [True]},
                help_text="RANSAC iterations for ground plane fitting.",
            ),
            # ── ICP alignment ─────────────────────────────────────────────
            PropertySchema(
                name="voxel_size",
                label="ICP Voxel Size (m)",
                type="number",
                default=0.005,
                min=0.001,
                max=0.1,
                step=0.001,
                help_text=(
                    "Voxel size for downsampling before multi-scale ICP. "
                    "Smaller values give more precision but more compute. "
                    "Scales: coarse=4×, medium=2×, fine=1× this value."
                ),
            ),
            PropertySchema(
                name="min_icp_fitness",
                label="ICP Min Fitness",
                type="number",
                default=0.3,
                min=0.05,
                max=1.0,
                step=0.01,
                help_text=(
                    "Minimum ICP fitness [0–1] to accept the alignment. "
                    "If the result is below this, the identity transform is "
                    "used instead (clouds assumed pre-aligned)."
                ),
            ),
            # ── Z-delta analysis ──────────────────────────────────────────
            PropertySchema(
                name="grid_res",
                label="Grid Resolution (m)",
                type="number",
                default=0.005,
                min=0.001,
                max=0.1,
                step=0.001,
                help_text=(
                    "XY grid cell size for the Z-delta surface interpolation. "
                    "Finer grids give better volume precision but use more "
                    "memory and CPU. 0.005 m (5 mm) is a good default."
                ),
            ),
            PropertySchema(
                name="delta_threshold",
                label="ΔZ Threshold (m)",
                type="number",
                default=0.02,
                min=0.001,
                max=0.5,
                step=0.001,
                help_text=(
                    "Minimum Z difference (m) between loaded and empty "
                    "surfaces to count as part of the load. Acts as a noise "
                    "floor — cells below this are treated as empty. "
                    "Typical value: 0.01–0.05 m (1–5 cm)."
                ),
            ),
            PropertySchema(
                name="morph_open_iterations",
                label="Morphological Opening Iterations",
                type="number",
                default=2,
                min=0,
                max=10,
                step=1,
                help_text=(
                    "Number of morphological opening iterations on the 2-D "
                    "delta mask. Removes isolated noise pixels before the "
                    "largest-component selection. 0 disables opening."
                ),
            ),
        ],
        inputs=[
            PortSchema(id="empty_input", label="Empty Reference"),
            PortSchema(id="loaded_input", label="Loaded Cloud"),
        ],
        outputs=[
            PortSchema(id="volume_output", label="Volume Result", data_type="json"),
        ],
    )
)


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────


@NodeFactory.register("volume_calculation")
def build_volume_calculation(node, service_context, edges):
    config: Dict[str, Any] = node.get("config") or {}
    empty_sensor_id = config.get("empty_sensor_id", "") or ""

    # Auto-detect empty sensor from first connected edge if not set
    if not empty_sensor_id:
        incoming_edges = [e for e in edges if e["target_node"] == node["id"]]
        if incoming_edges:
            empty_sensor_id = incoming_edges[0]["source_node"]

    # Lazy-import to avoid circular dependency at module load time
    from .node import VolumeCalculationNode

    return VolumeCalculationNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Volume Calculation",
        empty_sensor_id=empty_sensor_id,
        config=config,
    )
