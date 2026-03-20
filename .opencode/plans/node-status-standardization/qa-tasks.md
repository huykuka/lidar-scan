# Node Status Standardization — QA Tasks

**Owner**: `@qa`  
**Reference**: `requirements.md` (acceptance criteria), `api-spec.md` (schema), `technical.md` (architecture)  
**Branch**: `feature/node-status-standardization`  
**Must run**: After `@be-dev` and `@fe-dev` mark their respective task lists complete.

Update checkboxes from `[ ]` to `[x]` as each step completes. Record all results in `qa-report.md`.

---

## Phase 1 — Pre-QA Readiness Gate

Before starting any tests, confirm:

- [x] QA0.1 — All items in `backend-tasks.md` are checked `[x]` (except performance validation B13 which is part of QA)
- [x] QA0.2 — All items in `frontend-tasks.md` are checked `[x]`
- [ ] QA0.3 — `pytest` passes with zero failures: `pytest --tb=short`
- [x] QA0.4 — Angular build has no errors: `cd web && ng build --configuration production`
- [x] QA0.5 — Dev server starts cleanly (backend + frontend) and WebSocket connects: no errors in browser console on page load

---

## Phase 2 — Schema & Contract Validation

### Task Q1: Backend Schema Tests

Run: `pytest tests/schemas/test_status.py -v`

- [ ] Q1.1 — All schema unit tests introduced in `B1.3` pass
- [ ] Q1.2 — Verify that submitting an invalid `operational_state` (`"UNKNOWN"`) raises a `ValidationError` (Pydantic V2)
- [ ] Q1.3 — Verify that a node with `operational_state=ERROR` and `error_message=null` is accepted (error_message is optional, not required)
- [ ] Q1.4 — Verify `ApplicationState.value` accepts `str`, `bool`, `int`, `float` (four parameterized test cases)
- [ ] Q1.5 — Verify `NodeStatusUpdate.model_dump()` produces a clean JSON-serializable dict (no enums, no datetimes)

---

### Task Q2: API Contract Conformance

For each node type, hit the REST endpoint and compare the response to `api-spec.md § 3`.

Run: `pytest tests/api/test_nodes.py -v`

- [ ] Q2.1 — `GET /api/v1/nodes/status` returns HTTP 200 with body matching `SystemStatusBroadcast` shape: `{ "nodes": [ NodeStatusUpdate, ... ] }`
- [ ] Q2.2 — Each `NodeStatusUpdate` in the response contains `node_id`, `operational_state`, `timestamp`
- [ ] Q2.3 — `operational_state` values are strings from the allowed set: `INITIALIZE`, `RUNNING`, `STOPPED`, `ERROR`
- [ ] Q2.4 — `error_message` is absent (null/omitted) on non-ERROR nodes
- [ ] Q2.5 — `application_state` is absent (null/omitted) on nodes that have not yet received a state update
- [ ] Q2.6 — WebSocket `system_status` topic and REST endpoint return identical `NodeStatusUpdate` structures (compare a sample node ID across both)

---

## Phase 3 — Backend Unit & Integration Tests

### Task Q3: Node emit_status() Unit Tests

Run: `pytest tests/modules/ -v -k "emit_status"`

- [ ] Q3.1 — `LidarSensor.emit_status()` — stopped state returns `STOPPED` + `connection_status=disconnected` + red
- [ ] Q3.2 — `LidarSensor.emit_status()` — initializing state returns `INITIALIZE` + `connection_status=starting` + orange
- [ ] Q3.3 — `LidarSensor.emit_status()` — connected state returns `RUNNING` + `connection_status=connected` + green
- [ ] Q3.4 — `LidarSensor.emit_status()` — error state returns `ERROR` + `error_message` set + red
- [ ] Q3.5 — `CalibrationNode.emit_status()` — disabled returns `STOPPED` + calibrating=false
- [ ] Q3.6 — `CalibrationNode.emit_status()` — enabled idle returns `RUNNING` + calibrating=false
- [ ] Q3.7 — `CalibrationNode.emit_status()` — calibration in progress returns `RUNNING` + calibrating=true + blue
- [ ] Q3.8 — `IfConditionNode.emit_status()` — no evaluation returns `RUNNING` + no `application_state`
- [ ] Q3.9 — `IfConditionNode.emit_status()` — condition true returns `RUNNING` + condition=`"true"` + green
- [ ] Q3.10 — `IfConditionNode.emit_status()` — condition false returns `RUNNING` + condition=`"false"` + red
- [ ] Q3.11 — `IfConditionNode.emit_status()` — expression error returns `ERROR` + `error_message` set
- [ ] Q3.12 — `OperationNode.emit_status()` — idle returns `RUNNING` + processing=false
- [ ] Q3.13 — `OperationNode.emit_status()` — processing returns `RUNNING` + processing=true + blue
- [ ] Q3.14 — `FusionService.emit_status()` — disabled returns `STOPPED` + fusing=0
- [ ] Q3.15 — `FusionService.emit_status()` — 2 sensors active returns `RUNNING` + fusing=2 + blue

