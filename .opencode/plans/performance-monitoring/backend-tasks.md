# Performance Monitoring — Backend Tasks

> **Owner**: `@be-dev`
> **References**: `requirements.md` · `technical.md` · `api-spec.md`
> **Rule**: Check off each task (`- [ ]` → `- [x]`) as it is completed. Do not skip tasks or merge unrelated changes.

---

## Dependencies & Ordering

```
[BE-01] MetricsRegistry
    └── [BE-02] IMetricsCollector + MetricsCollector + NullCollector
            └── [BE-03] Module-level singleton (instance.py)
                    ├── [BE-04] DAG routing instrumentation hook
                    ├── [BE-05] WebSocket broadcast instrumentation hook
                    ├── [BE-06] FastAPI middleware
                    ├── [BE-07] SystemProbe background task
                    └── [BE-08] Open3D async timer
                            └── [BE-09] MetricsBroadcaster background task
                                    └── [BE-10] REST API endpoints + router registration
                                            └── [BE-11] App lifespan integration
                                                    └── [BE-12] NullCollector guard + CLI flag
                                                            └── [BE-13] Tests
```

---

## Ticket Group 1 — Core Metrics Infrastructure

### BE-01 — MetricsRegistry Singleton

**File**: `app/services/metrics/registry.py`

**What to build**:
Create the `MetricsRegistry` class that holds all in-memory metric state. This is a pure data-holding class with no external I/O.

**Acceptance Criteria**:
- [x] Class `MetricsRegistry` defined with the following attributes:
  - `node_metrics: Dict[str, NodeMetricsSample]` — keyed by `node_id`
  - `ws_topic_metrics: Dict[str, WsTopicSample]` — keyed by topic name
  - `system_metrics: Optional[SystemMetricsSample]`
  - `endpoint_metrics: Dict[str, EndpointSample]` — keyed by `"{method}:{path}"`
- [x] `NodeMetricsSample` is a `dataclass` with fields: `node_id`, `node_name`, `node_type`, `last_exec_ms`, `exec_times_deque` (deque maxlen=60), `calls_total`, `last_point_count`, `last_seen_ts`, `throttled_count`
  - `avg_exec_ms` is a `@property` computing the mean of `exec_times_deque`
  - `throughput_pps` stored as float, updated externally each 1-sec window
- [x] `WsTopicSample` is a `dataclass` with fields: `topic`, `messages_window` (deque maxlen=60 of `(ts, byte_size)` tuples), `total_messages`, `total_bytes`, `active_connections`
  - `messages_per_sec` and `bytes_per_sec` are `@property` computed over the last 1-sec window
- [x] `SystemMetricsSample` is a `dataclass` with fields matching `api-spec.md §4.6`
- [x] `EndpointSample` is a `dataclass` with fields: `path`, `method`, `latency_times_deque` (deque maxlen=60), `calls_total`, `last_status_code`
  - `avg_latency_ms` is a `@property` computing the mean of `latency_times_deque`
- [x] `MetricsRegistry` has a `snapshot() -> MetricsSnapshotModel` method that serializes the current state into a Pydantic `MetricsSnapshotModel` (see BE-10)
- [x] `MetricsRegistry` has a `reset()` method for testing
- [x] All fields use strict Python type hints (Pydantic V2 compatible)
- [x] `app/services/metrics/__init__.py` created, exports `MetricsRegistry`

**References**: `technical.md §3.1`, `api-spec.md §4`

---

### BE-02 — IMetricsCollector Protocol + MetricsCollector + NullMetricsCollector

**Files**:
- `app/services/metrics/collector.py`
- `app/services/metrics/null_collector.py`

**What to build**:
Define the `IMetricsCollector` Protocol and two concrete implementations.

**Acceptance Criteria**:
- [x] `IMetricsCollector` defined as a `typing.Protocol` with these exact method signatures:
  ```python
  def record_node_exec(self, node_id: str, node_name: str, node_type: str, exec_ms: float, point_count: int) -> None: ...
  def record_ws_message(self, topic: str, byte_size: int) -> None: ...
  def record_ws_connections(self, topic: str, count: int) -> None: ...
  def record_endpoint(self, path: str, method: str, latency_ms: float, status_code: int) -> None: ...
  def snapshot(self) -> "MetricsSnapshotModel": ...
  def is_enabled(self) -> bool: ...
  ```
