# Node Reload Improvement — QA Tasks

> **Reference documents**:
> - Requirements: `.opencode/plans/node-reload-improvement/requirements.md`
> - Technical blueprint: `.opencode/plans/node-reload-improvement/technical.md`
> - API contracts: `.opencode/plans/node-reload-improvement/api-spec.md`
> - Backend tasks: `.opencode/plans/node-reload-improvement/backend-tasks.md`
> - Frontend tasks: `.opencode/plans/node-reload-improvement/frontend-tasks.md`

> **@qa**: Check off each item (`[ ]` → `[x]`) as it is verified. Write the final `qa-report.md` when all tasks are complete.

---

## Phase 0: TDD Preparation (Before Any Implementation)

These tests must be **written and confirmed failing** before the corresponding implementation begins.
Running a failing test suite is the signal that implementation can start.

### 0.1 Backend — Failing Tests Baseline

- [ ] Run `pytest tests/services/nodes/test_config_hasher.py` — confirm 6 tests **FAIL** (module not yet created)
- [ ] Run `pytest tests/services/nodes/test_input_gate.py` — confirm 6 tests **FAIL**
- [ ] Run `pytest tests/services/nodes/test_selective_reload.py` — confirm 8 tests **FAIL**
- [ ] Run `pytest tests/api/test_node_selective_reload.py` — confirm 5 tests **FAIL** (404 on new endpoints)
- [ ] Confirm `tests/api/test_dag_config.py::TestSaveDagConfig` new test cases **FAIL** (6 new cases)
- [ ] Confirm `tests/services/nodes/test_routing.py` new gate cases **FAIL** (2 new cases)

### 0.2 Frontend — Failing Tests Baseline

- [ ] Run `cd web && ng test --include='**/system-status.service.spec.ts'` — confirm 4 new reload signal tests **FAIL**
- [ ] Run `cd web && ng test --include='**/canvas-edit-store.service.spec.ts'` — confirm 3 new debounce/toast tests **FAIL**
- [ ] Run `cd web && ng test --include='**/flow-canvas-node.component.spec.ts'` — confirm 4 new indicator tests **FAIL**

---

## Phase 1: Unit Tests — Backend

### 1.1 `ConfigHasher` (`test_config_hasher.py`)

- [ ] `test_hash_is_deterministic` — same node dict → identical hash string
- [ ] `test_hash_differs_on_config_change` — mutate `config.hostname` → different hash
- [ ] `test_hash_ignores_position` — identical config with different `x`/`y` → same hash
- [ ] `test_hash_differs_on_pose_change` — mutate `pose.yaw` → different hash
- [ ] `test_hash_differs_on_enabled_toggle` — flip `enabled` flag → different hash
- [ ] `test_config_hash_store_update_get` — full lifecycle: `update` → `get` → `remove` → `get` returns None → `clear`

### 1.2 `NodeInputGate` (`test_input_gate.py`)

- [ ] `test_gate_open_by_default` — `is_open()` returns `True` immediately after construction
- [ ] `test_pause_blocks_is_open` — after `await gate.pause()`, `is_open()` returns `False`
- [ ] `test_buffer_nowait_when_paused` — `buffer_nowait(payload)` returns `True`; queue size is 1
- [ ] `test_buffer_drops_when_full` — capacity=1, second `buffer_nowait()` returns `False` (with DEBUG log)
- [ ] `test_resume_drains_buffer_in_order` — buffer 3 frames; after `resume_and_drain`, target node receives them in FIFO order
- [ ] `test_resume_calls_on_input_for_each_frame` — mock target; assert `on_input` call count equals frames buffered

### 1.3 `SelectiveReloadManager` (`test_selective_reload.py`)

- [ ] `test_selective_reload_replaces_node_instance` — `nodes[node_id]` is a new object after reload
- [ ] `test_selective_reload_preserves_ws_topic` — `new_instance._ws_topic == old_instance._ws_topic`
- [ ] `test_selective_reload_no_unregister_topic_called` — spy on `ConnectionManager.unregister_topic`; asserts it is **never called**
- [ ] `test_selective_reload_pauses_downstream_before_stop` — assert `gate.pause()` is called **before** `old_instance.stop()`
- [ ] `test_selective_reload_resumes_downstream_after_start` — assert `gate.resume_and_drain()` is called **after** new instance `start()`
- [ ] `test_selective_reload_rollback_on_factory_failure` — `NodeFactory.create` raises → `nodes[node_id]` restored to original object
- [ ] `test_selective_reload_rollback_on_start_failure` — `new_instance.start()` raises → old instance restored; downstream gates cleaned up
- [ ] `test_selective_reload_updates_hash_store` — `_config_hash_store.get(node_id)` equals new config hash after success

