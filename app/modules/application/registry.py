"""
Node registry for the application module.

Registers all application-level node types with the DAG orchestrator.
Loaded automatically via :func:`~app.modules.discover_modules` at
application startup.

Side-effects executed at import time:

* :data:`~app.services.nodes.schema.node_schema_registry` receives the
  ``NodeDefinition`` for every node type defined here.
* :class:`~app.services.nodes.node_factory.NodeFactory` receives the
  builder function for every node type via the
  :meth:`~app.services.nodes.node_factory.NodeFactory.register` decorator.

Important — circular import prevention
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``HelloWorldNode`` class is imported **lazily** (inside the factory
function body) to avoid the circular dependency chain::

    instance.py → discover_modules() → registry → HelloWorldNode
    → status_aggregator → instance.py  (circular!)

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
# Schema Definition
# Defines how the node appears in the Angular flow-canvas UI palette.
# ─────────────────────────────────────────────────────────────────────────────

node_schema_registry.register(
    NodeDefinition(
        type="hello_world",
        display_name="Hello World App",
        category="application",
        description=(
            "Example application node: logs data, counts points, and forwards payload"
        ),
        icon="celebration",
        websocket_enabled=True,  # Forwards payload → downstream can render it
        properties=[
            PropertySchema(
                name="message",
                label="Message",
                type="string",
                default="Hello from DAG!",
                required=False,
                help_text="Custom message appended to every forwarded payload",
            ),
            PropertySchema(
                name="throttle_ms",
                label="Throttle (ms)",
                type="number",
                default=0,
                min=0,
                step=10,
                help_text=(
                    "Minimum milliseconds between processing frames "
                    "(0 = no limit)"
                ),
            ),
        ],
        inputs=[PortSchema(id="in", label="Input")],
        outputs=[PortSchema(id="out", label="Output")],
    )
)


# ─────────────────────────────────────────────────────────────────────────────
# Factory Builder
# ─────────────────────────────────────────────────────────────────────────────


@NodeFactory.register("hello_world")
def build_hello_world(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """
    Build a :class:`~app.modules.application.hello_world.node.HelloWorldNode`
    from a persisted node configuration record.

    Called by :meth:`~app.services.nodes.node_factory.NodeFactory.create`
    when the orchestrator instantiates a node of type ``"hello_world"``.

    Args:
        node:            Full node record produced by ``NodeModel.to_dict()``.
                         Relevant keys: ``"id"``, ``"name"``, ``"config"``.
        service_context: The :class:`~app.services.nodes.orchestrator.NodeManager`
                         instance (injected as ``manager`` into the node).
        edges:           Full list of DAG edges (may be used to resolve upstream
                         nodes; not required by ``HelloWorldNode``).

    Returns:
        A configured :class:`~app.modules.application.hello_world.node.HelloWorldNode`
        instance ready for integration into the DAG.
    """
    # Lazy import breaks the circular-import chain documented in technical.md § 9
    from app.modules.application.hello_world.node import HelloWorldNode  # noqa: PLC0415

    config: Dict[str, Any] = node.get("config") or {}

    # Normalise throttle_ms to float; fall back to 0 on bad input
    throttle_ms: float
    try:
        throttle_ms = float(config.get("throttle_ms", 0) or 0)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    return HelloWorldNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Hello World",
        config=config,
        throttle_ms=throttle_ms,
    )
