"""
Registry for the passthrough_logger plugin.

Registers the NodeDefinition schema (UI palette) and the NodeFactory
builder (runtime instantiation).

This file is the ONLY required entry point — app/plugins/__init__.py
imports it when load_plugin("passthrough_logger") is called.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition,
    PortSchema,
    PropertySchema,
    node_schema_registry,
)

# ── 1. UI schema ───────────────────────────────────────────────────────────
#   Defines how the node appears in the Angular flow-canvas palette.

node_schema_registry.register(
    NodeDefinition(
        type="passthrough_logger",
        display_name="Passthrough Logger",
        category="operation",
        description=(
            "Forwards point-cloud data downstream unchanged while logging "
            "per-frame statistics (frame count, point count) to the server log."
        ),
        use_case="Debugging pipelines — insert between any two nodes to inspect throughput.",
        icon="output",
        websocket_enabled=True,
        properties=[
            PropertySchema(
                name="log_every_n",
                label="Log every N frames",
                type="number",
                default=10,
                min=1,
                step=1,
                help_text="Emit a log line once every N received frames (1 = every frame).",
            ),
            PropertySchema(
                name="throttle_ms",
                label="Throttle (ms)",
                type="number",
                default=0,
                min=0,
                step=10,
                help_text="Minimum time between processing frames (0 = no limit).",
            ),
        ],
        inputs=[PortSchema(id="in", label="Input")],
        outputs=[PortSchema(id="out", label="Output")],
    )
)


# ── 2. Factory builder ─────────────────────────────────────────────────────
#   Called by NodeFactory.create() when the orchestrator instantiates this
#   node type from a persisted DAG configuration.

@NodeFactory.register("passthrough_logger")
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    from app.plugins.passthrough_logger.node import PassthroughLoggerNode  # lazy

    config = node.get("config", {})

    log_every_n = config.get("log_every_n", 10)
    try:
        log_every_n = int(log_every_n)
    except (ValueError, TypeError):
        log_every_n = 10

    return PassthroughLoggerNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", "PassthroughLogger"),
        log_every_n=log_every_n,
    )