### 1.4 `DataRouter` gate integration (`test_routing.py`)

- [ ] `test_forward_skips_paused_downstream` — gate exists and is closed → `on_input` NOT called; `buffer_nowait` called
- [ ] `test_forward_normal_when_no_gate` — `_input_gates` empty → `on_input` called normally; zero overhead path

---

## Phase 2: Unit Tests — Frontend

### 2.1 `SystemStatusService` reload signals

- [ ] `should add node_id to reloadingNodeIds on "reloading" status event`
- [ ] `should remove node_id from reloadingNodeIds on "ready" status event`
- [ ] `should remove node_id from reloadingNodeIds on "error" status event`
- [ ] `should clear all reloadingNodeIds when reload_event has node_id=null (full reload)`
- [ ] `should set lastReloadEvent signal when any reload_event arrives`
- [ ] `should clear reloadingNodeIds on WebSocket disconnect`

### 2.2 `CanvasEditStoreService` debounce and toast

- [ ] `should debounce rapid consecutive saveAndReload calls — only one HTTP PUT emitted` (use `fakeAsync + tick(150)`)
- [ ] `should NOT fire HTTP PUT if second call arrives within 150ms of first`
- [ ] `should show "reload in progress" warning toast on 409 lock-held conflict`
- [ ] `should distinguish version-conflict 409 from lock-held 409` (different toast type/message)
- [ ] `should show "Reloading N node(s)" toast when reload_mode = "selective"`
- [ ] `should show "Reloading DAG…" toast when reload_mode = "full"`
- [ ] `should show "Configuration saved." toast when reload_mode = "none"`

### 2.3 `FlowCanvasNodeComponent` reload indicator

- [ ] `should apply "animate-pulse" class when isReloading input = true`
- [ ] `should apply "opacity-70" class when isReloading input = true`
- [ ] `should NOT apply pulse/opacity classes when isReloading input = false`
- [ ] `should render spinner element (animate-spin) when isReloading = true`
- [ ] `should NOT render spinner when isReloading = false`
- [ ] `should apply "ring-2 ring-red-500" class on error event` (simulated via signal)
- [ ] `should set aria-label="Node is reloading" on spinner element`

### 2.4 `FlowCanvasComponent` signal passing

- [ ] `should pass isReloading=true to node whose ID is in reloadingNodeIds set`
- [ ] `should pass isReloading=false to nodes NOT in reloadingNodeIds set`
- [ ] `should NOT trigger re-render of non-reloading nodes when one node's reload state changes`

---

## Phase 3: Integration Tests — Backend

### 3.1 `save_dag_config` diff logic (`test_dag_config.py`)

- [ ] `test_save_param_change_triggers_selective_reload` — mock `selective_reload_node`; assert `reload_config` NOT called
- [ ] `test_save_topology_change_triggers_full_reload` — add a new node → assert `reload_config` called; `selective_reload_node` NOT called
- [ ] `test_save_edge_change_triggers_full_reload` — remove an edge → `reload_config` called
- [ ] `test_save_position_only_change_triggers_no_reload` — only `x`/`y` change → neither reload called
- [ ] `test_save_response_includes_reload_mode` — response body has `reload_mode` and `reloaded_node_ids`
- [ ] `test_save_response_reload_mode_none_on_no_change` — all nodes unchanged → `reload_mode = "none"`, `reloaded_node_ids = []`
- [ ] `test_save_409_when_lock_held` — `_reload_lock` acquired → `PUT /dag/config` returns 409 with correct message

### 3.2 New REST endpoints (`test_node_selective_reload.py`)

- [ ] `test_post_node_reload_success` — 200 with `NodeReloadResponse`; verify `status = "reloaded"`, `duration_ms > 0`, `ws_topic` present
- [ ] `test_post_node_reload_404_unknown_node` — unknown node_id → 404 with descriptive detail
- [ ] `test_post_node_reload_409_lock_held` — lock held → 409 with "already in progress" message
- [ ] `test_post_node_reload_500_on_failure_with_rollback` — `NodeFactory.create` raises → 500; assert old node still running
- [ ] `test_get_reload_status_idle` — 200 with `locked=false`, `active_reload_node_id=null`
- [ ] `test_get_reload_status_during_selective_reload` — while reload running → `locked=true`, `active_reload_node_id` set, `estimated_completion_ms=150`
- [ ] `test_get_reload_status_during_full_reload` — while full reload running → `locked=true`, `active_reload_node_id=null`, `estimated_completion_ms=3000`