- [x] `MetricsCollector` class implements `IMetricsCollector`:
  - Holds a `MetricsRegistry` instance
  - `record_node_exec()` updates `registry.node_metrics[node_id]`, creating entry if not present; appends `exec_ms` to `exec_times_deque`; increments `calls_total`; updates `last_point_count` and `last_seen_ts`
  - `record_ws_message()` appends `(time.monotonic(), byte_size)` to `registry.ws_topic_metrics[topic].messages_window`; increments `total_messages` and `total_bytes`
  - `record_ws_connections()` sets `active_connections` for the topic
  - `record_endpoint()` appends `latency_ms` to `registry.endpoint_metrics[key].latency_times_deque`; increments `calls_total`
  - `snapshot()` delegates to `registry.snapshot()`
  - `is_enabled()` returns `True`
- [x] `NullMetricsCollector` implements `IMetricsCollector` with all methods as no-ops:
  - `snapshot()` returns a valid empty `MetricsSnapshotModel` with zero values
  - `is_enabled()` returns `False`
- [x] No locks or threading primitives used — all operations are GIL-protected dict/list mutations (acceptable for this use case)
- [x] All methods use strict type hints

**References**: `technical.md §3.2`, `api-spec.md §4`

---

### BE-03 — Module-Level Singleton

**File**: `app/services/metrics/instance.py`

**What to build**:
Module-level singleton accessor, mirroring the pattern used by `app/services/nodes/instance.py`.

**Acceptance Criteria**:
- [x] File defines `_collector: IMetricsCollector = NullMetricsCollector()` at module level
- [x] `get_metrics_collector() -> IMetricsCollector` function returns the active collector
- [x] `set_metrics_collector(collector: IMetricsCollector) -> None` function replaces the active collector (called at startup)
- [x] Exported from `app/services/metrics/__init__.py`

**References**: `technical.md §3.2`

---

## Ticket Group 2 — Instrumentation Hook Points

### BE-04 — DAG Routing Instrumentation

**File**: `app/services/nodes/managers/routing.py` (modify)

**What to build**:
Add a single, minimal instrumentation call inside the existing `_send_to_target_node()` method.

**Acceptance Criteria**:
- [x] Import `get_metrics_collector` from `app.services.metrics.instance` (lazy import inside the method to avoid circular imports)
- [x] In `_send_to_target_node()`, record start time with `time.monotonic_ns()` before `await target_node.on_input(payload)`
- [x] After `on_input()` returns, compute `exec_ms = (time.monotonic_ns() - t0) / 1_000_000.0`
- [x] Call `get_metrics_collector().record_node_exec(target_id, node_name, node_type, exec_ms, point_count)` where:
  - `node_name = getattr(target_node, 'name', target_id)`
  - `node_type = getattr(target_node, 'type', 'unknown')`
  - `point_count = len(payload.get('points', []))` if `'points'` key exists, else `0`
- [x] The instrumentation is **outside the try/except** for the `on_input()` call so that errors in instrumentation don't suppress node errors
- [x] The instrumentation adds **no new exception paths** — wrap the entire `record_node_exec()` call in a `try/except Exception` that only logs a debug-level warning if instrumentation itself fails
- [x] Existing behavior of `_send_to_target_node()` is completely unchanged

**References**: `technical.md §3.3`, `requirements.md — Backend Monitoring`

---

### BE-05 — WebSocket Broadcast Instrumentation

**File**: `app/services/websocket/manager.py` (modify)

**What to build**:
Track message counts and byte sizes per topic inside the existing `broadcast()` method.

