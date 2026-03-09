# Swagger API Documentation — Technical Blueprint

## 1. Overview

This document specifies the technical design for adding comprehensive OpenAPI 3.1 documentation
to the LiDAR Standalone FastAPI backend. The implementation is **entirely additive**: no business
logic is changed. All work targets `app/app.py` (FastAPI instance metadata), the nine REST router
files under `app/api/v1/`, and the introduction of a shared `app/api/v1/schemas/` package for
reusable response models that currently return raw `dict`.

---

## 2. Scope Boundary

### Covered (REST only)

| Router file         | Tag label       | URL prefix           |
|---------------------|-----------------|----------------------|
| `system.py`         | `System`        | `/api/v1/`           |
| `nodes.py`          | `Nodes`         | `/api/v1/nodes`      |
| `edges.py`          | `Edges`         | `/api/v1/edges`      |
| `config.py`         | `Configuration` | `/api/v1/config`     |
| `recordings.py`     | `Recordings`    | `/api/v1/recordings` |
| `logs.py`           | `Logs`          | `/api/v1/logs`       |
| `calibration.py`    | `Calibration`   | `/api/v1/calibration`|
| `lidar.py`          | `LiDAR`         | `/api/v1/lidar`      |
| `assets.py`         | `Assets`        | `/api/v1/assets`     |
| `websocket.py`      | `Topics`        | `/api/v1/topics`     |

> **`/api/metrics/*`** — No metrics router exists yet. The requirements reference the
> performance-monitoring feature plan, which has not shipped. These endpoints are deferred to
> that feature. The swagger-doc feature will include a placeholder comment in `app/app.py`
> reserving the `/api/metrics` prefix for when that router lands.

### Excluded by design

- **WebSocket endpoints** (`GET /ws/{topic}`, `GET /logs/ws`) — these cannot be described by
  OpenAPI REST schemas and are documented separately via the LIDR protocol specification.
- **Open3D types** — `numpy.ndarray` point-cloud payloads are never exposed as JSON schemas.
  The `LIDR` binary wire format remains documented only in `protocols.md`.
- **Static file mounts** (`/recordings/*`, SPA root `/`) — Starlette `StaticFiles` mounts are
  not FastAPI route objects and produce no OpenAPI entries.

---

## 3. FastAPI Application Metadata (`app/app.py`)

### 3.1 `FastAPI(...)` constructor enrichment

The existing minimal constructor must be replaced with a fully annotated one:

```python
app = FastAPI(
    title="LiDAR Standalone API",
    description="""
## LiDAR Standalone REST API

Real-time point-cloud processing pipeline REST interface.

> **Binary streaming** (point cloud XYZ data) is served over the `LIDR` binary WebSocket
> protocol documented separately. Only metadata and control operations are available here.

### Quick-start
1. Check system health: `GET /api/v1/status`
2. List available nodes: `GET /api/v1/nodes`
3. Start a recording: `POST /api/v1/recordings/start`
    """,
    version=settings.VERSION,        # reads "1.3.0" from Settings
    openapi_tags=OPENAPI_TAGS,        # see §3.2
    contact={
        "name": "LiDAR Standalone Team",
    },
    license_info={
        "name": "Proprietary",
    },
    lifespan=lifespan,
    # Preserve default /docs (Swagger UI) and /redoc endpoints — do not override
)
```

### 3.2 Tag Definitions (`OPENAPI_TAGS`)

Defined as a module-level constant in `app/app.py` before the `FastAPI` constructor call:

```python
OPENAPI_TAGS: list[dict] = [
    {
        "name": "System",
        "description": "Lifecycle control and health checks for the pipeline engine.",
    },
    {
        "name": "Nodes",
        "description": (
            "CRUD operations for DAG processing nodes. "
            "Node configurations are persisted in SQLite; "
            "the live engine reflects changes after reload."
        ),
    },
    {
        "name": "Edges",
        "description": (
            "Manage directed connections between DAG nodes. "
            "Edges define the data-flow topology of the processing pipeline."
        ),
    },
    {
        "name": "Configuration",
        "description": (
            "Full-graph import/export and validation. "
            "Allows backup and restore of the entire node-edge topology."
        ),
    },
    {
        "name": "Recordings",
        "description": (
            "Start, stop, list, and download point-cloud recordings. "
            "Recordings capture raw numpy point arrays from any active DAG node."
        ),
    },
    {
        "name": "Logs",
        "description": (
            "Access and stream application logs. "
            "REST endpoint returns paginated log entries; "
            "live streaming is available via the `GET /api/v1/logs/ws` WebSocket (not in REST docs)."
        ),
    },
    {
        "name": "Calibration",
        "description": (
            "ICP multi-sensor calibration. "
            "Trigger alignment computation, accept/reject results, "
            "and rollback to a previous calibration state."
        ),
    },
    {
        "name": "LiDAR",
        "description": (
            "SICK LiDAR device profiles and configuration validation. "
            "Pure in-memory operations — no database or file-system access."
        ),
    },
    {
        "name": "Assets",
        "description": "Static image assets served directly from the lidar module bundle.",
    },
    {
        "name": "Topics",
        "description": (
            "Introspection of registered WebSocket topics. "
            "Use `GET /api/v1/topics/capture` for a single-frame HTTP snapshot. "
            "Live streaming requires the `ws://` WebSocket endpoints (not in REST docs)."
        ),
    },
]
```

### 3.3 Swagger UI & ReDoc mount strategy

FastAPI enables `/docs` and `/redoc` **by default** when `openapi_url` is not explicitly set to
`None`. Because the SPA is mounted **last** with `StaticFiles(html=True)`, the SPA catch-all
**does not interfere** — FastAPI routes are registered before the static mount. No routing
changes are needed.

#### Risk: SPA 404 handler

The custom `StarletteHTTPException` handler already gates on `request.url.path.startswith("/api/")`.
Both `/docs` and `/redoc` paths do **not** start with `/api/`, so the handler would currently
serve the SPA `index.html` if the static directory exists and a 404 is raised.

**Resolution**: Extend the 404 gate to also exclude `/docs`, `/redoc`, and `/openapi.json`:

```python
PROTECTED_PREFIXES = ("/api/", "/recordings/", "/docs", "/redoc", "/openapi.json")

if not any(request.url.path.startswith(p) for p in PROTECTED_PREFIXES):
    # ... serve SPA index.html
