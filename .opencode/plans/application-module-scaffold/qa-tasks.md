# Application Module Scaffold — QA Tasks

> **For**: `@qa`
> **References**: `technical.md`, `api-spec.md`, `backend-tasks.md`
> **QA Agent**: Check off each item (`[ ]` → `[x]`) as execution confirms it passes.

---

## Phase 1: TDD Preparation (Run Before Development)

These tests must be written first and verified **failing** before `@be-dev` implements the code.
This confirms the tests are actually testing the right things.

- [ ] **TDD-1** Confirm `tests/modules/application/test_hello_world.py` does NOT yet exist
  (empty application/ dir on disk)
- [ ] **TDD-2** Write stub test file with all planned test functions (raise `NotImplementedError`
  or just `pass`) — verifies pytest discovers the file correctly
- [ ] **TDD-3** Run `pytest tests/modules/application/ -v` — confirm all tests are
  COLLECTED but FAILING (ImportError or assertion failures expected at this stage)

---

## Phase 2: Unit Tests — `HelloWorldNode` Class

> **Command**: `pytest tests/modules/application/test_hello_world.py -v`

### Instantiation & Configuration

- [ ] **U-1** `test_hello_world_instantiation` — Node instantiates without error; `id`, `name`,
  `manager` attributes set correctly
- [ ] **U-2** `test_hello_world_config_defaults` — Empty `config={}` resolves `message` to
  `"Hello from DAG!"`
- [ ] **U-3** `test_hello_world_custom_message` — `config={"message": "custom"}` stores
  `self.message == "custom"`
- [ ] **U-4** `test_input_count_starts_at_zero` — `node.input_count == 0` before any `on_input`
  call

### Data Flow (`on_input`)

- [ ] **U-5** `test_on_input_forwarded` — `on_input()` with 100-point array calls
  `manager.forward_data(node.id, ...)` exactly once
- [ ] **U-6** `test_on_input_payload_keys` — Forwarded payload contains:
  `node_id`, `processed_by`, `app_message`, `app_point_count`
- [ ] **U-7** `test_on_input_node_id_overwritten` — `new_payload["node_id"]` equals `self.id`,
  NOT the upstream node id
- [ ] **U-8** `test_on_input_none_points` — `points=None` does NOT raise; forwards with
  `app_point_count=0`
- [ ] **U-9** `test_on_input_empty_array` — `points=np.zeros((0,3))` handles gracefully;
  forwards with `app_point_count=0`
- [ ] **U-10** `test_on_input_increments_counter` — Call `on_input` 3× → `input_count == 3`
- [ ] **U-11** `test_on_input_updates_last_input_at` — `last_input_at` is set to a recent timestamp
- [ ] **U-12** `test_on_input_shallow_copy` — Original upstream `payload` dict is NOT mutated
  (verify `"node_id"` in original payload still has upstream value after call)

### Status Reporting (`emit_status`)

- [ ] **U-13** `test_emit_status_returns_correct_type` — Return value is `NodeStatusUpdate`
  instance
- [ ] **U-14** `test_emit_status_idle` — No input: `operational_state=RUNNING`,
  `application_state.value=False`, `color="gray"`, `error_message=None`
- [ ] **U-15** `test_emit_status_active` — `last_input_at = time.time() - 0.5`:
  `application_state.value=True`, `color="blue"`
- [ ] **U-16** `test_emit_status_stale` — `last_input_at = time.time() - 10.0` (>5 s ago):
  `application_state.value=False`, `color="gray"` (back to idle)
- [ ] **U-17** `test_emit_status_error` — `last_error = "test error"`:
  `operational_state=ERROR`, `error_message="test error"`
- [ ] **U-18** `test_emit_status_node_id_correct` — `status.node_id == node.id`
- [ ] **U-19** `test_emit_status_has_timestamp` — `status.timestamp` is a recent float

### Lifecycle

- [ ] **U-20** `test_start_does_not_raise` — `node.start()` completes without exception
- [ ] **U-21** `test_stop_does_not_raise` — `node.stop()` completes without exception
- [ ] **U-22** `test_start_logs_at_info` — Patch logger; verify INFO message logged with
  node name and message
- [ ] **U-23** `test_stop_logs_at_info` — Verify INFO message logged with node name

---

## Phase 3: Registry Integration Tests

> **Command**: `pytest tests/modules/application/test_hello_world.py -v -k "registry"`

- [ ] **R-1** `test_registry_node_factory_registration` — After importing
  `app.modules.application.registry`, `"hello_world"` is in `NodeFactory._registry`
- [ ] **R-2** `test_registry_schema_registration` — `node_schema_registry.get("hello_world")`
  returns a `NodeDefinition` (not `None`)
- [ ] **R-3** `test_registry_schema_category` — `defn.category == "application"`
- [ ] **R-4** `test_registry_schema_websocket_enabled` — `defn.websocket_enabled is True`
- [ ] **R-5** `test_registry_schema_has_message_property` — `defn.properties` contains an
  item with `name="message"` and `type="string"`
- [ ] **R-6** `test_registry_schema_has_throttle_property` — `defn.properties` contains
  `name="throttle_ms"` with `type="number"`, `default=0`