**Acceptance Criteria**:
- [x] Import `get_metrics_collector` lazily inside `broadcast()`
- [x] After a successful `send_bytes()` or `send_json()` (inside the `_send()` closure), call `get_metrics_collector().record_ws_message(topic, byte_size)` where `byte_size = len(msg) if isinstance(msg, bytes) else len(json.dumps(msg).encode())`
- [x] In `connect()`, after `await websocket.accept()`, call `get_metrics_collector().record_ws_connections(topic, len(self.active_connections[topic]))`
- [x] In `disconnect()`, after removing the websocket, call `get_metrics_collector().record_ws_connections(topic, len(self.active_connections.get(topic, [])))`
- [x] `"system_metrics"` added to the `SYSTEM_TOPICS` set so it does not appear in `/ws/topics`
- [x] All instrumentation wrapped in `try/except` — errors must not affect broadcast delivery

**References**: `technical.md §3.3`, `api-spec.md §4.4`

---

### BE-06 — FastAPI Endpoint Latency Middleware

**File**: `app/middleware/metrics_middleware.py` (new)

**What to build**:
A `BaseHTTPMiddleware` that measures endpoint latency for `/api/**` routes only.

**Acceptance Criteria**:
- [x] Class `MetricsMiddleware(BaseHTTPMiddleware)` defined
- [x] `async def dispatch(self, request: Request, call_next)`:
  - Skip instrumentation if `not request.url.path.startswith("/api/")` — call `call_next()` directly
  - Record `t0 = time.monotonic_ns()`
  - `await call_next(request)`
  - Compute `latency_ms`
  - Call `get_metrics_collector().record_endpoint(path, method, latency_ms, status_code)`
- [x] Middleware is registered in `app/app.py` via `app.add_middleware(MetricsMiddleware)` — must be added **before** CORS middleware in the chain
- [x] Any exception in the instrumentation code must not swallow the original HTTP response

**References**: `technical.md §3.3`

---

### BE-07 — System Metrics Probe

**File**: `app/services/metrics/system_probe.py` (new)

**What to build**:
Background asyncio task that collects OS-level metrics at 2 Hz.

**Acceptance Criteria**:
- [x] `async def _system_probe_loop(registry: MetricsRegistry, stop_event: asyncio.Event)` coroutine:
  - Loops until `stop_event` is set
  - Every 500ms: calls `psutil.cpu_percent(interval=None)`, `psutil.virtual_memory()`, `threading.active_count()`, and reads `node_manager.data_queue.qsize()`
  - Updates `registry.system_metrics` with a fresh `SystemMetricsSample`
  - Uses `await asyncio.wait_for(stop_event.wait(), timeout=0.5)` pattern (same as `status_broadcaster`)
- [x] `start_system_probe(registry: MetricsRegistry) -> None` function that creates the task and stores it in a module-level var
- [x] `stop_system_probe() -> None` function
- [x] `psutil` is imported lazily inside the probe function to avoid hard dependency at module load
- [x] The probe loop catches and logs all exceptions without crashing

**References**: `technical.md §3.3`, `requirements.md — Monitor system CPU, memory, thread pool usage`

---

### BE-08 — Open3D Async Timer Context Manager

**File**: `app/services/metrics/open3d_timer.py` (new)

**What to build**:
An async context manager that times Open3D operations run via `asyncio.to_thread()`.

**Acceptance Criteria**:
- [x] `open3d_timer(operation_name: str, node_id: str)` implemented as an `asynccontextmanager`
- [x] Records wall-clock time of the block using `time.monotonic_ns()`
- [x] On exit, stores the result into `MetricsRegistry.node_metrics[node_id]` under an `open3d_ops` sub-dict: `{operation_name: {"last_ms": float, "avg_ms": float, "calls": int}}`
- [x] If the `node_id` does not yet have a `NodeMetricsSample`, the context manager creates a minimal placeholder entry
- [x] The context manager **does not suppress exceptions** from the wrapped block
- [x] Usage example in docstring matching `technical.md §3.3`

**References**: `technical.md §3.3`, `requirements.md — Monitor Open3D operation times`

---

## Ticket Group 3 — Broadcasting & API

### BE-09 — MetricsBroadcaster Background Task

**File**: `app/services/metrics/broadcaster.py` (new)

