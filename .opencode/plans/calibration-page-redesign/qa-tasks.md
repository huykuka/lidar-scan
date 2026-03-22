# QA Tasks: Calibration Page Redesign

**Feature:** `calibration-page-redesign`
**References:** `technical.md`, `api-spec.md`, `backend-tasks.md`, `frontend-tasks.md`
**Agent:** `@qa`

> **Checkbox rule:** Mark `[x]` when a task is verified passing. Record failures with a note.
> **Ordering rule:** Sections 1 (TDD Prep) and 2 (Backend Tests) must be run before Sections 3–4 (Frontend).
> **Failure protocol:** If any task fails, file a note in `qa-report.md` and block the PR until resolved.

---

## Section 1: TDD Preparation (Before Development Starts)

These failing tests must exist **before** any feature code is written. This validates the TDD contract.

### Task 1.1 — Verify failing backend tests exist before implementation

- [ ] `tests/modules/test_calibration_node.py::test_get_calibration_status_idle` — fails before Task 3.1 is implemented
- [ ] `tests/modules/test_calibration_node.py::test_get_calibration_status_pending_quality_good` — fails before Task 3.1
- [ ] `tests/modules/test_calibration_node.py::test_get_calibration_status_pending_quality_bad` — fails before Task 3.1
- [ ] `tests/api/test_calibration_workflow.py` — all tests fail before Group 5 (endpoints) is implemented
- [ ] `tests/api/test_calibration_rollback.py::test_rollback_with_record_id` — fails before Task 4.2
- [ ] `tests/api/test_calibration_rollback.py::test_rollback_with_timestamp_returns_422` — fails before Task 4.1

**Note:** If tests files don't exist yet, co-ordinate with `@be-dev` to write them as shell tests (import + `assert False`) before implementation.

### Task 1.2 — Verify failing frontend unit tests exist before implementation

- [ ] `calibration-store.service.spec.ts` with `describe('startPolling')` test that fails before Task 3.3
- [ ] `calibration-viewer.component.spec.ts` with `it('calibrationNode should not be null on init')` test that fails before Task 5.1
- [ ] `node-calibration-controls.spec.ts` with `it('should not have triggerCalibration method')` that fails before Task 4.1

---

## Section 2: Backend Unit & Integration Tests

### Task 2.1 — Run and verify migration idempotency test

- [ ] **Command:** `python -c "from app.db.migrate import ensure_schema; from app.db.session import get_engine; e=get_engine(); ensure_schema(e); ensure_schema(e); print('OK')"`
- [ ] Expected: Prints `OK` with no errors on both calls
- [ ] Confirm all 5 new columns appear in the schema:
  - [ ] `node_id TEXT`
  - [ ] `accepted_at TEXT`
  - [ ] `accepted_by TEXT`
  - [ ] `rollback_source_id TEXT`
  - [ ] `registration_method_json TEXT DEFAULT 'null'`
- [ ] **Failure note:** If migration fails on re-run, the `if "col" not in cal_cols:` guard is missing or wrong

### Task 2.2 — Run `CalibrationHistoryModel.to_dict()` coverage

- [ ] **Command:** `pytest tests/ -k "calibration_model" -v`
- [ ] `to_dict()` returns all 5 new keys: `node_id`, `accepted_at`, `accepted_by`, `rollback_source_id`, `registration_method`
- [ ] `registration_method` is parsed from JSON (not raw string), returns `None` for legacy rows where column is `'null'`
- [ ] Legacy row with missing columns does not raise `KeyError` or `AttributeError`

### Task 2.3 — Run ORM function tests

- [ ] **Command:** `pytest tests/ -k "calibration_orm" -v`
- [ ] `create_calibration_record()` without new params → existing behavior unchanged
- [ ] `create_calibration_record()` with `node_id="n1"` → `node_id` persisted to DB
- [ ] `update_calibration_acceptance(db, record_id, True, accepted_at="2026-01-01T00:00:00Z")` → `accepted_at` set
- [ ] `get_calibration_history_by_node(db, "test-node")` → returns records sorted descending by timestamp
- [ ] `get_calibration_history(db, sensor_id, 10, run_id="abc")` → filters by `run_id`

### Task 2.4 — Run `CalibrationNode.get_calibration_status()` unit tests

- [ ] **Command:** `pytest tests/modules/test_calibration_node.py -k "get_calibration_status" -v`
- [ ] `calibration_state = "idle"` when `_pending_calibration is None`
- [ ] `quality_good = None` when no pending calibration
- [ ] `calibration_state = "pending"` when `_pending_calibration` has records
- [ ] `quality_good = True` when all records have `fitness >= min_fitness_to_save`
- [ ] `quality_good = False` when any record has `fitness < min_fitness_to_save`
- [ ] `buffered_frames` keys match sensor IDs in `_frame_buffer`
- [ ] `pending_results[sensor_id].pose_before` has keys: `x, y, z, roll, pitch, yaw`
- [ ] `pending_results[sensor_id].transformation_matrix` is a `4×4` list of lists