---

### Task Q4: StatusAggregator Tests

Run: `pytest tests/services/test_status_aggregator.py -v`

- [ ] Q4.1 — `test_rate_limit_drops_excess_calls` passes
- [ ] Q4.2 — `test_debounce_batches_multiple_nodes` passes
- [ ] Q4.3 — `test_start_registers_system_status_topic` passes
- [ ] Q4.4 — `test_stop_cancels_pending_task` passes
- [ ] Q4.5 — `test_node_without_emit_status_is_skipped` passes

---

### Task Q5: Integration Tests

Run: `pytest tests/integration/test_status_flow.py -v`

- [ ] Q5.1 — `test_status_broadcast_on_dag_start` passes: DAG starts → WebSocket receives status update within 1 second
- [ ] Q5.2 — `test_status_broadcast_on_node_enable_disable` passes: toggle node → receive RUNNING then STOPPED
- [ ] Q5.3 — `test_multiple_nodes_batched_in_one_broadcast` passes: 3 nodes change state within 50ms → single broadcast
- [ ] Q5.4 — `test_rate_limit_prevents_flooding` passes: 50 state changes → ≤ 15 broadcasts

---

### Task Q6: Regression Tests (Existing Suite)

- [ ] Q6.1 — `pytest tests/services/websocket/ -v` — all WebSocket manager tests pass unchanged
- [ ] Q6.2 — `pytest tests/api/test_websocket.py -v` — all WebSocket API tests pass unchanged
- [ ] Q6.3 — `pytest tests/services/nodes/ -v` — all orchestrator and node manager tests pass unchanged
- [ ] Q6.4 — `pytest tests/test_api_schemas.py -v` — all API schema tests pass unchanged
- [ ] Q6.5 — Full suite: `pytest --tb=short -q` — zero failures

---

## Phase 4 — Frontend Unit Tests

Run: `cd web && ng test --watch=false --browsers=ChromeHeadless`

### Task Q7: StatusWebSocketService Tests

- [ ] Q7.1 — `test_parse_broadcast_and_populate_map` passes
- [ ] Q7.2 — `test_get_node_status_returns_correct_entry` passes
- [ ] Q7.3 — `test_unknown_node_returns_undefined` passes
- [ ] Q7.4 — `test_status_updates_are_debounced` passes

---

### Task Q8: FlowCanvasNodeComponent Tests

- [ ] Q8.1 — `test_operational_state_icon_initialize` passes (hourglass_empty + animate-pulse)
- [ ] Q8.2 — `test_operational_state_icon_running` passes (play_arrow + success colour)
- [ ] Q8.3 — `test_operational_state_icon_stopped` passes (pause + neutral colour)
- [ ] Q8.4 — `test_operational_state_icon_error` passes (error_outline + danger colour)
- [ ] Q8.5 — `test_application_state_badge_renders` passes (badge visible with correct text)
- [ ] Q8.6 — `test_application_state_badge_hidden_when_absent` passes (badge absent)
- [ ] Q8.7 — `test_error_message_displays_when_error` passes (error section visible)
- [ ] Q8.8 — `test_error_message_hidden_when_running` passes (error section hidden)

---

## Phase 5 — Manual Functional Testing

Run the full system with the dev server (`ng serve` + `uvicorn`). Perform all manual checks below.

### Task Q9: Node Lifecycle Verification

