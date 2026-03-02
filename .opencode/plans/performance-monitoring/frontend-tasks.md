# Performance Monitoring — Frontend Tasks

> **Owner**: `@fe-dev`
> **References**: `requirements.md` · `technical.md` · `api-spec.md`
> **Rule**: Check off each task (`- [ ]` → `- [x]`) as it is completed. Do not skip tasks or merge unrelated changes.
> **Important**: `@be-dev` tasks may not be complete. Use the mock data in `api-spec.md §6` and `MetricsMockService` until the real backend is available.

---

## Dependencies & Ordering

```
[FE-01] Metrics TypeScript models (interfaces)
    └── [FE-02] MetricsStore (Signal-based)
            ├── [FE-03] MetricsWebSocketService (WS consumer)
            │       └── depends on BE-09 (MetricsBroadcaster) or FE-01 mock
            ├── [FE-04] MetricsMockService (parallel dev unblock)
            └── [FE-05] MetricsApiService (REST snapshot)
                    └── [FE-06] ThreeJsMetricsCollector (in PointCloudComponent)
                            └── [FE-07] ComponentPerfService (PerformanceObserver)
                                    └── [FE-08] MultiWebsocketService client metrics extension
                                            └── [FE-09] Dashboard route + lazy component
                                                    ├── [FE-10] DagOverviewPanel (dumb)
                                                    ├── [FE-11] DagNodeDetailPanel (dumb)
                                                    ├── [FE-12] WebsocketPanel (dumb)
                                                    ├── [FE-13] SystemPanel (dumb)
                                                    ├── [FE-14] RenderingPanel (dumb)
                                                    └── [FE-15] MetricGauge (reusable dumb)
                                                            └── [FE-16] Nav link + route guard
                                                                    └── [FE-17] E2E smoke tests
```

---

## Ticket Group 1 — Data Models & Store

### FE-01 — Metrics TypeScript Models

**File**: `web/src/app/core/models/metrics.model.ts` (new)

**What to build**:
All TypeScript interfaces matching the API contracts in `api-spec.md`. This file is the single source of truth for metrics data shapes in the frontend.

**Acceptance Criteria**:
- [ ] `MetricsSnapshot` interface defined per `api-spec.md §5.2`
- [ ] `DagMetrics` interface defined per `api-spec.md §5.2`
- [ ] `DagNodeMetrics` interface with all fields from `api-spec.md §4.3`
- [ ] `WebSocketMetrics` interface per `api-spec.md §5.2`
- [ ] `WsTopicMetrics` interface per `api-spec.md §4.5`
- [ ] `SystemMetrics` interface per `api-spec.md §4.6`
- [ ] `EndpointMetrics` interface per `api-spec.md §4.7`
- [ ] `FrontendMetricsPayload` interface per `api-spec.md §5.1`
- [ ] `PerformanceHealthResponse` interface matching `api-spec.md §3.4`
- [ ] All interfaces exported from `web/src/app/core/models/metrics.model.ts`
- [ ] No `any` types used — all fields are properly typed

**References**: `api-spec.md §4`, `api-spec.md §5`

---

### FE-02 — MetricsStore (Angular Signals)

**File**: `web/src/app/core/services/stores/metrics-store.service.ts` (new)

**Scaffold command**: `cd web && ng g service core/services/stores/metrics-store`

**What to build**:
Signal-based store. The single write point for all metrics data in the frontend. Follows the pattern of existing store services in `web/src/app/core/services/stores/`.

**Acceptance Criteria**:
- [ ] `@Injectable({ providedIn: 'root' })` decorator applied
- [ ] Private writable signals using `#` private field syntax:
  - `#dagMetrics = signal<DagMetrics | null>(null)`
  - `#wsMetrics = signal<WebSocketMetrics | null>(null)`
  - `#systemMetrics = signal<SystemMetrics | null>(null)`
  - `#endpointMetrics = signal<EndpointMetrics[] | null>(null)`
  - `#frontendMetrics = signal<FrontendMetricsPayload | null>(null)`
  - `#lastUpdatedAt = signal<number | null>(null)`
  - `#isStale = signal<boolean>(false)` — set to `true` when WS disconnects, `false` when new data arrives
