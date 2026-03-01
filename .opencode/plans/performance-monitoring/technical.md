# Performance Monitoring — Technical Blueprint

> **Role**: Architecture Reference for `@be-dev` and `@fe-dev`
> **Status**: Design — do not modify without Architect review
> **Relates to**: `requirements.md`, `api-spec.md`

---

## 1. Guiding Principles

| Principle | Rationale |
|---|---|
| **Zero-copy instrumentation** | Metrics are collected from existing execution paths via lightweight wrappers; no separate processes or heavy frameworks. |
| **Session-only, in-memory** | No persistence. All metric state lives in a singleton `MetricsRegistry`; it resets when the process restarts. |
| **<1% overhead budget** | All collection paths use atomic counters, `time.monotonic_ns()`, and lock-free ring buffers. No synchronous I/O in the hot path. |
| **Decoupled by interface** | Backend emits metrics through a stable `IMetricsCollector` interface. Frontend consumes through a dedicated `MetricsApiService` and `MetricsWebSocketService`. Neither side knows about the other's implementation. |
| **No third-party monitoring stack** | No Prometheus, StatsD, OpenTelemetry, or Grafana. This is a self-contained developer tool. |

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  BACKEND  (Python / FastAPI)                                            │
│                                                                         │
│  ┌──────────────┐   wrap   ┌────────────────────────────────────────┐  │
│  │ DAG Routing  │ ───────► │  MetricsCollector (singleton)          │  │
│  │ (routing.py) │          │  - NodeMetrics ring buffer (per node)  │  │
│  └──────────────┘          │  - Open3DMetrics ring buffer           │  │
│                            │  - WebSocketMetrics atomic counters    │  │
│  ┌──────────────┐   wrap   │  - SystemMetrics (psutil)              │  │
│  │ ModuleNode   │ ───────► │  - FastAPI endpoint latency            │  │
│  │ on_input()   │          └────────────────┬───────────────────────┘  │
│  └──────────────┘                           │                           │
│                                             │ read (non-blocking)       │
│  ┌──────────────┐          ┌────────────────▼───────────────────────┐  │
│  │ WS Manager   │ ───────► │  MetricsBroadcaster (background task)  │  │
│  │ broadcast()  │          │  - 1 Hz JSON push to "system_metrics"  │  │
│  └──────────────┘          │    WS topic                            │  │
│                            └────────────────────────────────────────┘  │
│                                                                         │
│  REST endpoints (stateless snapshot reads from MetricsCollector):       │
│  GET /api/metrics          GET /api/metrics/dag                         │
│  GET /api/metrics/websocket  GET /api/health/performance               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │  JSON over WS (topic: system_metrics)
                                    │  JSON over HTTP (REST snapshots)
┌─────────────────────────────────────────────────────────────────────────┐
│  FRONTEND  (Angular 20 / Three.js)                                      │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  MetricsWebSocketService  (RxJS Observable, reconnecting)         │ │
│  │  Parses JSON → writes to MetricsStore (Signal-based)              │ │
│  └───────────────────────────┬────────────────────────────────────────┘ │
│                              │ signals                                   │
│  ┌───────────────────────────▼────────────────────────────────────────┐ │
│  │  MetricsStore  (Angular Signals)                                   │ │
│  │  dagMetrics / wsMetrics / systemMetrics / frontendMetrics (signals)│ │
│  └───────┬──────────────────────────┬─────────────────────────────────┘ │
│          │                          │                                    │
│  ┌───────▼──────────┐   ┌───────────▼──────────────────────────────┐   │
│  │ ThreeJsMetrics   │   │  PerformanceDashboard Feature             │   │
│  │ Collector        │   │  /dashboard/performance (lazy route)      │   │
│  │ (requestAnimFrame│   │  Smart component reads MetricsStore       │   │
│  │  hook inside     │   │  Dumb panel components receive @Input()   │   │
│  │  PointCloud      │   └──────────────────────────────────────────┘   │
│  │  component)      │                                                   │
│  └──────────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Backend — Detailed Design

### 3.1 MetricsRegistry (`app/services/metrics/registry.py`)

A **singleton** that holds all in-memory metric state. Zero external dependencies. All state is plain Python dicts and `collections.deque` (fixed maxlen = 300 samples, ~5 min at 1 Hz).

