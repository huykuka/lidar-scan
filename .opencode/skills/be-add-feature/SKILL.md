# Skill: Add New Feature (Builtin Module vs Extension Plugin)

Loaded by `be-dev` when implementing any new processing node or domain feature.
Answers: **where does this code live and what files do I create?**

---

## Decision: Builtin Module vs Extension Plugin

Master will have already clarified this with the user. The answer determines everything.

| Question | Builtin (`app/modules/`) | Extension Plugin (`app/plugins/installed/`) |
|---|---|---|
| Shipped with the app? | Yes — always present | Optional — can be uploaded at runtime |
| Hot-pluggable via API? | No | Yes (`POST /api/v1/nodes/plugins/upload`) |
| Discovery mechanism | `discover_modules()` scans sub-packages | `discover_plugins()` scans `installed/` |
| Requires app restart to add? | Yes | No (upload API hot-loads) |
| Typical use | Core sensors, fusion, pipeline ops | Customer/vendor-specific algorithms |

---

## Path A — Extension Plugin (`app/plugins/installed/`)

### File layout

```
app/plugins/installed/<snake_name>/
    __init__.py      ← package marker + one-line docstring (REQUIRED)
    registry.py      ← NodeDefinition + @NodeFactory.register (REQUIRED)
    node.py          ← ModuleNode subclass (REQUIRED)
    utils/           ← optional private helpers
        __init__.py
        <helper>.py
```

> Name must NOT start with `_` — those are skipped by `discover_plugins()`.

### Step-by-step

#### 1. Copy template
```bash
cp -r app/plugins/installed/_template app/plugins/installed/<snake_name>
```

#### 2. `__init__.py`
```python
"""<One-line description of what this plugin does>."""
```

#### 3. `registry.py` — full contract

```python
from typing import Any, Dict, List
from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PortSchema, PropertySchema, node_schema_registry,
)

node_schema_registry.register(
    NodeDefinition(
        type="<vendor>_<purpose>",          # UNIQUE globally — snake_case
        display_name="<Human Label>",
        category="operation",               # "sensor" | "fusion" | "operation" | "application"
        description="<One sentence>.",
        icon="<material_symbols_name>",     # https://fonts.google.com/icons
        websocket_enabled=True,             # False if node never streams to UI
        properties=[
            PropertySchema(
                name="<param>",
                label="<Label>",
                type="number",              # "string"|"number"|"boolean"|"select"|"vec3"|"list"|"pose"
                default=1.0,
                min=0.0, max=100.0, step=0.1,
                help_text="<Tooltip text>.",
            ),
            # PropertySchema with depends_on for conditional visibility:
            # depends_on={"other_param": ["value_a", "value_b"]}
        ],
        inputs=[PortSchema(id="in", label="Input")],    # remove if source node
        outputs=[PortSchema(id="out", label="Output")], # remove if sink node
    )
)

@NodeFactory.register("<vendor>_<purpose>")   # MUST match NodeDefinition.type exactly
def build(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    # Lazy import — keeps startup fast, avoids circular deps
    from app.plugins.installed.<snake_name>.node import <ClassName>

    config = node.get("config") or {}
    return <ClassName>(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "<Human Label>",
        # coerce each config value with fallback:
        my_param=float(config.get("my_param", 1.0)),
    )
```

#### 4. `node.py` — full contract

```python
import asyncio
from typing import Any, Dict, Optional
from app.core.logging import get_logger
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.nodes.base_module import ModuleNode
from app.services.status_aggregator import notify_status_change

logger = get_logger(__name__)

class <ClassName>(ModuleNode):
    def __init__(self, manager, node_id, name, my_param=1.0):
        self.manager = manager
        self.id = node_id
        self.name = name
        self.my_param = my_param
        self._enabled = False
        self._frame_count = 0
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self, data_queue=None, runtime_status=None) -> None:
        self._enabled = True
        notify_status_change(self.id)

    def stop(self) -> None:
        self._enabled = False
        self.last_error = None
        notify_status_change(self.id)

    # ── Data path ──────────────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """Called for every incoming frame by the orchestrator."""
        if not self._enabled:
            return

        points = payload.get("points")
        if points is None or len(points) == 0:
            return

        import time
        start = time.time()
        try:
            # ── CPU work < 1 ms: run directly ─────────────────────────────
            result = my_processing_fn(points, self.my_param)

            # ── CPU work > 1 ms: offload to thread ─────────────────────────
            # result = await asyncio.to_thread(my_heavy_fn, points)

            self._frame_count += 1
            self.processing_time_ms = (time.time() - start) * 1000
            self.last_error = None

            out_payload = {**payload, "points": result}
            asyncio.create_task(self.manager.forward_data(self.id, out_payload))
        except Exception as e:
            self.last_error = str(e)
            logger.error("[%s] error: %s", self.id, e, exc_info=True)
        finally:
            notify_status_change(self.id)

    # ── Status ─────────────────────────────────────────────────────────────

    def emit_status(self) -> NodeStatusUpdate:
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(label="state", value="error", color="red"),
                error_message=self.last_error,
            )
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING if self._enabled else OperationalState.STOPPED,
            application_state=ApplicationState(
                label="frames",
                value=str(self._frame_count),
                color="green" if self._enabled else "gray",
            ),
        )
```

