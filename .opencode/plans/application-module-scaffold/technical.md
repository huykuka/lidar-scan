# Application Module Scaffold — Technical Specification

> **Architect Note**: All conventions below are verified directly from the codebase via GitNexus
> queries and source-file inspection of `lidar`, `pipeline`, `fusion`, `calibration`, and
> `flow_control` modules. No conventions were assumed.

---

## 1. Context & Design Goals

The `app/modules/application/` directory is already present in the filesystem (empty — 0 entries)
and is already on the `discover_modules()` search path. The DAG orchestration system will
automatically scan it at application startup because `discover_modules()` in
`app/modules/__init__.py` calls `pkgutil.iter_modules([package_dir])` on every direct
sub-package and tries to import `<subpackage>.registry`.

### Design Goals

1. **Zero divergence** from the established module pattern (lidar, pipeline, fusion, calibration,
   flow_control).
2. **Automatic discovery** — the module must register itself via side-effect imports with NO
   changes to `instance.py`, `app.py`, or `app/modules/__init__.py`.
3. **Full DAG citizen** — the node must support routing, throttling, lifecycle hooks, status
   aggregation, and optional WebSocket broadcasting.
4. **Standalone testability** — the entire module must be testable with mocked dependencies; no
   DB, no running server.

---

## 2. Auto-Discovery Mechanism (Confirmed via GitNexus)

```
app/services/nodes/instance.py
  └── discover_modules()            ← called once at startup
        └── pkgutil.iter_modules([app/modules/])
              └── importlib.import_module(".application.registry", package="app.modules")
                    ├── node_schema_registry.register(NodeDefinition(...))   ← side-effect
                    └── @NodeFactory.register("hello_world")                 ← side-effect
```

**Critical rule confirmed from source**: `discover_modules()` silently skips sub-packages that
have **no `registry.py`** (`ModuleNotFoundError` is caught and logged at DEBUG). Any other
exception is caught, logged at ERROR, and **does not crash the app**. The `application` package
must therefore:

1. Be a Python package (contain `__init__.py`).
2. Contain a `registry.py` at the package root.

---

## 3. File Structure

Each application node sub-package owns its own `registry.py` that registers its `NodeDefinition`
and `NodeFactory` in isolation (self-registering pattern, identical to
`flow_control/if_condition/registry.py` and `flow_control/output/registry.py`). The top-level
`app/modules/application/registry.py` is a **pure aggregator** that only imports and re-exposes
the sub-registries — it contains **no** `node_schema_registry.register(...)` or
`@NodeFactory.register(...)` calls of its own.

```
app/modules/application/
├── __init__.py                  # Package marker — may be empty
├── registry.py                  # AGGREGATOR ONLY: imports sub-registries, no direct registrations
├── base_node.py                 # Abstract ApplicationNode(ModuleNode) base class
└── hello_world/
    ├── __init__.py              # Package marker — may be empty
    ├── registry.py              # SELF-REGISTERING: NodeDefinition + NodeFactory for hello_world
    └── node.py                  # HelloWorldNode implementation
```

**Corresponding test tree:**

```
tests/modules/application/
├── __init__.py
├── test_hello_world.py          # Node logic tests
└── test_hello_world_registry.py # Registry isolation test (self-registering contract)
```

### Rationale for the Self-Registering Pattern

| Concern | Monolithic `registry.py` (old) | Self-registering sub-`registry.py` (new) |
|---|---|---|
| Adding a new application node | Requires editing top-level `registry.py` | Add `<node>/registry.py`, one line in aggregator |
| Isolation / testability | All nodes register when any is tested | Each node can be tested without importing siblings |
| Consistency with codebase | Diverges from `flow_control` | Exactly matches `flow_control/{if_condition,output}/registry.py` |
| Circular-import surface | Single large file accumulates risk | Each sub-registry is minimal and self-contained |

---

## 4. Detailed File Specifications

### 4.1 `app/modules/application/__init__.py`