- [ ] Q9.1 — **Start DAG** → all nodes in canvas show the correct operational state icon within 2 seconds:
  - LiDAR sensor: transitions from hourglass (INITIALIZE) to play (RUNNING) or error (ERROR)
  - Pipeline operations: show play (RUNNING) immediately
  - Fusion node: shows play (RUNNING) with fusing badge showing sensor count
  - Calibration node: shows play (RUNNING) with calibrating=false badge
  - If-condition node: shows play (RUNNING) with no badge (no evaluation yet)
- [ ] Q9.2 — **Stop DAG** → all node icons transition to pause (STOPPED) within 2 seconds
- [ ] Q9.3 — **Enable / disable a node individually** → icon updates from pause → play (and back)
- [ ] Q9.4 — **Node startup race condition**: rapidly enable then disable a node → icon settles correctly on the final state

---

### Task Q10: Application State Badge Verification

- [ ] Q10.1 — **LiDAR sensor connected**: badge shows `"connection_status: connected"` with green background
- [ ] Q10.2 — **LiDAR sensor starting**: badge shows `"connection_status: starting"` with orange background during the connection handshake
- [ ] Q10.3 — **Calibration in progress**: badge shows `"calibrating: true"` with blue background while frames are buffered and ICP is running
- [ ] Q10.4 — **Calibration idle**: badge shows `"calibrating: false"` with gray background when node is enabled but not actively calibrating
- [ ] Q10.5 — **If-condition true**: badge shows `"condition: true"` with green background after a frame is routed through the true port
- [ ] Q10.6 — **If-condition false**: badge shows `"condition: false"` with red background after a frame is routed through the false port
- [ ] Q10.7 — **Fusion active**: badge shows `"fusing: N"` where N is the number of active input sensors
- [ ] Q10.8 — **Badge absent when application_state is null**: nodes with no status update yet show no badge

---

### Task Q11: Error State & Passive Display Verification

- [ ] Q11.1 — **Simulate LiDAR disconnect**: disconnect the sensor (unplug cable or kill the SICK mock process) → within 5 seconds:
  - Node header icon changes to error_outline (red)
  - Application state badge turns red with `"connection_status: disconnected"`
  - Error message box appears at the bottom of the node body with descriptive error text
- [ ] Q11.2 — **Error message truncation**: use a very long error string (>100 chars) → verify message is clamped to 2 lines with ellipsis; full text visible on hover title
- [ ] Q11.3 — **No modal on error**: confirm that no alert, toast, or modal dialog appears when a node enters ERROR state — error is purely passive within the node card
- [ ] Q11.4 — **Error clears on recovery**: reconnect the sensor → icon transitions back to RUNNING, error message box disappears, badge turns green
- [ ] Q11.5 — **If-condition expression error**: set an invalid expression on an IfConditionNode → verify ERROR state + error_message shows the Python exception text

---

### Task Q12: UI Rendering Quality

- [ ] Q12.1 — **Node layout integrity**: presence of the state icon and application state badge does not break the existing node layout (port connectors still aligned, action bar still visible)
- [ ] Q12.2 — **Badge overflow check**: badge does not clip outside the canvas viewport or overlap edges/connections
- [ ] Q12.3 — **Disabled node**: when a node is disabled (greyscale / opacity-40), the state icon and badge are also greyed out
- [ ] Q12.4 — **Color-blind check**: verify the three most critical states (RUNNING=green, ERROR=red, STOPPED=gray) are distinguishable without relying on colour alone (icon shape serves as the differentiator — confirm icons are visible)
- [ ] Q12.5 — **Multiple nodes in canvas**: at 10+ nodes, all badges render without overlap; canvas performance is acceptable (no janky scrolling or layout shifts)
- [ ] Q12.6 — **Rapid toggling (stress test)**: click enable/disable on a node 10 times quickly → icon settles on the correct final state; no ghost icons or stale state visible

---

## Phase 6 — Performance & Load Testing

### Task Q13: WebSocket Message Rate

- [ ] Q13.1 — Open browser DevTools → Network → WS → `system_status` connection
- [ ] Q13.2 — Start DAG with all nodes enabled
- [ ] Q13.3 — Observe for 60 seconds during normal steady-state operation (sensor running, no calibration)
- [ ] Q13.4 — Count WebSocket messages: **must be ≤ 100 messages total** (≤ ~1.7 msg/sec) — far less than the legacy 2 msg/sec minimum
- [ ] Q13.5 — Trigger rapid sensor reconnect (3 reconnects in 10 seconds) → message count during that window must not exceed 100 messages