- [ ] Public read-only signals exposed via `.asReadonly()`:
  - `dagMetrics`, `wsMetrics`, `systemMetrics`, `endpointMetrics`, `frontendMetrics`, `lastUpdatedAt`, `isStale`
- [ ] `computed()` derived signals:
  - `totalPointsPerSec = computed(() => sum of throughput_pps across all dag nodes)`
  - `worstNodeLatencyMs = computed(() => max avg_exec_ms across all dag nodes, or null)`
  - `activeNodeCount = computed(() => dag.running_nodes or 0)`
- [ ] Public methods:
  - `update(snapshot: MetricsSnapshot): void` — sets all backend signals, resets `isStale` to `false`, updates `lastUpdatedAt`
  - `updateFrontend(payload: FrontendMetricsPayload): void` — sets `#frontendMetrics`
  - `markStale(): void` — sets `isStale` to `true`
- [ ] No HTTP calls inside this service — it is a pure state container
- [ ] Exported from `web/src/app/core/services/index.ts`

**References**: `technical.md §4.2`, `frontend.md — State Management`

---

### FE-03 — MetricsWebSocketService

**File**: `web/src/app/core/services/metrics-websocket.service.ts` (new)

**Scaffold command**: `cd web && ng g service core/services/metrics-websocket`

**What to build**:
WebSocket client that connects to `ws://{apiBase}/ws/system_metrics` and feeds parsed data into `MetricsStore`. Must mirror the architecture of the existing `StatusWebSocketService`.

**Acceptance Criteria**:
- [ ] `@Injectable({ providedIn: 'root' })` decorator applied
- [ ] Injects `MetricsStore`
- [ ] `connected = signal<boolean>(false)` exposed as public read-only
- [ ] `connect(): void` method:
  - Derives WS URL from `environment.apiUrl` (same pattern as `StatusWebSocketService`)
  - Connects to `${wsUrl}/ws/system_metrics`
  - `binaryType = 'text'` (JSON, not binary)
  - `onopen` → sets `connected` to `true`, resets reconnect counter
  - `onmessage` → parses JSON, calls `metricsStore.update(data as MetricsSnapshot)`
  - `onerror` → logs error
  - `onclose` → sets `connected` to `false`, calls `metricsStore.markStale()`, triggers reconnect
- [ ] Reconnect logic with exponential backoff: initial delay 2s, max 10 attempts, doubles each attempt (max delay 30s)
- [ ] `disconnect(): void` method — closes socket, clears reconnect timer
- [ ] Private `#ws: WebSocket | null = null` field
- [ ] No manual JSON field mapping — use `data as MetricsSnapshot` with a type guard that checks for `timestamp` field existence; log a warning if parse fails

**References**: `technical.md §4.1`, `api-spec.md §2`

---

### FE-04 — MetricsMockService (Parallel Development Unblock)

**File**: `web/src/app/core/services/mocks/metrics-mock.service.ts` (new)

**What to build**:
A mock service that replaces `MetricsWebSocketService` during development, feeding `MetricsStore` with evolving fake data at 1 Hz via `setInterval`. Enables the dashboard to be developed before the backend is ready.

**Acceptance Criteria**:
- [ ] Implements the same public interface as `MetricsWebSocketService` (`connect()`, `disconnect()`, `connected` signal)
- [ ] On `connect()`, starts a `setInterval` at 1000ms
  - Each tick: generates a `MetricsSnapshot` based on `MOCK_METRICS_SNAPSHOT` from `api-spec.md §6`
  - Randomizes values slightly: `last_exec_ms += (Math.random() - 0.5) * 0.5`
  - Calls `metricsStore.update(snapshot)`
  - Sets `connected` signal to `true`
- [ ] On `disconnect()`, clears the interval
- [ ] Exported from `web/src/app/core/services/mocks/`
- [ ] `MOCK_METRICS_SNAPSHOT` constant defined exactly as specified in `api-spec.md §6`
- [ ] **This service must NOT be used in production builds** — it is development-only. Add a comment block at the top of the file: `// DEV ONLY — remove injection before production`

**References**: `api-spec.md §6`

---

### FE-05 — MetricsApiService (REST Snapshots)

**File**: `web/src/app/core/services/api/metrics-api.service.ts` (new)