### Task 2.5 — Run API endpoint tests

- [ ] **Command:** `pytest tests/api/ -k "calibration" -v`
- [ ] `GET /api/v1/calibration/{node_id}/status` → 200 with `CalibrationNodeStatusResponse` shape
- [ ] `GET /api/v1/calibration/nonexistent/status` → 404
- [ ] `GET /api/v1/calibration/history/status` — must NOT match the `{node_id}` route (route ordering test)
  - *Expected: 200 for `/history/{sensor_id}` route, not `/status` confusion*
- [ ] `POST /api/v1/calibration/{node_id}/reject` → `{"success": true, "rejected": ["sensor-id"]}` shape
- [ ] `POST /api/v1/calibration/{node_id}/reject` (nothing pending) → `{"success": true, "rejected": []}` — not a 400
- [ ] `GET /api/v1/calibration/history/{sensor_id}?run_id=abc` → filtered by run_id
- [ ] `POST /api/v1/calibration/rollback/{sensor_id}` with `{"record_id": "abc"}` → 200 with `new_record_id`
- [ ] `POST /api/v1/calibration/rollback/{sensor_id}` with `{"timestamp": "..."}` → 422 (Pydantic validation error)

### Task 2.6 — Run full calibration workflow integration test

- [ ] **Command:** `pytest tests/api/test_calibration_workflow.py -v`
- [ ] Full sequence passes:
  1. Trigger → `pending_approval: true`
  2. Poll status → `calibration_state: "pending"`, `pending_results` non-empty
  3. Accept → `success: true`, `accepted` list non-empty
  4. Poll status → `calibration_state: "idle"`
  5. History → 1 accepted record with `accepted_at` set
  6. Rollback → `success: true`, `new_record_id` returned
  7. History → 2 records; rollback record has `rollback_source_id` set

### Task 2.7 — Verify `sample_frames` default unification

- [ ] **Command:** `pytest tests/api/ -k "trigger" -v`
- [ ] Triggering with no `sample_frames` param → uses `5` (not `1`)
- [ ] Confirm in `dto.py`: `TriggerCalibrationRequest.sample_frames = 5`
- [ ] Confirm in `calibration_node.py`: `params.get("sample_frames", 5)`

### Task 2.8 — Verify `accepted_at` is stamped on accept

- [ ] After accepting a calibration, query the DB record directly
- [ ] `record.accepted_at` is a valid ISO-8601 string (not `None`)
- [ ] `record.node_id` equals the calibration node's ID

---

## Section 3: Frontend Unit Tests

### Task 3.1 — Verify `CalibrationStoreService` unit tests

- [ ] **Command:** `ng test --include="**/calibration-store.service.spec.ts" --watch=false`
- [ ] `startPolling()` sets `pollingNodeId` signal
- [ ] `stopPolling()` clears `pollingNodeId` signal and `_pollTimer`
- [ ] `startPolling()` calls `_fetchStatus()` immediately (no 2s delay on first call)
- [ ] `triggerCalibration()` sets `isTriggering: true` during API call, `false` after
- [ ] `triggerCalibration()` sets `error` on API failure
- [ ] `acceptCalibration()` re-fetches status on success
- [ ] `rejectCalibration()` re-fetches status on success
- [ ] `rollbackHistory()` sets `isRollingBack: true` during call, `false` after
- [ ] `loadHistory()` updates `historyByNode` signal on success

### Task 3.2 — Verify `NodeCalibrationControls` has no action buttons

- [ ] **Command:** `ng test --include="**/node-calibration-controls.spec.ts" --watch=false`
- [ ] Component class has no `triggerCalibration()` method
- [ ] Component class has no `acceptCalibration()` method
- [ ] Component class has no `rejectCalibration()` method
- [ ] Template contains no `<syn-button>` with trigger/accept/reject labels
- [ ] Template contains `<syn-icon-button>` for navigation
- [ ] Template contains `<syn-badge>` for status display
- [ ] Clicking icon button calls `navigateToCalibration()`

### Task 3.3 — Verify `CalibrationViewerComponent` unit tests

- [ ] **Command:** `ng test --include="**/calibration-viewer.component.spec.ts" --watch=false`
- [ ] `calibrationNode` computed is NOT `null` after store is loaded with mock data
- [ ] `computePoseDelta()` returns correct Δ values: `dx = pose_after.x - pose_before.x`
- [ ] `toggleMatrix('sensor-1')` sets `showMatrixFor()['sensor-1'] = true`
- [ ] `ngOnDestroy()` calls `calibrationStore.stopPolling()`
- [ ] With `calibration_state: 'pending'`, pending results section renders
- [ ] With `calibration_state: 'idle'`, pending results section is hidden

