"""
Registry for _template.

This is the ONLY file the plugin loader imports.  It must:
  1. Call node_schema_registry.register(NodeDefinition(...))  — UI palette entry
  2. Decorate a factory function with @NodeFactory.register("<type>")  — runtime builder

Copy this file, replace every TODO, and rename the type string to something
globally unique (convention: <vendor>_<purpose>, e.g. "acme_bandpass").
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
#
#   NodeDefinition fields:
#     type            – unique key; MUST match @NodeFactory.register(...)
#     display_name    – label in the Angular node palette
#     category        – "sensor" | "fusion" | "operation"
#     description     – tooltip / help text shown in the palette
#     use_case        – one-line explanation of when to use this node
#     icon            – Material Symbols icon name (https://fonts.google.com/icons)
#     websocket_enabled – False hides visibility & recording controls in the UI
#     properties      – list of PropertySchema — rendered as the config panel
#     inputs / outputs – list of PortSchema — rendered as DAG edge connectors

node_schema_registry.register(
    NodeDefinition(
        type="TODO_my_plugin",                  # TODO: unique snake_case type key
        display_name="TODO My Plugin",          # TODO: human label
        category="operation",                   # TODO: "sensor" | "fusion" | "operation"
        description="TODO one-sentence description.",
        use_case="TODO when would someone use this?",
        icon="settings_input_component",        # TODO: Material Symbols icon name
        websocket_enabled=True,                 # set False if node never streams data
        properties=[
            # ── String input ──────────────────────────────────────────────
            PropertySchema(
                name="my_string_param",
                label="My String Param",
                type="string",
                default="hello",
                required=False,
                help_text="A free-text configuration value.",
            ),
            # ── Number input ──────────────────────────────────────────────
            PropertySchema(
                name="my_number_param",
                label="My Number Param",
                type="number",
                default=1.0,
                min=0.0,
                max=100.0,
                step=0.5,
                help_text="A numeric slider / input.",
            ),
            # ── Boolean toggle ────────────────────────────────────────────
            PropertySchema(
                name="my_bool_param",
                label="Enable Feature",
                type="boolean",
                default=False,
                help_text="Toggle a binary option.",
            ),
            # ── Drop-down select ──────────────────────────────────────────
            PropertySchema(
                name="my_select_param",
                label="Algorithm",
                type="select",
                default="fast",
                options=[
                    {"label": "Fast",     "value": "fast"},
                    {"label": "Accurate", "value": "accurate"},
                ],
                help_text="Pick one of the predefined options.",
            ),
            # ── Conditional property (shown only when another has a value) ─
            PropertySchema(
                name="my_conditional_param",
                label="Accuracy Threshold",
                type="number",
                default=0.01,
                depends_on={"my_select_param": ["accurate"]},  # shown only when accurate
                help_text="Only visible when Algorithm = Accurate.",
            ),
        ],
        inputs=[
            PortSchema(id="in", label="Input"),   # remove if this is a source node
        ],
        outputs=[
            PortSchema(id="out", label="Output"), # remove if this is a sink node
        ],
    )
)


# ── 2. Factory builder ─────────────────────────────────────────────────────
#
#   Signature is fixed: (node, service_context, edges) -> ModuleNode instance.
#
#   node            – dict from persisted DAG: {"id": "...", "config": {...}, ...}
#   service_context – NodeManager instance (pass to ModuleNode as manager=)
#   edges           – list of DAG edge dicts (rarely needed; usually ignored)

@NodeFactory.register("TODO_my_plugin")         # TODO: same type key as NodeDefinition
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    # ── Lazy import keeps startup fast and avoids circular deps ────────────
    from app.plugins.installed._template.node import TemplateNode  # TODO: update import path after renaming

    config = node.get("config", {})

    # ── Safely extract + coerce each config value ──────────────────────────
    my_string = str(config.get("my_string_param", "hello"))

    try:
        my_number = float(config.get("my_number_param", 1.0))
    except (ValueError, TypeError):
        my_number = 1.0

    my_bool = bool(config.get("my_bool_param", False))
    my_select = str(config.get("my_select_param", "fast"))

    return TemplateNode(                         # TODO: replace with your node class
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", "TemplateNode"),
        my_string=my_string,
        my_number=my_number,
        my_bool=my_bool,
        my_select=my_select,
    )
