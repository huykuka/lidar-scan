# QA Tasks — Node Visibility Control

**Feature:** `node-visibility-control`  
**Assignee:** @qa  
**References:**
- Requirements: `.opencode/plans/node-visibility-control/requirements.md`
- Technical Spec: `.opencode/plans/node-visibility-control/technical.md`
- API Contract: `.opencode/plans/node-visibility-control/api-spec.md`
- Backend Tasks: `.opencode/plans/node-visibility-control/backend-tasks.md`
- Frontend Tasks: `.opencode/plans/node-visibility-control/frontend-tasks.md`

---

## TDD Preparation (Write Failing Tests First)

These tests must be written and committed as **failing** before development begins.

- [ ] **QA-TDD-1** Write failing backend unit test: `test_node_visible_defaults_to_true`
  - Assert that a `NodeModel` created without `visible` has `visible=True`
  - Assert that `to_dict()` includes `"visible": True`

- [ ] **QA-TDD-2** Write failing backend unit test: `test_set_visible_updates_db`
  - Assert `NodeRepository.set_visible(id, False)` changes the DB row

- [ ] **QA-TDD-3** Write failing backend unit test: `test_invisible_node_topic_not_registered`
  - Assert `ConfigLoader` does NOT call `manager.register_topic()` when `visible=False`
  - Assert `node_instance._ws_topic is None`

- [ ] **QA-TDD-4** Write failing backend unit test: `test_broadcast_skipped_for_invisible_node`
  - Assert `DataRouter._broadcast_to_websocket()` returns early when topic is `None`
  - Assert no bytes were sent to `ConnectionManager`

- [ ] **QA-TDD-5** Write failing backend integration test: `test_put_visibility_endpoint`
  - Assert `PUT /api/v1/nodes/{id}/visible` returns `200` with `{"status": "success"}`
  - Assert subsequent `GET /api/v1/nodes/{id}` reflects the new `visible` value

- [ ] **QA-TDD-6** Write failing backend integration test: `test_system_topic_visibility_protected`
  - Assert `PUT /api/v1/nodes/{system_node_id}/visible` returns `400`

- [ ] **QA-TDD-7** Write failing frontend unit test for `NodeVisibilityToggleComponent`
  - Assert that the component renders a `syn-icon-button`
  - Assert that clicking it emits `visibilityChanged` with the negated `visible` value

---

## Backend Unit Tests

*Coordinate with @be-dev. Check off after tests pass.*

- [ ] **QA-BE-1** `NodeModel.to_dict()` includes `visible: True` by default  
- [ ] **QA-BE-2** `NodeModel.to_dict()` includes `visible: False` when set  
- [ ] **QA-BE-3** `ensure_schema()` migration adds `visible` column to existing DB without error  
- [ ] **QA-BE-4** `ensure_schema()` migration is idempotent (safe to call twice)  
- [ ] **QA-BE-5** `NodeRepository.set_visible()` updates only the `visible` column (no side effects on other fields)  
- [ ] **QA-BE-6** `NodeRepository.set_visible()` raises `ValueError` for unknown node ID  
- [ ] **QA-BE-7** `NodeRepository.upsert()` persists `visible=False` correctly  
- [ ] **QA-BE-8** `NodeRepository.upsert()` defaults `visible=True` when field is absent  
- [ ] **QA-BE-9** `ConfigLoader._register_node_websocket_topic()`: topic registered when `visible=True`  
- [ ] **QA-BE-10** `ConfigLoader._register_node_websocket_topic()`: topic NOT registered when `visible=False`, `_ws_topic=None`  
- [ ] **QA-BE-11** `DataRouter._get_node_topic()`: returns `None` when `node_instance._ws_topic is None`  
- [ ] **QA-BE-12** `DataRouter._broadcast_to_websocket()`: returns immediately when topic is `None`, no exceptions  
- [ ] **QA-BE-13** `DataRouter._record_node_data()`: called even when topic is `None` (recording bypass verified)  
- [ ] **QA-BE-14** `DataRouter._forward_to_downstream_nodes()`: called even when topic is `None` (DAG routing bypass verified)  
- [ ] **QA-BE-15** `LifecycleManager._unregister_node_websocket_topic_async()`: returns without error when `_ws_topic=None`  
- [ ] **QA-BE-16** `NodeManager.set_node_visible(id, False)`: calls `unregister_topic()` and sets `_ws_topic=None`  
- [ ] **QA-BE-17** `NodeManager.set_node_visible(id, True)`: calls `register_topic()` and sets `_ws_topic=<topic>`  
- [ ] **QA-BE-18** `NodeManager.set_node_visible(id, ...)` with unknown `node_id`: no exception, silent no-op  
- [ ] **QA-BE-19** `set_node_visible()` service: returns `404` for unknown node ID  
- [ ] **QA-BE-20** `set_node_visible()` service: returns `400` for system topic node  
- [ ] **QA-BE-21** `NodeRecord` Pydantic schema validates with `visible` field  
- [ ] **QA-BE-22** `NodeStatusItem` Pydantic schema validates with `visible` and nullable `topic`  

