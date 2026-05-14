# Backend Tasks: Application Node Results Storage

> References: [`requirements.md`](./requirements.md) · [`technical.md`](./technical.md) · [`api-spec.md`](./api-spec.md)

---

## Phase 1: Storage Service & DB

- [x] Create `app/services/results_storage.py` with `ResultsStorageService` class
  - [x] ~~Inline SQLite migration~~ → Schema managed by `app/db/migrate.py` (`ensure_schema`); `ApplicationResultModel` added to `app/db/models.py`
  - [x] `save_result(node_id, pcds: List[Tuple[str, o3d.geometry.PointCloud]], metadata, status)` → `str`
    - [x] Sanitize PCD labels (`re.sub(r'[^a-zA-Z0-9_-]', '_', label)`)
    - [x] `os.makedirs(data/results/{node_id}/{result_id}/)` atomically
    - [x] Write PCD files via `asyncio.to_thread(open3d.io.write_point_cloud, ...)` (binary, little-endian)
    - [x] ORM INSERT via `SessionLocal` in transaction (replaced raw `BEGIN IMMEDIATE`)
    - [x] On failure: `shutil.rmtree(result_dir, ignore_errors=True)` + re-raise
  - [x] `get_node_index()` → `List[NodeResultSummary]` (count + latest_ts per node_id)
  - [x] `get_results_by_node(node_id, limit, offset)` → `List[ResultSummary]` (metadata_summary = top-level scalars only)
  - [x] `get_result_detail(node_id, result_id)` → `ResultDetail`
  - [x] `delete_results_by_node(node_id)` → `int` (DB first, then `shutil.rmtree`, log errors but continue)
  - [x] `delete_result(node_id, result_id)` → `bool`
  - [x] `asyncio.Lock` per `node_id` for concurrent write safety (replaced `threading.Lock` to avoid event-loop deadlock)
  - [x] Log disk usage of `data/results/` at INFO on service startup
  - [x] Enforce 50MB per PCD file limit; raise `ValueError` if exceeded
- [x] Define Pydantic V2 schemas in `app/schemas/results.py`: `NodeResultSummary`, `ResultSummary`, `ResultDetail`, `PcdFileEntry`, `DeleteResultResponse`

## Phase 2: API Routes

- [x] Create router `app/api/v1/results/router.py`, mount at `/api/v1/results` in main app
- [x] `GET /api/v1/results` → calls `get_node_index()`, merges with active DAG application nodes (node_type filter)
- [x] `GET /api/v1/results/{node_id}` → `get_results_by_node()`, 404 if node unknown
- [x] `GET /api/v1/results/{node_id}/{result_id}` → `get_result_detail()`, 404 if not found
- [x] `GET /api/v1/results/{node_id}/{result_id}/pcd/{label}` → `FileResponse` (binary PCD), 404 if file missing; `StreamingResponse` for files >10MB
- [x] `DELETE /api/v1/results/{node_id}/{result_id}` → `delete_result()`, 404 if not found
- [x] Swagger annotations on all endpoints and response models

## Phase 3: Node Integration

- [x] Inject `ResultsStorageService` singleton into `VolumeCalculationNode` constructor
- [x] In `VolumeCalculationNode.on_input()`: after successful calculation, pre-color 3 PCDs (empty=blue, loaded=red, merged=green or domain scheme), call `save_result()`
- [x] Inject `ResultsStorageService` into `VehicleProfilerNode`, call `save_result()` with profile slice PCD + metadata
- [x] Document node integration pattern in a docstring on `ResultsStorageService.save_result()`

## Phase 4: Lifecycle Hook

- [x] In orchestrator node-delete path: call `await results_service.delete_results_by_node(node_id)`
- [x] Startup orphan sweep: scan `data/results/` subdirs not referenced in DB → log + delete

## Phase 5: Tests

- [x] `tests/unit/test_results_storage.py`:
  - [x] save → retrieve detail round-trip
  - [x] delete_results_by_node removes DB records and directory
  - [x] Rollback on simulated PCD write failure
  - [x] Concurrent saves to same node (asyncio.gather)
- [x] `tests/integration/test_results_api.py`:
  - [x] Full lifecycle via HTTP: POST result (via service) → GET list → GET detail → GET PCD → DELETE
  - [x] 404 on unknown node_id / result_id
  - [x] Node delete cascade via orchestrator integration

## Phase 7: Static File Serving

- [x] Mount `StaticFiles(directory="data")` at `/data` in `app/app.py` (after all API routes, before SPA)
- [x] `data/` directory created eagerly on startup (`mkdir parents=True, exist_ok=True`)
- [x] `/data/` added to `PROTECTED_PREFIXES` (SPA fallback bypass)
- [x] Sanity test: file written to `data/results/…` returns HTTP 200 via `/data/results/…` URL
- [x] Technical spec updated with static serving section

## Phase 6: Main DB Unification (Refactor)

- [x] `ApplicationResultModel` added to `app/db/models.py` with composite index `idx_results_node_ts`
- [x] `ensure_schema` in `app/db/migrate.py` creates table + backward-compat index guard
- [x] `ResultsStorageService` uses `SessionLocal` (main DB) — no separate `results.db`
- [x] Tests updated: fixtures use `DATABASE_URL` env var + `init_engine()` (no `db_path` param)
- [x] `asyncio.Lock` fix: concurrent saves no longer deadlock the event loop (16 unit + 12 integration tests pass)