**Scaffold command**: `cd web && ng g service core/services/api/metrics-api`

**What to build**:
Centralized HTTP service for REST metrics endpoints. Used for the initial page-load snapshot before the WebSocket is established.

**Acceptance Criteria**:
- [ ] `@Injectable({ providedIn: 'root' })` decorator applied
- [ ] Injects `HttpClient` (via `inject()`)
- [ ] `getSnapshot(): Observable<MetricsSnapshot>` — `GET /api/metrics`
- [ ] `getDagMetrics(): Observable<DagMetrics>` — `GET /api/metrics/dag`
- [ ] `getWebSocketMetrics(): Observable<WebSocketMetrics>` — `GET /api/metrics/websocket`
- [ ] `getHealthPerformance(): Observable<PerformanceHealthResponse>` — `GET /api/health/performance`
- [ ] All methods use `environment.apiUrl` as base URL
- [ ] No `HttpClient` injection directly in any component — this service is the sole entry point
- [ ] Error handling: all methods use `catchError` to return `null` observable on failure (dashboard shows stale data banner)

**References**: `api-spec.md §3`, `frontend.md — API Services`

---

## Ticket Group 2 — Frontend Metrics Collection

### FE-06 — ThreeJsMetricsCollector

**File**: `web/src/app/features/workspaces/components/point-cloud/point-cloud.component.ts` (modify)

**What to build**:
Lightweight in-class metrics collector that hooks into the existing `animate()` loop and `updatePointsForTopic()` method. Emits `FrontendMetricsPayload` every 60 frames via an `output()` signal.

**Acceptance Criteria**:
- [ ] A private inner class `ThreeJsMetricsCollector` defined at the top of the component file (not exported):
  ```typescript
  // Fields: frameTimes: number[] (maxlen 60), renderTimes: number[] (maxlen 60),
  //         bufferMutationTimes: number[] (maxlen 60), lastFrameAt: number
  // Methods: recordFrame(renderMs), recordBufferMutation(ms), getSnapshot(): FrontendMetricsPayload
  ```
- [ ] `private metricsCollector = new ThreeJsMetricsCollector()` field added to `PointCloudComponent`
- [ ] `metricsEmit = output<FrontendMetricsPayload>()` Signal output added to the component
- [ ] In `animate()`:
  - Record `const frameStart = performance.now()` before `renderer.render()`
  - After `renderer.render()`: `const renderMs = performance.now() - frameStart`
  - Call `this.metricsCollector.recordFrame(renderMs)`
  - Every 60th frame: `this.metricsEmit.emit(this.metricsCollector.getSnapshot())`
- [ ] In `updatePointsForTopic()`:
  - Wrap `positions.set(...)` call with `performance.now()` before and after
  - Call `this.metricsCollector.recordBufferMutation(ms)`
- [ ] `ThreeJsMetricsCollector.getSnapshot()` returns `FrontendMetricsPayload` with:
  - `fps`: computed as `1000 / avg(frameTimes)`
  - `avg_render_ms`: avg of `renderTimes`
  - `avg_buffer_mutation_ms`: avg of `bufferMutationTimes`
  - `collected_at`: `Date.now()`
  - `long_task_count: 0`, `long_task_total_ms: 0` (populated by `ComponentPerfService` separately)
  - `ws_frames_per_sec: {}`, `ws_parse_latency_ms: {}`, `ws_bytes_per_sec: {}` (populated elsewhere)
- [ ] **Existing `animate()` and `updatePointsForTopic()` behavior must not change** — only additive instrumentation
- [ ] The `metricsEmit` output is wired in the parent workspace smart component to call `metricsStore.updateFrontend(payload)` (see FE-09 for parent wiring)

**References**: `technical.md §4.3`, `requirements.md — Track Three.js FPS, frame/block render times`

---

### FE-07 — ComponentPerfService (PerformanceObserver)

**File**: `web/src/app/core/services/component-perf.service.ts` (new)

**Scaffold command**: `cd web && ng g service core/services/component-perf`

**What to build**:
Passive service using the Web `PerformanceObserver` API to detect long tasks (>50ms main-thread blocks) and push counts/durations into `MetricsStore`.