---

## Phase 4: E2E / Functional Verification

These tests require both backend and frontend to be running together. Execute after both implementation phases are complete.

### 4.1 Selective Reload — Happy Path

- [ ] **Setup**: Start the DAG with at least 2 nodes (Node A upstream, Node B downstream) streaming data over WebSocket
- [ ] **Action**: Change a parameter in Node A's config (e.g., filter threshold), then click Save
- [ ] **Verify**:
  - [ ] `PUT /dag/config` response has `reload_mode = "selective"` and `reloaded_node_ids = [nodeA_id]`
  - [ ] Node A's card shows `animate-pulse` indicator in the UI
  - [ ] `system_status` WebSocket emits `reload_event { status: "reloading" }` for Node A
  - [ ] `system_status` WebSocket emits `reload_event { status: "ready" }` after reload completes
  - [ ] Node A's pulsing indicator disappears
  - [ ] **Node B never disconnects from WebSocket** — browser DevTools WS panel shows zero close frames for Node B
  - [ ] **Node A's WebSocket topic is preserved** — same topic name before and after, no reconnect on the client
  - [ ] Total time from Save click to `ready` event < 500ms (measure via browser DevTools Network timing)

### 4.2 Topology Change — Full Reload Path

- [ ] **Action**: Add a new node to the DAG and Save
- [ ] **Verify**:
  - [ ] `PUT /dag/config` response has `reload_mode = "full"` and `reloaded_node_ids = []`
  - [ ] Full DAG reload proceeds (existing behavior)
  - [ ] No `animate-pulse` indicators appear on individual nodes

### 4.3 Position-Only Change — No Reload Path

- [ ] **Action**: Drag a node to a new position on the canvas, then Save
- [ ] **Verify**:
  - [ ] `PUT /dag/config` response has `reload_mode = "none"` and `reloaded_node_ids = []`
  - [ ] No reload event is emitted on `system_status` WebSocket
  - [ ] No visual reload indicator appears on any node

### 4.4 Concurrent Reload — 409 Rejection

- [ ] **Setup**: Simulate a slow reload (node takes >200ms to restart)
- [ ] **Action**: Send a second `PUT /dag/config` while the first reload is in progress
- [ ] **Verify**:
  - [ ] Second request returns HTTP 409
  - [ ] Frontend shows "A reload is already in progress" toast (NOT a generic error)
  - [ ] First reload completes successfully without interruption

### 4.5 Reload Failure — Rollback Behavior

- [ ] **Setup**: Configure Node A with an invalid port (e.g., a port already bound by another process)
- [ ] **Action**: Save config to trigger reload
- [ ] **Verify**:
  - [ ] `system_status` emits `reload_event { status: "error", error_message: "..." }`
  - [ ] Node A shows red ring indicator (`ring-2 ring-red-500`) in the UI
  - [ ] Red ring disappears after 3 seconds
  - [ ] Old Node A instance is still running (rollback was successful)
  - [ ] Node B and all other nodes are unaffected
  - [ ] `PUT /dag/config` returns HTTP 500 with clear error message including rollback status

### 4.6 WebSocket Connection Preservation (Zero Drop Verification)

- [ ] **Setup**: Open browser DevTools → Network → WS filter. Connect to a node's WebSocket topic.
- [ ] **Action**: Trigger 5 consecutive selective reloads on that node (changing a parameter each time, waiting for each to complete)
- [ ] **Verify**:
  - [ ] Zero `1001` (Going Away) close frames appear in the WS panel for that connection
  - [ ] Zero reconnection attempts visible in the Network panel
  - [ ] Data stream resumes within 100ms after each `ready` event

---

## Phase 5: Performance Testing

### 5.1 Single-Node Reload Timing

- [ ] Measure 10 consecutive single-node selective reloads (sensor node with network reconnect)
- [ ] **Acceptance criterion**: All 10 reloads complete in < 500ms (from Save click to `ready` WS event)
- [ ] Record `duration_ms` from each `NodeReloadResponse` and log to `qa-report.md`
- [ ] Verify the backend-only portion (`duration_ms`) is < 75ms for parameter-only changes (no network reconnect)

### 5.2 Reload Overhead in Normal Operation (< 1% CPU)

- [ ] Measure CPU baseline: run DAG for 30 seconds with no reloads — record average CPU%
- [ ] Measure CPU with 1 reload per 10 seconds for 60 seconds — record average CPU%
- [ ] **Acceptance criterion**: CPU increase due to reload mechanism ≤ 1% of baseline (gate check overhead)
- [ ] Confirm no memory leak: take heap snapshot before and after 20 selective reloads; old node instances are garbage-collected

