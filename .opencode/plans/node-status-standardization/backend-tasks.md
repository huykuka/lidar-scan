# Node Status Standardization — Backend Tasks

**Owner**: `@be-dev`  
**Reference**: `technical.md` (architecture), `api-spec.md` (schema contract)  
**Branch**: `feature/node-status-standardization`

Update checkboxes from `[ ]` to `[x]` as each step completes.

---

## Phase 1 — Schema & Infrastructure

### Task B1: Define Pydantic Status Schema

**File**: `app/schemas/status.py` (new file)

- [x] B1.1 — Create `app/schemas/status.py` with `OperationalState` enum, `ApplicationState` model, `NodeStatusUpdate` model, `SystemStatusBroadcast` model exactly as specified in `api-spec.md § 1.1`
- [x] B1.2 — Add `app/schemas/__init__.py` export if missing
- [x] B1.3 — Write unit test `tests/schemas/test_status.py`:
  - [x] Test `OperationalState` enum has exactly 4 values: `INITIALIZE`, `RUNNING`, `STOPPED`, `ERROR`
  - [x] Test `NodeStatusUpdate` requires `node_id`, `operational_state`, `timestamp`; optionals (`application_state`, `error_message`) default to `None`
  - [x] Test `NodeStatusUpdate` with `operational_state=ERROR` and no `error_message` is still valid (relaxed — error_message is optional)
  - [x] Test `ApplicationState.value` accepts `str`, `bool`, `int`, `float`
  - [x] Test Pydantic rejects `operational_state="UNKNOWN"` with `ValidationError`
  - [x] Test `SystemStatusBroadcast.nodes` serialises to JSON without numpy or binary types

---

### Task B2: Implement StatusAggregator

**File**: `app/services/status_aggregator.py` (new file, replaces `status_broadcaster.py`)

- [x] B2.1 — Create `app/services/status_aggregator.py` with:
  - `notify_status_change(node_id: str)` — public entry point; per-node 100ms rate limit; schedules debounced broadcast task
  - `_broadcast_system_status()` — async; collects `node.emit_status()` from all live nodes; broadcasts via `manager.broadcast("system_status", payload.model_dump())`; 100ms debounce sleep before collecting
  - `start_status_aggregator()` — registers `system_status` topic, sets `_aggregator_running = True`
  - `stop_status_aggregator()` — cancels pending task, resets state
- [x] B2.2 — Rate-limit implementation detail: maintain module-level `_last_emit_time: Dict[str, float]`; skip `notify_status_change` if `time.time() - _last_emit_time[node_id] < 0.1`
- [x] B2.3 — Debounce detail: use single pending task; if `_pending_broadcast_task` is not done, don't create another; re-read: batches multiple calls into one broadcast after the 100ms sleep window
- [x] B2.4 — All `manager.broadcast(...)` calls must use `asyncio.create_task()` (fire-and-forget) — do **not** `await` on the broadcast itself inside the node
- [x] B2.5 — Write unit tests `tests/services/test_status_aggregator.py`:
  - [x] `test_rate_limit_drops_excess_calls`: call `notify_status_change` 20 times in 50ms → mock `manager.broadcast` → assert it was called at most 1–2 times
  - [x] `test_debounce_batches_multiple_nodes`: call `notify_status_change` for 3 different nodes within 30ms window → assert a single broadcast covers all 3
  - [x] `test_start_registers_system_status_topic`: `start_status_aggregator()` → assert `"system_status"` in `manager.active_connections`
  - [x] `test_stop_cancels_pending_task`: start aggregator, schedule task, call `stop_status_aggregator()` → assert task cancelled
  - [x] `test_node_without_emit_status_is_skipped`: register a node without `emit_status` → assert broadcast proceeds without raising

---

### Task B3: Update ModuleNode Base Class

**File**: `app/services/nodes/base_module.py`