**Acceptance Criteria**:
- [ ] `@Injectable({ providedIn: 'root' })` decorator applied
- [ ] Injects `MetricsStore`
- [ ] `startObserving(): void` method:
  - Creates a `PerformanceObserver` observing `"longtask"` entry type
  - On each entry batch: accumulates `count` and `totalMs` for the current 1-sec window
  - Uses `setInterval(1000)` to flush accumulated values into `MetricsStore.updateFrontend()` partial update — only updates the `long_task_count` and `long_task_total_ms` fields of the existing `frontendMetrics` signal
  - Guards against `PerformanceObserver` not being available (Safari/older browsers) with a `try/catch` — degrades gracefully
- [ ] `stopObserving(): void` method — disconnects observer and clears interval
- [ ] Service is started from the `DashboardComponent` `ngOnInit()` and stopped on `ngOnDestroy()`
- [ ] Does not instrument anything outside the `PerformanceObserver` callback — completely passive

**References**: `technical.md §4.4`, `requirements.md — Monitor Angular component/UI responsiveness`

---

### FE-08 — WebSocket Client Metrics Extension

**File**: `web/src/app/core/services/multi-websocket.service.ts` (modify)

**What to build**:
Extend `MultiWebsocketService` to track per-topic frame rates, byte rates, and parse latency. Push to `MetricsStore` via a 1-second flush interval.

**Acceptance Criteria**:
- [ ] Injects `MetricsStore` via `inject()`
- [ ] Private `#topicStats = new Map<string, { framesThisSec: number, bytesThisSec: number, parseTimes: number[] }>()` field added
- [ ] In `connect()`, inside `socket.onmessage`:
  - Record `const t0 = performance.now()` before any parsing
  - After parsing (DataView decode, if applicable): `const parseMs = performance.now() - t0`
  - Increment `framesThisSec` and `bytesThisSec` (from `event.data.byteLength` or `event.data.length`)
  - Append `parseMs` to `parseTimes` array (max 60 entries)
- [ ] `#flushInterval = setInterval(() => this.#flushMetrics(), 1000)` started in constructor
- [ ] `#flushMetrics()` computes `ws_frames_per_sec`, `ws_bytes_per_sec`, `ws_parse_latency_ms` for all topics and calls `metricsStore.updateFrontend({ ws_frames_per_sec, ws_bytes_per_sec, ws_parse_latency_ms })` as a partial update
- [ ] `disconnectAll()` clears the flush interval
- [ ] **Existing `connect()`, `disconnect()`, `isConnected()`, `getActiveTopics()` behavior unchanged**

**References**: `technical.md §4.5`, `requirements.md — Frontend WebSocket performance stats`

---

## Ticket Group 3 — Dashboard UI

### FE-09 — Dashboard Route + Smart Component

**Files**:
- `web/src/app/features/dashboard/dashboard.component.ts` (new)
- `web/src/app/features/dashboard/dashboard.component.html` (new)
- `web/src/app/app.routes.ts` (modify)

**Scaffold command**: `cd web && ng g component features/dashboard/dashboard --standalone`

**What to build**:
The top-level smart component for `/dashboard/performance`. Reads `MetricsStore` signals and passes data down to dumb panel components. Handles initial REST snapshot load before WS is ready.

**Acceptance Criteria**:
- [ ] `@Component` with `standalone: true`, `imports: [all panel components]`
- [ ] Injects: `MetricsStore`, `MetricsWebSocketService`, `MetricsApiService`, `ComponentPerfService`
- [ ] `ngOnInit()`:
  - Calls `metricsWebSocketService.connect()`
  - Calls `componentPerfService.startObserving()`
  - Calls `metricsApiService.getSnapshot()` for an immediate data load before first WS push
- [ ] `ngOnDestroy()`:
  - Calls `metricsWebSocketService.disconnect()`
  - Calls `componentPerfService.stopObserving()`
- [ ] Template structure (Tailwind layout, Synergy UI `syn-card` wrappers):
  ```html
  <!-- Header bar: "Performance Dashboard" title + connected/stale badge -->
  <!-- Row 1: System panel (full width) -->
  <!-- Row 2: DAG Overview panel (2/3 width) + WebSocket panel (1/3 width) -->
  <!-- Row 3: Rendering panel (1/2 width) + Endpoint table (1/2 width) -->
  ```