### Task 3.4 — Verify `CalibrationHistoryDetailComponent` rollback tests

- [ ] **Command:** `ng test --include="**/calibration-history-detail.component.spec.ts" --watch=false`
- [ ] For `accepted = true` record: Rollback button renders
- [ ] For `accepted = false` record: Rollback button does NOT render
- [ ] Clicking Rollback button emits `rollback` output with the correct `record.id`
- [ ] `[disabled]="isRollingBack()"` disables the button when `isRollingBack = true`

### Task 3.5 — Verify model type shapes compile correctly

- [ ] **Command:** `tsc --noEmit -p web/tsconfig.json`
- [ ] Zero TypeScript errors in `calibration.model.ts`
- [ ] `CalibrationRollbackRequest` has `record_id`, NOT `timestamp`
- [ ] `CalibrationNodeStatusResponse` has all required fields
- [ ] `PendingCalibrationResult` has `pose_before` and `pose_after` of type `Pose`
- [ ] `CalibrationHistoryRecord` includes `accepted_at`, `node_id`, `rollback_source_id`

---

## Section 4: Frontend E2E & Integration Tests

### Task 4.1 — Verify calibration viewer page navigation and rendering

- [ ] Navigate to `/calibration` — list page renders without errors
- [ ] Each calibration node card shows:
  - [ ] Status badge (`Idle` or `Pending`)
  - [ ] Buffered frame counts
  - [ ] "Run Calibration" button
  - [ ] "View Details →" link
- [ ] Click "View Details" on a node → navigates to `/calibration/:id`
- [ ] No `calibrationNode is null` error in console
- [ ] Node name and status render correctly

### Task 4.2 — Verify Δ-pose table and matrix display

- [ ] Navigate to `/calibration/:id` with a node in `calibration_state: 'pending'`
  - (Use mock data: `MOCK_CALIBRATION_STATUS_PENDING`)
- [ ] Pending results section is visible
- [ ] Δ-pose table shows:
  - [ ] `Δx`, `Δy`, `Δz` labeled as `(mm)`
  - [ ] `Δroll`, `Δpitch`, `Δyaw` labeled as `(°)`
  - [ ] Values are numerically correct (e.g., `Δx = 2.30` for mock data)
- [ ] Fitness displays as percentage: `92.1%` (not `0.921`)
- [ ] RMSE displays with unit label: `0.00312 m`
- [ ] Clicking "Show Transformation Matrix" expands the 4×4 matrix
- [ ] Matrix is displayed as a table (not a raw JSON blob)

### Task 4.3 — Verify calibration workflow actions

- [ ] With backend running (or backend mock activated):
  - [ ] Click "Run Calibration" → button shows "Running..." while loading
  - [ ] After trigger, next poll (≤2s) updates the pending results section
  - [ ] Click "Accept Calibration" → button shows "Accepting..." while loading
  - [ ] After accept, `calibration_state` returns to `idle`, pending section disappears
  - [ ] Click "Reject" → pending section disappears, `calibration_state` returns to `idle`
- [ ] Error case: When API returns 4xx/5xx, toast notification appears

### Task 4.4 — Verify rollback workflow

- [ ] Navigate to `/calibration/:id` with history records in the store
- [ ] History section shows entries in descending order
- [ ] Accepted entries (`accepted: true`) show "Rollback to This" button
- [ ] Non-accepted entries do NOT show rollback button
- [ ] Click "Rollback to This" → button shows "Rolling back..." while loading
- [ ] After rollback, a toast confirmation appears
- [ ] Rollback request body is `{ "record_id": "..." }` — verify in Network tab (NOT `{ "timestamp": "..." }`)

### Task 4.5 — Verify DAG canvas calibration controls

- [ ] Open the Settings → Flow Canvas page
- [ ] Locate a calibration node on the canvas
- [ ] The node card shows:
  - [ ] Status badge only (`Idle` or `Pending`)
  - [ ] Navigation icon button (`open_in_new`)
  - [ ] **NO** Trigger button
  - [ ] **NO** Accept button
  - [ ] **NO** Reject button
- [ ] Clicking the icon button navigates to `/calibration/:id` correctly

### Task 4.6 — Verify polling starts and stops correctly

- [ ] Open Network tab
- [ ] Navigate to `/calibration/:id` — confirm `/api/v1/calibration/{id}/status` polling starts (request every ~2s)
- [ ] Navigate away from `/calibration/:id` — confirm polling stops (no more requests to `/status`)
- [ ] Navigate back — confirm polling restarts
- [ ] Open `/calibration` list page — confirm polling requests for all nodes (or just node 1 if single-poll limitation)

