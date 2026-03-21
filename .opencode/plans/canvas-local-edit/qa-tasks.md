# Canvas Local Edit — QA Tasks

**Feature:** `canvas-local-edit`  
**Agent:** `@qa`  
**References:**
- Requirements: `requirements.md`
- Technical design: `technical.md`
- API contract: `api-spec.md`
- Backend tasks: `backend-tasks.md`
- Frontend tasks: `frontend-tasks.md`

**Revision v2:** `Cancel/Revert` renamed → **`Sync`**. New standalone **`Reload`** button (backend runtime restart
only). All test sections updated to reflect the 3-button toolbar: `[Reload]`, `[Sync]`, `[Save & Reload]`.

---

## Pre-Development: TDD Preparation

These failing tests must be written **before** development begins (Red phase of TDD). Check them off as they are
written.

### Backend — Write Failing Tests First

- [ ] Create `tests/api/test_dag_config.py` with all test stubs (bodies raise `NotImplementedError` or
  `AssertionError`)
- [ ] Create `tests/repositories/test_dag_meta_orm.py` with all test stubs
- [ ] Verify all stub tests fail on `pytest` run before any implementation
- [ ] Confirm test files are collected: `pytest tests/api/test_dag_config.py --collect-only`

### Frontend — Write Failing Tests First

- [ ] Create `web/src/app/features/settings/services/canvas-edit-store.service.spec.ts` with all test stubs
- [ ] Create `web/src/app/features/settings/utils/dag-validator.spec.ts` with all test stubs
- [ ] Create `web/src/app/core/guards/unsaved-changes.guard.spec.ts` with all test stubs
- [ ] Verify stubs fail: `cd web && ng test --include='**/canvas-edit-store*' --watch=false`

---

## 0. Dead Code Purge Verification (Phase -1 Gate)

> **QA must verify Phase -1 is complete before any other frontend testing begins.**
> These checks confirm that every obsolete symbol has been deleted and the codebase compiles cleanly.

- [ ] Run `rg -n "hasUnsavedChanges|saveAllPositions|onReloadConfig|cancelAndRevert|isReverting|loadGraphData|unsavedPositions" web/src/app/features/settings/` — expect **zero** matches
- [ ] Run `rg -n "hasUnsavedChangesChange" web/src/app/features/settings/` — expect **zero** matches (the output
  and all its bindings must be gone)
- [ ] Run `cd web && npx tsc --noEmit` — expect **zero** type errors
- [ ] Run `cd web && ng build --configuration=development` — expect **zero** template compilation errors
- [ ] Manually verify `settings.component.html` has **no** `(hasUnsavedChangesChange)` binding on `<app-flow-canvas>`
- [ ] Manually verify `settings.component.html` has **no** old single-button "Save & Reload" gated on
  `!flowCanvas().hasUnsavedChanges()`
- [ ] Manually verify `flow-canvas.component.ts` has **no** `saveAllPositions` method
- [ ] Manually verify `flow-canvas.component.ts` has **no** `loadGraphData` method
- [ ] Manually verify `settings.component.ts` has **no** `onReloadConfig` method
- [ ] Manually verify `settings.component.ts` has **no** `loadConfig` method (old `nodesApi.getNodes()` version)
- [ ] Confirm no `EdgesApiService` is imported in `flow-canvas.component.ts`

---

## 1. Backend Unit Tests

**Verify with:** `pytest tests/ -v`  
**Coordinate with:** `@be-dev` (check all `backend-tasks.md` boxes are marked `[x]` before verifying)

### 1.1 `DagMetaRepository` (`tests/repositories/test_dag_meta_orm.py`)

- [ ] `test_get_version_returns_0_for_fresh_db` — Fresh DB after `ensure_schema()` returns `config_version=0`
- [ ] `test_increment_version_returns_new_value` — After one increment, `get_version()` returns `1`
- [ ] `test_increment_version_is_atomic` — Two sequential increments return `1` and `2` respectively; no skipped values

### 1.2 Migration Tests