- [ ] Wires `(metricsEmit)` output from `PointCloudComponent` to `metricsStore.updateFrontend($event)` — this requires the workspace feature to be present in scope; use an Angular `effect()` to subscribe if the workspace is not directly inside the dashboard
- [ ] `isStale` signal from `MetricsStore` used to show a `syn-badge` warning banner: "Data stale — reconnecting..."
- [ ] `connected` signal from `MetricsWebSocketService` shown in the header as a green/red indicator dot
- [ ] Lazy route added to `app.routes.ts`:
  ```typescript
  {
    path: 'dashboard/performance',
    loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent)
  }
  ```

**References**: `technical.md §4.6`, `frontend.md — Separation of Concerns`

---

### FE-10 — DagOverviewPanel (Dumb Component)

**Files**:
- `web/src/app/features/dashboard/components/dag-overview-panel/dag-overview-panel.component.ts` (new)
- Corresponding `.html` template

**Scaffold command**: `cd web && ng g component features/dashboard/components/dag-overview-panel --standalone`

**What to build**:
Dumb panel displaying an overview table of all DAG nodes and their key metrics.

**Acceptance Criteria**:
- [ ] `standalone: true`, zero service injections
- [ ] Signal inputs (using `input()` syntax from Angular 20):
  - `nodes = input<DagNodeMetrics[]>([])`
  - `totalNodes = input<number>(0)`
  - `runningNodes = input<number>(0)`
- [ ] Template renders a `syn-card` containing:
  - A header: "DAG Processing — `runningNodes` / `totalNodes` running" with a `syn-badge`
  - An HTML `<table>` (Tailwind styled) with columns: Node Name | Type | Avg Exec (ms) | Last Exec (ms) | Throughput (pts/s) | Points (last) | Throttled | Last Seen
  - `@for (node of nodes(); track node.node_id)` iteration
  - Cells are plain text — no charts
  - "Last Seen" column: formatted as `Xs ago` using a `TimeAgoPipe` (create a simple pure pipe if not already present)
  - Rows highlighted in amber (`bg-amber-950/30`) if `avg_exec_ms > 20` (configurable threshold)
- [ ] Empty state: if `nodes()` is empty, show "No DAG nodes reporting metrics yet."
- [ ] `@Output` for node row click: `nodeSelected = output<DagNodeMetrics>()` — emits the selected node so parent can show detail panel

**References**: `technical.md §4.6`, `requirements.md — Per-node detail and overview`

---

### FE-11 — DagNodeDetailPanel (Dumb Component)

**Files**:
- `web/src/app/features/dashboard/components/dag-node-detail-panel/dag-node-detail-panel.component.ts`
- Corresponding `.html`

**Scaffold command**: `cd web && ng g component features/dashboard/components/dag-node-detail-panel --standalone`

**What to build**:
Detailed stats panel for a single selected DAG node, shown as a slide-over or expandable card when a row in the overview table is clicked.

**Acceptance Criteria**:
- [ ] `standalone: true`, zero service injections
- [ ] Signal input: `node = input<DagNodeMetrics | null>(null)`
- [ ] Template inside a `syn-card`:
  - Node name as `<h3>` with `syn-badge` for node type
  - Key-value grid (Tailwind `grid grid-cols-2`) showing all `DagNodeMetrics` fields with human-readable labels
  - `calls_total` formatted with thousands separator
  - `throughput_pps` formatted as `X.X k pts/s`
  - `last_seen_ts` formatted as absolute time (ISO string) + relative `Xs ago`
  - `throttled_count > 0` shown in amber with a warning icon
- [ ] `@if (node() === null)` — shows "Select a node from the overview to see details."
- [ ] A close/deselect `output()` signal: `closeDetail = output<void>()`

**References**: `technical.md §4.6`

---

### FE-12 — WebsocketPanel (Dumb Component)

**Scaffold command**: `cd web && ng g component features/dashboard/components/websocket-panel --standalone`

**What to build**:
Panel showing per-topic WebSocket streaming statistics.

