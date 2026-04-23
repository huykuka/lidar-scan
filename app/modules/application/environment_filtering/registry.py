"""
Node registry for the EnvironmentFiltering application module.

Registers the ``environment_filtering`` node type with the DAG orchestrator.
Loaded automatically when :mod:`app.modules.application.registry` is imported.

Side-effects executed at import time:

* :data:`~app.services.nodes.schema.node_schema_registry` receives the
  ``NodeDefinition`` for the ``environment_filtering`` type.
* :class:`~app.services.nodes.node_factory.NodeFactory` receives the
  builder function via the
  :meth:`~app.services.nodes.node_factory.NodeFactory.register` decorator.

Important — circular import prevention
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``EnvironmentFilteringNode`` is imported **lazily** (inside the factory
function body) to avoid the circular dependency chain.
See :mod:`tests.services.test_circular_import_fix` for the regression test.
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
# Schema Definition — 20 properties across 5 groups
# ─────────────────────────────────────────────────────────────────────────────

node_schema_registry.register(
    NodeDefinition(
        type="environment_filtering",
        display_name="Environment Filtering",
        category="application",
        description=(
            "Removes floor and ceiling planes from real-time indoor LiDAR scans. "
            "Detects all horizontal planes, picks the lowest as floor and the highest "
            "as ceiling, and removes them. Output is always at original resolution."
        ),
        icon="layers_clear",
        websocket_enabled=True,
        properties=[
            PropertySchema(
                name="remove_floor",
                label="Remove Floor",
                type="boolean",
                default=True,
                help_text="Remove the lowest detected horizontal plane (floor).",
            ),
            PropertySchema(
                name="remove_ceiling",
                label="Remove Ceiling",
                type="boolean",
                default=True,
                help_text="Remove the highest detected horizontal plane (ceiling).",
            ),
            PropertySchema(
                name="plane_thickness",
                label="Plane Thickness (m)",
                type="number",
                default=0.05,
                min=0.01,
                max=0.5,
                step=0.01,
                help_text=(
                    "Half-thickness of the perpendicular slab swept around each plane. "
                    "A point is removed when its perpendicular distance to the plane is "
                    "<= this value. 0.05m covers most floor/ceiling scan noise. "
                    "Increase for thick carpets or uneven surfaces."
                ),
            ),
            # ── Group A: Performance ──────────────────────────────────────
            PropertySchema(
                name="throttle_ms",
                label="Throttle (ms)",
                type="number",
                default=0,
                min=0,
                step=10,
                help_text=(
                    "Minimum milliseconds between processed frames. "
                    "0 = no limit. Use 50-100ms for 30Hz LiDAR streams."
                ),
            ),
            PropertySchema(
                name="voxel_downsample_size",
                label="Voxel Downsample Size (m)",
                type="number",
                default=0.01,
                min=0.0,
                max=1.0,
                step=0.005,
                help_text=(
                    "Reduce point cloud density before plane detection to improve "
                    "performance on dense scans (100k+ points). "
                    "Smaller = higher precision but slower. "
                    "Recommended: 0.01m (1cm) for indoor scans. "
                    "Set to 0 to disable downsampling."
                ),
            ),
            # ── Group B: Plane Detection ───────────────────────────────────
            PropertySchema(
                name="normal_variance_threshold_deg",
                label="Normal Variance (deg)",
                type="number",
                default=60.0,
                min=1.0,
                max=90.0,
                step=1.0,
                help_text=(
                    "Max spread of point normals vs plane normal. "
                    "Smaller = stricter, fewer planes. "
                    "Increase (65-75) for noisy/uneven floors."
                ),
            ),
            PropertySchema(
                name="coplanarity_deg",
                label="Coplanarity (deg)",
                type="number",
                default=75.0,
                min=1.0,
                max=90.0,
                step=1.0,
                help_text=(
                    "Max deviation from planar fit. "
                    "Smaller = tighter planes. "
                    "Reduce for smooth surfaces."
                ),
            ),
            PropertySchema(
                name="outlier_ratio",
                label="Outlier Ratio",
                type="number",
                default=0.75,
                min=0.0,
                max=1.0,
                step=0.05,
                help_text=(
                    "Max fraction of outlier points before rejecting a plane. "
                    "Increase (0.8-0.9) for debris-covered floors."
                ),
            ),
            PropertySchema(
                name="min_plane_edge_length",
                label="Min Edge Length (m)",
                type="number",
                default=0.0,
                min=0.0,
                step=0.01,
                help_text=(
                    "Minimum OBB edge to qualify as a plane. "
                    "0 = auto (1% of cloud bbox)."
                ),
            ),
            PropertySchema(
                name="min_num_points",
                label="Min Points",
                type="number",
                default=0,
                min=0,
                step=1,
                help_text=(
                    "Minimum points for plane fitting. "
                    "0 = auto (0.1% of total). "
                    "Increase to skip tiny fragments."
                ),
            ),
            PropertySchema(
                name="max_nn",
                label="Max Neighbors",
                type="number",
                default=30,
                min=5,
                max=100,
                step=1,
                help_text=(
                    "Maximum nearest neighbors within the search radius for normal "
                    "estimation and plane growing. Higher = better quality but slower. "
                    "Reduce (15-20) for real-time streaming."
                ),
            ),
            PropertySchema(
                name="search_radius",
                label="Search Radius (m)",
                type="number",
                default=0.2,
                min=0.01,
                max=1.0,
                step=0.01,
                help_text=(
                    "Radius (in metres) of the KDTree hybrid search used for normal "
                    "estimation and plane growing. Only neighbours within this distance "
                    "AND up to max_nn count are used. Increase for sparse/noisy scans; "
                    "decrease for dense high-resolution sensors."
                ),
            ),
            PropertySchema(
                name="cache_refresh_frames",
                label="Cache Refresh (frames)",
                type="number",
                default=30,
                min=1,
                step=1,
                help_text=(
                    "Number of frames to reuse cached floor/ceiling Z values before "
                    "re-running plane detection. Higher = less CPU. "
                    "30 frames at 10Hz = refresh every 3 seconds."
                ),
            ),
            PropertySchema(
                name="miss_confirm_frames",
                label="Miss Confirm (frames)",
                type="number",
                default=3,
                min=1,
                max=10,
                step=1,
                help_text=(
                    "Consecutive detection failures required before the cache is "
                    "invalidated. Prevents a single noisy frame from wiping a good "
                    "cache. 3 frames = must miss 3 in a row to reset."
                ),
            ),            
            # ── Group D: Validation ────────────────────────────────────────
            PropertySchema(
                name="vertical_tolerance_deg",
                label="Vertical Tolerance (deg)",
                type="number",
                default=15.0,
                min=1.0,
                max=45.0,
                step=0.5,
                help_text=(
                    "How close to vertical the plane normal must be "
                    "(0° = perfectly horizontal). "
                    "15° covers typical scanner tilt. "
                    "Increase (20-30°) for sloped floors/ramps."
                ),
            ),
            PropertySchema(
                name="min_plane_area",
                label="Min Plane Area (m²)",
                type="number",
                default=1.0,
                min=0.1,
                step=0.1,
                help_text=(
                    "Minimum plane area in m² to qualify as floor/ceiling. "
                    "Prevents shelves or table tops from being removed. "
                    "Increase (3-10m²) for open warehouse scans."
                ),
            ),
        ],
        inputs=[
            PortSchema(id="in", label="Input Point Cloud"),
        ],
        outputs=[
            PortSchema(id="out", label="Filtered Point Cloud"),
        ],
    )
)


# ─────────────────────────────────────────────────────────────────────────────
# Factory Builder
# ─────────────────────────────────────────────────────────────────────────────


@NodeFactory.register("environment_filtering")
def build_environment_filtering(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """
    Build an :class:`~app.modules.application.environment_filtering.node.EnvironmentFilteringNode`
    from a persisted node configuration record.

    Called by :meth:`~app.services.nodes.node_factory.NodeFactory.create`
    when the orchestrator instantiates a node of type ``"environment_filtering"``.

    Args:
        node:            Full node record (keys: ``"id"``, ``"name"``, ``"config"``).
        service_context: The :class:`~app.services.nodes.orchestrator.NodeManager` instance.
        edges:           Full list of DAG edges (not required by this node).

    Returns:
        A configured :class:`EnvironmentFilteringNode` ready for DAG integration.
    """
    # Lazy import breaks the circular-import chain
    from app.modules.application.environment_filtering.node import EnvironmentFilteringNode  # noqa: PLC0415

    config: Dict[str, Any] = node.get("config") or {}

    try:
        throttle_ms: float = float(config.get("throttle_ms", 0) or 0)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    return EnvironmentFilteringNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Environment Filtering",
        config=config,
        throttle_ms=throttle_ms,
    )