Empty file (or minimal docstring). Its sole purpose is to make the directory a Python package
so `pkgutil.iter_modules` detects it.

```python
"""Application-level DAG node modules."""
```

---

### 4.2 `app/modules/application/base_node.py`

**Purpose**: Provide an optional intermediate abstract class `ApplicationNode(ModuleNode)` that
all application nodes can extend. This is the same pattern used by
`app/modules/pipeline/base.py` (`PipelineOperation`) and
`app/modules/calibration/calibration_node.py` (directly extends `ModuleNode`).

**Class Hierarchy:**

```
abc.ABC
└── ModuleNode          (app/services/nodes/base_module.py)
    └── ApplicationNode (app/modules/application/base_node.py)
        └── HelloWorldNode (app/modules/application/hello_world/node.py)
```

**Required contents:**

```python
"""
Abstract base class for all application-level DAG nodes.

Application nodes consume processed point cloud data from upstream nodes
and perform higher-level logic (analytics, detection, event processing).
Unlike pipeline operation nodes they are NOT expected to transform and
re-emit point clouds — they MAY forward data or act as sinks.
"""
from abc import abstractmethod
from typing import Any, Dict, Optional

from app.schemas.status import NodeStatusUpdate
from app.services.nodes.base_module import ModuleNode


class ApplicationNode(ModuleNode):
    """
    Abstract base class for all pluggable application-level nodes.

    Extends ModuleNode with conventions specific to application processing:
    - Nodes should store `self.id`, `self.name`, `self.manager` in __init__.
    - Heavy CPU work MUST be offloaded via `await asyncio.to_thread(...)`.
    - Forward results via `self.manager.forward_data(self.id, payload)`.

    Required attributes (must be set by concrete subclass __init__):
        id (str):      Unique node instance identifier.
        name (str):    Display name for this node.
        manager (Any): Reference to NodeManager (avoids circular import).
    """

    # --- Abstract interface (inherited from ModuleNode) ---

    @abstractmethod
    async def on_input(self, payload: Dict[str, Any]) -> None: ...

    @abstractmethod
    def emit_status(self) -> NodeStatusUpdate: ...
```

**Note**: `start()`, `stop()`, `enable()`, `disable()` are provided as no-ops in `ModuleNode`.
Application nodes only override them if they manage background resources.

---

### 4.3a `app/modules/application/hello_world/registry.py` — Self-Registering Node Registry

This is the **canonical file for each node** — it follows the exact pattern of
`flow_control/if_condition/registry.py`. Every application node sub-package must have its own
`registry.py` that registers its `NodeDefinition` schema **and** its `@NodeFactory` builder.
No `node_schema_registry.register(...)` or `@NodeFactory.register(...)` calls are allowed
outside of these per-node files.

```python
"""
Node registry for the hello_world application node.

Registers the hello_world node type with the DAG orchestrator.
Follows the canonical pattern from flow_control/if_condition/registry.py.
"""
from typing import Any, Dict, List

from app.services.nodes.node_factory import NodeFactory
from app.services.nodes.schema import (
    NodeDefinition, PropertySchema, PortSchema, node_schema_registry
)

# ─────────────────────────────────────────────────────────────────
# Schema Definition
# Defines how the node appears in the Angular flow-canvas UI palette
# ─────────────────────────────────────────────────────────────────

node_schema_registry.register(NodeDefinition(
    type="hello_world",
    display_name="Hello World App",
    category="application",
    description="Example application node: logs data, counts points, and forwards payload",
    icon="celebration",
    websocket_enabled=True,         # Forwards payload → downstream can render it
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
            help_text="Minimum milliseconds between processing frames (0 = no limit)",
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")],
))


# ─────────────────────────────────────────────────────────────────
# Factory Builder
# ─────────────────────────────────────────────────────────────────

@NodeFactory.register("hello_world")
def build_hello_world(
    node: Dict[str, Any],
    service_context: Any,
    edges: List[Dict[str, Any]],
) -> Any:
    """Build a HelloWorldNode instance from persisted node configuration."""
    from .node import HelloWorldNode  # lazy import — avoids circular dependency

    config = node.get("config", {})

    throttle_ms = config.get("throttle_ms", 0)
    try:
        throttle_ms = float(throttle_ms)
    except (ValueError, TypeError):
        throttle_ms = 0.0

    return HelloWorldNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Hello World",
        config=config,
        throttle_ms=throttle_ms,
    )
```