- [x] B3.1 — Add `from app.schemas.status import NodeStatusUpdate` import
- [x] B3.2 — Add abstract method:
  ```python
  @abstractmethod
  def emit_status(self) -> NodeStatusUpdate:
      """Return standardised status. Called by StatusAggregator on state changes."""
      ...
  ```
- [x] B3.3 — Convert existing `get_status()` from `@abstractmethod` to a **concrete** method with a deprecation warning that calls `self.emit_status()` and converts to legacy dict format (see `technical.md § 1.2` for the shim). This maintains backward compat for the REST nodes service until it is also updated.
- [x] B3.4 — Update docstring of `get_status()` to say `DEPRECATED — use emit_status()`.
- [x] B3.5 — Run existing test suite; confirm no new failures from the base class change: `pytest tests/services/nodes/`

---

## Phase 2 — Node Implementations

> All five nodes must implement `emit_status()` **and** call `notify_status_change(self.id)` on every meaningful state transition.

---

### Task B4: LidarSensor

**File**: `app/modules/lidar/sensor.py`

- [x] B4.1 — Add imports: `NodeStatusUpdate`, `OperationalState`, `ApplicationState`, `notify_status_change`
- [x] B4.2 — Implement `emit_status()`:
  - Process running + connection_status=`"connected"` → `RUNNING`, app_state green
  - Process running + connection_status=`"starting"` → `INITIALIZE`, app_state orange
  - Process running + `last_error` set → `ERROR`, app_state red, propagate error_message
  - Process not alive / None → `STOPPED`, app_state red disconnected
  - Read `connection_status` and `last_error` from `self.manager.node_runtime_status.get(self.id, {})`
- [x] B4.3 — Call `notify_status_change(self.id)` in:
  - `start()` — after spawning worker process (INITIALIZE)
  - `stop()` — after terminating worker process (STOPPED)
  - The runtime-status update point where `connection_status` changes (in the async reading loop / worker callback)
- [x] B4.4 — Update tests `tests/modules/test_lidar_sensor.py`:
  - [x] Replace / augment old `test_get_status_*` tests with `test_emit_status_stopped`, `test_emit_status_initialize`, `test_emit_status_running`, `test_emit_status_error`
  - [x] Each test asserts `isinstance(status, NodeStatusUpdate)` and checks `operational_state`, `application_state.label`, `application_state.value`, `application_state.color`

---

### Task B5: CalibrationNode

**File**: `app/modules/calibration/calibration_node.py`

- [x] B5.1 — Add imports: `NodeStatusUpdate`, `OperationalState`, `ApplicationState`, `notify_status_change`
- [x] B5.2 — Implement `emit_status()`:
  - `self._enabled == False` → `STOPPED`, calibrating=false, gray
  - `self._enabled == True` and `self._pending_calibration is None` → `RUNNING`, calibrating=false, gray
  - `self._enabled == True` and `self._pending_calibration is not None` → `RUNNING`, calibrating=true, blue
- [x] B5.3 — Call `notify_status_change(self.id)` in:
  - `enable()` after setting `_enabled = True`
  - `disable()` after setting `_enabled = False`
  - Point in `on_input()` where `_pending_calibration` is assigned (calibration starts)
  - Point in calibration callback where `_pending_calibration` is cleared (calibration ends)
- [x] B5.4 — Update tests `tests/modules/test_calibration_provenance.py`:
  - [x] Replace `test_get_status_reports_buffer_sizes` with `test_emit_status_*` variants covering enabled/disabled/calibrating states

---

### Task B6: IfConditionNode

**File**: `app/modules/flow_control/if_condition/node.py`

- [x] B6.1 — Add imports: `NodeStatusUpdate`, `OperationalState`, `ApplicationState`, `notify_status_change`
- [x] B6.2 — Implement `emit_status()`:
  - `self.last_error` set → `ERROR`, `application_state=None`, propagate error_message
  - `self.state is None` → `RUNNING`, `application_state=None` (no evaluation yet)
  - `self.state == True` → `RUNNING`, condition=`"true"`, green
  - `self.state == False` → `RUNNING`, condition=`"false"`, red