**What to build**:
Background task that pushes `MetricsSnapshot` to the `system_metrics` WebSocket topic at 1 Hz. Must follow the exact architecture of `app/services/status_broadcaster.py`.

**Acceptance Criteria**:
- [x] `async def _metrics_broadcast_loop(stop_event: asyncio.Event)` coroutine:
  - Registers `"system_metrics"` topic via `manager.register_topic("system_metrics")`
  - Loops until `stop_event` is set at configurable interval (`METRICS_BROADCAST_HZ` env var, default `1`)
  - Calls `get_metrics_collector().snapshot()` → serializes via `.model_dump()` → calls `await manager.broadcast("system_metrics", payload_dict)`
  - Uses `await asyncio.wait_for(stop_event.wait(), timeout=1.0/hz)` pattern
  - Catches and logs all exceptions without crashing
- [x] `start_metrics_broadcaster() -> None` function (module-level `_broadcast_task` pattern)
- [x] `stop_metrics_broadcaster() -> None` function
- [x] If `get_metrics_collector().is_enabled()` is `False`, the loop skips broadcast silently (does not error)

**References**: `technical.md §3.4`, `api-spec.md §2`

---

### BE-10 — Pydantic V2 Response Models + REST API Router

**Files**:
- `app/services/metrics/models.py` (new)
- `app/api/v1/metrics.py` (new)
- `app/api/v1/__init__.py` (modify — register router)

**What to build**:
All Pydantic V2 response models and the REST endpoints defined in `api-spec.md`.

**Acceptance Criteria — `models.py`**:
- [x] `DagNodeMetricsModel(BaseModel)` with all fields from `api-spec.md §4.3` using strict Python type hints
- [x] `DagMetricsModel(BaseModel)` wrapping a list of `DagNodeMetricsModel`
- [x] `WsTopicMetricsModel(BaseModel)` — `api-spec.md §4.5`
- [x] `WebSocketMetricsModel(BaseModel)` — `api-spec.md §4.4`
- [x] `SystemMetricsModel(BaseModel)` — `api-spec.md §4.6`
- [x] `EndpointMetricsModel(BaseModel)` — `api-spec.md §4.7`
- [x] `MetricsSnapshotModel(BaseModel)` — root envelope from `api-spec.md §4.1`
- [x] `PerformanceHealthModel(BaseModel)` — `api-spec.md §3.4` response
- [x] All models use `model_config = ConfigDict(from_attributes=True)`

**Acceptance Criteria — `metrics.py` router**:
- [x] `router = APIRouter(prefix="/metrics", tags=["metrics"])`
- [x] `GET /metrics` → returns `MetricsSnapshotModel`; raises `HTTPException(503)` if metrics disabled
- [x] `GET /metrics/dag` → returns `DagMetricsModel` subset
- [x] `GET /metrics/websocket` → returns `WebSocketMetricsModel` subset
- [x] `GET /health/performance` → always returns `PerformanceHealthModel` (never 503, even when disabled)
- [x] All endpoints are `async def` and use FastAPI dependency injection for the metrics collector (no direct singleton access in route handlers — inject via `Depends`)
- [x] Router registered in `app/api/v1/__init__.py` under the existing `/api` prefix

**References**: `api-spec.md §3`, `technical.md §3.5`, `backend.md — Pydantic V2 models`

---

## Ticket Group 4 — Integration & Configuration

### BE-11 — App Lifespan Integration

**File**: `app/app.py` (modify)

**What to build**:
Wire all new services into the FastAPI application lifespan, following the existing `status_broadcaster` pattern exactly.

**Acceptance Criteria**:
- [x] Import and call `start_metrics_broadcaster()` in the `lifespan` startup block, **after** `start_status_broadcaster()`
- [x] Import and call `stop_metrics_broadcaster()` in the `lifespan` shutdown block, **before** `stop_status_broadcaster()`
- [x] Import and call `start_system_probe(registry)` in startup, `stop_system_probe()` in shutdown
- [x] `MetricsMiddleware` registered with `app.add_middleware(MetricsMiddleware)` before CORS
- [x] The `set_metrics_collector(MetricsCollector(registry))` or `set_metrics_collector(NullMetricsCollector())` call happens at startup based on the `LIDAR_ENABLE_METRICS` env var check

