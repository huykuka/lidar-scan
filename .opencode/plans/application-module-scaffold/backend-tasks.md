# Application Module Scaffold — Backend Tasks

> **For**: `@be-dev`
> **References**: `technical.md`, `api-spec.md`, `requirements.md`
> **No** REST endpoints or database changes are required for this feature.
> **No** changes to `app/modules/__init__.py`, `instance.py`, or `orchestrator.py`.

---

## Task Overview

Create the `app/modules/application/` module from scratch, following the **self-registering
sub-registry pattern** established by `flow_control/if_condition/registry.py` and
`flow_control/output/registry.py`.

**Architecture rule (mandatory):**
Every application node sub-package must own its own `registry.py` that registers its
`NodeDefinition` schema and its `@NodeFactory` builder. The top-level
`app/modules/application/registry.py` is a **pure aggregator** — it only imports sub-registries
and exposes them via `__all__`. It contains **no** `node_schema_registry.register(...)` or
`@NodeFactory.register(...)` calls.

The `application/` directory already exists on disk but is empty.

---

## Task 1: Package Scaffolding

- [ ] **1.1** Create `app/modules/application/__init__.py`
  - Content: minimal docstring `"""Application-level DAG node modules."""`
  - This makes the directory a proper Python package for `pkgutil.iter_modules`

- [ ] **1.2** Create `app/modules/application/hello_world/__init__.py`
  - Empty file (or minimal docstring)
  - Required to make `hello_world/` a Python package for relative imports inside
    `hello_world/registry.py` and `hello_world/node.py`

- [ ] **1.3** Create `tests/modules/application/__init__.py`
  - Empty file
  - Required for pytest discovery

---

## Task 2: `base_node.py` — Abstract Base Class

> **File**: `app/modules/application/base_node.py`
> **Reference**: `technical.md § 4.2`

- [ ] **2.1** Implement `ApplicationNode(ModuleNode)` abstract class
  - Import `ModuleNode` from `app.services.nodes.base_module`
  - Import `NodeStatusUpdate` from `app.schemas.status`
  - Declare `@abstractmethod` on `on_input(self, payload: Dict[str, Any]) -> None`
  - Declare `@abstractmethod` on `emit_status(self) -> NodeStatusUpdate`
  - Add module-level, class-level, and method-level docstrings
  - Full type hints on all signatures

- [ ] **2.2** Verify class hierarchy:
  ```
  abc.ABC → ModuleNode → ApplicationNode → HelloWorldNode
  ```
  Confirm `ApplicationNode` does NOT re-declare `start()`, `stop()`, `enable()`, `disable()` —
  these are inherited as no-ops from `ModuleNode`.

---

## Task 3: `hello_world/node.py` — Node Implementation

> **File**: `app/modules/application/hello_world/node.py`
> **Reference**: `technical.md § 4.5`, `api-spec.md § 1`

- [ ] **3.1** Implement `HelloWorldNode(ApplicationNode)` class with constructor:
  ```python
  def __init__(self, manager, node_id, name, config, throttle_ms=0)
  ```
  Set all required attributes (see `api-spec.md § 1.1`):
  - `self.id = node_id`
  - `self.name = name`
  - `self.manager = manager`
  - `self.config = config`
  - `self.message = config.get("message", "Hello from DAG!")`
  - `self.input_count = 0`
  - `self.last_input_at: Optional[float] = None`
  - `self.last_error: Optional[str] = None`
  - `self.processing_time_ms: float = 0.0`

- [ ] **3.2** Implement `async def on_input(self, payload: Dict[str, Any]) -> None`:
  - Record `self.last_input_at = time.time()`
  - Extract `points`, compute `point_count`
  - Increment `self.input_count`
  - Log at INFO: `f"[{self.id}] on_input: {point_count} points from node_id={payload.get('node_id')!r}"`
  - Build `new_payload = payload.copy()` (shallow copy)
  - Set `new_payload["node_id"] = self.id`
  - Set `new_payload["processed_by"] = self.id`
  - Set `new_payload["app_message"] = self.message`
  - Set `new_payload["app_point_count"] = point_count`
  - Call `asyncio.create_task(self.manager.forward_data(self.id, new_payload))`
  - Call `notify_status_change(self.id)` on first frame (`input_count` was 0)
  - Wrap everything in try/except: on exception set `self.last_error`, call `notify_status_change`, log ERROR

- [ ] **3.3** Implement `def emit_status(self) -> NodeStatusUpdate`:
  - Follow the state machine in `api-spec.md § 1.3` exactly
  - Matches `OperationNode.emit_status()` pattern from `pipeline/operation_node.py`

- [ ] **3.4** Implement `def start(self, data_queue=None, runtime_status=None) -> None`:
  - Log INFO: `f"[{self.id}] HelloWorldNode '{self.name}' started. message={self.message!r}"`

- [ ] **3.5** Implement `def stop(self) -> None`:
  - Log INFO: `f"[{self.id}] HelloWorldNode '{self.name}' stopped."`

- [ ] **3.6** Verify all imports use `app.core.logging.get_logger(__name__)` — NOT `import logging`