**Key architectural rules:**

| Rule | Source | Applied |
|---|---|---|
| Per-node `registry.py` inside the node sub-package | `flow_control/if_condition/registry.py`, `flow_control/output/registry.py` | `hello_world/registry.py` |
| Lazy import inside factory function | `if_condition/registry.py` L66 | `from .node import HelloWorldNode` inside body |
| `throttle_ms` extracted and normalized before passing to node | `pipeline/registry.py` L358-363 | `float(throttle_ms)` with try/except |
| `@NodeFactory.register("type")` decorator on a plain function | All existing registries | Applied exactly |
| Top-level `node_schema_registry.register(NodeDefinition(...))` side-effect | All existing registries | Applied exactly |

---

### 4.3b `app/modules/application/registry.py` — Aggregator Only

The top-level `application/registry.py` is a **pure aggregator** that imports each node
sub-registry to trigger their side-effects. It contains **zero** direct
`node_schema_registry.register(...)` or `@NodeFactory.register(...)` calls. This mirrors
`flow_control/registry.py` exactly.

```python
"""
Application module registry — aggregator.

Imports all application node sub-registries to trigger their side-effects
(NodeDefinition and NodeFactory registrations).

Loaded automatically via discover_modules() at application startup.

To add a new application node:
    1. Create app/modules/application/<node_name>/registry.py
       (NodeDefinition + @NodeFactory.register, lazy node import inside factory)
    2. Add one import line here:
       from .<node_name> import registry as <node_name>_registry
    3. Add the alias to __all__.
"""

from .hello_world import registry as hello_world_registry

__all__ = ["hello_world_registry"]
```

**Structural analogy:**

| `flow_control/` | `application/` |
|---|---|
| `flow_control/registry.py` (aggregator) | `application/registry.py` (aggregator) |
| `flow_control/if_condition/registry.py` | `application/hello_world/registry.py` |
| `flow_control/output/registry.py` | `application/<next_node>/registry.py` |

---

### 4.4 `app/modules/application/hello_world/__init__.py`

Empty (makes `hello_world/` a Python package, required for relative imports inside
`hello_world/registry.py`).

---

### 4.5 `app/modules/application/hello_world/node.py`

**Full interface contract** (see `api-spec.md` for payload details):