- [ ] `dag_meta` table is created by `ensure_schema()` if it doesn't exist
- [ ] Seed row `(id=1, config_version=0)` is inserted on first run
- [ ] `ensure_schema()` is idempotent: running twice produces exactly one row (no duplicate key error)
- [ ] `dag_meta` table is present after migration when starting from a DB that had only `nodes` and `edges` tables

### 1.3 `GET /api/v1/dag/config` (`tests/api/test_dag_config.py`)

- [ ] `test_get_returns_empty_dag_for_fresh_db` — Empty nodes `[]`, empty edges `[]`, `config_version=0`
- [ ] `test_get_returns_correct_version_and_nodes` — Seed DB with 2 nodes + 1 edge; assert all fields are present
- [ ] `test_version_is_integer` — `config_version` field type is `int`, not float or string
- [ ] `test_get_includes_canvas_positions` — Node `x` and `y` fields are present in the response

### 1.4 `PUT /api/v1/dag/config` — Success Path

- [ ] `test_save_success_increments_version` — PUT with `base_version=0` returns `config_version=1`
- [ ] `test_save_replaces_nodes` — PUT with 1 node after seeding 3; DB contains exactly 1 node after save
- [ ] `test_save_replaces_edges` — PUT with 0 edges after seeding 2; DB contains exactly 0 edges after save
- [ ] `test_save_assigns_new_id_for_temp_nodes` — PUT with node `id="__new__abc"`; `node_id_map` key present; new ID
  is valid UUID
- [ ] `test_save_updates_edge_references_for_temp_nodes` — PUT with node `id="__new__1"` and edge pointing to it;
  after save, edge in DB references the real UUID
- [ ] `test_save_triggers_reload` — `node_manager.reload_config` is called exactly once on a successful PUT
- [ ] `test_subsequent_get_reflects_saved_state` — After PUT, GET returns same nodes/edges and `config_version+1`

### 1.5 `PUT /api/v1/dag/config` — Error Cases

- [ ] `test_save_409_on_version_conflict` — DB version=5, PUT with `base_version=3` → 409; `"Version conflict"` in
  body; DB version unchanged
- [ ] `test_save_409_on_reload_in_progress` — Mock `_reload_lock.locked()` = True; PUT → 409; `"reload in progress"`
  in body
- [ ] `test_save_does_not_increment_on_db_error` — Mock `NodeRepository.upsert` to raise; PUT → 500; version
  unchanged
- [ ] `test_save_422_on_missing_node_name` — PUT with node missing `name` field → 422
- [ ] `test_save_422_on_missing_base_version` — PUT without `base_version` field → 422
- [ ] `test_save_500_body_contains_detail_field` — Mock DB error; 500 response has `"detail"` field

### 1.6 `POST /api/v1/nodes/reload` — Reload Button (Existing Endpoint, Regression Tests)

> These validate that the existing endpoint used by the **Reload** button is unmodified and behaves correctly.

- [ ] `test_reload_returns_200_on_success` — POST `/nodes/reload` returns 200
- [ ] `test_reload_does_not_modify_config_version` — After POST `/nodes/reload`, GET `/dag/config` returns the same
  `config_version` as before
- [ ] `test_reload_does_not_modify_nodes_or_edges` — After POST `/nodes/reload`, node and edge content in DB is
  unchanged

---

## 2. Frontend Unit Tests

**Verify with:** `cd web && ng test --watch=false --code-coverage`  
**Coordinate with:** `@fe-dev` (check all `frontend-tasks.md` boxes are marked `[x]` before verifying)

### 2.1 `dag-validator.ts` (`dag-validator.spec.ts`)

- [ ] `detectCycles` returns empty array for a DAG with no cycles (linear chain: A→B→C)
- [ ] `detectCycles` returns a non-empty array when a direct cycle exists (A→B→A)
- [ ] `detectCycles` returns a non-empty array for an indirect cycle (A→B→C→A)
- [ ] `detectCycles` returns empty array for empty node and edge arrays
- [ ] `validateRequiredFields` returns empty array when all required fields are populated
- [ ] `validateRequiredFields` returns one `ValidationError` per missing required field
- [ ] `validateRequiredFields` ignores fields where `required !== true`
- [ ] `ValidationError` objects include `nodeId`, `nodeName`, and `field` properties

