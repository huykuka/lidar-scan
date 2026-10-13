"""
Node registry for the Point Cloud Matching module.

Registers the UI schema and the factory for the ``point_cloud_matching`` node.
Loaded automatically via discover_modules() at application startup.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PortSchema, PropertySchema, node_schema_registry,
)

node_schema_registry.register(NodeDefinition(
    type="point_cloud_matching",
    display_name="Point Cloud Matching",
    category="operation",
    description="Finds a stored reference point cloud in the incoming frames and reports its pose",
    use_case="Locate a known object (pallet, part, vehicle section) in a live scan — "
             "upload the reference once in Point Cloud Assets, then pick it here to get "
             "its position, orientation and bounding box per frame.",
    icon="join_inner",
    websocket_enabled=True,
    properties=[
        PropertySchema(
            name="asset_id", label="Reference Asset", type="select", default="",
            required=True, options_source="point_cloud_assets",
            help_text="Reference point cloud to look for (managed on the Point Cloud Assets page).",
        ),
        PropertySchema(
            name="reference_scale", label="Reference Scale", type="number",
            default=1.0, min=0.000001, step=0.001,
            help_text="Multiply the reference by this to convert it to metres (e.g. 0.001 for millimetres).",
        ),
        PropertySchema(
            name="voxel_size", label="Voxel Size (m)", type="number",
            default=0.05, min=0.005, max=1.0, step=0.005,
            help_text="Downsampling resolution for matching. Larger is faster, smaller is more precise.",
        ),
        PropertySchema(
            name="min_fitness", label="Min Fitness", type="number",
            default=0.3, min=0.0, max=1.0, step=0.05,
            help_text="Fraction of the reference that must be explained by the scene. "
                      "Lower for partially visible objects, raise to reject false positives.",
        ),
        PropertySchema(
            name="max_instances", label="Max Instances", type="number",
            default=1, min=1, max=20, step=1,
            help_text="Maximum number of copies of the reference to look for per frame.",
        ),
        PropertySchema(
            name="tracking", label="Track Between Frames", type="boolean", default=True,
            help_text="Seed each frame from the previous pose (fast ICP) and fall back to a full "
                      "search when lost. Only used when Max Instances = 1.",
        ),
        PropertySchema(
            name="output_mode", label="Output Points", type="select", default="passthrough",
            options=[
                {"label": "Pass through input", "value": "passthrough"},
                {"label": "Matched points only", "value": "matched_points"},
            ],
            help_text="'Matched points only' drops frames where nothing was found.",
        ),
        PropertySchema(
            name="emit_shapes", label="Emit Bounding Boxes", type="boolean", default=True,
            help_text="Draw a box around each match in the 3D view.",
        ),
        PropertySchema(
            name="ransac_iterations", label="RANSAC Iterations", type="number",
            default=100000, min=1000, max=10000000, step=1000,
            help_text="Upper bound for the global search. Higher is more robust but slower.",
        ),
        PropertySchema(
            name="icp_iterations", label="ICP Iterations", type="number",
            default=50, min=1, max=500, step=1,
            help_text="Maximum refinement iterations.",
        ),
        PropertySchema(
            name="throttle_ms", label="Throttle (ms)", type="number",
            default=0, min=0, step=10,
            help_text="Minimum wait time between frames. 0 = process every frame.",
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")],
))


def _num(config: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(config.get(key, default))
    except (TypeError, ValueError):
        return float(default)


@NodeFactory.register("point_cloud_matching")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.modules.matching.node import MatchingNode

    c = node.get("config", {})
    return MatchingNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", node["id"]),
        asset_id=str(c.get("asset_id") or ""),
        reference_scale=_num(c, "reference_scale", 1.0),
        voxel_size=_num(c, "voxel_size", 0.05),
        min_fitness=_num(c, "min_fitness", 0.3),
        max_instances=int(_num(c, "max_instances", 1)),
        tracking=bool(c.get("tracking", True)),
        output_mode=str(c.get("output_mode", "passthrough")),
        emit_shapes=bool(c.get("emit_shapes", True)),
        ransac_iterations=int(_num(c, "ransac_iterations", 100000)),
        icp_iterations=int(_num(c, "icp_iterations", 50)),
    )
