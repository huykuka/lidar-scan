"""
Node registry for the Object Classification application module.

Registers the ``object_classification`` node type with the DAG orchestrator.
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
        type="object_classification",
        display_name="Object Classification",
        category="application",
        description=(
            "Real-time object detection and classification node. Uses DBSCAN "
            "clustering to segment the point cloud into individual objects, then "
            "classifies each cluster by bounding box dimensions using configurable "
            "size rules. Emits labeled 3D shape overlays and classification metadata."
        ),
        icon="category",
        websocket_enabled=True,
        properties=[
            # ── Clustering Parameters ────────────────────────────────────
            PropertySchema(
                name="eps",
                label="Cluster Distance (m)",
                type="number",
                default=0.3,
                min=0.05,
                max=5.0,
                step=0.05,
                help_text=(
                    "Maximum distance (metres) between two points for them to be "
                    "considered part of the same cluster (DBSCAN ε). Lower values "
                    "produce tighter clusters; higher values merge spread-out "
                    "returns. Set to roughly 2× the expected point spacing."
                ),
            ),
            PropertySchema(
                name="min_cluster_points",
                label="Min Cluster Points",
                type="number",
                default=10,
                min=3,
                max=500,
                step=1,
                help_text=(
                    "Minimum number of points a cluster must contain to be "
                    "considered for classification. Rejects small noise clusters. "
                    "Increase if false positives appear; decrease for sparse clouds."
                ),
            ),
            PropertySchema(
                name="min_classify_points",
                label="Min Points for Classification",
                type="number",
                default=5,
                min=1,
                max=200,
                step=1,
                help_text=(
                    "Minimum number of points in a cluster to attempt size-based "
                    "classification. Clusters below this are still detected but "
                    "may have unreliable bounding box dimensions."
                ),
            ),
            # ── Display Options ──────────────────────────────────────────
            PropertySchema(
                name="show_unknown",
                label="Show Unknown Objects",
                type="boolean",
                default=True,
                help_text=(
                    "Whether to display bounding boxes for objects that don't "
                    "match any classification rule. Disable to only show "
                    "positively classified objects."
                ),
            ),
        ],
        inputs=[
            PortSchema(
                id="cloud_input",
                label="Point Cloud",
                multiple=False,
            ),
        ],
        outputs=[
            PortSchema(id="classified_output", label="Classified Cloud"),
        ],
    )
)


# ─────────────────────────────────────────────────────────────────────────────
# Factory Builder
# ─────────────────────────────────────────────────────────────────────────────


@NodeFactory.register("object_classification")
def build_object_classification(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build an ObjectClassificationNode from persisted node configuration.

    Called by NodeFactory.create() when the orchestrator instantiates a node
    of type ``"object_classification"``.
    """
    from app.modules.application.object_classification.node import (
        ObjectClassificationNode,
    )

    config: Dict[str, Any] = node.get("config") or {}

    return ObjectClassificationNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Object Classification",
        config=config,
    )