### 2.2 `CanvasEditStoreService` (`canvas-edit-store.service.spec.ts`)

**State & Dirty Tracking**

- [ ] `isDirty()` returns `false` after `initFromBackend()` with the same data as `NodeStoreService`
- [ ] `isDirty()` returns `true` after `moveNode()` changes a node position
- [ ] `isDirty()` returns `true` after `addNode()`
- [ ] `isDirty()` returns `true` after `deleteNode()`
- [ ] `isDirty()` returns `true` after `addEdge()`
- [ ] `isDirty()` returns `true` after `deleteEdge()`
- [ ] `isDirty()` returns `false` again after `syncFromBackend()` completes (mock `DagApiService`)

**Mutation Methods**

- [ ] `deleteNode()` cascades: removes edges where `source_node === id` or `target_node === id`
- [ ] `deleteNode()` does not remove edges unrelated to the deleted node
- [ ] `addEdge()` prevents duplicate edges (same `source_node + source_port + target_node`)
- [ ] `addEdge()` assigns a temp ID when none is provided
- [ ] `addNode()` assigns a temp ID starting with `__new__` when no `id` is provided
- [ ] `updateNode()` only updates the targeted node; other nodes are unchanged

**Save Flow**

- [ ] `saveAndReload()` calls `DagApiService.saveDagConfig()` with `base_version`, `nodes`, and `edges`
- [ ] `saveAndReload()` applies `node_id_map` on 200: `__new__*` IDs in `_localNodes` are replaced
- [ ] `saveAndReload()` applies `node_id_map` on 200: edge `source_node`/`target_node` references are also remapped
- [ ] `saveAndReload()` sets `isSaving()` to `true` during the call and `false` after
- [ ] `saveAndReload()` calls `NodeStoreService.setState()` on success
- [ ] `saveAndReload()` does NOT call `DagApiService` when `isDirty()` is false
- [ ] `saveAndReload()` does NOT call `DagApiService` when `isValid()` is false; shows toast instead

**Conflict (409) Handling**

- [ ] `saveAndReload()` emits on `conflictDetected$` when `DagApiService` throws a 409
- [ ] On 409: `isDirty()` remains `true` (local edits are preserved)
- [ ] On 409: `isSaving()` is reset to `false`

**Sync Flow (renamed from Cancel/Revert)**

- [ ] `syncFromBackend()` shows confirmation dialog when `isDirty()` is `true` and `skipConfirm` is `false`
- [ ] `syncFromBackend()` does NOT show dialog when `isDirty()` is `false`
- [ ] `syncFromBackend()` does NOT show dialog when `skipConfirm` is `true` (conflict-path bypass)
- [ ] `syncFromBackend()` aborts (no GET call) when dialog is dismissed
- [ ] `syncFromBackend()` calls `DagApiService.getDagConfig()` when confirmed (or not dirty)
- [ ] `syncFromBackend()` calls `initFromBackend()` with the fetched config
- [ ] `syncFromBackend()` sets `isSyncing()` to `true` during the call and `false` after

**Reload Runtime Flow (NEW)**

- [ ] `reloadRuntime()` calls `POST /api/v1/nodes/reload` (via existing service) exactly once
- [ ] `reloadRuntime()` sets `isReloading()` to `true` during the call and `false` after (success path)
- [ ] `reloadRuntime()` sets `isReloading()` to `false` after an error (error path)
- [ ] `reloadRuntime()` shows a success toast on 200
- [ ] `reloadRuntime()` shows a danger toast on error
- [ ] **`reloadRuntime()` does NOT modify `_localNodes` — value is identical before and after**
- [ ] **`reloadRuntime()` does NOT modify `_localEdges` — value is identical before and after**
- [ ] **`reloadRuntime()` does NOT modify `_baseVersion` — value is identical before and after**
- [ ] **`reloadRuntime()` does NOT change `isDirty()` — value is identical before and after (both true and false
  cases)**