```
MetricsRegistry
├── node_metrics: Dict[node_id, NodeMetricsSample]   (latest snapshot per node)
├── ws_metrics: WebSocketMetricsSample               (rolling atomic counters)
├── system_metrics: SystemMetricsSample              (last psutil reading)
└── endpoint_metrics: Dict[path, EndpointMetricsSample]
```

`NodeMetricsSample` fields (collected per `forward_data()` call):
- `last_exec_time_ms: float` — wall-clock time of the node's `on_input()` call
- `avg_exec_time_ms: float` — rolling 60-sample average
- `calls_total: int` — monotonically increasing counter
- `throughput_pps: float` — points per second (last interval)
- `queue_depth: int` — current data_queue size
- `last_point_count: int`
- `last_seen_ts: float`
- `throttled_count: int` — forwarded from existing `ThrottleManager`

### 3.2 MetricsCollector Interface (`app/services/metrics/collector.py`)

Thin **protocol class** (Python `Protocol`) — the only contract that DAG code calls:

```python
class IMetricsCollector(Protocol):
    def record_node_exec(self, node_id: str, exec_ms: float, point_count: int) -> None: ...
    def record_ws_message(self, topic: str, byte_size: int) -> None: ...
    def record_endpoint(self, path: str, latency_ms: float, status_code: int) -> None: ...
    def snapshot(self) -> MetricsSnapshot: ...
```

A `NullMetricsCollector` (no-ops) is always available so the system runs cleanly when metrics are disabled. The active collector is injected via `app/services/metrics/instance.py` (module-level singleton, same pattern as `node_manager`).

### 3.3 Instrumentation Hook Points

#### DAG Routing (`app/services/nodes/managers/routing.py`)

In `_send_to_target_node()`, wrap the `await target_node.on_input(payload)` call:

```
t0 = time.monotonic_ns()
await target_node.on_input(payload)
exec_ms = (time.monotonic_ns() - t0) / 1e6
metrics_collector.record_node_exec(target_id, exec_ms, len(payload.get("points", [])))
```

This is the **single instrumentation point** for all DAG node execution timing. It does not touch `ModuleNode` directly, preserving the decoupling rule.

#### WebSocket Broadcast (`app/services/websocket/manager.py`)

In `broadcast()`, after `send_bytes()` / `send_json()`:
```
metrics_collector.record_ws_message(topic, len(msg_bytes))
```

#### FastAPI Middleware (`app/middleware/metrics_middleware.py`)

A thin `BaseHTTPMiddleware` subclass measures request/response latency for `/api/**` routes only. Non-API paths (static, SPA) are excluded.

#### System Metrics (`app/services/metrics/system_probe.py`)

A standalone background coroutine (`asyncio.create_task`) runs at **2 Hz**. Calls `psutil.cpu_percent(interval=None)`, `psutil.virtual_memory()`, and reads `threading.active_count()`. This is the **only psutil call**; it is never in the hot path.

#### Open3D Metrics

Open3D operations run inside `asyncio.to_thread()`. Each node that calls Open3D wraps the call in a context manager from `app/services/metrics/open3d_timer.py`:

```python
async with open3d_timer("voxel_downsample", node_id):
    result = await asyncio.to_thread(o3d.geometry.PointCloud.voxel_down_sample, ...)
```

The context manager records wall-clock time and operation name into the `MetricsRegistry`.

### 3.4 MetricsBroadcaster (`app/services/metrics/broadcaster.py`)

Follows the **same architecture pattern** as `status_broadcaster.py`:
- Started in `app/app.py` lifespan alongside `status_broadcaster`
- Runs in a background `asyncio.Task` at **1 Hz** (configurable via env var `METRICS_BROADCAST_HZ`, default 1)
- Calls `metrics_collector.snapshot()` → serializes to JSON → calls `manager.broadcast("system_metrics", payload)`
- Registers `"system_metrics"` as a system topic in `SYSTEM_TOPICS` set in `websocket/manager.py`
- Uses the same start/stop pattern: `start_metrics_broadcaster()` / `stop_metrics_broadcaster()`

### 3.5 REST Snapshot Endpoints (`app/api/v1/metrics.py`)

All REST endpoints are **read-only, stateless snapshots** of the `MetricsRegistry`:

| Endpoint | Returns |
|---|---|
| `GET /api/metrics` | Full `MetricsSnapshot` (all subsystems) |
| `GET /api/metrics/dag` | `dag` sub-object only (per-node array) |
| `GET /api/metrics/websocket` | `websocket` sub-object |
| `GET /api/health/performance` | Health check: boolean flags, version |

