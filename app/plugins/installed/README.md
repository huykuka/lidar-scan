# Plugin Development Blueprint

Plugins live here as individual Python packages. Each plugin is auto-loaded
at startup by `discover_plugins()` and can also be uploaded at runtime via
`POST /nodes/plugins/upload`.

---

## Directory layout

```
my_plugin/
    __init__.py    ← package marker + short docstring
    registry.py    ← REQUIRED: registers NodeDefinition + NodeFactory builder
    node.py        ← node implementation (extend ModuleNode)
```

> Packages whose name starts with `_` are skipped by `discover_plugins`
> (use this convention for templates / drafts).

See `_template/` for a fully-annotated skeleton you can copy.

---

## Contract checklist

### registry.py
- [ ] `node_schema_registry.register(NodeDefinition(...))` called at module level
- [ ] `@NodeFactory.register("<type>")` decorator on a factory function
- [ ] Factory function signature: `build(node, service_context, edges) -> ModuleNode`
- [ ] `type` string is globally unique (use `vendor_name` convention, e.g. `acme_filter`)

### node.py (ModuleNode subclass)
- [ ] `async def on_input(self, payload: dict)` — called for every incoming frame
- [ ] `def emit_status(self) -> NodeStatusUpdate` — polled by the orchestrator
- [ ] `def start(...)` **or** `def enable()` — lifecycle activation

### NodeDefinition fields
| Field | Notes |
|---|---|
| `type` | Unique string key matching `@NodeFactory.register(...)` |
| `display_name` | Shown in the Angular palette |
| `category` | `"sensor"` / `"fusion"` / `"operation"` |
| `icon` | Material Symbols icon name |
| `websocket_enabled` | `False` hides visibility + recording controls in UI |
| `properties` | List of `PropertySchema` — rendered as config panel inputs |
| `inputs` / `outputs` | List of `PortSchema` — rendered as DAG ports |

### PropertySchema `type` values
`"string"` · `"number"` · `"boolean"` · `"select"` · `"vec3"` · `"list"` · `"pose"`

---

## Pack & upload

```bash
# Validate + zip the plugin (output goes to plugin_packages/<name>.zip)
bash scripts/pack_plugin.sh app/plugins/installed/my_plugin

# Upload via API
curl -X POST http://localhost:8005/api/v1/nodes/plugins/upload \
     -F "file=@plugin_packages/my_plugin.zip"

# List loaded plugins
curl http://localhost:8005/api/v1/nodes/plugins
```

The script runs AST validation before zipping and will exit with an error if
the plugin structure is invalid (missing registry call, wrong factory signature,
missing `on_input` / `emit_status` / `start`/`enable`).
