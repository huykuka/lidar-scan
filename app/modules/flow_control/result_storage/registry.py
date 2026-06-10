"""
Node registry for the Result Storage flow-control module.

Registers the ``result_storage`` node type with the DAG orchestrator.
Loaded automatically when :mod:`app.modules.flow_control.registry` is imported.
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
        type="result_storage",
        display_name="Result Storage",
        category="flow_control",
        description=(
            "Terminal sink node that persists point-cloud results (PCD files) "
            "and metadata to the application results database. Accepts input "
            "exclusively from application-category nodes. Supports single-PCD "
            "payloads (via 'points' key) and multi-PCD payloads (via 'pcds' dict)."
        ),
        icon="save",
        websocket_enabled=False,
        properties=[
            PropertySchema(
                name="default_status",
                label="Default Result Status",
                type="select",
                default="success",
                options=[
                    {"label": "Success", "value": "success"},
                    {"label": "Warning", "value": "warning"},
                    {"label": "Error", "value": "error"},
                ],
                help_text=(
                    "Default status assigned to persisted results when the "
                    "upstream payload does not include an explicit status field."
                ),
            ),
            PropertySchema(
                name="status_key",
                label="Status Metadata Key",
                type="string",
                default="",
                help_text=(
                    "Optional metadata key to derive the result status from. "
                    "When set, the node reads this key from the payload metadata "
                    "and maps truthy values to 'success' and falsy to 'warning'. "
                    "Leave empty to always use the default status above."
                ),
            ),
        ],
        inputs=[
            PortSchema(
                id="in",
                label="Application Result",
                data_type="any",
                allowed_source_categories=["application"],
            ),
        ],
        outputs=[],
    )
)


# ─────────────────────────────────────────────────────────────────────────────
# Factory Builder
# ─────────────────────────────────────────────────────────────────────────────


@NodeFactory.register("result_storage")
def build_result_storage(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build a ResultStorageNode from persisted node configuration."""
    from .node import ResultStorageNode

    config: Dict[str, Any] = node.get("config") or {}

    try:
        from app.api.v1.results.router import _get_service as _get_results_svc
        results_svc = _get_results_svc()
    except Exception:
        results_svc = None

    return ResultStorageNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Result Storage",
        config=config,
        results_service=results_svc,
    )