All endpoints return Pydantic V2 models. No path parameters needed — data is the current in-memory state.

### 3.6 Configuration Guard

`--enable-metrics` CLI flag (or env var `LIDAR_ENABLE_METRICS=true`) controls whether the real `MetricsCollector` or the `NullMetricsCollector` is injected at startup. The default in development is **enabled**; the default in production builds is **disabled** (zero overhead).

---

## 4. Frontend — Detailed Design

### 4.1 MetricsWebSocketService (`web/src/app/core/services/metrics-websocket.service.ts`)

Mirrors the existing `StatusWebSocketService` pattern:
- Opens WebSocket to `ws://{apiBase}/ws/system_metrics`
- Binary type: `text` (JSON messages, not binary LIDR frames)
- Parses incoming JSON → calls `MetricsStore.update(payload)`
- Handles reconnection with exponential backoff (same logic as `StatusWebSocketService`)
- Exposes `connected = signal<boolean>(false)`

**RxJS** is used **only** for the WebSocket message stream (an `Observable<MetricsSnapshot>` from the raw `WebSocket.onmessage` event). The parsed data is then pushed into Angular Signals.

### 4.2 MetricsStore (`web/src/app/core/services/stores/metrics-store.service.ts`)

Signal-based store. Follows the `signals-simple-store.service.ts` pattern already in the codebase:

```typescript
// Writable internals
readonly #dagMetrics = signal<DagMetricsPayload | null>(null);
readonly #wsMetrics = signal<WsMetricsPayload | null>(null);
readonly #systemMetrics = signal<SystemMetricsPayload | null>(null);
readonly #frontendMetrics = signal<FrontendMetricsPayload | null>(null);

// Public read-only views
readonly dagMetrics = this.#dagMetrics.asReadonly();
readonly wsMetrics = this.#wsMetrics.asReadonly();
readonly systemMetrics = this.#systemMetrics.asReadonly();
readonly frontendMetrics = this.#frontendMetrics.asReadonly();

// Derived/computed signals
readonly totalPointsPerSec = computed(() => ...);
readonly worstNodeLatency = computed(() => ...);
```

The `update(snapshot: MetricsSnapshot)` method is the single write entry point, called by `MetricsWebSocketService`.

### 4.3 ThreeJsMetricsCollector