- [ ] `reloadRuntime()` does NOT call `DagApiService.getDagConfig()` or `DagApiService.saveDagConfig()`

### 2.3 `unsavedChangesGuard` (`unsaved-changes.guard.spec.ts`)

- [ ] Returns `true` (allow navigation) when `CanvasEditStoreService.isDirty()` is `false`
- [ ] Returns the result of `DialogService.confirm()` when `isDirty()` is `true`
- [ ] Returns `false` (block navigation) when dialog is dismissed
- [ ] Returns `true` (allow navigation) when dialog is confirmed

---

## 3. Integration Tests

### 3.1 Backend — Full Request/Response Cycle

**Verify with:** `pytest tests/api/test_dag_config.py -v` (using the test client, real in-memory SQLite)

- [ ] `GET → PUT → GET` round-trip: version increments from 0 → 1 between first and second GET
- [ ] Two sequential `PUT` calls with correct incremental `base_version` both succeed: versions 0→1, 1→2
- [ ] `GET` after a failed `PUT` (version conflict) still returns the unchanged version
- [ ] Node created with temp ID (`__new__*`) via PUT is retrievable via GET with its real UUID
- [ ] **`POST /nodes/reload` followed by `GET /dag/config` returns the same `config_version`** (reload does not
  increment version)

### 3.2 Frontend — Component Integration

**Verify with:** `cd web && ng test --include='**/settings*' --watch=false`

- [ ] `SettingsComponent` calls `DagApiService.getDagConfig()` on init and seeds `CanvasEditStoreService`
- [ ] `FlowCanvasComponent` renders nodes from `canvasEditStore.localNodes()`, not `nodeStore.nodes()`
- [ ] Dragging a node updates `canvasEditStore.localNodes()` and sets `isDirty()` to `true`
- [ ] `onSaveAndReload()` delegates entirely to `canvasEditStore.saveAndReload()`
- [ ] `onSync()` delegates to `canvasEditStore.syncFromBackend()`
- [ ] `onReloadRuntime()` delegates to `canvasEditStore.reloadRuntime()`
- [ ] After `onReloadRuntime()` completes, `isDirty()` is unchanged (still matches pre-reload state)
- [ ] Conflict dialog shows "Sync & Discard My Changes" when `conflictDetected$` emits
- [ ] Clicking "Sync & Discard" in conflict dialog calls `syncFromBackend(true)` (skipConfirm)

---

## 4. E2E / Acceptance Tests

These must be verified manually or via an automated E2E framework (e.g., Playwright/Cypress) against a running
full-stack environment.

### 4.1 Initial Load

- [ ] On navigating to `/settings`, the canvas renders existing nodes and edges from the backend
- [ ] No dirty indicator is shown on first load
- [ ] Save & Reload button is disabled on first load
- [ ] Reload and Sync buttons are **enabled** on first load

### 4.2 Editing — No API Calls During Local Edits

- [ ] Open DevTools Network tab → filter to `XHR / Fetch`
- [ ] Drag a node on the canvas → **zero** network requests are made
- [ ] Add an edge between two nodes → **zero** network requests are made
- [ ] Delete a node → **zero** network requests are made
- [ ] Open a node editor and change a config field → **zero** network requests are made
- [ ] All of the above: dirty indicator appears immediately after first edit

### 4.3 Save & Reload — Happy Path

- [ ] Make at least one edit (drag, add edge, or delete node)
- [ ] Click **Save & Reload**: spinner appears on button, button is disabled during save
- [ ] Success: dirty indicator disappears, title reverts to "Settings" (no "●")
- [ ] Success toast is shown
- [ ] WebSocket reconnects (if any active topics) without error
- [ ] After page reload, changes are persisted (GET returns the new state)

### 4.4 Sync — Happy Path (No Local Edits)

- [ ] With no local edits (clean state), click **Sync**
- [ ] **No confirmation dialog appears** — sync executes immediately
- [ ] Canvas re-renders with backend state; dirty indicator remains absent
- [ ] Sync toast is shown

