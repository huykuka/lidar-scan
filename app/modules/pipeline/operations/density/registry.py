"""
Node registry for the densify operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="densify",
    display_name="Point Cloud Densify",
    category="operation",
    description="Increases point cloud density by interpolating synthetic points",
    icon="blur_circular",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Wait time between updates. 0 means as fast as possible."),
        PropertySchema(
            name="algorithm", label="Algorithm", type="select",
            default="nearest_neighbor",
            options=[
                {"label": "Nearest Neighbor (Fast)",        "value": "nearest_neighbor"},
                {"label": "Statistical (Balanced)",         "value": "statistical"},
                {"label": "Moving Least Squares (Smooth)",  "value": "mls"},
                {"label": "Poisson (Best, Slow)",           "value": "poisson"},
            ],
            help_text="Pick how new points are created. Top options are faster, bottom ones look better."
        ),
        PropertySchema(
            name="density_multiplier", label="Multiply By", type="number",
            default=2.0, min=1.0, max=8.0, step=0.5,
            help_text="How many times more points you want. 2 = twice as many, 4 = four times as many."
        ),
        PropertySchema(
            name="preserve_normals", label="Keep Normals", type="boolean",
            default=True,
            help_text="Keep lighting and shading correct on new points. Turn off to speed things up."
        ),
        # ── Nearest Neighbor params ──────────────────────────────────────────
        PropertySchema(
            name="nn_params.displacement_min", label="Min Spread", type="number",
            default=0.05, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["nearest_neighbor"]},
            help_text="New points won't be placed closer than this. Lower = tighter clusters."
        ),
        PropertySchema(
            name="nn_params.displacement_max", label="Max Spread", type="number",
            default=0.50, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["nearest_neighbor"]},
            help_text="New points won't be placed farther than this. Higher = fills bigger gaps but may look rougher."
        ),
        # ── MLS params ───────────────────────────────────────────────────────
        PropertySchema(
            name="mls_params.k_neighbors", label="Smoothness", type="number",
            default=20, min=3, max=100, step=1,
            depends_on={"algorithm": ["mls"]},
            help_text="How many nearby points to look at when fitting the surface. Higher = smoother but slower."
        ),
        PropertySchema(
            name="mls_params.projection_radius_factor", label="Spread", type="number",
            default=0.5, min=0.01, max=2.0, step=0.05,
            depends_on={"algorithm": ["mls"]},
            help_text="How far from each point new ones can appear. Bigger = wider coverage."
        ),
        PropertySchema(
            name="mls_params.min_dist_factor", label="Min Gap", type="number",
            default=0.05, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["mls"]},
            help_text="Keeps new points from piling up on top of existing ones."
        ),
        # ── Statistical params ───────────────────────────────────────────────
        PropertySchema(
            name="statistical_params.k_neighbors", label="Scan Range", type="number",
            default=10, min=2, max=100, step=1,
            depends_on={"algorithm": ["statistical"]},
            help_text="How many nearby points to check when looking for thin areas. Higher = more thorough but slower."
        ),
        PropertySchema(
            name="statistical_params.sparse_percentile", label="Fill Amount (%)", type="number",
            default=50.0, min=1.0, max=100.0, step=1.0,
            depends_on={"algorithm": ["statistical"]},
            help_text="What portion of thin areas to fill. 50 = fill half, 80 = fill most gaps."
        ),
        PropertySchema(
            name="statistical_params.min_dist_factor", label="Min Gap", type="number",
            default=0.3, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["statistical"]},
            help_text="Keeps new points from piling up on top of existing ones."
        ),
        # ── Poisson params ───────────────────────────────────────────────────
        PropertySchema(
            name="poisson_params.depth", label="Detail", type="number",
            default=8, min=4, max=12, step=1,
            depends_on={"algorithm": ["poisson"]},
            help_text="How much detail to capture. Higher = sharper edges but much slower."
        ),
        PropertySchema(
            name="poisson_params.density_threshold_quantile", label="Edge Cleanup", type="number",
            default=0.1, min=0.0, max=0.5, step=0.01,
            depends_on={"algorithm": ["poisson"]},
            help_text="Trims stray points around the edges. Higher = cleaner edges, but may cut into the shape."
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


# --- Factory Builder ---
@NodeFactory.register("densify")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.pipeline.operation_node import OperationNode
    config = node.get("config", {})
    op_config = config.copy()
    op_config.pop("op_type", None)
    throttle_ms = op_config.pop("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    return OperationNode(
        manager=service_context,
        node_id=node["id"],
        op_type="densify",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