- [x] B6.3 — Call `notify_status_change(self.id)` in `on_input()` after `self.state` is updated
- [x] B6.4 — Update tests `tests/modules/flow_control/test_if_node.py`:
  - [x] Replace `test_get_status_*` with `test_emit_status_no_evaluation`, `test_emit_status_true`, `test_emit_status_false`, `test_emit_status_error`

---

### Task B7: OperationNode

**File**: `app/modules/pipeline/operation_node.py`

- [x] B7.1 — Add imports: `NodeStatusUpdate`, `OperationalState`, `ApplicationState`, `notify_status_change`
- [x] B7.2 — Implement `emit_status()`:
  - `self.last_error` set → `ERROR`, processing=false, gray, propagate error_message
  - `self.last_input_at` and `time.time() - self.last_input_at < 5` → `RUNNING`, processing=true, blue
  - Otherwise → `RUNNING`, processing=false, gray
- [x] B7.3 — Call `notify_status_change(self.id)` in:
  - `enable()` / `disable()` (if they exist or are added)
  - `on_input()` on first frame (`self.input_count == 1`) and on any error
- [x] B7.4 — Add tests `tests/modules/test_operation_node.py`:
  - [x] `test_emit_status_idle`, `test_emit_status_processing`, `test_emit_status_error`

---

### Task B8: FusionService

**File**: `app/modules/fusion/service.py`

- [x] B8.1 — Add imports: `NodeStatusUpdate`, `OperationalState`, `ApplicationState`, `notify_status_change`
- [x] B8.2 — Implement `emit_status()`:
  - `self._enabled == False` → `STOPPED`, fusing=0, gray
  - `self._enabled == True` and `len(self._latest_frames) == 0` → `RUNNING`, fusing=0, gray
  - `self._enabled == True` and frames present → `RUNNING`, fusing=len, blue
  - `self.last_error` set → `ERROR`, fusing=0, red, propagate error_message
- [x] B8.3 — Call `notify_status_change(self.id)` in:
  - `enable()`, `disable()`
  - `on_input()` when a new sensor contributes its first frame (len of `_latest_frames` increases)
- [x] B8.4 — Add tests `tests/modules/test_fusion_service_status.py`:
  - [x] `test_emit_status_disabled`, `test_emit_status_no_inputs`, `test_emit_status_with_inputs`, `test_emit_status_error`

---

## Phase 3 — Wiring & Integration

### Task B9: Orchestrator Integration

**File**: `app/services/nodes/orchestrator.py`

- [x] B9.1 — Import `start_status_aggregator`, `stop_status_aggregator`, `notify_status_change` from `app.services.status_aggregator`
- [x] B9.2 — In `start()` (DAG startup): call `start_status_aggregator()` **before** starting nodes; after all nodes are initialised, call `notify_status_change(node_id)` for each node
- [x] B9.3 — In `stop()` (DAG shutdown): call `notify_status_change(node_id)` for each node **before** stopping them; call `stop_status_aggregator()` **after** all nodes stopped
- [x] B9.4 — In `reload_config()` (config reload): after new nodes are registered, call `notify_status_change(node_id)` for all nodes in the new graph
- [x] B9.5 — Remove the import and call of `start_status_broadcaster` / `stop_status_broadcaster` (old `status_broadcaster.py`)
- [x] B9.6 — Run orchestrator reload tests: `pytest tests/services/nodes/test_orchestrator_reload.py`

---

### Task B10: Update REST Status Endpoint

**File**: `app/api/v1/nodes/service.py`

- [x] B10.1 — Update `get_all_nodes_status()` (or equivalent) to iterate `node_manager.nodes` and call `node.emit_status()` instead of `node.get_status()`
- [x] B10.2 — Return `{"nodes": [s.model_dump() for s in status_updates]}` — same structure as WebSocket broadcast
- [x] B10.3 — Keep a fallback for nodes without `emit_status` (log warning, skip node) for safety
- [x] B10.4 — Update API tests `tests/api/test_nodes.py` to assert the new response shape matches `SystemStatusBroadcast`