**References**: `technical.md §9`, `technical.md §3.6`

---

### BE-12 — NullCollector Guard & Configuration

**File**: `app/core/config.py` (modify)

**What to build**:
Add the configuration flag that gates metrics collection.

**Acceptance Criteria**:
- [x] `LIDAR_ENABLE_METRICS: bool = True` added to the `Settings` Pydantic model, populated from env var `LIDAR_ENABLE_METRICS` (default `True`)
- [x] `settings.LIDAR_ENABLE_METRICS` used in `app.py` to select `MetricsCollector` vs `NullMetricsCollector`
- [x] `--enable-metrics` CLI argument documented in `app/main.py` docstring or startup log

**References**: `technical.md §3.6`, `requirements.md — Collection must introduce <1% overhead`

---

## Ticket Group 5 — Tests

### BE-13 — Unit & Integration Tests

**Directory**: `tests/` (new files)

**What to build**:
Automated tests covering the metrics pipeline. No load testing required here (that is `@qa`'s responsibility).

**Acceptance Criteria**:
- [x] `tests/test_metrics_registry.py`:
  - [x] `test_record_node_exec_creates_entry()` — calling `record_node_exec()` with a new node_id creates a `NodeMetricsSample`
  - [x] `test_avg_exec_ms_rolling_window()` — verify that `avg_exec_ms` correctly averages the last 60 samples, discarding older ones
  - [x] `test_ws_metrics_per_second_windowing()` — verify `messages_per_sec` only counts messages in the last 1-sec window
  - [x] `test_snapshot_serialization()` — `registry.snapshot()` returns a valid `MetricsSnapshotModel` with no validation errors
  - [x] `test_null_collector_is_enabled()` — `NullMetricsCollector().is_enabled()` returns `False`
  - [x] `test_null_collector_snapshot_is_valid()` — `NullMetricsCollector().snapshot()` returns empty but valid `MetricsSnapshotModel`

- [x] `tests/test_metrics_endpoints.py` (using FastAPI `TestClient`):
  - [x] `test_get_metrics_returns_200_when_enabled()` — with real `MetricsCollector`, endpoint returns `200`
  - [x] `test_get_metrics_returns_503_when_disabled()` — with `NullMetricsCollector`, `GET /api/metrics` returns `503`
  - [x] `test_health_performance_always_200()` — `GET /api/health/performance` returns `200` regardless of collector type
  - [x] `test_dag_endpoint_schema()` — response validates against `DagMetricsModel`
  - [x] `test_websocket_endpoint_schema()` — response validates against `WebSocketMetricsModel`

- [x] `tests/test_metrics_broadcaster.py`:
  - [x] `test_broadcaster_does_not_crash_on_null_collector()` — start broadcaster with `NullMetricsCollector`, verify no exception raised in 2 broadcast cycles
  - [x] `test_broadcaster_serializes_snapshot()` — mock `manager.broadcast`, verify the JSON payload matches `MetricsSnapshotModel` schema

**References**: `requirements.md — Collection must introduce <1% overhead`, `api-spec.md §7`

---

## Summary Checklist

| # | Task | Status |
|---|---|---|
| BE-01 | MetricsRegistry + dataclasses | - [x] |
| BE-02 | IMetricsCollector + MetricsCollector + NullCollector | - [x] |
| BE-03 | Module-level singleton `instance.py` | - [x] |
| BE-04 | DAG routing instrumentation hook | - [x] |
| BE-05 | WebSocket broadcast instrumentation | - [x] |
| BE-06 | FastAPI endpoint latency middleware | - [x] |
| BE-07 | SystemProbe background task | - [x] |
| BE-08 | Open3D async timer context manager | - [x] |
| BE-09 | MetricsBroadcaster background task | - [x] |
| BE-10 | Pydantic models + REST API router | - [x] |
| BE-11 | App lifespan integration | - [x] |
| BE-12 | Config flag + NullCollector guard | - [x] |
| BE-13 | Unit & integration tests | - [x] |