---

## Section 5: Linter & Type Checks

### Task 5.1 — Run backend linter

- [ ] **Command:** `ruff check app/ tests/`
- [ ] Zero linting errors in modified files:
  - `app/db/migrate.py`
  - `app/db/models.py`
  - `app/repositories/calibration_orm.py`
  - `app/modules/calibration/calibration_node.py`
  - `app/modules/calibration/history.py`
  - `app/api/v1/calibration/handler.py`
  - `app/api/v1/calibration/service.py`
  - `app/api/v1/calibration/dto.py`
  - `app/api/v1/schemas/calibration.py`

### Task 5.2 — Run backend type checker

- [ ] **Command:** `mypy app/ --ignore-missing-imports`
- [ ] Zero type errors in modified files listed in Task 5.1
- [ ] All new Pydantic models have full type annotations

### Task 5.3 — Run frontend linter

- [ ] **Command:** `ng lint` or `eslint web/src/app/... --ext .ts,.html`
- [ ] Zero lint errors in modified files:
  - `web/src/app/core/models/calibration.model.ts`
  - `web/src/app/core/services/api/calibration-api.service.ts`
  - `web/src/app/core/services/stores/calibration-store.service.ts` (new)
  - `web/src/app/features/settings/.../node-calibration-controls.ts`
  - `web/src/app/features/settings/.../node-calibration-controls.html`
  - `web/src/app/features/calibration/calibration.component.ts`
  - `web/src/app/features/calibration/components/calibration-viewer/*.ts`
  - `web/src/app/features/calibration/components/calibration-viewer/*.html`
  - `web/src/app/features/calibration/components/calibration-history-detail/*.ts`
  - `web/src/app/features/calibration/components/calibration-history-detail/*.html`

### Task 5.4 — Run frontend TypeScript type check

- [ ] **Command:** `tsc --noEmit -p web/tsconfig.json`
- [ ] Zero TypeScript errors across all modified files
- [ ] `CalibrationRollbackRequest.record_id` is `string` (not `timestamp`)

### Task 5.5 — Run frontend build

- [ ] **Command:** `ng build --configuration=production`
- [ ] Build completes with zero errors
- [ ] Bundle size diff is acceptable (new store + mock file should add < 10KB)

---

## Section 6: Pre-PR Verification

### Task 6.1 — Full test suite pass

- [ ] **Command (backend):** `pytest tests/ -v --tb=short`
- [ ] All tests pass. Zero failures.
- [ ] Test count: confirm new tests were added (Group 6 in `backend-tasks.md` = 3 new test files/sections)

- [ ] **Command (frontend):** `ng test --watch=false --browsers=ChromeHeadless`
- [ ] All tests pass. Zero failures.

### Task 6.2 — Developer sign-off

- [ ] `@be-dev` confirms all checkboxes in `backend-tasks.md` are `[x]`
- [ ] `@fe-dev` confirms all checkboxes in `frontend-tasks.md` are `[x]`

### Task 6.3 — Acceptance criteria cross-check

Verify all acceptance criteria from `requirements.md` are met:

- [ ] DAG canvas node card shows **zero** action buttons (only status badge + nav icon)
- [ ] `/calibration/:id` page is fully functional (no longer broken/null)
- [ ] Calibration can be triggered from both the list page and the detail page
- [ ] Δ-pose table shows correct units (mm, °, m, %) for all metric types
- [ ] 4×4 transformation matrix is expandable and labeled correctly
- [ ] Rollback is available for **any** accepted history entry (not just most recent)
- [ ] Rollback uses `record_id` (PK) not `timestamp` for reliable lookup
- [ ] `accepted_at` timestamp is persisted to DB when a calibration is accepted
- [ ] `node_id` is persisted to DB for each calibration history record
- [ ] New DB columns added without breaking existing rows (migration is idempotent)
- [ ] `sample_frames` defaults to `5` in both DTO and `CalibrationNode`
- [ ] Reject response returns `{ success, rejected: string[] }` (not legacy `{ status: "success" }`)

### Task 6.4 — Performance check (polling overhead)

- [ ] Confirm polling requests to `/api/v1/calibration/{node_id}/status` complete in < 100ms (typical case)
- [ ] Confirm polling stops cleanly on page navigation (no memory leak or orphaned intervals)
- [ ] Confirm polling does NOT fire when the `/calibration` route is not active

### Task 6.5 — Write `qa-report.md`

- [ ] Create `.opencode/plans/calibration-page-redesign/qa-report.md`
- [ ] Document:
  - Test run date and environment
  - Total tests run (backend + frontend)
  - Pass / fail counts
  - Any skipped tests and reason
  - Performance measurements (polling latency)
  - Sign-off statement