### 4.5 Sync — With Unsaved Edits

- [ ] Make an edit; click **Sync**
- [ ] Confirmation dialog appears: _"You have unsaved changes. Syncing will discard them and load the latest backend
  configuration. Continue?"_
- [ ] Dismissing dialog: no changes; dirty indicator still visible; local edits still present
- [ ] Confirming dialog: canvas reverts to server state; dirty indicator disappears; toast shown

### 4.6 Reload (Runtime Only — No State Change)

- [ ] With **no local edits**: click **Reload**
  - No confirmation dialog appears
  - Reload spinner appears on button; other buttons remain in their normal state
  - Success toast "DAG runtime reloaded successfully" appears
  - No dirty indicator appears (state was already clean)
  - Canvas display is unchanged
- [ ] With **unsaved local edits**: click **Reload**
  - No confirmation dialog appears
  - Reload spinner appears; dirty indicator **remains visible** throughout
  - Success toast appears
  - **Local edits are fully preserved** — verify by checking dirty indicator is still shown and unsaved node
    positions/config are unchanged
  - **No GET request to `/dag/config` is made** (verify via DevTools Network tab)
  - **No state is pulled from backend** (verify canvas still shows local edits after reload)
- [ ] Reload button disabled (spinner) while in-flight; re-enables after completion
- [ ] Reload error (simulate network error): error toast shown; `isReloading()` resets to false

### 4.7 Navigation Guard — Angular Router

- [ ] Make an edit; attempt to navigate to a different route via the sidebar
- [ ] Confirmation dialog appears: "Unsaved Changes — You have unsaved changes on the canvas. Leaving will discard
  them."
- [ ] Clicking **Stay**: navigation is blocked; user remains on `/settings` with edits intact
- [ ] Clicking **Leave & Discard**: navigation proceeds; dirty state is gone

### 4.8 Navigation Guard — Browser Tab Close / Refresh

- [ ] Make an edit; press `F5` (or `Ctrl+R`) → browser "Leave site?" dialog appears
- [ ] Make an edit; attempt to close the tab → browser "Leave site?" dialog appears
- [ ] With no unsaved changes: `F5` proceeds without any browser dialog

### 4.9 Version Conflict (409) Scenario

- [ ] Open the canvas in **two browser tabs** simultaneously (Tab A and Tab B)
- [ ] In Tab A: make an edit and click **Save & Reload** → succeeds (version 0→1)
- [ ] In Tab B: make a different edit and click **Save & Reload** → conflict dialog appears, with
  **"Sync & Discard My Changes"** and **"Stay & Keep Editing"** buttons
- [ ] Tab B: click **Stay & Keep Editing** → dialog closes; Tab B's local edits are still visible; dirty indicator
  remains
- [ ] Tab B: click **Sync & Discard My Changes** → canvas reloads to Tab A's saved state; dirty indicator disappears

### 4.10 Validation — Save Blocked on Errors

- [ ] Create a cycle (A→B→A) in the canvas
- [ ] **Save & Reload** button is disabled (or clicking shows a toast/error)
- [ ] Required-field error: open a node editor, clear a required field → toast shows "Fix validation errors before
  saving"
- [ ] After fixing the cycle/required field: Save & Reload is enabled again

### 4.11 Live-Action Operations (Exempt From Local Buffer)

- [ ] Toggle node visibility (eye icon) → **immediately** calls backend API; does NOT set `isDirty()` to `true`
- [ ] Toggle node enable/disable → **immediately** calls backend API; does NOT set `isDirty()` to `true`

---

## 5. Edge Case & Regression Tests

### 5.1 Concurrent Save (Lock Race)

- [ ] Trigger a `POST /api/v1/nodes/reload` while a `PUT /api/v1/dag/config` is in progress (simulate via backend
  test with mocked lock)
- [ ] The second request returns 409 "reload in progress" without corrupting DB state
- [ ] After lock is released, a fresh PUT with the correct version succeeds