---

### Task Q14: CPU Overhead

- [ ] Q14.1 — Run backend with `py-spy` or the existing performance monitoring dashboard
- [ ] Q14.2 — Baseline: measure CPU with status aggregator disabled (comment out `start_status_aggregator()` temporarily)
- [ ] Q14.3 — Test: measure CPU with status aggregator enabled at steady state (all nodes running, no rapid state changes)
- [ ] Q14.4 — **Pass criterion**: overhead must be < 1% of total CPU time
- [ ] Q14.5 — Run same measurement during a DAG reload (all nodes restart simultaneously) — overhead spike must return below 1% within 5 seconds

---

### Task Q15: No Event Loop Blocking

- [ ] Q15.1 — Run backend under `asyncio` debug mode: `PYTHONASYNCIODEBUG=1 uvicorn app.main:app`
- [ ] Q15.2 — Trigger status updates from all 5 node types
- [ ] Q15.3 — Assert no `slow callback` warnings appear in logs (each event loop tick takes <100ms)
- [ ] Q15.4 — Verify `notify_status_change()` is synchronous (not `async`) and does not block the caller

---

## Phase 7 — Edge Cases & Regression

### Task Q16: Edge Cases

- [ ] Q16.1 — **DAG empty (no nodes)**: start DAG with zero nodes → WebSocket receives an empty `{"nodes": []}` payload
- [ ] Q16.2 — **Node removed mid-session**: remove a node via API while DAG is running → status for that node_id no longer appears in broadcasts
- [ ] Q16.3 — **Node added mid-session**: add a new node while DAG is running → status for the new node_id appears within 1 second
- [ ] Q16.4 — **WebSocket reconnect**: close browser tab and reopen → reconnect to `system_status` → signal is repopulated within 2 seconds (after next status event or on DAG reload)
- [ ] Q16.5 — **Node with no application_state**: a minimal node type that only emits `node_id + operational_state + timestamp` (no `application_state`) → no badge rendered, no JS error
- [ ] Q16.6 — **Long node_id**: node IDs are UUID-like strings (`lidar_sensor_abc12345678`) → verify badge text truncation with `title` attribute
- [ ] Q16.7 — **Simultaneous ERROR on multiple nodes**: force 3 nodes into ERROR state simultaneously → all three show error icon and message; no crash or render error

---

### Task Q17: Backward Compatibility Check

- [ ] Q17.1 — `get_status()` shim in `ModuleNode` still works: call `node.get_status()` on each node type and assert it returns a non-empty dict with `id`, `running`, `name` keys
- [ ] Q17.2 — `status_broadcaster.py` is fully deleted — confirm no import errors anywhere in the codebase: `python -c "from app.main import app"` succeeds without warnings
- [ ] Q17.3 — Existing API consumers (e.g., the node editor) still function after the REST endpoint schema change

---

## Phase 8 — Documentation Review

### Task Q18: Documentation Checks

- [ ] Q18.1 — `api-spec.md` accurately reflects the deployed schema (spot-check sample payloads against live WebSocket output)
- [ ] Q18.2 — `.opencode/rules/backend.md` has been updated with `emit_status()` contract (per requirements §Documentation)
- [ ] Q18.3 — `.opencode/rules/frontend.md` has been updated with UI rendering guidelines for status badges
- [ ] Q18.4 — Code comments in `base_module.py` explain the Node-RED-inspired pattern
- [ ] Q18.5 — `AGENTS.md` updated to reference new status workflow

---

## QA Sign-Off Criteria

Before marking this feature as QA-complete, **all** of the following must be satisfied:

| Criterion                                           | Status |
|-----------------------------------------------------|--------|
| All automated backend tests pass                    | [ ]    |
| All automated frontend tests pass                   | [ ]    |
| All manual functional tests complete                | [ ]    |
| WebSocket message rate < 100 msg/sec confirmed      | [ ]    |
| CPU overhead < 1% confirmed                         | [ ]    |
| No event loop blocking warnings                     | [ ]    |
| Error states display passively (no modals)          | [ ]    |
| All 5 node types show correct status badges         | [ ]    |
| Backward compat shim verified                       | [ ]    |
| Documentation updated and reviewed                  | [ ]    |

**QA Report**: Record all test results, screenshots, and performance measurements in `qa-report.md`.