### 5.3 Downstream Buffer Gate Overhead

- [ ] Instrument the `DataRouter._forward_to_downstream_nodes` hot path (100k+ frames/minute)
- [ ] **Acceptance criterion**: When no reload is active (gate = None), `dict.get()` lookup adds < 1µs per frame on average
- [ ] Verify with profiling that the gate check does not appear in the top-10 hotspots when idle

---

## Phase 6: Linting & Static Analysis

### 6.1 Backend

- [ ] Run `ruff check app/` — zero errors in new files:
  - `app/services/nodes/config_hasher.py`
  - `app/services/nodes/input_gate.py`
  - `app/services/nodes/managers/selective_reload.py`
  - `app/api/v1/nodes/reload_handler.py`
- [ ] Run `mypy app/services/nodes/config_hasher.py` — passes strict type check
- [ ] Run `mypy app/services/nodes/input_gate.py` — passes strict type check
- [ ] Run `mypy app/services/nodes/managers/selective_reload.py` — passes strict type check
- [ ] Run `mypy app/api/v1/dag/service.py` — no new type errors after diff logic added
- [ ] Run `mypy app/services/nodes/orchestrator.py` — no new type errors
- [ ] Circular import check: `python -c "from app.services.nodes.managers.selective_reload import SelectiveReloadManager"` — no ImportError

### 6.2 Frontend

- [ ] Run `cd web && ng lint` — zero new warnings or errors
- [ ] Run `cd web && ng build` — zero compilation errors; no `any` type escapes in new code
- [ ] Bundle size delta < 1KB for all new frontend code (verify in build output)

---

## Phase 7: Developer Coordination Checkpoints

### 7.1 Backend Developer (@be-dev) Sign-off

- [ ] All backend phases (1–8) in `backend-tasks.md` checked off as `[x]`
- [ ] `pytest tests/` passes with zero failures (excluding pre-existing skipped tests)
- [ ] New endpoints (`POST /nodes/{id}/reload`, `GET /nodes/reload/status`) are live and responding to curl/httpie

### 7.2 Frontend Developer (@fe-dev) Sign-off

- [ ] All frontend phases (1–8) in `frontend-tasks.md` checked off as `[x]`
- [ ] `cd web && ng test --watch=false` passes with zero failures
- [ ] Reload indicator is visually confirmed in browser (screenshots in `qa-report.md`)

---

## Phase 8: Pre-PR Final Checklist

- [ ] All unit tests passing: `pytest tests/` — zero failures
- [ ] All frontend tests passing: `cd web && ng test --watch=false` — zero failures
- [ ] Backend linter clean: `ruff check app/` — zero issues
- [ ] Frontend linter clean: `cd web && ng lint` — zero issues
- [ ] Frontend build clean: `cd web && ng build` — zero errors
- [ ] All E2E functional tests in Phase 4 manually verified and results recorded
- [ ] Performance targets in Phase 5 verified and results recorded
- [ ] `qa-report.md` written with:
  - [ ] Test coverage summary (lines covered per new module)
  - [ ] Performance measurements table (reload timing, CPU overhead)
  - [ ] WebSocket preservation evidence (screenshot or log extract)
  - [ ] Any deviations from requirements with justification

---

## Acceptance Criteria Traceability

| Requirement | Test(s) | Status |
|-------------|---------|--------|
| Hash-based config diffing detects changed nodes | §1.1, §3.1 | - |
| Unchanged nodes continue without interruption | §4.1, §4.6 | - |
| Single node reload < 500ms | §4.1, §5.1 | - |
| Zero WebSocket reconnections during reload | §4.1, §4.6 | - |
| Downstream nodes pause and buffer data | §1.2, §1.3, §1.4 | - |
| Concurrent reload requests rejected with 409 | §3.1, §4.4 | - |
| 409 message distinguishes lock vs version conflict | §2.2, §4.4 | - |
| Reload failures logged; old node restored | §1.3, §3.2, §4.5 | - |
| Visual reload indicator on affected node | §2.3, §4.1 | - |
| DAG visualization stable (no full re-render) | §2.4, §4.1 | - |
| Only affected node visuals updated | §2.4 | - |
| Overhead < 1% CPU in normal operation | §5.2 | - |
| Position-only save triggers no reload | §3.1, §4.3 | - |
| Topology change still triggers full reload | §3.1, §4.2 | - |