### 5.2 Network Failure During Save

- [ ] Simulate a network timeout on `PUT /api/v1/dag/config` (e.g., via browser DevTools → Offline mid-request)
- [ ] Error toast is displayed: "Request timed out" or "Save failed"
- [ ] `isSaving()` is reset to `false`
- [ ] `isDirty()` remains `true` (local edits are NOT lost)
- [ ] Restoring network and retrying Save & Reload succeeds

### 5.3 Network Failure During Reload (Runtime)

- [ ] Simulate a network failure on `POST /api/v1/nodes/reload`
- [ ] Error toast is displayed
- [ ] `isReloading()` is reset to `false`
- [ ] `isDirty()` is unchanged (unaffected by Reload error)
- [ ] Local canvas state is fully intact (no nodes/edges lost)

### 5.4 Network Failure During Sync

- [ ] Simulate a network failure on `GET /api/v1/dag/config` during Sync
- [ ] Error toast is displayed
- [ ] `isSyncing()` is reset to `false`
- [ ] `isDirty()` and local state are unchanged (sync aborted cleanly)

### 5.5 Partial DB Failure Atomicity

- [ ] Backend: mock a DB failure occurring after nodes are written but before edges are written
- [ ] Verify: DB transaction is rolled back; no orphaned nodes; `config_version` NOT incremented
- [ ] Client receives HTTP 500 with `"Save failed:"` detail

### 5.6 Empty Canvas Save

- [ ] Delete all nodes and edges from the canvas (empty DAG)
- [ ] Click Save & Reload → succeeds; GET returns `nodes: [], edges: []`; version increments

### 5.7 Large Canvas Performance

- [ ] Load a canvas with 50 nodes and 60 edges
- [ ] Drag a node: dirty indicator appears in **< 100ms**
- [ ] Click Save & Reload: `PUT` response time is **< 3 seconds**
- [ ] Canvas re-renders after save in **< 200ms**
- [ ] **Reload** button round-trip: **< 2 seconds**
- [ ] **Sync** button round-trip: **< 2 seconds** (GET + canvas re-render)
- [ ] Confirm: **zero** network requests occurred during any drag operation

### 5.8 WebSocket Stability After Save

- [ ] Active sensor streams are running (WebSocket topics open)
- [ ] Perform a Save & Reload
- [ ] Backend calls `reload_config()` and WebSocket topics are cleaned up and re-registered per `protocols.md`
- [ ] Frontend receives `1001 Going Away` close codes and reconnects automatically
- [ ] No duplicate WebSocket topic subscriptions after reconnect

### 5.9 WebSocket Stability After Reload (Runtime Only)

- [ ] Active sensor streams are running (WebSocket topics open)
- [ ] Click **Reload** button
- [ ] Backend restarts runtime; verify WebSocket topics are cleaned up and reconnect per `protocols.md`
- [ ] Local canvas state is unchanged throughout

### 5.10 Page Refresh Mid-Edit

- [ ] Make edits; do NOT save; do a hard page refresh (`Ctrl+Shift+R`)
- [ ] Browser dialog appears (from `beforeunload` handler); if user confirms, page refreshes
- [ ] After reload, canvas reflects the last **saved** server state (local edits NOT persisted — autosave out of
  scope)

### 5.11 Re-navigation After Save

- [ ] Make an edit; save successfully
- [ ] Navigate away to another page
- [ ] Navigate back to `/settings`
- [ ] No dirty indicator; Save & Reload disabled; canvas shows most recently saved state
- [ ] `CanvasEditStoreService` is a **fresh instance** (feature-scoped) — no stale local state

### 5.12 Reload Does Not Trigger Dirty State

- [ ] Navigate to `/settings` (clean state, `isDirty() = false`)
- [ ] Click **Reload**
- [ ] After Reload completes: `isDirty()` is still `false`
- [ ] Make an edit (`isDirty() = true`); click **Reload**
- [ ] After Reload completes: `isDirty()` is still `true` (local edits preserved)
- [ ] The unsaved-changes indicator is **still visible** after Reload when edits existed pre-Reload

