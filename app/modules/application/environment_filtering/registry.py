"""
Node registry for the EnvironmentFiltering application module.

Registers the ``environment_filtering`` node type with the DAG orchestrator.
Loaded automatically when :mod:`app.modules.application.registry` is imported.

Side-effects executed at import time:

* :data:`~app.services.nodes.schema.node_schema_registry` receives the
  ``NodeDefinition`` for the ``environment_filtering`` type (14 properties).
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
# Schema Definition — 14 properties across 3 groups
# ─────────────────────────────────────────────────────────────────────────────

node_schema_registry.register(
    NodeDefinition(
        type="environment_filtering",
        display_name="Environment Filtering",
        category="application",
        description=(
            "Removes floor and ceiling planes from real-time indoor LiDAR scans "
            "using patch-based plane segmentation. Produces a filtered point cloud "
            "containing only objects of interest (walls, furniture, obstacles). "
            "For dense point clouds (>50k points), automatic voxel downsampling "
            "improves performance while maintaining filtering accuracy. "
            "Output is always at original resolution."
        ),
        icon="layers_clear",
        websocket_enabled=True,
        properties=[
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
                    "Set to 0 to disable downsampling (advanced users only)."
                ),
            ),
            # ── Group B: Plane Detection (patch_plane_segmentation params) ─
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
                name="knn",
                label="KNN",
                type="number",
                default=30,
                min=5,
                max=100,
                step=1,
                help_text=(
                    "Nearest neighbors for plane growing. "
                    "Higher = better quality but slower. "
                    "Reduce (15-20) for real-time streaming."
                ),
            ),
            # ── Group C: Validation ────────────────────────────────────────
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
                name="floor_height_min",
                label="Floor Height Min (m)",
                type="number",
                default=-0.5,
                step=0.1,
                help_text=(
                    "Minimum Z-coordinate for the floor centroid (world frame, Z-up). "
                    "Adjust for multi-level environments or raised platforms."
                ),
            ),
            PropertySchema(
                name="floor_height_max",
                label="Floor Height Max (m)",
                type="number",
                default=0.5,
                step=0.1,
                help_text=(
                    "Maximum Z-coordinate for the floor centroid. "
                    "Expand for scanner mounted above floor level."
                ),
            ),
            PropertySchema(
                name="ceiling_height_min",
                label="Ceiling Height Min (m)",
                type="number",
                default=2.0,
                step=0.1,
                help_text=(
                    "Minimum Z-coordinate for the ceiling centroid. "
                    "Adjust min if drop ceilings exist."
                ),
            ),
            PropertySchema(
                name="ceiling_height_max",
                label="Ceiling Height Max (m)",
                type="number",
                default=4.0,
                step=0.1,
                help_text=(
                    "Maximum Z-coordinate for the ceiling centroid. "
                    "Increase max for warehouses (8-12m)."
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
                    "Minimum plane area in m² to classify as floor/ceiling. "
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
