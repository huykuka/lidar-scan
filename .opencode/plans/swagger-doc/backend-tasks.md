# Swagger API Documentation — Backend Tasks

> **Feature**: `swagger-doc`  
> **Refs**: [`requirements.md`](requirements.md) · [`technical.md`](technical.md) · [`api-spec.md`](api-spec.md)  
> **Assignee**: `@be-dev`

All tasks are **pure documentation annotations** — no business logic is modified.
Check off each box (`[ ]` → `[x]`) as work completes.

---

## Task Overview

This document outlines the specific implementation tasks required to add comprehensive Swagger/OpenAPI documentation to the LiDAR Standalone backend. All tasks follow the technical architecture defined in `technical.md` and API specification in `api-spec.md`.

---

## Phase 0 — Scaffolding

- [x] **0.1** Create the `app/api/v1/schemas/` package directory with an empty `__init__.py`
- [ ] **0.2** Verify `app/api/v1/__init__.py` does not need changes (router assembly is already correct)

---

## Phase 1 — Shared Schema Models

> All new files land in `app/api/v1/schemas/`.

- [x] **1.1** Create `app/api/v1/schemas/common.py`
  - `StatusResponse(BaseModel)` — `status: str`
  - `UpsertResponse(BaseModel)` — `status: str`, `id: str`
  - `DeleteEdgeResponse(BaseModel)` — `status: str`, `id: str`

- [x] **1.2** Create `app/api/v1/schemas/nodes.py`
  - `NodeRecord(BaseModel)` — `id`, `name`, `type`, `category`, `enabled`, `config: Dict[str, Any]`, `x: Optional[float]`, `y: Optional[float]`
  - `NodeStatusItem(BaseModel)` — `id`, `name`, `type`, `category`, `enabled`, `running`, `topic: Optional[str]`, `last_frame_at: Optional[float]`, `frame_age_seconds: Optional[float]`, `last_error: Optional[str]`, `throttle_ms: float = 0.0`, `throttled_count: int = 0`
  - `NodesStatusResponse(BaseModel)` — `nodes: List[NodeStatusItem]`
  - Add `model_config` with `json_schema_extra` example on `NodeRecord`

- [x] **1.3** Create `app/api/v1/schemas/edges.py`
  - `EdgeRecord(BaseModel)` — `id: str`, `source_node: str`, `source_port: str`, `target_node: str`, `target_port: str`

- [x] **1.4** Create `app/api/v1/schemas/system.py`
  - `SystemStatusResponse(BaseModel)` — `is_running: bool`, `active_sensors: List[str]`, `version: str`
  - `SystemControlResponse(BaseModel)` — `status: str`, `is_running: bool`

- [x] **1.5** Create `app/api/v1/schemas/config.py`
  - `ImportSummary(BaseModel)` — `nodes: int`, `edges: int`
  - `ImportResponse(BaseModel)` — `success: bool`, `mode: str`, `imported: ImportSummary`, `node_ids: List[str]`, `reloaded: bool`
  - `ConfigValidationSummary(BaseModel)` — `nodes: int`, `edges: int`
  - `ValidationResponse(BaseModel)` — `valid: bool`, `errors: List[str]`, `warnings: List[str]`, `summary: ConfigValidationSummary`

- [x] **1.6** Create `app/api/v1/schemas/logs.py`
  - `LogEntry(BaseModel)` — `timestamp: str`, `level: str`, `module: str`, `message: str`

- [x] **1.7** Create `app/api/v1/schemas/calibration.py`
  - `CalibrationResult(BaseModel)` — `fitness: Optional[float]`, `rmse: Optional[float]`, `quality: Optional[str]`
  - `CalibrationTriggerResponse(BaseModel)` — `success: bool`, `results: Dict[str, CalibrationResult]`, `pending_approval: bool`
  - `AcceptResponse(BaseModel)` — `success: bool`, `accepted: List[str]`
  - `RollbackResponse(BaseModel)` — `success: bool`, `sensor_id: str`, `restored_to: str`
  - `CalibrationRecord(BaseModel)` — `id: str`, `sensor_id: str`, `timestamp: str`, `accepted: bool`, `fitness: Optional[float]`, `rmse: Optional[float]`
  - `CalibrationHistoryResponse(BaseModel)` — `sensor_id: str`, `history: List[CalibrationRecord]`
  - `CalibrationStatsResponse(BaseModel)` — `sensor_id: str`, `total_attempts: int`, `accepted_count: int`, `avg_fitness: Optional[float]`, `avg_rmse: Optional[float]`

- [x] **1.8** Populate `app/api/v1/schemas/__init__.py` to re-export all public models from the sub-modules above

---

## Phase 2 — `app/app.py` — FastAPI Metadata & 404 Fix

- [ ] **2.1** Define `OPENAPI_TAGS: list[dict]` constant at module level (before `FastAPI(...)`) with all 10 tag objects per `technical.md §3.2`
- [ ] **2.2** Enrich `FastAPI(...)` constructor:
  - Set `title`, `description` (multi-line markdown with quick-start), `version`, `openapi_tags`, `contact`, `license_info`
  - Keep `lifespan=lifespan` — do **not** set `openapi_url=None` (preserve default docs)
