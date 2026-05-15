# QA Tasks: Application Node Results Storage

> References: [`requirements.md`](./requirements.md) · [`technical.md`](./technical.md) · [`api-spec.md`](./api-spec.md)

---

## Phase 0: TDD Preparation (before dev starts)

- [ ] Write **failing** unit test stubs for `ResultsStorageService` (save, retrieve, delete, rollback)
- [ ] Write **failing** unit test stubs for `PcdParserService` (ASCII, binary, malformed)
- [ ] Confirm test runners execute (`pytest` for backend, `ng test` for frontend) before implementation begins

---

## Phase 1: Backend Unit Tests

- [ ] `ResultsStorageService.save_result` persists DB record and writes PCD file(s) to correct path
- [ ] `save_result` returns valid UUID4 result_id
- [ ] `get_result_detail` returns exact metadata and pcd_files list after save
- [ ] `delete_results_by_node` removes all DB records and `data/results/{node_id}/` directory
- [ ] DB rollback on simulated file write failure (no orphaned DB record, no partial directory)
- [ ] Concurrent saves to same `node_id` via `ThreadPoolExecutor` — no race conditions, distinct result dirs
- [ ] 50MB limit: `save_result` raises `ValueError` when PCD exceeds limit

---

## Phase 2: Backend Integration Tests

- [ ] `GET /api/v1/results` returns active application nodes with correct result counts
- [ ] `GET /api/v1/results/{node_id}` returns results newest-first; 404 for unknown node
- [ ] `GET /api/v1/results/{node_id}/{result_id}` returns full metadata + pcd_files; 404 for invalid id
- [ ] `GET /api/v1/results/{node_id}/{result_id}/pcd/{label}` returns binary PCD content; 404 for missing label
- [ ] `DELETE /api/v1/results/{node_id}/{result_id}` removes record and file; 404 for missing result
- [ ] Node deletion via orchestrator cascades: DB records + disk directory deleted, logged at INFO

---

## Phase 3: Frontend Unit Tests

- [ ] `ResultsApiService`: each HTTP method calls correct URL, maps response to model types
- [ ] `PcdParserService`: parse ASCII PCD → correct Float32Arrays; parse binary PCD → correct Float32Arrays
- [ ] `PcdParserService`: malformed header → throws `PcdParseError`, does not crash
- [ ] `MetadataTableComponent`: renders all scalar fields; collapses nested objects; handles empty `{}`
- [ ] `PcdViewerComponent`: on URL input change, fetches + parses + mutates geometry (no recreation); shows error on parse failure
- [ ] `ResultsOverviewComponent`: refresh button triggers new API call; empty state renders when list is `[]`
- [ ] `NodeResultsListComponent`: status badge maps correctly; breadcrumb shows node_name
- [ ] `ResultDetailComponent`: tab switch updates `activeLabel` Signal; metadata panel always visible

---

## Phase 4: E2E Tests

- [ ] Navigate: `/results` → click node card → `/results/{nodeId}` → click result row → `/results/{nodeId}/{resultId}`
- [ ] PCD viewer renders point cloud on detail page (no console errors)
- [ ] Tab switching on result with 3 PCDs changes rendered cloud
- [ ] Delete node via DAG editor → navigate to `/results/{deletedNodeId}` → shows "Node not found" error state
- [ ] Breadcrumb links navigate correctly at each level
- [ ] Invalid `resultId` in URL → 404 error state with back link

---

## Phase 5: Linter & Type Checks

- [ ] Backend: `ruff check app/` passes with zero errors
- [ ] Backend: `mypy app/` passes on `results_storage.py` and `results/router.py`
- [ ] Frontend: `ng lint` passes with zero errors
- [ ] Frontend: `ng build --configuration production` (no type errors)

---

## Phase 6: Pre-PR Verification (coordinate with devs)

- [ ] Confirm `@be-dev` has checked off all `backend-tasks.md` items
- [ ] Confirm `@fe-dev` has checked off all `frontend-tasks.md` items
- [ ] `pytest --tb=short` passes (backend unit + integration)
- [ ] `ng test --watch=false --code-coverage` passes (frontend)
- [ ] Coverage thresholds met: backend >80%, frontend >80%
- [ ] No console errors on full E2E flow in browser
- [ ] Manual smoke test: save a VolumeCalculation result, view it in the 3D viewer, delete the node, verify cleanup

---

## QA Report

> To be filled in after test execution → [`qa-report.md`](./qa-report.md)