A lightweight class **instantiated inside `PointCloudComponent`** (not a service — it's local to the rendering context):

```typescript
class ThreeJsMetricsCollector {
  private lastFrameTime = performance.now();
  private frameTimes: number[] = [];   // ring buffer, maxlen=60

  recordFrame(renderTimeMs: number): void { ... }
  getSnapshot(): FrontendMetricsPayload { ... }
}
```

The `animate()` method in `PointCloudComponent` records:
1. Time between `requestAnimationFrame` callbacks → **FPS**
2. Time for `this.renderer.render(scene, camera)` → **render time per frame**
3. Time for `positions.set(subarray)` in `updatePointsForTopic()` → **buffer mutation time**

The `PointCloudComponent` exposes an `output()` signal: `metricsEmit = output<FrontendMetricsPayload>()`, fired every 60 frames (~1 sec). The parent smart component (workspace) receives this and calls `MetricsStore.updateFrontend(payload)`.

### 4.4 Angular Component Responsiveness Metrics

Uses the **`PerformanceObserver` API** (Web standard) inside a dedicated Angular service `ComponentPerfService`:
- Observes `"longtask"` entries (tasks >50ms blocking the main thread)
- Records count and duration per 1-sec interval
- Pushes into `MetricsStore.updateFrontend()`

This is **passive observation** — zero instrumentation code in component templates.

### 4.5 WebSocket Client Metrics

`MultiWebsocketService` is extended to count:
- Frames received per topic per second
- Bytes received per topic per second
- Parse latency (from `onmessage` timestamp to DataView decode completion)

These are tracked in a `Map<topic, ClientWsStats>` inside the service and pushed to `MetricsStore` periodically via a `setInterval(1000)`.

### 4.6 Performance Dashboard Feature (`/dashboard/performance`)

**Route**: lazy-loaded, added to `app.routes.ts` as a child of the main layout.
**Guard**: no auth required in dev builds, protected by a `isDevelopment` route guard in production.

Directory: `web/src/app/features/dashboard/`

```
dashboard/
├── dashboard.component.ts           (Smart — reads MetricsStore signals)
├── dashboard.component.html
├── components/
│   ├── dag-overview-panel/          (Dumb — @Input() nodes: DagNodeMetrics[])
│   ├── dag-node-detail-panel/       (Dumb — @Input() node: DagNodeMetrics)
│   ├── websocket-panel/             (Dumb — @Input() wsMetrics)
│   ├── system-panel/                (Dumb — @Input() sysMetrics)
│   ├── rendering-panel/             (Dumb — @Input() frontendMetrics)
│   └── metric-gauge/                (Reusable Synergy UI wrapper)
```

**Synergy UI** components used:
- `syn-card` for each metric panel
- `syn-badge` for status indicators (healthy / degraded / critical)
- `syn-progress` for CPU/memory gauges
- `syn-tag` for node type labels
- Standard HTML `<table>` with Tailwind for DAG node table

**No charting library** — no historical data means sparklines/charts are meaningless. Metrics are shown as current values + rolling average badges.

---

## 5. Data Flow Diagram

```
Sensor Worker Process
      │ multiprocessing.Queue
      ▼
NodeManager._queue_listener()
      │ asyncio.create_task
      ▼
DataRouter.handle_incoming_data()
      │
      ▼
ModuleNode.on_input(payload)          ◄─── t0 = monotonic_ns()
      │                                         │
      │ forward_data(node_id, result)     exec_ms recorded
      ▼                                 metrics_collector.record_node_exec()
DataRouter.forward_data()
      │
      ├─► _broadcast_to_websocket()    ◄─── metrics_collector.record_ws_message()
      │       └── pack_points_binary()
      │           └── manager.broadcast(topic, binary)
      │
      └─► _forward_to_downstream_nodes()  (recursive)

Background (2 Hz):
  SystemProbe.collect() → MetricsRegistry.system_metrics

Background (1 Hz):
  MetricsBroadcaster
    └── MetricsRegistry.snapshot()
        └── manager.broadcast("system_metrics", json)
                │
                ▼ WebSocket JSON
           MetricsWebSocketService (Angular)
                │ parse JSON
                ▼
           MetricsStore.update(snapshot)
                │ signals
                ▼
           PerformanceDashboard components
```

---

## 6. Data Schemas

All schemas are defined both as Pydantic V2 models (backend) and TypeScript interfaces (frontend). They are authoritative in `api-spec.md`.

### 6.1 MetricsSnapshot (top-level envelope)

```
{
  "timestamp": float,          // Unix epoch seconds
  "dag": DagMetrics,
  "websocket": WebSocketMetrics,
  "system": SystemMetrics,
  "endpoints": EndpointMetrics[]
}
```

### 6.2 DagNodeMetrics (per node)

```
{
  "node_id": string,
  "node_name": string,
  "node_type": string,
  "last_exec_ms": float,
  "avg_exec_ms": float,
  "calls_total": int,
  "throughput_pps": float,
  "last_point_count": int,
  "throttled_count": int,
  "queue_depth": int,
  "last_seen_ts": float
}
```

### 6.3 WebSocketMetrics

```
{
  "topics": {
    "<topic_name>": {
      "messages_per_sec": float,
      "bytes_per_sec": float,
      "active_connections": int,
      "total_messages": int,
      "total_bytes": int
    }
  },
  "total_connections": int
}
```

### 6.4 SystemMetrics

```
{
  "cpu_percent": float,
  "memory_used_mb": float,
  "memory_total_mb": float,
  "memory_percent": float,
  "thread_count": int,
  "queue_depth": int          // multiprocessing.Queue current size
}
```

### 6.5 FrontendMetrics (client-side only, not sent to backend)

```typescript
{
  fps: number,
  avg_render_ms: number,
  avg_buffer_mutation_ms: number,
  long_task_count: number,
  ws_frames_per_sec: Record<string, number>,
  ws_parse_latency_ms: Record<string, number>
}
```

---

## 7. Key Integration Points & Decoupling Contracts

| Contract | Owner | Consumed By |
|---|---|---|
| `IMetricsCollector` protocol | `@be-dev` | All DAG instrumentation points |
| `MetricsSnapshot` Pydantic model | `@be-dev` | REST endpoints, WS broadcaster |
| `GET /api/metrics*` REST shape | `api-spec.md` | `@fe-dev` (mock during dev) |
| `system_metrics` WS topic JSON | `api-spec.md` | `MetricsWebSocketService` |
| `MetricsStore` signal API | `@fe-dev` | Dashboard smart component |
| `FrontendMetricsPayload` TS interface | `@fe-dev` | `ThreeJsMetricsCollector`, `ComponentPerfService` |
| `metricsEmit output()` on `PointCloudComponent` | `@fe-dev` | Parent workspace component |

---

## 8. Performance Budget & Overhead Analysis

| Component | Overhead Mechanism | Budget |
|---|---|---|
| `record_node_exec()` | 2× `time.monotonic_ns()` + dict write | ~200 ns/call |
| `record_ws_message()` | 1 atomic int increment + dict write | ~50 ns/call |
| `SystemProbe` at 2 Hz | `psutil` call every 500ms | Negligible |
| `MetricsBroadcaster` at 1 Hz | JSON serialize + WS send | ~1 ms/sec total |
| `ThreeJsMetricsCollector` | `performance.now()` in rAF loop | ~0.05ms/frame |
| `PerformanceObserver` | Browser native API, passive | ~0 |

At 100Hz sensor input (10ms intervals), instrumentation adds **~400 ns per frame** = **0.004% overhead**. Well within the <1% budget.

---

## 9. File Map — New Files to Create

### Backend
```
app/
├── services/
│   └── metrics/
│       ├── __init__.py
│       ├── registry.py         # MetricsRegistry singleton state
│       ├── collector.py        # IMetricsCollector protocol + MetricsCollector impl
│       ├── null_collector.py   # NullMetricsCollector (no-ops)
│       ├── instance.py         # Module-level singleton (get_metrics_collector())
│       ├── broadcaster.py      # MetricsBroadcaster background task
│       ├── system_probe.py     # SystemMetrics collection via psutil
│       └── open3d_timer.py     # Async context manager for Open3D timing
├── api/
│   └── v1/
│       └── metrics.py          # REST endpoints router
└── middleware/
    └── metrics_middleware.py   # FastAPI BaseHTTPMiddleware for endpoint latency
```

### Frontend
```
web/src/app/
├── core/
│   ├── models/
│   │   └── metrics.model.ts        # All TS interfaces for metrics data shapes
│   └── services/
│       ├── metrics-websocket.service.ts
│       ├── component-perf.service.ts
│       └── stores/
│           └── metrics-store.service.ts
└── features/
    └── dashboard/
        ├── dashboard.component.ts
        ├── dashboard.component.html
        └── components/
            ├── dag-overview-panel/
            │   ├── dag-overview-panel.component.ts
            │   └── dag-overview-panel.component.html
            ├── dag-node-detail-panel/
            │   ├── dag-node-detail-panel.component.ts
            │   └── dag-node-detail-panel.component.html
            ├── websocket-panel/
            │   ├── websocket-panel.component.ts
            │   └── websocket-panel.component.html
            ├── system-panel/
            │   ├── system-panel.component.ts
            │   └── system-panel.component.html
            ├── rendering-panel/
            │   ├── rendering-panel.component.ts
            │   └── rendering-panel.component.html
            └── metric-gauge/
                ├── metric-gauge.component.ts
                └── metric-gauge.component.html
```

### Modified Files
```
app/app.py                          # Add start/stop MetricsBroadcaster + SystemProbe in lifespan
app/services/websocket/manager.py   # Add "system_metrics" to SYSTEM_TOPICS
app/services/nodes/managers/routing.py  # Add record_node_exec() instrumentation hook
app/api/v1/__init__.py              # Register metrics router
web/src/app/app.routes.ts           # Add /dashboard/performance lazy route
web/src/app/layout/main-layout/     # Add nav link to performance dashboard
web/src/app/features/workspaces/components/point-cloud/point-cloud.component.ts
    # Add ThreeJsMetricsCollector + metricsEmit output()
```

---

## 10. Constraints & Non-Goals (reiterated for implementors)

- **No historical storage** — no database writes, no file writes for metrics data.
- **No Prometheus exposition format** — only internal JSON.
- **No alerting** — dashboard is display-only.
- **No user-facing access** — the `/dashboard/performance` route must be protected in production builds. In development it is open.
- **Metrics channel does not carry point cloud data** — the `system_metrics` WS topic is JSON-only; LIDR binary frames travel on separate node topics.
- **Backend `metrics.py` API router must be registered under `/api/` prefix** to avoid conflicts with the Angular SPA catch-all route handler in `app.py`.