**Acceptance Criteria**:
- [ ] `standalone: true`, zero service injections
- [ ] Signal input: `wsMetrics = input<WebSocketMetrics | null>(null)`
- [ ] Template inside `syn-card`:
  - Header: "WebSocket Streams — `total_connections` active connections"
  - `@for` loop over `wsMetrics()?.topics` entries
  - Per-topic row: Topic name | Msgs/sec | MB/sec | Active connections | Total msgs
  - `bytes_per_sec` formatted as `X.X MB/s`
  - If no topics: "No active WebSocket topics."
- [ ] `total_connections` shown with a colored `syn-badge`: green ≥1, grey = 0

**References**: `api-spec.md §4.4`, `requirements.md — Monitor WebSocket (LIDR) message rates`

---

### FE-13 — SystemPanel (Dumb Component)

**Scaffold command**: `cd web && ng g component features/dashboard/components/system-panel --standalone`

**What to build**:
Panel showing OS-level system resource metrics using Synergy UI progress components.

**Acceptance Criteria**:
- [ ] `standalone: true`, zero service injections
- [ ] Signal input: `systemMetrics = input<SystemMetrics | null>(null)`
- [ ] Template inside `syn-card`:
  - Header: "System Resources"
  - CPU gauge: `syn-progress` with `value = cpu_percent`, label "CPU `cpu_percent`%"
    - Color: green < 50%, amber 50–80%, red > 80% (use Tailwind class binding)
  - Memory gauge: `syn-progress` with `value = memory_percent`, label "Memory `memory_used_mb | number:'1.0-0'` / `memory_total_mb` MB"
  - Thread count: plain text "Threads: `thread_count`"
  - Queue depth: plain text "Queue depth: `queue_depth`" — amber if > 10
- [ ] Empty state if `systemMetrics()` is null: animated skeleton placeholder rows (Tailwind `animate-pulse`)

**References**: `api-spec.md §4.6`, `requirements.md — Monitor system CPU, memory, thread pool usage`

---

### FE-14 — RenderingPanel (Dumb Component)

**Scaffold command**: `cd web && ng g component features/dashboard/components/rendering-panel --standalone`

**What to build**:
Panel showing frontend Three.js rendering and WebSocket client performance metrics.

**Acceptance Criteria**:
- [ ] `standalone: true`, zero service injections
- [ ] Signal input: `frontendMetrics = input<FrontendMetricsPayload | null>(null)`
- [ ] Template inside `syn-card`:
  - Header: "Frontend Rendering"
  - FPS display: large number `fps` with color coding: green ≥ 55, amber 30–55, red < 30
  - Avg render time: "`avg_render_ms` ms / frame"
  - Avg buffer mutation time: "`avg_buffer_mutation_ms` ms / update"
  - Long tasks: "`long_task_count` long tasks (`long_task_total_ms` ms blocked)" — amber if > 0
  - WS parse latency section: `@for` loop over `ws_parse_latency_ms` entries, showing topic + latency
- [ ] Empty state if `frontendMetrics()` is null: "Metrics available when workspace is open."
- [ ] `fps` shown with `| number:'1.0-0'` pipe

**References**: `technical.md §4.3`, `requirements.md — Track Three.js FPS`

---

### FE-15 — MetricGauge Reusable Component

**Scaffold command**: `cd web && ng g component features/dashboard/components/metric-gauge --standalone`

**What to build**:
Small reusable "number + label + status badge" component wrapping Synergy UI, used across all panels for key metrics.

**Acceptance Criteria**:
- [ ] `standalone: true`, zero service injections
- [ ] Signal inputs:
  - `label = input.required<string>()`
  - `value = input.required<number | string>()`
  - `unit = input<string>('')`
  - `status = input<'good' | 'warn' | 'bad' | 'neutral'>('neutral')`
  - `tooltip = input<string>('')`
- [ ] Template: `syn-card` or `div` with Tailwind, showing `label`, large `value` + `unit`, and a `syn-badge` colored by `status`
- [ ] Status color mapping: `good` → green, `warn` → amber, `bad` → red, `neutral` → grey
- [ ] Used by `SystemPanel` for CPU and memory (as an alternative to `syn-progress` for compact display)

**References**: `technical.md §4.6`

---

## Ticket Group 4 — Navigation & Guards

### FE-16 — Navigation Link + Development Route Guard