```python
"""
HelloWorldNode — example application-level DAG node.

Demonstrates the canonical application node pattern:
  1. Receive data via on_input()
  2. Perform lightweight processing (no heavy CPU → to_thread not needed here)
  3. Append metadata and forward via manager.forward_data()
  4. Report status via emit_status()
"""
import asyncio
import time
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.modules.application.base_node import ApplicationNode
from app.schemas.status import ApplicationState, NodeStatusUpdate, OperationalState
from app.services.status_aggregator import notify_status_change


logger = get_logger(__name__)


class HelloWorldNode(ApplicationNode):
    """
    Example application node.

    Receives any point cloud payload, logs it, appends a custom `message`
    field, records stats, and forwards the payload downstream.
    """

    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        config: Dict[str, Any],
        throttle_ms: float = 0,
    ) -> None:
        self.manager = manager
        self.id = node_id
        self.name = name
        self.config = config
        self.message: str = config.get("message", "Hello from DAG!")

        # Runtime stats
        self.input_count: int = 0
        self.last_input_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.processing_time_ms: float = 0.0

    # ── Lifecycle ────────────────────────────────────────────────

    def start(
        self,
        data_queue: Any = None,
        runtime_status: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called by NodeManager.start(). Log startup context."""
        logger.info(
            f"[{self.id}] HelloWorldNode '{self.name}' started. "
            f"message={self.message!r}"
        )

    def stop(self) -> None:
        """Called by NodeManager.stop(). Log shutdown."""
        logger.info(f"[{self.id}] HelloWorldNode '{self.name}' stopped.")

    # ── Data flow ────────────────────────────────────────────────

    async def on_input(self, payload: Dict[str, Any]) -> None:
        """
        Receive a payload from upstream, annotate, and forward downstream.

        Args:
            payload: Standard DAG payload dict.
                     Expected keys: points (np.ndarray), timestamp (float),
                     node_id (str), lidar_id (str, optional).
        """
        self.last_input_at = time.time()
        start_t = self.last_input_at

        points = payload.get("points")
        point_count = len(points) if points is not None else 0

        first_frame = self.input_count == 0
        self.input_count += 1

        logger.info(
            f"[{self.id}] on_input: {point_count} points "
            f"from node_id={payload.get('node_id')!r}. "
            f"message={self.message!r}"
        )

        try:
            # Build enriched payload (shallow copy to avoid mutating upstream data)
            new_payload = payload.copy()
            new_payload["node_id"] = self.id
            new_payload["processed_by"] = self.id
            new_payload["app_message"] = self.message
            new_payload["app_point_count"] = point_count

            self.processing_time_ms = (time.time() - start_t) * 1000
            self.last_error = None

            if first_frame:
                notify_status_change(self.id)

            # Fire-and-forget to avoid stalling this coroutine
            asyncio.create_task(self.manager.forward_data(self.id, new_payload))

        except Exception as exc:
            self.last_error = str(exc)
            notify_status_change(self.id)
            logger.error(f"[{self.id}] Error in on_input: {exc}", exc_info=True)

    # ── Status ───────────────────────────────────────────────────

    def emit_status(self) -> NodeStatusUpdate:
        """
        Return standardized status for StatusAggregator broadcasts.

        State mapping:
          - last_error set → ERROR, processing=False, gray
          - recent input (<5 s) → RUNNING, processing=True, blue
          - idle (no input yet or >5 s ago) → RUNNING, processing=False, gray
        """
        if self.last_error:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.ERROR,
                application_state=ApplicationState(
                    label="processing",
                    value=False,
                    color="gray",
                ),
                error_message=self.last_error,
            )

        recently_active = (
            self.last_input_at is not None
            and time.time() - self.last_input_at < 5.0
        )
        return NodeStatusUpdate(
            node_id=self.id,
            operational_state=OperationalState.RUNNING,
            application_state=ApplicationState(
                label="processing",
                value=recently_active,
                color="blue" if recently_active else "gray",
            ),
        )
```

---

## 5. DAG Integration Data Flow

```
LidarSensor ──► [edge] ──► HelloWorldNode.on_input(payload)
                                  │
                                  ├── payload.copy()                  # non-mutating
                                  ├── new_payload["app_message"] = …  # annotate
                                  └── manager.forward_data(self.id, new_payload)
                                              │
                                              ▼
                                  WebSocket broadcast (if visible + ws_enabled)
                                  Downstream nodes (if edges exist)
                                  Recording service (if recording active)
```

**NodeManager lifecycle interaction:**

| NodeManager method | HelloWorldNode reaction |
|---|---|
| `load_config()` → `ConfigLoader._create_node()` | `build_hello_world()` factory called |
| `start()` → `LifecycleManager.start_all_nodes()` | `start()` called (log only) |
| `stop()` → `LifecycleManager.stop_all_nodes()` | `stop()` called (log only) |
| `forward_data(upstream_id, payload)` | `on_input(payload)` called by DataRouter |
| `StatusAggregator` poll | `emit_status()` called |

---

## 6. WebSocket Topic Registration

When `websocket_enabled=True` in the `NodeDefinition` **and** the node instance's `visible=True`
in the DB record, `ConfigLoader._register_node_websocket_topic()` automatically:

1. Generates topic = `{slugify(node.name)}_{node.id[:8]}`
2. Calls `websocket_manager.register_topic(topic)`
3. Sets `node_instance._ws_topic = topic`