- [ ] **3.7** Verify NO direct import of `node_manager` or `from app.services.nodes.instance import ...`
  at module level (circular import prevention — see `technical.md § 9`)

---

## Task 4a: `hello_world/registry.py` — Self-Registering Node Registry

> **File**: `app/modules/application/hello_world/registry.py`
> **Reference**: `technical.md § 4.3a`, `api-spec.md § 2, 3`
> **Model**: `flow_control/if_condition/registry.py` (exact pattern)

This file is the **canonical registration unit** for the `hello_world` node. It must be
self-contained: both the schema registration and the factory builder live here. The top-level
`application/registry.py` must NOT contain any registration logic.

- [ ] **4a.1** Add top-level imports (module level, NOT inside functions):
  ```python
  from typing import Any, Dict, List
  from app.services.nodes.node_factory import NodeFactory
  from app.services.nodes.schema import (
      NodeDefinition, PropertySchema, PortSchema, node_schema_registry
  )
  ```

- [ ] **4a.2** Register `NodeDefinition` for `"hello_world"` type via module-level call:
  ```python
  node_schema_registry.register(NodeDefinition(
      type="hello_world",
      display_name="Hello World App",
      category="application",
      description="Example application node: logs data, counts points, and forwards payload",
      icon="celebration",
      websocket_enabled=True,
      properties=[
          PropertySchema(name="message", label="Message", type="string",
                        default="Hello from DAG!", help_text="..."),
          PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number",
                        default=0, min=0, step=10, help_text="..."),
      ],
      inputs=[PortSchema(id="in", label="Input")],
      outputs=[PortSchema(id="out", label="Output")],
  ))
  ```

- [ ] **4a.3** Define factory function with `@NodeFactory.register("hello_world")` decorator:
  ```python
  @NodeFactory.register("hello_world")
  def build_hello_world(node, service_context, edges):
      from .node import HelloWorldNode  # LAZY import — relative path
      config = node.get("config", {})
      throttle_ms = float(config.get("throttle_ms", 0) or 0)
      return HelloWorldNode(
          manager=service_context,
          node_id=node["id"],
          name=node.get("name") or "Hello World",
          config=config,
          throttle_ms=throttle_ms,
      )
  ```

- [ ] **4a.4** Verify the `HelloWorldNode` import is **inside** the factory function body using a
  **relative import** (`from .node import HelloWorldNode`) — matches `if_condition/registry.py` L66

- [ ] **4a.5** Verify module-level imports do NOT include `HelloWorldNode`, `node_manager`,
  or `status_aggregator` (circular import prevention)

---

## Task 4b: `registry.py` — Top-Level Aggregator (Replace Existing File)

> **File**: `app/modules/application/registry.py`
> **Reference**: `technical.md § 4.3b`
> **Model**: `flow_control/registry.py` (exact pattern)

The existing `application/registry.py` contains inline `NodeDefinition` and `@NodeFactory.register`
calls. **Replace it entirely** with a pure aggregator that only imports sub-registries. After this
change, `application/registry.py` must contain **zero** `node_schema_registry.register(...)` or
`@NodeFactory.register(...)` calls.

- [ ] **4b.1** Replace the contents of `app/modules/application/registry.py` with:
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

- [ ] **4b.2** Verify `application/registry.py` contains NO `node_schema_registry.register(...)` calls

- [ ] **4b.3** Verify `application/registry.py` contains NO `@NodeFactory.register(...)` decorators

- [ ] **4b.4** Verify the existing `NodeDefinition` and `build_hello_world` logic that was in
  `application/registry.py` is now correctly moved to `hello_world/registry.py` (Task 4a)

---

## Task 5: Integration Verification

- [ ] **5.1** Run `python -c "from app.modules import discover_modules; discover_modules()"`
  and confirm log line: `"Loaded module registry: application"`

- [ ] **5.2** Run:
  ```python
  from app.services.nodes.node_factory import NodeFactory
  assert "hello_world" in NodeFactory._registry
  ```

- [ ] **5.3** Run:
  ```python
  from app.services.nodes.schema import node_schema_registry
  defn = node_schema_registry.get("hello_world")
  assert defn is not None
  assert defn.category == "application"
  assert defn.websocket_enabled is True
  ```

- [ ] **5.4** Run `NodeFactory.create()` with a mock `service_context`:
  ```python
  from unittest.mock import MagicMock
  node_data = {"id": "test-hw-001", "type": "hello_world", "name": "Test",
               "config": {"message": "hi", "throttle_ms": 0}}
  ctx = MagicMock()
  hw_node = NodeFactory.create(node_data, ctx, [])
  assert hw_node.id == "test-hw-001"
  assert hw_node.message == "hi"
  ```

- [ ] **5.5** Verify that importing ONLY `hello_world.registry` (without the aggregator) still
  registers the node — the sub-registry is fully self-contained:
  ```python
  from app.modules.application.hello_world import registry  # noqa: F401
  from app.services.nodes.node_factory import NodeFactory
  assert "hello_world" in NodeFactory._registry
  ```

- [ ] **5.6** Verify `application/registry.py` source contains **no** occurrences of
  `node_schema_registry.register` or `@NodeFactory.register` (grep check)