- [ ] **2.3** Add `PROTECTED_PREFIXES` tuple and update `custom_http_exception_handler` so 404s for `/docs`, `/redoc`, and `/openapi.json` fall through to the JSON error response instead of serving the SPA

---

## Phase 3 — `system.py` Router Annotations

- [ ] **3.1** Add `tags=["System"]` to `router = APIRouter()`
- [ ] **3.2** `GET /status` — add `response_model=SystemStatusResponse`
- [ ] **3.3** `POST /start` — add `response_model=SystemControlResponse` and a one-line docstring
- [ ] **3.4** `POST /stop` — add `response_model=SystemControlResponse` and a one-line docstring

---

## Phase 4 — `nodes.py` Router Annotations

- [ ] **4.1** Add `tags=["Nodes"]` to `router = APIRouter()`
- [ ] **4.2** `GET /nodes` — add `response_model=list[NodeRecord]` and docstring
- [ ] **4.3** `GET /nodes/definitions` — add `response_model=list[NodeDefinition]` (already imported from `services.nodes.schema`)
- [ ] **4.4** `GET /nodes/{node_id}` — add `response_model=NodeRecord`, `responses={404: {"description": "Node not found"}}`, and docstring
- [ ] **4.5** `POST /nodes` — add `response_model=UpsertResponse`
- [ ] **4.6** `PUT /nodes/{node_id}/enabled` — add `response_model=StatusResponse` and docstring
- [ ] **4.7** `DELETE /nodes/{node_id}` — add `response_model=StatusResponse`, `responses={404: {"description": "Node not found"}}`
- [ ] **4.8** `POST /nodes/reload` — add `response_model=StatusResponse`, `responses={409: {"description": "Reload in progress"}}`
- [ ] **4.9** `GET /nodes/status/all` — add `response_model=NodesStatusResponse`
- [ ] **4.10** Add `model_config` example to `NodeCreateUpdate` (one sensor example, one fusion example per `technical.md §9`)

---

## Phase 5 — `edges.py` Router Annotations

- [ ] **5.1** Add `tags=["Edges"]` to `router = APIRouter()`
- [ ] **5.2** `GET /edges` — add `response_model=list[EdgeRecord]` and docstring
- [ ] **5.3** `POST /edges` — add `response_model=EdgeRecord`
- [ ] **5.4** `DELETE /edges/{edge_id}` — add `response_model=DeleteEdgeResponse` and docstring
- [ ] **5.5** `POST /edges/bulk` — add `response_model=StatusResponse`

---

## Phase 6 — `config.py` Router Annotations

- [ ] **6.1** Add `tags=["Configuration"]` to `router = APIRouter()`
- [ ] **6.2** `GET /config/export` — annotate with `responses={200: {"description": "Downloadable JSON file", "content": {"application/json": {}}}}` (raw `Response` — no Pydantic `response_model`)
- [ ] **6.3** `POST /config/import` — add `response_model=ImportResponse`, `responses={400: {"description": "Invalid configuration"}}`
- [ ] **6.4** `POST /config/validate` — add `response_model=ValidationResponse`
- [ ] **6.5** Add `model_config` example to `ConfigurationImport` (2-node, 1-edge example per `api-spec.md`)

---

## Phase 7 — `recordings.py` Router Annotations

- [ ] **7.1** Add `tags=["Recordings"]` to `router = APIRouter()`
- [ ] **7.2** `POST /recordings/start` — add `responses={400: ..., 404: ..., 500: ...}`; add example to `StartRecordingRequest` model
- [ ] **7.3** `POST /recordings/{recording_id}/stop` — add `responses={404: ..., 500: ...}`
- [ ] **7.4** `GET /recordings` — already has `response_model=ListRecordingsResponse` ✓; confirm `responses={}` documented
- [ ] **7.5** `GET /recordings/{recording_id}` — already has `response_model=RecordingResponse` ✓; add `responses={404: ...}`
- [ ] **7.6** `DELETE /recordings/{recording_id}` — add `responses={404: ...}`
- [ ] **7.7** `GET /recordings/{recording_id}/download` — add `responses={200: {"content": {"application/octet-stream": {}}}, 404: ...}`
- [ ] **7.8** `GET /recordings/{recording_id}/info` — confirm docstring is present ✓
- [ ] **7.9** `GET /recordings/{recording_id}/frame/{frame_index}` — add `responses={400: ..., 404: ..., 500: ...}`
- [ ] **7.10** `GET /recordings/{recording_id}/thumbnail` — add `responses={200: {"content": {"image/png": {}}}, 404: ...}`

---

## Phase 8 — `logs.py` Router Annotations

- [ ] **8.1** Add `tags=["Logs"]` to `router = APIRouter()`
- [ ] **8.2** `GET /logs` — add `response_model=list[LogEntry]` and verify return type annotation
- [ ] **8.3** `GET /download` — add docstring and `responses={200: {"content": {"text/plain": {}}}, 404: ...}`
- [ ] **8.4** Ensure `@router.websocket("/logs/ws")` has **no** `tags` kwarg (exclude from REST docs)