#### 5. Verify contract
```bash
# Plugin loader validates structure before zipping:
bash scripts/pack_plugin.sh app/plugins/installed/<snake_name>

# Upload to running instance (hot-load):
curl -X POST http://localhost:8005/api/v1/nodes/plugins/upload \
     -F "file=@plugin_packages/<snake_name>.zip"

# Confirm loaded:
curl http://localhost:8005/api/v1/nodes/plugins
```

#### 6. Tests
- `tests/modules/test_<snake_name>_node.py` — unit test `on_input`, `emit_status`, `start/stop`
- `tests/api/test_plugin_<snake_name>.py` — integration: upload + NodeFactory creates node

---

## Path B — Builtin Module (`app/modules/<category>/`)

Use when the feature ships with the application (not customer-uploadable).

### Categories

| Folder | Purpose |
|---|---|
| `app/modules/lidar/` | LiDAR sensor drivers and profiles |
| `app/modules/fusion/` | Multi-sensor fusion algorithms |
| `app/modules/pipeline/` | Pipeline operations (filter, transform, gate) |
| `app/modules/application/` | Application-level algorithms (volume, profiler, etc.) |
| `app/modules/calibration/` | Calibration nodes |
| `app/modules/flow_control/` | Gate, trigger, timing nodes |
| `app/modules/pcd_injection/` | Manual point cloud injection |
| `app/modules/playback/` | Recording playback nodes |
| `app/modules/visionary/` | SICK Visionary camera nodes |

### File layout

```
app/modules/<category>/<name>/
    __init__.py
    registry.py      ← NodeDefinition + @NodeFactory.register
    node.py          ← ModuleNode subclass
    utils/           ← optional helpers
```

### Step-by-step

#### 1. Create module folder
```bash
mkdir -p app/modules/<category>/<name>
touch app/modules/<category>/<name>/__init__.py
```

#### 2. `registry.py`

Same structure as plugin `registry.py` (see Path A §3), **except**:
- Import path for node: `from app.modules.<category>.<name>.node import <ClassName>`
- No vendor prefix needed on `type` (it's internal)

#### 3. `node.py`

Identical contract to plugin `node.py` (see Path A §4).

#### 4. Register in category registry

Open `app/modules/<category>/registry.py` (or `__init__.py`) and add:

```python
from .<name> import registry as <name>_registry  # noqa: F401
```

If there is no category-level `registry.py`, add one:
```python
# app/modules/<category>/registry.py
from .<name> import registry as <name>_registry  # noqa: F401
```

And ensure `app/modules/<category>/__init__.py` exposes it or that
`discover_modules()` will find it (it auto-imports `registry.py` from each direct sub-package of `app/modules/`).

> **Important for `application/` category**: `app/modules/application/registry.py` already exists and must be updated manually — `discover_modules()` imports it, which then imports sub-registries.

#### 5. Verify startup loads it
```bash
uv run uvicorn main:app --reload --port 8005
# Look for: [modules] Loaded core module: <category>
# Or: INFO app.modules — no error for <name>
```

#### 6. Tests
- `tests/modules/test_<name>_node.py` — unit test node class
- `tests/integration/test_<name>_pipeline.py` — integration with orchestrator

---

## Also needed: Frontend node UI plugin

When adding any new node type (builtin or plugin), a matching **frontend plugin** is usually needed so the node appears correctly in the DAG palette and has a config panel.

Inform `@fe-dev` with:
- Node `type` string (e.g. `"acme_bandpass"`)
- `NodeDefinition.properties` list (so FE can render the config form)
- `NodeDefinition.inputs` / `outputs` (so FE can render DAG ports)
- `category` (determines which palette group it appears in)
- Whether it streams WebSocket data (so FE can render live visualisation)

Frontend plugin lives in: `web/src/app/plugins/<category>/`

---

## Common mistakes (blockers in review)

| Mistake | Correct |
|---|---|
| `from app.modules.application.<name>.node import ...` in plugin | `from app.plugins.installed.<name>.node import ...` |
| Forgetting `__init__.py` in plugin folder | Add empty `__init__.py` |
| `type` in `NodeDefinition` ≠ `@NodeFactory.register(...)` key | They must be identical strings |
| Plugin name starts with `_` | Rename — `discover_plugins()` skips it |
| Not calling `notify_status_change(self.id)` after state change | Add it in `start()`, `stop()`, and error paths |
| Not updating category `registry.py` for builtin module | Add `from .<name> import registry` import |
| CPU-heavy sync work in `async def on_input` without `asyncio.to_thread` | Wrap ops > ~1 ms in `await asyncio.to_thread(fn, args)` |