- [ ] **R-7** `test_registry_schema_ports` — `len(defn.inputs) == 1`, `len(defn.outputs) == 1`
- [ ] **R-8** `test_factory_creates_hello_world_node` — `NodeFactory.create(node_data, mock_ctx, [])`
  returns a `HelloWorldNode` instance
- [ ] **R-9** `test_factory_extracts_throttle_ms` — `config={"throttle_ms": "150"}` (string)
  is coerced to `float`; no `ValueError` raised
- [ ] **R-10** `test_factory_name_fallback` — `node={"id": "x", "type": "hello_world",
  "config": {}}` (no `name` key) → `HelloWorldNode.name == "Hello World"`

---

## Phase 4: `discover_modules()` Integration

> **Command**: `pytest tests/services/test_circular_import_fix.py -v`
> (Also: `pytest tests/modules/application/ -v`)

- [ ] **D-1** `test_node_manager_imports_without_circular_error` — existing test still passes
  (no circular import regression from new module)
- [ ] **D-2** `test_all_module_registries_loaded` — Run the existing
  `tests/services/test_circular_import_fix.py::test_all_module_registries_loaded` test;
  it checks required types include `['sensor', 'calibration', 'fusion', 'operation', 'if_condition']`
  — still passes after adding `application` module
- [ ] **D-3** NEW: Verify `"hello_world"` appears in `NodeFactory._registry` when
  `discover_modules()` runs (add assertion to existing or new integration test)
- [ ] **D-4** Run application startup via: `python -c "from app.services.nodes.instance import node_manager"`
  — no `ERROR` log lines for `application` module

---

## Phase 5: DAG Lifecycle Integration

> **Command**: `pytest tests/modules/application/ -v -k "lifecycle or dag"`

These tests verify that the node participates correctly in the full NodeManager lifecycle
using mocked infrastructure.

- [ ] **L-1** Node can be created via `NodeFactory.create()` with a realistic mock `service_context`
  (has `nodes`, `_throttle_config`, `_last_process_time`, `_throttled_count` dicts)
- [ ] **L-2** `node.start()` followed by `node.stop()` — no exception, no state corruption
- [ ] **L-3** `on_input()` called while `manager.forward_data` is `AsyncMock()` — task is
  scheduled without `await` blocking (fire-and-forget pattern)
- [ ] **L-4** `emit_status()` can be called repeatedly without side effects
- [ ] **L-5** Node instance has `_ws_topic` attribute settable from outside (NodeManager sets
  this; verify the attribute can be set: `node._ws_topic = "hello_world_abc12345"`)

---

## Phase 6: Node Definition Schema Completeness

> **Command**: `pytest tests/modules/test_node_definitions.py -v`

- [ ] **S-1** Existing `test_all_definitions_have_websocket_enabled_field` still passes
  (includes new `hello_world` definition)
- [ ] **S-2** Existing `test_streaming_nodes_have_websocket_enabled_true` — add `"hello_world"`
  to the `streaming_types` list in that test OR write a new dedicated test:
  `test_hello_world_node_definition_is_streaming`

---

## Phase 7: Linter & Type Checker

> Run these manually and/or in CI before marking feature complete.

- [ ] **Q-1** `ruff check app/modules/application/` — **0 errors, 0 warnings**
- [ ] **Q-2** `mypy app/modules/application/ --ignore-missing-imports` — **0 errors**
- [ ] **Q-3** `pytest tests/modules/application/ --tb=short -q` — **all passed, 0 warnings**
- [ ] **Q-4** `pytest tests/ -x --ignore=tests/integration -q` — full suite, no regressions

---

## Phase 8: Developer Coordination Checkpoints

- [ ] **C-1** `@be-dev` confirms Tasks 1–5 in `backend-tasks.md` are marked `[x]`
- [ ] **C-2** `@be-dev` confirms Task 6 (test suite) passes 100%
- [ ] **C-3** `@fe-dev` confirms "Hello World App" appears in Angular node palette (after deploy)
- [ ] **C-4** Manual smoke test: add a `hello_world` node in the UI, connect it to a sensor
  node, confirm data flows and `app_message` appears in the WebSocket stream payload

---

## Phase 9: Pre-PR Verification

- [ ] **P-1** `git diff --name-only` — only files under `app/modules/application/` and
  `tests/modules/application/` are changed (no unintended touches to orchestrator, instance.py,
  frontend, or existing module registries)
- [ ] **P-2** `pytest tests/ -x -q` — full test suite green
- [ ] **P-3** `ruff check app/` — zero errors
- [ ] **P-4** No `print()` debug statements left in production files

---

## QA Report Checklist Summary

| Area | Tests | Status |
|---|---|---|
| Unit: Instantiation | U-1 to U-4 | [ ] |
| Unit: Data Flow | U-5 to U-12 | [ ] |
| Unit: Status | U-13 to U-19 | [ ] |
| Unit: Lifecycle | U-20 to U-23 | [ ] |
| Registry Integration | R-1 to R-10 | [ ] |
| discover_modules() | D-1 to D-4 | [ ] |
| DAG Lifecycle | L-1 to L-5 | [ ] |
| Schema Completeness | S-1 to S-2 | [ ] |
| Linter/Mypy | Q-1 to Q-4 | [ ] |
| Pre-PR | P-1 to P-4 | [ ] |