---

## Phase 9 — `calibration.py` Router Annotations

- [ ] **9.1** Add `tags=["Calibration"]` to `router = APIRouter()`
- [ ] **9.2** `POST /calibration/{node_id}/trigger` — add `response_model=CalibrationTriggerResponse`, `responses={400: ..., 404: ..., 500: ...}`
- [ ] **9.3** `POST /calibration/{node_id}/accept` — add `response_model=AcceptResponse`, `responses={400: ..., 404: ...}`
- [ ] **9.4** `POST /calibration/{node_id}/reject` — add `response_model=StatusResponse`, `responses={404: ...}`
- [ ] **9.5** `GET /calibration/history/{sensor_id}` — add `response_model=CalibrationHistoryResponse`, `responses={500: ...}`
- [ ] **9.6** `POST /calibration/rollback/{sensor_id}` — add `response_model=RollbackResponse`, `responses={400: ..., 404: ..., 500: ...}`
- [ ] **9.7** `GET /calibration/statistics/{sensor_id}` — add `response_model=CalibrationStatsResponse`, `responses={500: ...}`
- [ ] **9.8** Add example to `TriggerCalibrationRequest` model (per `api-spec.md`)

---

## Phase 10 — `lidar.py` Router Annotations

- [ ] **10.1** Rename `tags=["lidar"]` → `tags=["LiDAR"]` on `router = APIRouter(...)` (capitalisation matches tag definition)
- [ ] **10.2** Both endpoints already have `response_model` ✓; add `responses={400: ..., 404: ...}` where applicable
- [ ] **10.3** Add `model_config` example to `LidarConfigValidationRequest` (show multiScan vs tiM-5xx shape)

---

## Phase 11 — `assets.py` Router Annotations

- [ ] **11.1** Rename `tags=["assets"]` → `tags=["Assets"]` on `router = APIRouter(...)`
- [ ] **11.2** `GET /assets/lidar/` — add inline `ThumbnailItem` and `ThumbnailListResponse` models; add `response_model=ThumbnailListResponse`, `responses={500: ...}`
- [ ] **11.3** `GET /assets/lidar/{filename}` — add `responses={200: {"content": {"image/png": {}}}, 400: ..., 404: ...}`

---

## Phase 12 — `websocket.py` REST Route Annotations

- [ ] **12.1** Add `tags=["Topics"]` to `router = APIRouter()` — only REST routes receive this tag; `@router.websocket(...)` is unaffected
- [ ] **12.2** `GET /topics` — add inline `TopicsResponse` model and `response_model=TopicsResponse`
- [ ] **12.3** `GET /topics/capture` — add docstring, `responses={200: {"content": {"application/octet-stream": {}}}, 503: ..., 504: ...}`

---

## Phase 13 — Verification & Smoke Test

- [ ] **13.1** Start the development server: `python main.py` (or `uvicorn app.app:app --reload`)
- [ ] **13.2** Navigate to `http://localhost:8005/docs` — verify Swagger UI loads with all 10 tag groups visible
- [ ] **13.3** Navigate to `http://localhost:8005/redoc` — verify ReDoc renders all endpoints
- [ ] **13.4** Navigate to `http://localhost:8005/openapi.json` — verify JSON schema is valid (no 404 or SPA redirect)
- [ ] **13.5** For each tag group, verify at least one endpoint shows a correct request/response schema in Swagger UI
- [ ] **13.6** Confirm `GET /api/v1/nodes/status/all` shows `NodesStatusResponse` schema (not `{}`)
- [ ] **13.7** Confirm `POST /api/v1/nodes/reload` shows `409` in the Responses section
- [ ] **13.8** Confirm `GET /api/v1/recordings/{id}/frame/{frame_index}` does **not** expose any Open3D type in its schema
- [ ] **13.9** Confirm `GET /api/v1/logs/ws` does **not** appear under any tag in Swagger UI
- [ ] **13.10** Confirm `GET /api/v1/ws/{topic}` does **not** appear under any tag in Swagger UI
- [ ] **13.11** Run existing test suite — confirm zero regressions: `pytest tests/ -q`
- [ ] **13.12** Check that the SPA still loads at `/` in a browser (static mount not broken)

---

## Dependencies & Order

```
Phase 0
  └── Phase 1 (schemas package must exist before routers import it)
        ├── Phase 2 (app.py metadata — independent of routers)
        ├── Phase 3–12 (router annotations — can proceed in parallel once Phase 1 is done)
              └── Phase 13 (verification — requires all prior phases complete)
```

> Phases 3–12 have no inter-dependencies and can be distributed across parallel work streams.

---

## Pre-PR Checklist

- [ ] All `response_model` annotations compile without `ImportError`
- [ ] `GET /openapi.json` returns HTTP 200 with valid JSON
- [ ] No new Pyright/mypy errors introduced by schema models
- [ ] `pytest tests/ -q` passes with 0 failures
- [ ] Swagger UI (`/docs`) and ReDoc (`/redoc`) both load and show all 10 tag groups
- [ ] No Open3D types appear in any generated schema
- [ ] WebSocket endpoints absent from REST documentation