The `HelloWorldNode` must **not** set `_ws_topic` itself. The orchestrator owns this lifecycle.
The node only needs to call `manager.forward_data()` — the `DataRouter` reads `_ws_topic` and
broadcasts automatically.

---

## 7. Throttling

`throttle_ms` extracted in `registry.py` and passed as a constructor argument is accepted by
the node (stored or discarded). The **actual throttling is enforced centrally by `NodeManager`**
via `ThrottleManager`, which checks `_throttle_config[node_id]` before calling
`node.on_input()`. The node itself does NOT implement throttle logic.

---

## 8. Category in `ConfigLoader.initialize_nodes()`

The `ConfigLoader.initialize_nodes()` method initializes nodes in the order:
`sensor → operation → fusion → other`.

Nodes with `category="application"` fall into the **`other` bucket** (line 61 of `config.py`:
`other = [n for n in enabled_nodes if n.get("category") not in ("sensor", "operation", "fusion")]`).

This is correct — application nodes may depend on upstream sensor/operation/fusion nodes and
must initialize after them.

---

## 9. Circular Import Prevention

**Confirmed anti-pattern to avoid** (documented in `tests/services/test_circular_import_fix.py`):

```
BAD:  registry.py (top level) → from app.modules.application.hello_world.node import HelloWorldNode
GOOD: registry.py (inside factory func) → from app.modules.application.hello_world.node import HelloWorldNode
```

The `HelloWorldNode` itself may freely import `notify_status_change` and other utilities at the
top level **because** those utilities use lazy internal imports of `node_manager`.

---

## 10. Test Architecture

Tests live in `tests/modules/application/test_hello_world.py`. They must:

1. **Not** import from `app.services.nodes.instance` (that triggers `discover_modules()` +
   `NodeManager()` which requires a running app).
2. Use `unittest.mock.Mock` / `AsyncMock` for `manager`.
3. Import the module's public symbols directly:
   ```python
   from app.modules.application.hello_world.node import HelloWorldNode
   from app.modules.application.registry import build_hello_world
   from app.services.nodes.node_factory import NodeFactory
   from app.services.nodes.schema import node_schema_registry
   ```
4. For registry integration tests, reload registries to ensure side-effects run.

See `tests/modules/test_operation_node.py` and `tests/services/test_circular_import_fix.py` as
canonical test patterns.

---

## 11. Summary of Architectural Decisions

| Decision | Rationale |
|---|---|
| `ApplicationNode(ModuleNode)` intermediate base class | Enables future application nodes to share utilities without touching `ModuleNode` itself |
| `category="application"` | Falls into `other` bucket → initializes after sensors/operations/fusions |
| `websocket_enabled=True` on HelloWorldNode | It forwards data downstream; clients may subscribe to its output topic |
| Lazy import inside factory (`from .node import HelloWorldNode`) | Avoids circular import chain (`instance.py → discover_modules → registry → node → status_aggregator → instance.py`) |
| `asyncio.create_task(manager.forward_data(...))` | Fire-and-forget pattern; prevents slow downstream nodes from stalling `on_input` coroutine (matches `operation_node.py` L104) |
| `notify_status_change(self.id)` on first frame and on error | Consistent with `OperationNode` and `CalibrationNode` patterns |
| No `_ws_topic` manipulation in node code | NodeManager owns this via `ConfigLoader._register_node_websocket_topic()` |
| `throttle_ms` constructor arg accepted but not used | Throttling is central in `ThrottleManager`; node stores it for observability only |
| **Per-node `registry.py` inside each sub-package** | Matches `flow_control/if_condition/registry.py` exactly; each node is self-contained and self-registering; adding a new application node requires zero changes to any existing file except the one-line import in the aggregator |
| **Top-level `application/registry.py` is a pure aggregator** | Mirrors `flow_control/registry.py`; contains only `from .<node> import registry as …` imports and `__all__`; no `node_schema_registry.register()` or `@NodeFactory.register()` calls |