---

## Backend Integration Tests

- [ ] **QA-BE-INT-1** `GET /api/v1/nodes` — response includes `visible` for all nodes  
- [ ] **QA-BE-INT-2** `GET /api/v1/nodes/{id}` — response includes `visible` field  
- [ ] **QA-BE-INT-3** `POST /api/v1/nodes` with `visible=false` — persists correctly, confirmed via GET  
- [ ] **QA-BE-INT-4** `POST /api/v1/nodes` without `visible` field — defaults to `true`  
- [ ] **QA-BE-INT-5** `PUT /api/v1/nodes/{id}/visible` `{visible: false}` — returns `200`, topic removed from `/topics`  
- [ ] **QA-BE-INT-6** `PUT /api/v1/nodes/{id}/visible` `{visible: true}` — returns `200`, topic appears in `/topics`  
- [ ] **QA-BE-INT-7** `PUT /api/v1/nodes/{id}/visible` with non-existent ID — returns `404`  
- [ ] **QA-BE-INT-8** `PUT /api/v1/nodes/{id}/visible` for system topic node — returns `400`  
- [ ] **QA-BE-INT-9** `GET /api/v1/nodes/status/all` — `visible=false` nodes have `topic: null`  
- [ ] **QA-BE-INT-10** `GET /api/v1/topics` — invisible node topics are absent  
- [ ] **QA-BE-INT-11** Config reload after hiding node: node remains hidden (verified via `/topics`)  
- [ ] **QA-BE-INT-12** Config import with `visible: false` node — node starts hidden  
- [ ] **QA-BE-INT-13** Config import without `visible` field — node defaults to visible  
- [ ] **QA-BE-INT-14** Config export — `visible` field present for all nodes  

---

## Frontend Unit Tests

*Coordinate with @fe-dev.*

- [ ] **QA-FE-1** `NodeConfig` interface includes `visible: boolean`  
- [ ] **QA-FE-2** `NodeStatus` interface includes `visible: boolean` and `topic: string | null`  
- [ ] **QA-FE-3** `NodesApiService.setNodeVisible()` makes `PUT` call to correct URL with correct body  
- [ ] **QA-FE-4** `NodeStoreService.visibleNodes` computed returns only nodes where `visible !== false`  
- [ ] **QA-FE-5** `NodeVisibilityToggleComponent`: renders eye icon when `visible=true`  
- [ ] **QA-FE-6** `NodeVisibilityToggleComponent`: renders eye-off icon when `visible=false`  
- [ ] **QA-FE-7** `NodeVisibilityToggleComponent`: emits `visibilityChanged` with `false` when visible node is clicked  
- [ ] **QA-FE-8** `NodeVisibilityToggleComponent`: emits `visibilityChanged` with `true` when hidden node is clicked  
- [ ] **QA-FE-9** `NodeVisibilityToggleComponent`: button is disabled when `isPending=true`  
- [ ] **QA-FE-10** Smart component: optimistic update changes store before API returns  
- [ ] **QA-FE-11** Smart component: store rolled back when API call returns error  
- [ ] **QA-FE-12** Smart component: toast error shown on API failure  
- [ ] **QA-FE-13** Smart component: `isTogglingVisibility` is `true` during API call, `null` after  

---

## Frontend E2E Tests