---

### Task B11: Integration Tests

**File**: `tests/integration/test_status_flow.py` (new file)

- [x] B11.1 — `test_status_broadcast_on_dag_start`: start orchestrator → connect to `system_status` WebSocket → assert at least one `NodeStatusUpdate` received with `operational_state` in `[INITIALIZE, RUNNING]`
- [x] B11.2 — `test_status_broadcast_on_node_enable_disable`: toggle a node enable/disable → assert WebSocket receives `RUNNING` then `STOPPED`
- [x] B11.3 — `test_multiple_nodes_batched_in_one_broadcast`: enable 3 nodes within 50ms → assert a single WebSocket message contains all 3 node updates
- [x] B11.4 — `test_rate_limit_prevents_flooding`: trigger state changes 50 times in 1 second on one node → assert `manager.broadcast` called ≤ 15 times

---

### Task B12: Remove Legacy Status Broadcaster

- [x] B12.1 — Delete `app/services/status_broadcaster.py`
- [x] B12.2 — Search and remove all imports of `start_status_broadcaster`, `stop_status_broadcaster` across the codebase
- [x] B12.3 — Run full test suite: `pytest` — confirm all tests pass (pre-existing failures confirmed unrelated to our changes)
- [x] B12.4 — Confirm `get_status()` shim is still in place (do **not** remove yet — that's Phase 4 cleanup)

---

### Task B12.5: Fix Circular Import Issue (Emergency Bugfix)

**Context**: After completing B12, backend startup failed with circular import errors.

- [x] B12.5.1 — Diagnose circular import chain: `instance.py → discover_modules() → registries → node implementations → status_aggregator.py → instance.py`
- [x] B12.5.2 — Implement lazy import of `node_manager` in `status_aggregator.py::_broadcast_system_status()` to break the cycle
- [x] B12.5.3 — Update tests to patch lazy import location (`app.services.nodes.instance.node_manager` instead of `status_aggregator.node_manager`)
- [x] B12.5.4 — Add comprehensive test suite `tests/services/test_circular_import_fix.py` to prevent regressions
- [x] B12.5.5 — Verify all modules load correctly and node types are registered
- [x] B12.5.6 — Document fix in `.opencode/plans/node-status-standardization/CIRCULAR_IMPORT_FIX.md`

**Result**: ✅ All module registries load successfully, sensor nodes instantiate correctly, backend starts without errors.

---

### Task B13: Performance Validation

- [ ] B13.1 — Run the DAG with 10+ nodes for 60 seconds
- [ ] B13.2 — Measure WebSocket message rate on `system_status` topic: must be < 100 msg/sec
- [ ] B13.3 — Measure CPU overhead delta vs baseline (no status): must be < 1%
- [ ] B13.4 — Confirm zero blocking calls on the event loop (check for accidental `await` on `notify_status_change`)
- [ ] B13.5 — Document results in `qa-report.md`

---

## Task Summary Checklist

```
Phase 1 — Schema & Infrastructure
  [x] B1 — Pydantic schema (app/schemas/status.py)
  [x] B2 — StatusAggregator service
  [x] B3 — ModuleNode base class update

Phase 2 — Node Implementations
  [x] B4 — LidarSensor.emit_status()
  [x] B5 — CalibrationNode.emit_status()
  [x] B6 — IfConditionNode.emit_status()
  [x] B7 — OperationNode.emit_status()
  [x] B8 — FusionService.emit_status()

Phase 3 — Wiring & Integration
  [x] B9  — Orchestrator integration
  [x] B10 — REST endpoint update
  [x] B11 — Integration tests
  [x] B12 — Delete legacy status_broadcaster.py
  [ ] B13 — Performance validation
```