**Files**:
- `web/src/app/layout/main-layout/` (modify navigation template)
- `web/src/app/core/guards/dev-only.guard.ts` (new)

**What to build**:
Add a navigation link to the sidebar for the Performance Dashboard. Guard the route so it is inaccessible in production builds.

**Acceptance Criteria**:
- [ ] New `DevOnlyGuard` created (`cd web && ng g guard core/guards/dev-only`):
  - Implements `CanActivateFn`
  - Returns `true` if `!environment.production`, else redirects to `/`
  - Logs a console warning if blocked: `console.warn('[DevOnly] Performance dashboard is not available in production builds.')`
- [ ] Route in `app.routes.ts` updated to include `canActivate: [DevOnlyGuard]` on `dashboard/performance`
- [ ] Navigation sidebar in `main-layout` template:
  - New nav item: icon (use `monitor` or `chart-bar` SVG/Synergy icon) + label "Performance"
  - Link: `routerLink="/dashboard/performance"`
  - `@if (!environment.production)` wrapper — the link is not rendered in production builds
- [ ] `RouterLinkActive` applied so the nav item highlights when the dashboard route is active

**References**: `technical.md §4.6`, `requirements.md — Built-in Angular metrics dashboard (developer access only)`

---

## Ticket Group 5 — Tests

### FE-17 — Unit Tests & Smoke Tests

**What to build**:
Unit tests for the core services and a basic smoke test for the dashboard route.

**Acceptance Criteria**:
- [ ] `metrics-store.service.spec.ts`:
  - [ ] `should initialize with null signals` — all signals are null on creation
  - [ ] `should update dagMetrics on update()` — after calling `update(MOCK_METRICS_SNAPSHOT)`, `dagMetrics()` equals the snapshot's dag field
  - [ ] `should compute totalPointsPerSec correctly` — computed signal sums throughput_pps
  - [ ] `should mark stale` — after `markStale()`, `isStale()` is `true`; after next `update()`, `isStale()` is `false`

- [ ] `metrics-websocket.service.spec.ts`:
  - [ ] `should set connected to false initially` — before `connect()` is called
  - [ ] `should parse valid MetricsSnapshot and call store.update()` — mock WebSocket `onmessage`, verify `metricsStore.update` was called with correct data
  - [ ] `should call store.markStale() on disconnect` — mock `onclose`, verify `markStale` called

- [ ] `dag-overview-panel.component.spec.ts`:
  - [ ] `should render node rows for each DagNodeMetrics input`
  - [ ] `should show empty state when nodes array is empty`
  - [ ] `should emit nodeSelected when a row is clicked`

- [ ] `dashboard.component.spec.ts` (smoke test):
  - [ ] `should create without errors` — component instantiates using `TestBed` with `MetricsMockService` substituted for `MetricsWebSocketService`
  - [ ] `should show stale banner when isStale is true` — set store's stale signal, verify banner is in DOM

**References**: `requirements.md — Display real-time metrics in Angular dashboard`

---

## Summary Checklist

| # | Task | Status |
|---|---|---|
| FE-01 | Metrics TypeScript models | - [ ] |
| FE-02 | MetricsStore (Signal-based) | - [ ] |
| FE-03 | MetricsWebSocketService | - [ ] |
| FE-04 | MetricsMockService (dev unblock) | - [ ] |
| FE-05 | MetricsApiService (REST snapshots) | - [ ] |
| FE-06 | ThreeJsMetricsCollector (in PointCloudComponent) | - [ ] |
| FE-07 | ComponentPerfService (PerformanceObserver) | - [ ] |
| FE-08 | MultiWebsocketService client metrics extension | - [ ] |
| FE-09 | Dashboard route + smart DashboardComponent | - [x] |
| FE-10 | DagOverviewPanel (dumb) | - [x] |
| FE-11 | DagNodeDetailPanel (dumb) | - [x] |
| FE-12 | WebsocketPanel (dumb) | - [x] |
| FE-13 | SystemPanel (dumb) | - [x] |
| FE-14 | RenderingPanel (dumb) | - [x] |
| FE-15 | MetricGauge reusable component | - [x] |
| FE-16 | Nav link + DevOnlyGuard | - [ ] |
| FE-17 | Unit & smoke tests | - [ ] |