---

## Task 6: Test Suite

> **Files**: `tests/modules/application/test_hello_world.py`
>            `tests/modules/application/test_hello_world_registry.py`
> **Reference**: `technical.md § 10`, `api-spec.md § 1`

- [ ] **6.1** Add `import pytest`, `pytest.mark.asyncio`, `unittest.mock` boilerplate

- [ ] **6.2** Write `test_hello_world_instantiation`:
  - Creates `HelloWorldNode` with `Mock()` manager
  - Asserts `node.id`, `node.name`, `node.message` set correctly
  - Asserts `node.input_count == 0`, `node.last_input_at is None`

- [ ] **6.3** Write `test_hello_world_config_defaults`:
  - Creates node with empty `config={}`
  - Asserts `node.message == "Hello from DAG!"`

- [ ] **6.4** Write `test_on_input_forwarded` (async):
  - Creates node with `manager.forward_data = AsyncMock()`
  - Calls `await node.on_input({"points": np.zeros((100, 3)), "timestamp": 1.0, "node_id": "upstream"})`
  - Asserts `manager.forward_data` was called
  - Asserts call args contain `"node_id": node.id`
  - Asserts call args contain `"app_message": node.message`
  - Asserts call args contain `"app_point_count": 100`

- [ ] **6.5** Write `test_on_input_none_points` (async):
  - Calls `await node.on_input({"points": None, "timestamp": 1.0})`
  - Asserts `manager.forward_data` still called (graceful handling)
  - Asserts `app_point_count == 0`

- [ ] **6.6** Write `test_emit_status_idle`:
  - `last_input_at=None`, `last_error=None`
  - Asserts `operational_state == OperationalState.RUNNING`
  - Asserts `application_state.value is False`
  - Asserts `application_state.color == "gray"`

- [ ] **6.7** Write `test_emit_status_active`:
  - `last_input_at = time.time() - 0.5` (recent)
  - Asserts `application_state.value is True`
  - Asserts `application_state.color == "blue"`

- [ ] **6.8** Write `test_emit_status_error`:
  - `last_error = "something broke"`
  - Asserts `operational_state == OperationalState.ERROR`
  - Asserts `error_message == "something broke"`

- [ ] **6.9** Write `test_lifecycle_start_stop`:
  - Calls `node.start()` — asserts no exception
  - Calls `node.stop()` — asserts no exception

- [ ] **6.10** Write `test_sub_registry_node_factory_registration`
  (in `test_hello_world_registry.py`):
  - Imports `app.modules.application.hello_world.registry` directly (NOT the aggregator)
  - Asserts `"hello_world" in NodeFactory._registry`
  - This verifies the **sub-registry is self-contained**

- [ ] **6.11** Write `test_sub_registry_schema_registration`
  (in `test_hello_world_registry.py`):
  - Imports `app.modules.application.hello_world.registry` directly
  - Asserts `node_schema_registry.get("hello_world") is not None`
  - Asserts `.websocket_enabled is True`
  - Asserts `.category == "application"`

- [ ] **6.12** Write `test_aggregator_does_not_register_directly`
  (in `test_hello_world_registry.py`):
  - Read `app/modules/application/registry.py` source as a string
  - Assert `"node_schema_registry.register"` NOT in source
  - Assert `"@NodeFactory.register"` NOT in source
  - This is a **structural guard** ensuring the aggregator stays clean

- [ ] **6.13** Write `test_factory_creates_correct_instance`:
  - Uses `build_hello_world` factory from `hello_world/registry.py` directly with a mock
    `service_context`
  - Asserts returns `HelloWorldNode` instance
  - Asserts `throttle_ms` config handled without error (float conversion)

- [ ] **6.14** Run full test suite: `pytest tests/modules/application/ -v`
  - All tests must pass with 0 failures

---

## Task 7: Code Quality

- [ ] **7.1** Run `ruff check app/modules/application/` — zero errors
- [ ] **7.2** Run `mypy app/modules/application/ --ignore-missing-imports` — zero errors in application/ files (pre-existing repo-wide issues in other modules are unrelated)
- [ ] **7.3** Verify no `print()` statements in production code (only `logger.*` calls)
- [ ] **7.4** Verify all public methods have docstrings
- [ ] **7.5** Verify all method signatures have complete type hints

---

## Dependency Notes

- **Task 4a before 4b**: `hello_world/registry.py` must exist before `application/registry.py`
  is updated to import it (else the aggregator import will fail).
- **Task 3 before 4a**: `hello_world/node.py` must exist before `hello_world/registry.py` can
  lazy-import it (the factory will import at call-time, not at import-time, but the module must
  be present on disk for the import to succeed at runtime).
- **No blocked tasks**: All other tasks in this feature are entirely additive. No existing files
  outside of `app/modules/application/registry.py` are modified.
- **No new `requirements.txt` entries**: All imports are from existing project packages.
- **Frontend**: No blocked frontend work — Angular schema palette updates automatically when
  `GET /api/v1/nodes/schemas` returns the new `hello_world` definition. See `frontend-tasks.md`.