- [ ] **QA-FE-E2E-1** Eye icon toggle is visible next to each node in settings node list  
- [ ] **QA-FE-E2E-2** Clicking the eye icon hides a visible node (icon changes, row dims) within 100ms  
- [ ] **QA-FE-E2E-3** Clicking the eye-off icon shows a hidden node (icon changes, row returns to full opacity)  
- [ ] **QA-FE-E2E-4** Workspace topic selector does NOT list a hidden node's topic  
- [ ] **QA-FE-E2E-5** Workspace Three.js scene removes the point cloud when node is hidden  
- [ ] **QA-FE-E2E-6** UI does not show any JavaScript console errors during toggle  
- [ ] **QA-FE-E2E-7** Double-clicking the toggle does not cause duplicate requests (button disabled during flight)  

---

## Edge Case Tests

- [ ] **QA-EC-1** Rapid toggles: hide and show the same node 5 times in rapid succession — system ends in correct final state  
- [ ] **QA-EC-2** Hide 50 nodes simultaneously (batch test) — all topics absent from `/topics` within 1 second  
- [ ] **QA-EC-3** Hide a node while its WebSocket has 3 active browser clients — all clients receive `1001` close  
- [ ] **QA-EC-4** Hide a node while a `wait_for_next()` interceptor is pending — returns `asyncio.CancelledError` or 503  
- [ ] **QA-EC-5** Disable (`enabled=false`) a hidden node, then re-enable it — node remains hidden (DB state preserved)  
- [ ] **QA-EC-6** Hide a node while recording is active — recording file continues growing (data integrity)  
- [ ] **QA-EC-7** System topic protection: `system_status` topic cannot be hidden (400 response)  
- [ ] **QA-EC-8** Import a config with `visible: false` nodes, reload is triggered — node stays hidden after reload  
- [ ] **QA-EC-9** WebSocket client connects to a topic for a hidden node — client connects but receives no frames (no crash)  

---

## Performance Tests

- [ ] **QA-PERF-1** Single visibility toggle: end-to-end latency from UI click to topic removal < 1000ms  
- [ ] **QA-PERF-2** UI optimistic update latency < 100ms (measured via browser performance timeline)  
- [ ] **QA-PERF-3** Batch hide of 50 nodes: all complete within 1000ms  
- [ ] **QA-PERF-4** Memory baseline after 100 hide/show cycles — no memory leak in Three.js GPU buffers (Chrome Task Manager)  
- [ ] **QA-PERF-5** `forward_data()` hot path overhead: topic=None guard adds < 1µs per call (profiling check)  

---

## Linter & Type-Check Verification

- [ ] **QA-LINT-1** Backend: `ruff check app/` — zero new errors  
- [ ] **QA-LINT-2** Backend: `mypy app/` or equivalent — zero new type errors related to this feature  
- [ ] **QA-LINT-3** Frontend: `cd web && ng build --configuration production` — zero compilation errors  
- [ ] **QA-LINT-4** Frontend: `cd web && ng lint` — zero linting errors  

---

## Developer Coordination

- [ ] **QA-COORD-1** Confirm with @be-dev that all backend tasks (BE-1.x through BE-6.x) are checked off  
- [ ] **QA-COORD-2** Confirm with @fe-dev that all frontend tasks (FE-1.x through FE-7.x) are checked off  
- [ ] **QA-COORD-3** Verify BE-FE integration: frontend calls real `PUT /nodes/{id}/visible` against running backend  
- [ ] **QA-COORD-4** Verify WebSocket close flow end-to-end in browser DevTools Network tab  

---

## Pre-PR Verification Checklist

Before raising a Pull Request, confirm all of the following:

- [ ] All TDD tests written and now passing  
- [ ] All unit tests passing (`pytest tests/` — backend, `ng test` — frontend)  
- [ ] All integration tests passing  
- [ ] All edge case tests passing  
- [ ] All performance benchmarks met  
- [ ] All linter/type-checker checks clean  
- [ ] Manual demo: hide a node, confirm topic gone from workspace selector, Three.js scene cleared  
- [ ] Manual demo: show a node, confirm topic re-appears in workspace selector, streaming resumes  
- [ ] All acceptance criteria in `requirements.md` checked off (AC1–AC26)  
- [ ] `qa-report.md` written with test coverage summary and any outstanding risks  
