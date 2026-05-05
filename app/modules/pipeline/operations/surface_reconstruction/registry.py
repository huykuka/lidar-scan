"""
Node registry for the surface reconstruction operation.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# --- Schema Definition ---
node_schema_registry.register(NodeDefinition(
    type="surface_reconstruction",
    display_name="Surface Reconstruction",
    category="operation",
    description="Reconstructs a triangle mesh from a point cloud and samples it back to points",
    icon="view_in_ar",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number", default=0, min=0, step=10,
                       help_text="Minimum time between processing frames (0 = no limit)"),
        PropertySchema(
            name="algorithm", label="Algorithm", type="select",
            default="poisson",
            options=[
                {"label": "Alpha Shape (Fast, Convex Hull)",  "value": "alpha_shape"},
                {"label": "Ball Pivoting (Balanced)",         "value": "ball_pivoting"},
                {"label": "Poisson (Smooth, Best Quality)",   "value": "poisson"},
            ],
            help_text="Surface reconstruction method. Poisson gives the smoothest results."
        ),
        PropertySchema(
            name="sample_points", label="Resample Points", type="number",
            default=0, min=0, step=1000,
            help_text="Resample mesh to this many points. 0 = use mesh vertices directly."
        ),
        PropertySchema(
            name="estimate_normals", label="Estimate Normals", type="boolean",
            default=True,
            help_text="Estimate normals on input if missing. Required for Ball Pivoting and Poisson."
        ),
        PropertySchema(
            name="normal_radius", label="Normal Radius (m)", type="number",
            default=0.1, min=0.001, max=10.0, step=0.01,
            help_text="Search radius for normal estimation."
        ),
        PropertySchema(
            name="normal_max_nn", label="Normal Max Neighbours", type="number",
            default=30, min=3, max=200, step=1,
            help_text="Max neighbours for normal estimation."
        ),
        # ── Alpha Shape params ────────────────────────────────────────────────
        PropertySchema(
            name="alpha_shape_params.alpha", label="Alpha", type="number",
            default=0.03, min=0.001, max=10.0, step=0.01,
            depends_on={"algorithm": ["alpha_shape"]},
            help_text="Controls surface detail. Smaller = finer mesh, larger = coarser hull."
        ),
        # ── Ball Pivoting params ──────────────────────────────────────────────
        PropertySchema(
            name="ball_pivoting_params.radii", label="Ball Radii (m)", type="string",
            default="0.005,0.01,0.02,0.04",
            depends_on={"algorithm": ["ball_pivoting"]},
            help_text="Comma-separated ball radii. Multiple radii handle varying point densities."
        ),
        # ── Poisson params ────────────────────────────────────────────────────
        PropertySchema(
            name="poisson_params.depth", label="Octree Depth", type="number",
            default=8, min=1, max=13, step=1,
            depends_on={"algorithm": ["poisson"]},
            help_text="Higher = finer detail but slower. 8 is a good default."
        ),
        PropertySchema(
            name="poisson_params.scale", label="Scale", type="number",
            default=1.1, min=0.1, max=5.0, step=0.1,
            depends_on={"algorithm": ["poisson"]},
            help_text="Ratio between reconstruction cube and bounding cube."
        ),
        PropertySchema(
            name="poisson_params.linear_fit", label="Linear Fit", type="boolean",
            default=False,
            depends_on={"algorithm": ["poisson"]},
            help_text="Use linear interpolation for surface positioning."
        ),
        PropertySchema(
            name="poisson_params.density_quantile", label="Density Trim", type="number",
            default=0.01, min=0.0, max=1.0, step=0.01,
            depends_on={"algorithm": ["poisson"]},
            help_text="Remove low-density vertices below this quantile. Higher = more trimming."
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))


def _unflatten_dot_keys(flat: Dict[str, Any]) -> Dict[str, Any]:
    """Unflatten dot-notation keys into nested dicts.

    Example: {"poisson_params.depth": 12, "algorithm": "poisson"}
          -> {"poisson_params": {"depth": 12}, "algorithm": "poisson"}
    """
    out: Dict[str, Any] = {}
    for key, value in flat.items():
        if "." in key:
            parent, child = key.split(".", 1)
            out.setdefault(parent, {})[child] = value
        else:
            out[key] = value
    return out


# --- Factory Builder ---
@NodeFactory.register("surface_reconstruction")
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

    op_config = _unflatten_dot_keys(op_config)

    return OperationNode(
        manager=service_context,
        node_id=node["id"],
        op_type="surface_reconstruction",
        op_config=op_config,
        name=node.get("name"),
        throttle_ms=throttle_ms,
    )