---

## 6. Linter & Type-Check Verification

- [ ] **Backend linter:** `cd app && ruff check . && ruff format --check .` — zero errors
- [ ] **Backend type check:** `mypy app/api/v1/dag/ app/repositories/dag_meta_orm.py` — zero errors
- [ ] **Frontend linter:** `cd web && npx eslint src/ --ext .ts,.html` — zero errors
- [ ] **Frontend type check:** `cd web && npx tsc --noEmit` — zero errors
- [ ] **Frontend tests coverage:** `ng test --watch=false --code-coverage` — coverage ≥ 80% on new files
  (`canvas-edit-store.service.ts`, `dag-validator.ts`, `unsaved-changes.guard.ts`)

---

## 7. Developer Coordination Checkpoints

Use these before moving to the next phase. Do NOT start QA verification of a phase until the dev confirms completion.

- [ ] **Frontend Phase -1 complete** (`@fe-dev` marks all Phase -1 checkboxes `[x]`): dead code purged, `tsc --noEmit` passes, `ng build` passes — **QA must independently verify §0 before any other FE testing**
- [ ] **Backend Phase 1 complete** (`@be-dev` marks all Phase 1 checkboxes `[x]`): DB layer testable
- [ ] **Backend Phase 2–3 complete** (`@be-dev` marks Phases 2–3 `[x]`): schemas + service layer testable
- [ ] **Backend Phase 4–5 complete** (`@be-dev` marks Phases 4–5 `[x]`): endpoints live and all backend tests pass
- [ ] **Frontend Phase 0–1 complete** (`@fe-dev` marks Phases 0–1 `[x]`): mocked `DagApiService` +
  `CanvasEditStoreService` unit-testable (including `reloadRuntime()`)
- [ ] **Frontend Phase 2–4 complete** (`@fe-dev` marks Phases 2–4 `[x]`): canvas refactor + 3-button toolbar visible
- [ ] **Frontend Phase 5–7 complete** (`@fe-dev` marks Phases 5–7 `[x]`): template, guard, cleanup done
- [ ] **Backend integrated with Frontend** (frontend `environment.useMockDag` set to `false`): full-stack E2E testing
  can begin

---

## 8. Pre-PR Final Checklist

All items below must be checked before creating the pull request.

- [ ] All backend unit tests pass: `pytest tests/ -v --tb=short` — 0 failures, 0 errors
- [ ] All frontend unit tests pass: `cd web && ng test --watch=false` — 0 failures
- [ ] Backend linter clean: `ruff check app/` — 0 issues
- [ ] Frontend linter clean: `npx eslint src/` — 0 issues
- [ ] Frontend type check clean: `npx tsc --noEmit` — 0 errors
- [ ] No `console.log` or debug statements left in frontend source
- [ ] No `print()` or `breakpoint()` debug statements left in backend source
- [ ] `environment.useMockDag` is `false` (or removed) in committed environment files
- [ ] All acceptance criteria from `requirements.md` have a corresponding passing test or manual verification note
- [ ] **Dead code verification (mandatory):** `rg "hasUnsavedChanges|saveAllPositions|onReloadConfig|cancelAndRevert|isReverting|loadGraphData|unsavedPositions" web/src/app/features/settings/` returns **zero** matches
- [ ] **Dead code verification (mandatory):** `rg "hasUnsavedChangesChange" web/src/app/features/settings/` returns **zero** matches
- [ ] Toolbar has exactly **3 buttons** in the canvas action area: **Reload**, **Sync**, **Save & Reload** — no leftover `Cancel`, `Revert`, or old single "Save & Reload" button gated on `hasUnsavedChanges`
- [ ] `EdgesApiService` is **not imported** in `flow-canvas.component.ts`
- [ ] `loadGraphData()` method does **not exist** in `flow-canvas.component.ts`
- [ ] `onReloadConfig()` method does **not exist** in `settings.component.ts`
- [ ] `qa-report.md` is created and filled with final test run results and coverage summary