```

This must be patched in the `custom_http_exception_handler` in `app/app.py`.

---

## 4. Router-Level Tag Assignment

Each `APIRouter()` constructor call in `app/api/v1/` must receive a `tags=[...]` kwarg.
Currently only `lidar.py` and `assets.py` set tags; the remaining routers do not.

| File             | Current `tags` | Required change                        |
|------------------|----------------|----------------------------------------|
| `system.py`      | _none_         | `tags=["System"]`                      |
| `nodes.py`       | _none_         | `tags=["Nodes"]`                       |
| `edges.py`       | _none_         | `tags=["Edges"]`                       |
| `config.py`      | _none_         | `tags=["Configuration"]`               |
| `recordings.py`  | _none_         | `tags=["Recordings"]`                  |
| `logs.py`        | _none_         | `tags=["Logs"]`                        |
| `calibration.py` | _none_         | `tags=["Calibration"]`                 |
| `lidar.py`       | `["lidar"]`    | Rename to `["LiDAR"]` (capitalisation) |
| `assets.py`      | `["assets"]`   | Rename to `["Assets"]` (capitalisation)|
| `websocket.py`   | _none_         | `tags=["Topics"]` on REST routes only  |

> WebSocket route `@router.websocket("/ws/{topic}")` does **not** accept a `tags` parameter and
> must be left untagged to keep it out of the REST OpenAPI schema.

---

## 5. Pydantic Model Coverage Audit & Gap Analysis

### 5.1 Already fully covered (request + response models exist)

| Router           | Models in place                                                                 |
|------------------|---------------------------------------------------------------------------------|
| `recordings.py`  | `StartRecordingRequest`, `RecordingResponse`, `ActiveRecordingResponse`, `ListRecordingsResponse` |
| `lidar.py`       | `SickLidarProfileResponse`, `ProfilesListResponse`, `LidarConfigValidationRequest`, `LidarConfigValidationResponse` |
| `calibration.py` | `TriggerCalibrationRequest`, `AcceptCalibrationRequest`, `RollbackRequest`      |
| `nodes.py`       | `NodeCreateUpdate`, `NodeStatusToggle`                                          |
| `edges.py`       | `EdgeCreateUpdate`                                                               |
| `config.py`      | `ConfigurationExport`, `ConfigurationImport`                                    |

### 5.2 Missing response models (return raw `dict` — OpenAPI shows `{}`)

These must be resolved to give Swagger meaningful schemas:

| Router          | Endpoint                          | Gap                                         | Fix                              |
|-----------------|-----------------------------------|---------------------------------------------|----------------------------------|
| `nodes.py`      | `GET /nodes`                      | Returns `list[dict]`                        | Add `response_model=list[NodeRecord]` |
| `nodes.py`      | `GET /nodes/{node_id}`            | Returns `dict`                              | Add `response_model=NodeRecord`  |
| `nodes.py`      | `POST /nodes`                     | Returns `{"status", "id"}`                 | Add `response_model=UpsertResponse` |
| `nodes.py`      | `PUT /nodes/{node_id}/enabled`    | Returns `{"status"}`                       | Add `response_model=StatusResponse` |
| `nodes.py`      | `DELETE /nodes/{node_id}`         | Returns `{"status"}`                       | Add `response_model=StatusResponse` |
| `nodes.py`      | `POST /nodes/reload`              | Returns `{"status"}`                       | Add `response_model=StatusResponse` |
| `nodes.py`      | `GET /nodes/status/all`           | Returns `{"nodes": [...]}`                 | Add `response_model=NodesStatusResponse` |
| `nodes.py`      | `GET /nodes/definitions`          | Returns `list[NodeDefinition]` (Pydantic ✓)| Add explicit `response_model`    |
| `edges.py`      | `GET /edges`                      | Returns `list[dict]`                        | Add `response_model=list[EdgeRecord]` |
| `edges.py`      | `POST /edges`                     | Returns `dict`                              | Add `response_model=EdgeRecord`  |
| `edges.py`      | `DELETE /edges/{edge_id}`         | Returns `{"status", "id"}`                 | Add `response_model=DeleteEdgeResponse` |
| `edges.py`      | `POST /edges/bulk`                | Returns `{"status"}`                       | Add `response_model=StatusResponse` |
| `system.py`     | `GET /status`                     | Returns `dict`                              | Add `response_model=SystemStatusResponse` |
| `system.py`     | `POST /start`                     | Returns `dict`                              | Add `response_model=SystemControlResponse` |
| `system.py`     | `POST /stop`                      | Returns `dict`                              | Add `response_model=SystemControlResponse` |
| `config.py`     | `GET /config/export`              | Returns `Response` (file)                   | Add `responses={200: {...}}` annotation |
| `config.py`     | `POST /config/import`             | Returns `dict`                              | Add `response_model=ImportResponse` |
| `config.py`     | `POST /config/validate`           | Returns `dict`                              | Add `response_model=ValidationResponse` |
| `logs.py`       | `GET /logs`                       | Returns `list[dict]`                        | Add `response_model=list[LogEntry]` |
| `calibration.py`| `POST /calibration/{id}/trigger`  | Returns `dict`                              | Add `response_model=CalibrationTriggerResponse` |
| `calibration.py`| `POST /calibration/{id}/accept`   | Returns `dict`                              | Add `response_model=AcceptResponse` |
| `calibration.py`| `POST /calibration/{id}/reject`   | Returns `dict`                              | Add `response_model=StatusResponse` |
| `calibration.py`| `GET /calibration/history/{id}`   | Returns `dict`                              | Add `response_model=CalibrationHistoryResponse` |
| `calibration.py`| `POST /calibration/rollback/{id}` | Returns `dict`                              | Add `response_model=RollbackResponse` |
| `calibration.py`| `GET /calibration/statistics/{id}`| Returns `dict`                              | Add `response_model=CalibrationStatsResponse` |
| `websocket.py`  | `GET /topics`                     | Returns `dict`                              | Add `response_model=TopicsResponse` |
| `assets.py`     | `GET /assets/lidar/`              | Returns `dict`                              | Add `response_model=ThumbnailListResponse` |

### 5.3 Open3D exclusion strategy

Endpoints that internally work with `numpy.ndarray` / Open3D objects (`recordings/{id}/frame/{idx}`,
`recordings/{id}/thumbnail`, `assets/lidar/{filename}`) return `FileResponse`. FastAPI
automatically annotates `FileResponse` routes with `content: application/octet-stream` or
`image/*`. No special handling needed — Pydantic schemas are never generated for binary responses.

---

## 6. Shared Schema Package (`app/api/v1/schemas/`)

A new package `app/api/v1/schemas/` will centralise cross-cutting response models to avoid
duplicate definitions:

```
app/api/v1/schemas/
├── __init__.py          # re-exports all public models
├── common.py            # StatusResponse, UpsertResponse, DeleteEdgeResponse
├── nodes.py             # NodeRecord, NodeStatusItem, NodesStatusResponse, NodeThrottleStats
├── edges.py             # EdgeRecord
├── system.py            # SystemStatusResponse, SystemControlResponse
├── config.py            # ImportResponse, ValidationResponse
├── logs.py              # LogEntry
└── calibration.py       # CalibrationTriggerResponse, AcceptResponse, RollbackResponse,
                         # CalibrationHistoryResponse, CalibrationStatsResponse
```

> `recordings.py` models (`RecordingResponse` etc.) already live in `app/api/v1/recordings.py`
> and are well-structured — they stay in place. `lidar.py` models stay in place similarly.
> `websocket.py` adds `TopicsResponse` inline (small enough not to warrant a dedicated file).
> `assets.py` adds `ThumbnailListResponse` and `ThumbnailItem` inline.

### 6.1 Key new model definitions

#### `common.py`
```python
class StatusResponse(BaseModel):
    status: str  # "success" | "error"

class UpsertResponse(BaseModel):
    status: str
    id: str

class DeleteEdgeResponse(BaseModel):
    status: str
    id: str
```

#### `nodes.py`
```python
class NodeRecord(BaseModel):
    id: str
    name: str
    type: str
    category: str
    enabled: bool
    config: Dict[str, Any] = {}
    x: Optional[float] = None
    y: Optional[float] = None

class NodeThrottleStats(BaseModel):
    throttle_ms: float = 0.0
    throttled_count: int = 0
    last_process_time: Optional[float] = None

class NodeStatusItem(BaseModel):
    id: str
    name: str
    type: str
    category: str
    enabled: bool
    running: bool
    topic: Optional[str] = None
    last_frame_at: Optional[float] = None
    frame_age_seconds: Optional[float] = None
    last_error: Optional[str] = None
    throttle_ms: float = 0.0
    throttled_count: int = 0

class NodesStatusResponse(BaseModel):
    nodes: List[NodeStatusItem]
```

#### `system.py`
```python
class SystemStatusResponse(BaseModel):
    is_running: bool
    active_sensors: List[str]
    version: str

class SystemControlResponse(BaseModel):
    status: str
    is_running: bool
```

#### `logs.py`
```python
class LogEntry(BaseModel):
    timestamp: str
    level: str
    module: str
    message: str
```

#### `calibration.py`
```python
class CalibrationResult(BaseModel):
    """Per-sensor ICP result."""
    fitness: Optional[float] = None
    rmse: Optional[float] = None
    quality: Optional[str] = None  # "good" | "acceptable" | "poor"

class CalibrationTriggerResponse(BaseModel):
    success: bool
    results: Dict[str, CalibrationResult]
    pending_approval: bool

class AcceptResponse(BaseModel):
    success: bool
    accepted: List[str]

class RollbackResponse(BaseModel):
    success: bool
    sensor_id: str
    restored_to: str   # ISO-8601 timestamp

class CalibrationRecord(BaseModel):
    id: str
    sensor_id: str
    timestamp: str
    accepted: bool
    fitness: Optional[float] = None
    rmse: Optional[float] = None

class CalibrationHistoryResponse(BaseModel):
    sensor_id: str
    history: List[CalibrationRecord]

class CalibrationStatsResponse(BaseModel):
    sensor_id: str
    total_attempts: int
    accepted_count: int
    avg_fitness: Optional[float] = None
    avg_rmse: Optional[float] = None
```

---

## 7. HTTP Status Code Annotation

FastAPI's `responses=` parameter on each route decorator will be used to document non-200
status codes. The developer must add structured `responses` dicts for all routes that raise
`HTTPException`. Standard pattern:

```python
@router.get(
    "/nodes/{node_id}",
    response_model=NodeRecord,
    responses={404: {"description": "Node not found"}},
)
```

### Status code matrix

| Group                  | Codes used                    |
|------------------------|-------------------------------|
| Success                | 200 OK                        |
| Client errors          | 400 Bad Request, 404 Not Found, 409 Conflict |
| Server / timeout       | 500 Internal Server Error, 503 Service Unavailable, 504 Gateway Timeout |

All `HTTPException` raises in the route handlers already match these codes — no logic changes.

---

## 8. Endpoint Summary Strings (`summary=` / `description=`)

Where an endpoint already has a docstring, FastAPI uses the first line as the summary and the
rest as the description. All routes that currently lack docstrings must receive them. Routes that
already have docstrings are verified to be clear and concise.

Incomplete docstring audit:

| File          | Route                           | Action required         |
|---------------|---------------------------------|-------------------------|
| `system.py`   | `POST /start`, `POST /stop`     | Add docstring           |
| `edges.py`    | `GET /edges`                    | Add docstring           |
| `nodes.py`    | `GET /nodes`, `GET /nodes/{id}` | Add docstring           |
| `nodes.py`    | `PUT /nodes/{id}/enabled`       | Add docstring           |
| `nodes.py`    | `DELETE /nodes/{id}`            | Existing inline comment → move to docstring |
| `logs.py`     | `GET /download`                 | Add docstring           |
| `websocket.py`| `GET /topics/capture`           | Add docstring           |

---

## 9. Examples Strategy

FastAPI propagates Pydantic model `model_config = ConfigDict(json_schema_extra={"examples": [...]})` 
or per-field `Field(examples=[...])` into the OpenAPI `example` block.

### Priority examples to add

| Model                      | Why it matters                                   |
|----------------------------|--------------------------------------------------|
| `NodeCreateUpdate`         | Complex nested `config: Dict` — one sensor example, one fusion example |
| `StartRecordingRequest`    | Show `node_id` UUID format                       |
| `LidarConfigValidationRequest` | Show multiScan vs tiM-5xx shape difference  |
| `ConfigurationImport`      | Full topology example (2 nodes, 1 edge)          |
| `TriggerCalibrationRequest`| Show `sample_frames` and optional sensor lists   |

Examples must use **concrete, realistic values** (valid UUIDs, valid IP ranges, real SICK model IDs).

---

## 10. Integration with Existing Lifecycle

`app/app.py` `lifespan` is not modified — it runs startup/shutdown as today. The OpenAPI schema
is generated lazily by FastAPI the first time `/openapi.json` is requested; this adds ~0ms to
application startup. No database calls, file I/O, or DAG operations are involved.

The CORS middleware (`allow_origins=["*"]`) already permits the Swagger UI (served from the same
origin in production and from `localhost` in development) to fetch `/openapi.json`. No changes
needed.

The `/recordings` `StaticFiles` mount and the SPA `StaticFiles` mount remain unchanged.

---

## 11. Non-Goals (Confirmed Exclusions)

- **No authentication layer** on `/docs` or `/redoc`.
- **No `openapi_url=None`** override; docs remain publicly accessible.
- **No custom CSS/JS** injection into Swagger UI.
- **No server URL list** (relies on FastAPI default of current host).
- **No `x-` vendor extensions** in the generated schema.
- **No `/api/metrics`** endpoints — deferred to the performance-monitoring feature.

---

## 12. File Change Summary

| File                              | Type of change                              |
|-----------------------------------|---------------------------------------------|
| `app/app.py`                      | Enrich `FastAPI(...)`, add `OPENAPI_TAGS`, patch 404 handler |
| `app/api/v1/system.py`            | Add `tags`, docstrings, `response_model`    |
| `app/api/v1/nodes.py`             | Add `tags`, docstrings, `response_model`, `responses` |
| `app/api/v1/edges.py`             | Add `tags`, docstrings, `response_model`, `responses` |
| `app/api/v1/config.py`            | Add `tags`, `response_model`, `responses`   |
| `app/api/v1/recordings.py`        | Add `tags`, `responses`, annotate `FileResponse` routes |
| `app/api/v1/logs.py`              | Add `tags`, docstrings, `response_model`    |
| `app/api/v1/calibration.py`       | Add `tags`, `response_model`, `responses`   |
| `app/api/v1/lidar.py`             | Rename tag to `"LiDAR"`, add `responses`    |
| `app/api/v1/assets.py`            | Rename tag to `"Assets"`, add `response_model`, `responses` |
| `app/api/v1/websocket.py`         | Add `tags` to REST routes only              |
| `app/api/v1/schemas/__init__.py`  | **New** — re-export package                 |
| `app/api/v1/schemas/common.py`    | **New** — shared simple models              |
| `app/api/v1/schemas/nodes.py`     | **New** — node record & status models       |
| `app/api/v1/schemas/edges.py`     | **New** — edge record model                 |
| `app/api/v1/schemas/system.py`    | **New** — system status models              |
| `app/api/v1/schemas/config.py`    | **New** — import/validate response models   |
| `app/api/v1/schemas/logs.py`      | **New** — log entry model                   |
| `app/api/v1/schemas/calibration.py` | **New** — calibration response models    |
