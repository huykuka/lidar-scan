# Performance Monitoring — QA Test Plan & Coverage Matrix

> **Status**: PRE-IMPLEMENTATION REVIEW
> **Role**: `@qa` — This document is for user review and approval before any test code is written.
> **Purpose**: Lock the comprehensive test strategy covering <1% overhead validation, real-time metrics accuracy, dashboard functionality, and edge cases.

---

## Executive Summary

This QA plan validates the **Performance Monitoring & Metrics** feature across three critical dimensions:

1. **Backend Instrumentation** — Overhead < 1%, correct DAG/WebSocket/Endpoint metric collection
2. **Frontend Metrics Collection** — Three.js FPS/render times, component responsiveness, WebSocket client performance
3. **Dashboard Accuracy & UX** — Real-time data flow, stale state handling, error resilience, visual correctness

**Test Scope**: 
- 18 backend unit/integration tests
- 12 frontend unit/component tests
- 8 end-to-end integration tests
- 6 performance/load tests for overhead validation
- 12 edge case & error path tests

**Estimated Coverage**: 87% code coverage (backend), 92% (frontend), 100% (critical paths)

---

## Part 1: Backend Test Strategy

### 1.1 Backend Testing Tiers

| Tier | Scope | Tools | Count |
|------|-------|-------|-------|
| **Unit** | Registry, Collector, Models | `pytest` | 6 |
| **Integration** | Instrumentation hooks, Middleware, Background tasks | `pytest`, async fixtures | 7 |
| **API** | REST endpoints, Error paths | `TestClient` | 5 |
| **Performance** | Overhead measurement, throughput | `pytest-benchmark` | 6 |
| **Edge Cases** | Null metrics, disabled state, threading | `pytest` | 4 |

### 1.2 Backend Unit Tests

#### **BE-UT-001**: MetricsRegistry Initialization
- **Test**: `test_metrics_registry_initializes_empty()`
- **Verify**: 
  - `node_metrics` is empty dict
  - `ws_topic_metrics` is empty dict
  - `system_metrics` is None
  - `endpoint_metrics` is empty dict
- **Pass Condition**: All attributes have correct initial state
- **Coverage**: `app/services/metrics/registry.py` __init__ method

#### **BE-UT-002**: NodeMetricsSample Rolling Window Average
- **Test**: `test_avg_exec_ms_rolling_window_60_samples()`
- **Setup**: Create `NodeMetricsSample`, add 70 execution times (0.5ms to 5.0ms)
- **Verify**:
  - `exec_times_deque` maxlen is exactly 60
  - After 70 additions, oldest 10 are discarded
  - `avg_exec_ms` property correctly computes mean of last 60
  - Property value is within 1% of manual calculation
- **Pass Condition**: `abs(computed_avg - manual_avg) < 0.05ms`
- **Edge Case**: Zero execution times, all same values, mixed high/low

#### **BE-UT-003**: WsTopicSample Per-Second Windowing
- **Test**: `test_ws_topic_messages_per_sec_windowing()`
- **Setup**: Create `WsTopicSample`, record messages at specific timestamps (0s, 0.2s, 0.8s, 1.2s, 2.5s)
- **Verify**:
  - `messages_per_sec` property counts only messages in the last 1-second window
  - At t=2.5s, only messages from t>=1.5s are counted
  - `bytes_per_sec` correctly aggregates byte sizes in the window
- **Pass Condition**: Window boundaries respected, off-by-one errors prevented
- **Coverage**: `registry.py` window computation logic

#### **BE-UT-004**: EndpointSample Latency Averaging
- **Test**: `test_endpoint_sample_avg_latency_ms()`
- **Setup**: Record endpoint latencies: [1ms, 2ms, 3ms, 5ms, 8ms]
- **Verify**:
  - `avg_latency_ms` property computes correct mean
  - `calls_total` monotonically increases
  - `last_status_code` reflects most recent code
- **Pass Condition**: All three fields reflect current state
- **Coverage**: `EndpointSample` dataclass

#### **BE-UT-005**: NullMetricsCollector No-Op Behavior
- **Test**: `test_null_collector_all_methods_noop()`
- **Setup**: Create `NullMetricsCollector`, call all interface methods
- **Verify**:
  - `record_node_exec()`, `record_ws_message()`, etc. do not raise exceptions
  - `is_enabled()` returns `False`
  - `snapshot()` returns valid empty `MetricsSnapshotModel` with zero values
- **Pass Condition**: No exceptions, valid empty state
- **Coverage**: `app/services/metrics/null_collector.py`

#### **BE-UT-006**: MetricsCollector Snapshot Serialization
- **Test**: `test_metrics_collector_snapshot_to_pydantic()`
- **Setup**: `MetricsCollector` with 2 nodes, 3 WS topics, system metrics, 2 endpoints
- **Verify**:
  - `snapshot()` returns `MetricsSnapshotModel` (Pydantic V2)
  - All fields are non-null as expected
  - `.model_dump()` produces valid JSON
  - Round-trip: `model_validate(json_dict)` restores equivalent object
- **Pass Condition**: Serialization round-trip succeeds, schema matches `api-spec.md`
- **Coverage**: `collector.py` snapshot method, Pydantic models

### 1.3 Backend Integration Tests

#### **BE-IT-001**: DAG Routing Instrumentation Hook
- **Test**: `test_dag_routing_records_node_exec()`
- **Setup**: Mock `DataRouter`, `ModuleNode`, `MetricsCollector`; call `_send_to_target_node()` with a payload containing 100 points
- **Verify**:
  - `metrics_collector.record_node_exec()` called exactly once per `on_input()`
  - Arguments: correct `node_id`, `node_name`, `node_type`, `exec_ms` > 0, `point_count = 100`
  - Hook timing includes only `on_input()` execution, not payload creation
  - If `on_input()` raises exception, timing is still recorded (outside try/except)
- **Pass Condition**: Metrics recorded before exception propagates
- **Coverage**: `app/services/nodes/managers/routing.py` instrumentation

#### **BE-IT-002**: WebSocket Broadcast Instrumentation
- **Test**: `test_websocket_broadcast_records_message()`
- **Setup**: Mock `WebSocketManager`, `MetricsCollector`; broadcast 500 bytes to topic "lidar_front"
- **Verify**:
  - `record_ws_message("lidar_front", 500)` called after broadcast
  - For JSON payloads, byte size is computed as `len(json.dumps(payload).encode())`
  - Multiple calls accumulate in topic metrics
  - Connection count tracked in `record_ws_connections()`
- **Pass Condition**: Byte counts and connection counts accurate
- **Coverage**: `app/services/websocket/manager.py` instrumentation

#### **BE-IT-003**: FastAPI Middleware Latency Recording
- **Test**: `test_metrics_middleware_records_endpoint_latency()`
- **Setup**: Create FastAPI app with `MetricsMiddleware`, make HTTP request to `/api/nodes` that takes ~10ms
- **Verify**:
  - `record_endpoint("/api/nodes", "GET", ~10ms, 200)` called
  - Non-API paths (e.g., `/static/index.html`) are not instrumented
  - Status code is captured correctly
  - Latency is wall-clock time (includes serialization)
- **Pass Condition**: Only `/api/**` routes instrumented, latency accurate ±2ms
- **Coverage**: `app/middleware/metrics_middleware.py`

#### **BE-IT-004**: System Probe 2 Hz Collection Loop
- **Test**: `test_system_probe_collects_at_2hz()`
- **Setup**: Start `_system_probe_loop()` with stop event, let it run for 2.5 seconds
- **Verify**:
  - `SystemMetricsSample` created and stored in registry 4–6 times (2 Hz ± 10%)
  - Each sample has valid `cpu_percent` (0–100), `memory_used_mb` > 0, `thread_count` > 0
  - Loop handles `psutil` errors gracefully (e.g., on first call with `interval=None`)
  - Loop stops cleanly when `stop_event` is set
- **Pass Condition**: 4–6 samples in 2.5 sec, all valid fields
- **Coverage**: `app/services/metrics/system_probe.py`

#### **BE-IT-005**: Open3D Async Timer Context Manager
- **Test**: `test_open3d_timer_async_context()`
- **Setup**: Use `async with open3d_timer("voxel_downsample", "node-xyz")` around a dummy async operation
- **Verify**:
  - Execution time recorded (>= actual operation time)
  - Registry entry `node_metrics["node-xyz"].open3d_ops["voxel_downsample"]` exists
  - Multiple calls accumulate: second call shows updated `avg_ms` and incremented `calls`
  - Timer does not suppress exceptions from the wrapped block
- **Pass Condition**: Timing accurate, multiple calls tracked, exceptions propagate
- **Coverage**: `app/services/metrics/open3d_timer.py`

#### **BE-IT-006**: MetricsBroadcaster 1 Hz Broadcast Loop
- **Test**: `test_metrics_broadcaster_pushes_at_1hz()`
- **Setup**: Mock `WebSocketManager`, start `_metrics_broadcast_loop()` with stop event, let run 2.5 seconds
- **Verify**:
  - `manager.broadcast("system_metrics", json_payload)` called 2–4 times (1 Hz ± 20%)
  - Payload is valid `MetricsSnapshotModel` serialized to dict
  - Loop gracefully handles if `get_metrics_collector()` returns `NullCollector` (skips silently)
  - Loop stops cleanly when `stop_event` is set
- **Pass Condition**: 2–4 broadcasts in 2.5 sec, payloads valid
- **Coverage**: `app/services/metrics/broadcaster.py`

#### **BE-IT-007**: Lifespan Integration (Startup & Shutdown)
- **Test**: `test_app_lifespan_starts_stops_all_services()`
- **Setup**: Create FastAPI app with full metrics lifespan context
- **Verify**:
  - On startup: `MetricsCollector` injected, `MetricsBroadcaster` task created, `SystemProbe` task created
  - Within 1 second of startup: first metrics snapshot available via `/api/metrics`
  - On shutdown: both background tasks cancelled cleanly, no exceptions
  - If `LIDAR_ENABLE_METRICS=false`: `NullCollector` injected, broadcaster/probe don't start
- **Pass Condition**: Services start/stop in correct order, no orphaned tasks
- **Coverage**: `app/app.py` lifespan context

### 1.4 Backend API Tests (TestClient)

#### **BE-API-001**: GET /api/metrics Returns Full Snapshot
- **Test**: `test_get_api_metrics_full_snapshot()`
- **Setup**: Seed registry with 2 nodes, 3 WS topics, system metrics, 2 endpoints
- **Verify**:
  - Status code: 200
  - Response schema validates as `MetricsSnapshotModel`
  - `timestamp` is present and > 0
  - All subsections (`dag`, `websocket`, `system`, `endpoints`) populated
- **Pass Condition**: Valid 200 response, full payload
- **Coverage**: `app/api/v1/metrics.py` GET /metrics endpoint

#### **BE-API-002**: GET /api/metrics Returns 503 When Disabled
- **Test**: `test_get_api_metrics_503_when_disabled()`
- **Setup**: App configured with `NullMetricsCollector`
- **Verify**:
  - Status code: 503 Service Unavailable
  - Response contains error message indicating metrics disabled
- **Pass Condition**: 503 returned for disabled metrics
- **Coverage**: Error path in GET /metrics

#### **BE-API-003**: GET /api/metrics/dag Subset Endpoint
- **Test**: `test_get_api_metrics_dag_subset()`
- **Setup**: Seed 3 nodes
- **Verify**:
  - Status code: 200
  - Response contains only `dag` section with `nodes`, `total_nodes`, `running_nodes`
  - No `websocket`, `system`, `endpoints` fields
- **Pass Condition**: Correct subset returned
- **Coverage**: GET /metrics/dag endpoint

#### **BE-API-004**: GET /api/health/performance Always Returns 200
- **Test**: `test_get_health_performance_always_200()`
- **Setup**: Test with both enabled and disabled metrics
- **Verify**:
  - Status code: 200 in both cases
  - When enabled: `metrics_enabled: true`, `broadcaster_running: true`, `node_count > 0`
  - When disabled: `metrics_enabled: false`, `broadcaster_running: false`, `node_count: 0`
- **Pass Condition**: Always 200, fields reflect actual state
- **Coverage**: GET /api/health/performance endpoint

#### **BE-API-005**: Endpoint Response Content-Type
- **Test**: `test_all_endpoints_return_json()`
- **Setup**: Call all metrics endpoints
- **Verify**:
  - All responses have `Content-Type: application/json` header
- **Pass Condition**: All endpoints serve JSON
- **Coverage**: FastAPI route configuration

### 1.5 Backend Performance Tests (Overhead Validation)

#### **BE-PERF-001**: record_node_exec() Overhead < 1µs
- **Test**: `test_record_node_exec_overhead_benchmark()`
- **Benchmark**: Call `record_node_exec()` 10,000 times with realistic data
- **Verify**:
  - Average latency per call: < 1 microsecond (1000 nanoseconds)
  - P99 latency: < 5 microseconds
  - **Acceptance**: At 100 Hz sensor input, total instrumentation overhead = 10,000 calls/sec × 1µs = 0.01% CPU
- **Pass Condition**: Benchmark confirms overhead < 0.05%
- **Tool**: `pytest-benchmark` with baseline fixture
- **Coverage**: `collector.py` record_node_exec method

#### **BE-PERF-002**: record_ws_message() Overhead < 0.5µs
- **Test**: `test_record_ws_message_overhead_benchmark()`
- **Benchmark**: Call `record_ws_message()` 10,000 times
- **Verify**:
  - Average latency: < 0.5 microseconds
  - At 1000 msgs/sec, overhead = 0.5ms/sec = 0.00005% CPU
- **Pass Condition**: Benchmark confirms overhead < 0.02%
- **Coverage**: WebSocket message recording

#### **BE-PERF-003**: MetricsRegistry.snapshot() < 2ms
- **Test**: `test_snapshot_serialization_time_benchmark()`
- **Setup**: Registry with 50 nodes, 20 WS topics, 30 endpoints
- **Benchmark**: Call `snapshot()` 1000 times
- **Verify**:
  - Average: < 2ms per snapshot
  - P99: < 5ms
  - **At 1 Hz broadcast**: 1 snapshot/sec × 2ms = 0.0002% CPU
- **Pass Condition**: Benchmark confirms overhead < 0.001% for broadcast
- **Coverage**: Serialization logic

#### **BE-PERF-004**: SystemProbe 2 Hz Collection Overhead
- **Test**: `test_system_probe_overhead_benchmark()`
- **Benchmark**: Run probe loop, measure CPU used by probe vs baseline
- **Verify**:
  - Probe overhead < 0.01% CPU (at 2 Hz sampling)
  - No blocking I/O in hot path (psutil calls are quick)
- **Pass Condition**: Negligible system impact
- **Coverage**: System metrics collection

#### **BE-PERF-005**: Middleware Latency Recording Overhead
- **Test**: `test_middleware_overhead_on_api_requests()`
- **Setup**: Make 100 requests to `/api/nodes` with and without middleware
- **Verify**:
  - Median response time difference: < 0.5ms
  - P99 difference: < 1ms
- **Pass Condition**: Instrumentation adds < 0.5% latency
- **Coverage**: Middleware dispatch method

#### **BE-PERF-006**: Total System Overhead Cumulative Test
- **Test**: `test_total_backend_metrics_overhead_under_1pct()`
- **Setup**: Simulate realistic workload: 100 Hz sensor input + 10 msgs/sec WS broadcast + 20 API requests/sec
- **Verify**:
  - All instrumentation combined adds < 1% CPU overhead
  - Memory overhead: < 10 MB (for registry + deques)
- **Pass Condition**: `(with_metrics_cpu - baseline_cpu) / baseline_cpu < 0.01`
- **Coverage**: End-to-end overhead

### 1.6 Backend Edge Cases & Error Paths

#### **BE-EDGE-001**: Large Point Cloud Count (1M Points)
- **Test**: `test_record_node_exec_with_large_point_count()`
- **Setup**: Call `record_node_exec()` with `point_count = 1_000_000`
- **Verify**:
  - No integer overflow
  - `throughput_pps` correctly computed
- **Pass Condition**: Large numbers handled without error

#### **BE-EDGE-002**: Division by Zero in Averaging
- **Test**: `test_empty_deque_averaging_no_division_by_zero()`
- **Setup**: Access `avg_exec_ms` on a `NodeMetricsSample` that has never recorded a time
- **Verify**:
  - Returns 0.0 or raises handled exception (not unhandled ZeroDivisionError)
- **Pass Condition**: Graceful handling

#### **BE-EDGE-003**: Stale WebSocket Topic Metrics
- **Test**: `test_ws_topic_old_messages_excluded_from_window()`
- **Setup**: Record messages at t=0, then request metrics at t=5 seconds (no new messages)
- **Verify**:
  - Old messages are correctly filtered out by timestamp
  - `messages_per_sec` returns 0, not stale old value
- **Pass Condition**: Time window correctly updated

#### **BE-EDGE-004**: Disabled Metrics Don't Crash on Broadcast
- **Test**: `test_disabled_metrics_broadcaster_noop_silently()`
- **Setup**: Broadcaster running with `NullMetricsCollector`
- **Verify**:
  - No exception raised during broadcast cycle
  - No messages sent to WebSocket (verified via mock)
- **Pass Condition**: Graceful no-op

---

## Part 2: Frontend Test Strategy

### 2.1 Frontend Testing Tiers

| Tier | Scope | Tools | Count |
|------|-------|-------|-------|
| **Unit (Services)** | MetricsStore, MetricsWebSocketService, MetricsApiService | `jasmine`, `TestBed` | 5 |
| **Unit (Components)** | DagOverviewPanel, SystemPanel, RenderingPanel | `jasmine`, Synergy fixtures | 4 |
| **Integration** | Dashboard smart component, data flow | `TestBed` + `HttpClientTestingModule` | 3 |
| **E2E Smoke** | Dashboard route, navigation | `Cypress` or Protractor | 2 |
| **Performance** | FPS collection, WebSocket latency | `jasmine` + `performance.now()` | 3 |
| **Edge Cases** | Stale data, WS reconnect, null metrics | `jasmine` | 3 |

### 2.2 Frontend Unit Tests (Services)

#### **FE-UT-001**: MetricsStore Initialization
- **Test**: `should initialize with null signals`
- **Verify**:
  - All signals (`dagMetrics`, `wsMetrics`, `systemMetrics`, `endpointMetrics`, `frontendMetrics`) are initially `null`
  - `isStale` is initially `false`
  - `lastUpdatedAt` is initially `null`
- **Pass Condition**: All initial states correct
- **Coverage**: `MetricsStore` constructor

#### **FE-UT-002**: MetricsStore Update Flow
- **Test**: `should update all metrics on update() call`
- **Setup**: Call `store.update(MOCK_METRICS_SNAPSHOT)`
- **Verify**:
  - `dagMetrics()` signal equals snapshot's dag
  - `wsMetrics()` signal equals snapshot's websocket
  - `systemMetrics()` signal equals snapshot's system
  - `lastUpdatedAt()` is approximately `Date.now() / 1000`
  - `isStale` is `false`
- **Pass Condition**: All signals updated correctly
- **Coverage**: `MetricsStore.update()` method

#### **FE-UT-003**: MetricsStore Computed Signals
- **Test**: `should compute totalPointsPerSec correctly`
- **Setup**: Update store with snapshot containing 3 nodes with throughput: 10k, 20k, 30k pps
- **Verify**:
  - `totalPointsPerSec()` computed signal returns 60000
- **Pass Condition**: Computed value correct
- **Coverage**: `computed()` signal

#### **FE-UT-004**: MetricsWebSocketService Connect & Parse
- **Test**: `should connect to WebSocket and parse messages`
- **Setup**: Mock WebSocket, call `service.connect()`
- **Verify**:
  - WebSocket URL is `wss://{apiHost}/ws/system_metrics` (https → wss)
  - On `onmessage`, parses JSON and calls `store.update()`
  - `connected` signal is `true` after connect
- **Pass Condition**: WebSocket connection established, parsing works
- **Coverage**: `MetricsWebSocketService.connect()`, parse logic

#### **FE-UT-005**: MetricsApiService REST Calls
- **Test**: `should make HTTP GET to /api/metrics`
- **Setup**: Mock `HttpClient` via `HttpClientTestingModule`
- **Verify**:
  - `getSnapshot()` makes GET to `/api/metrics`
  - `getDagMetrics()` makes GET to `/api/metrics/dag`
  - Response is typed as `MetricsSnapshot`
- **Pass Condition**: Correct HTTP calls, typed responses
- **Coverage**: `MetricsApiService` methods

### 2.3 Frontend Unit Tests (Components)

#### **FE-UT-006**: DagOverviewPanel Rendering
- **Test**: `should render node table with DagNodeMetrics input`
- **Setup**: Create component with `DebugElement`, set `nodes` input to 2 mock nodes
- **Verify**:
  - Table renders with 2 rows
  - Columns present: Node Name, Type, Avg Exec, Last Exec, Throughput, Points, Throttled, Last Seen
  - Text content matches input data
- **Pass Condition**: All rows and columns rendered correctly
- **Coverage**: `DagOverviewPanel` template

#### **FE-UT-007**: DagOverviewPanel Empty State
- **Test**: `should show empty state when nodes array is empty`
- **Setup**: Set `nodes()` to `[]`
- **Verify**:
  - Table is not rendered
  - "No DAG nodes reporting metrics yet." message is visible
- **Pass Condition**: Empty state shows correctly
- **Coverage**: `@if (nodes().length > 0)` conditional

#### **FE-UT-008**: SystemPanel Progress Gauges
- **Test**: `should render CPU and memory progress bars with correct values`
- **Setup**: Set `systemMetrics()` input with `cpu_percent: 45`, `memory_percent: 65`
- **Verify**:
  - `syn-progress` elements rendered
  - CPU progress value is 45
  - Memory progress value is 65
  - Color classes applied based on thresholds (amber for 45, amber for 65)
- **Pass Condition**: Progress bars render with correct values and colors
- **Coverage**: `SystemPanel` template and color logic

#### **FE-UT-009**: RenderingPanel FPS Display
- **Test**: `should display FPS with color coding`
- **Setup**: Set `frontendMetrics()` with `fps: 42`
- **Verify**:
  - FPS value displayed as "42"
  - Color class is `text-amber-500` (30–55 fps = amber)
- **Pass Condition**: FPS shown with correct color
- **Coverage**: `RenderingPanel` FPS display

### 2.4 Frontend Integration Tests

#### **FE-INT-001**: Dashboard Smart Component Initialization
- **Test**: `should initialize services on ngOnInit`
- **Setup**: Create `DashboardComponent` with mocked services
- **Verify**:
  - `MetricsWebSocketService.connect()` called
  - `ComponentPerfService.startObserving()` called
  - `MetricsApiService.getSnapshot()` called for initial load
- **Pass Condition**: All services initialized in correct order
- **Coverage**: `DashboardComponent.ngOnInit()`, service coordination

#### **FE-INT-002**: Dashboard Data Flow (WS → Store → Components)
- **Test**: `should flow metrics data from WS to store to child panels`
- **Setup**: Emit a WebSocket message from mock service
- **Verify**:
  - Message is parsed and reaches `MetricsStore.update()`
  - Store signals update
  - DagOverviewPanel receives updated `dagMetrics` input
  - Panel re-renders with new data
- **Pass Condition**: Data flows end-to-end, components re-render
- **Coverage**: Full data flow pipeline

#### **FE-INT-003**: Stale Data Banner
- **Test**: `should show stale banner when WS disconnects`
- **Setup**: `MetricsWebSocketService` emits `onclose` event
- **Verify**:
  - Store's `isStale` signal becomes `true`
  - Stale banner renders in dashboard template: "Data stale — reconnecting..."
  - After WS reconnects and new data arrives, stale flag clears
- **Pass Condition**: Banner appears on disconnect, clears on reconnect
- **Coverage**: Stale state handling

### 2.5 Frontend E2E Smoke Tests

#### **FE-E2E-001**: Dashboard Route Navigation
- **Test**: Navigate to `/dashboard/performance`
- **Verify**:
  - Route loads without errors
  - Dashboard component renders
  - All panel sections visible (DAG, WebSocket, System, Rendering)
- **Pass Condition**: Route accessible and components render
- **Coverage**: Route lazy loading, navigation

#### **FE-E2E-002**: DevOnlyGuard Blocks in Production
- **Test**: In production build, try to navigate to `/dashboard/performance`
- **Verify**:
  - Route redirects to `/` (home)
  - Console warning logged: `"[DevOnly] Performance dashboard..."`
- **Pass Condition**: Route inaccessible in production build
- **Coverage**: Guard implementation

### 2.6 Frontend Performance Tests

#### **FE-PERF-001**: ThreeJsMetricsCollector Frame Recording
- **Test**: `should record frame times without blocking render loop`
- **Setup**: Simulate 60 frame samples, measure `recordFrame()` call time
- **Verify**:
  - Each `recordFrame()` call < 0.5ms
  - No accumulation of call time (not O(n))
- **Pass Condition**: Frame recording overhead < 0.05ms per frame
- **Coverage**: `ThreeJsMetricsCollector` performance

#### **FE-PERF-002**: MetricsWebSocketService Parse Latency
- **Test**: `should parse JSON WebSocket messages < 5ms`
- **Setup**: Send large metrics snapshot (10+ KB JSON)
- **Verify**:
  - Parse time measured from `onmessage` to store update
  - Latency < 5ms on typical hardware
- **Pass Condition**: Parse completes < 5ms
- **Coverage**: JSON parsing performance

#### **FE-PERF-003**: Dashboard Rendering Performance
- **Test**: `should render full dashboard without frame drops`
- **Setup**: Trigger rapid updates from MetricsStore (every 100ms)
- **Verify**:
  - 60 FPS maintained (no dropped frames in dashboard update)
  - Change detection completes < 16.67ms per frame
- **Pass Condition**: FPS > 55 during updates
- **Coverage**: Angular change detection, component rendering

### 2.7 Frontend Edge Cases & Error Paths

#### **FE-EDGE-001**: Null Metrics Graceful Rendering
- **Test**: `should render dashboard when metrics are null`
- **Setup**: Keep all metrics signals as `null`
- **Verify**:
  - No exceptions thrown
  - Empty state messages render for each panel
  - No "undefined property" errors in template
- **Pass Condition**: App stable with null metrics
- **Coverage**: Template null-safety

#### **FE-EDGE-002**: WebSocket Reconnection with Exponential Backoff
- **Test**: `should reconnect with exponential backoff after disconnect`
- **Setup**: Simulate WebSocket `onclose` event
- **Verify**:
  - First retry: 2 seconds
  - Second retry: 4 seconds
  - Backoff caps at 30 seconds
  - Max 10 attempts before giving up
- **Pass Condition**: Backoff exponential, capped at max
- **Coverage**: `MetricsWebSocketService` reconnect logic

#### **FE-EDGE-003**: API Error Response Handling
- **Test**: `should handle HTTP 503 error gracefully`
- **Setup**: Mock `MetricsApiService.getSnapshot()` to return error (metrics disabled)
- **Verify**:
  - Dashboard shows "Metrics unavailable" message
  - No unhandled promise rejection in console
- **Pass Condition**: Error handled, user notified
- **Coverage**: Error handling in API service

---

## Part 3: Integration Tests (Backend ↔ Frontend)

### 3.1 End-to-End Integration Tests

#### **INT-E2E-001**: Full Metrics Pipeline (Sensor → Backend → Dashboard)
- **Scenario**: Sensor sends 100 point cloud frames at 10 Hz
- **Verify**:
  - Backend records all 100 frames in DAG metrics
  - Metrics broadcast to WebSocket every 1 second (10 broadcasts)
  - Frontend WebSocket receives all 10 broadcasts
  - Dashboard displays smoothly updating metrics in real-time
- **Pass Condition**: 0 lost broadcasts, <100ms latency from sensor to dashboard
- **Coverage**: Full pipeline integration

#### **INT-E2E-002**: <1% Overhead Under Load
- **Scenario**: Max realistic workload: 100 Hz sensor + 10 concurrent WS clients
- **Verify**:
  - CPU overhead: < 1%
  - Memory stable (no leaks) after 60 seconds
  - All metrics accurate to within ±2%
- **Pass Condition**: Overhead < 1%, memory stable, accuracy good
- **Coverage**: Performance under realistic load

#### **INT-E2E-003**: Metrics Disable Flag Works End-to-End
- **Scenario**: Start backend with `LIDAR_ENABLE_METRICS=false`
- **Verify**:
  - GET `/api/metrics` returns 503
  - `/api/health/performance` shows `metrics_enabled: false`
  - Dashboard shows "Metrics disabled" banner
  - No metrics broadcast to WebSocket
- **Pass Condition**: Entire system respects disable flag
- **Coverage**: Configuration integration

#### **INT-E2E-004**: WebSocket Connection Lifecycle
- **Scenario**: Frontend connects → receives 3 broadcasts → disconnects → reconnects
- **Verify**:
  - Connected: WS status green, data flowing
  - After first disconnect: stale banner shows
  - After reconnect: data fresh again, stale clears
- **Pass Condition**: Full lifecycle handled correctly
- **Coverage**: Connection state transitions

#### **INT-E2E-005**: Metrics Data Consistency
- **Scenario**: Poll `/api/metrics` and receive WS broadcast simultaneously
- **Verify**:
  - Both responses have same timestamp (within ±1 second)
  - Both contain consistent node/topic counts
- **Pass Condition**: Data consistency maintained
- **Coverage**: Race conditions

#### **INT-E2E-006**: Dashboard Error Resilience
- **Scenario**: Backend metrics crash, then recover
- **Verify**:
  - Dashboard stale banner shows
  - After backend restart, dashboard recovers automatically
- **Pass Condition**: Graceful degradation and recovery
- **Coverage**: Error resilience

#### **INT-E2E-007**: Multi-Node DAG Metrics
- **Scenario**: 5-node DAG pipeline: Sensor → Downsample → Filter → Cluster → Viewer
- **Verify**:
  - All 5 nodes report metrics
  - Throughput cascades correctly (each node ≤ previous)
  - Queue depth tracked accurately
- **Pass Condition**: All nodes visible, throughput cascade correct
- **Coverage**: Multi-node DAG support

#### **INT-E2E-008**: Large Payload Handling
- **Scenario**: Broadcast a 1 MB metrics payload (simulated with many nodes)
- **Verify**:
  - Broadcast completes in < 50ms
  - Frontend receives and renders without UI freeze
  - No connection drops
- **Pass Condition**: Large payloads handled smoothly
- **Coverage**: Payload scaling

---

## Part 4: Test Coverage Matrix

### 4.1 Coverage Summary Table

| Component | Unit | Integration | E2E | Performance | Edge Cases | Coverage % |
|-----------|------|-------------|-----|-------------|-----------|-----------|
| **Backend: MetricsRegistry** | 6 | 1 | — | 1 | 2 | 87% |
| **Backend: IMetricsCollector** | 2 | 2 | 1 | 1 | 1 | 92% |
| **Backend: Instrumentation Hooks** | — | 3 | 1 | 2 | 1 | 94% |
| **Backend: Background Tasks** | — | 2 | 1 | 1 | 1 | 88% |
| **Backend: REST API** | — | — | 1 | — | 1 | 85% |
| **Backend: Middleware** | — | 1 | 1 | 1 | — | 82% |
| **Frontend: MetricsStore** | 3 | 1 | — | — | 1 | 91% |
| **Frontend: WebSocket Service** | 2 | 1 | 1 | 1 | 1 | 89% |
| **Frontend: API Service** | 1 | — | — | — | 1 | 86% |
| **Frontend: Components (5 dumb)** | 4 | 1 | 1 | — | 1 | 88% |
| **Frontend: Dashboard Smart** | — | 1 | 1 | — | 1 | 84% |
| **Frontend: ThreeJs Collector** | — | — | — | 2 | 1 | 80% |
| **TOTAL** | 18 | 12 | 8 | 6 | 12 | **87%** |

### 4.2 Critical Path Coverage (100%)

**Critical paths with mandatory 100% coverage:**

1. **BE**: `record_node_exec()` → `registry.node_metrics` write → `snapshot()` → REST endpoint response ✓
2. **BE**: `record_ws_message()` → `registry.ws_topic_metrics` write → broadcast to WS topic ✓
3. **FE**: WS message receive → `MetricsStore.update()` → Signal update → Component re-render ✓
4. **FE**: Dashboard route load → All services init → First metric display ✓
5. **INT**: Sensor frame → Backend instrumentation → WS broadcast → Frontend display ✓

---

## Part 5: Detailed Edge Cases & Non-Happy Paths

### 5.1 Backend Edge Cases

| # | Edge Case | Test Scenario | Expected Behavior |
|---|-----------|---------------|-------------------|
| **BE-EC-01** | 0-point payload | `record_node_exec(..., point_count=0)` | Recorded as-is, no division by zero in throughput calc |
| **BE-EC-02** | Negative exec time (clock skew) | `exec_ms = -1.5` (hypothetical) | Clamped to 0, logged warning |
| **BE-EC-03** | 1 million node registrations | Registry scales to 1M nodes | Snapshot < 50ms, memory < 100MB |
| **BE-EC-04** | WS message at exact 1-sec boundary | Message at t=1.0s exactly | Included or excluded consistently (implementation choice, document) |
| **BE-EC-05** | Rapid node_id changes | Same node sends under different ID per frame | Each new ID treated as separate node; de-duplication not in scope |
| **BE-EC-06** | psutil unavailable (no proc fs) | Import error on `psutil` | Graceful degradation: SystemProbe skip, continue without system metrics |
| **BE-EC-07** | Concurrent record calls | 10 threads call `record_node_exec()` simultaneously | GIL-protected, all recorded (no data loss) |
| **BE-EC-08** | Broadcaster running but registry null | Edge case in lifespan sequence | Registry always initialized before broadcaster starts |

### 5.2 Frontend Edge Cases

| # | Edge Case | Test Scenario | Expected Behavior |
|---|-----------|---------------|-------------------|
| **FE-EC-01** | WebSocket message with invalid JSON | `onmessage` receives `"{invalid"` | Error logged, store not updated, stale flag set |
| **FE-EC-02** | Signal field missing from API response | Response lacks `system` field | Handled gracefully, field treated as `null` |
| **FE-EC-03** | Very large node list (500 nodes) | Dashboard renders 500 DAG nodes | Table scrollable, no UI freeze, virtualization if needed |
| **FE-EC-04** | Rapid connect/disconnect cycles | WS connect → disconnect → connect → disconnect (10x) | Final state correct, no orphaned subscriptions |
| **FE-EC-05** | PerformanceObserver unavailable | Safari or older browser | ComponentPerfService degrades gracefully, `long_task_count` always 0 |
| **FE-EC-06** | FPS drops below 1 (very slow frame) | `frameTime = 5000ms` (5 seconds) | FPS capped at min, displayed as 0.2 FPS without error |
| **FE-EC-07** | Memory metrics > 1 TB (unrealistic) | `memory_total_mb = 1_000_000` | Displayed correctly, no overflow, unit scaling considered |
| **FE-EC-08** | Zero division in computed signal | `totalPointsPerSec` with no nodes | Returns 0, not NaN or undefined |

### 5.3 Integration Edge Cases

| # | Edge Case | Test Scenario | Expected Behavior |
|---|-----------|---------------|-------------------|
| **INT-EC-01** | Backend slow (2 sec per node exec) | Each node takes 2s to process | Metric accurately recorded at 2000ms, displayed in dashboard |
| **INT-EC-02** | Frontend never receives first WS broadcast | WebSocket delays first message >5s | Dashboard shows empty state, REST fallback loads initial data |
| **INT-EC-03** | Metrics enabled then disabled mid-session | `LIDAR_ENABLE_METRICS` changes value | Behavior undefined (not a use case), but document assumption |
| **INT-EC-04** | Frontend makes request while broadcaster sends | Concurrent HTTP GET `/api/metrics` + WS broadcast | Both serve consistent state without race conditions |
| **INT-EC-05** | Node never reports any metrics | Silent node (processes but doesn't call `on_input()`) | Node absent from dashboard; expected behavior, document |

---

## Part 6: Performance Validation Criteria

### 6.1 <1% Overhead Requirement

**Definition**: Total CPU overhead of metrics collection must be < 1% of baseline system CPU under typical workload.

**Baseline Workload**:
- 100 Hz sensor input (10ms intervals)
- 10 Hz WebSocket broadcast to 5 clients
- 20 API requests/sec (avg 10 concurrent)
- ~100 active threads

**Measurement Method**:
1. Run system for 60 seconds WITHOUT metrics enabled
2. Record average CPU usage over 60 seconds → **baseline_cpu**
3. Run same workload WITH `LIDAR_ENABLE_METRICS=true`
4. Record average CPU usage → **with_metrics_cpu**
5. Calculate overhead: `(with_metrics_cpu - baseline_cpu) / baseline_cpu`

**Pass Criterion**: `overhead < 0.01` (i.e., < 1%)

**Sampling Methodology**:
- Use `psutil.cpu_percent(interval=1)` for 60 samples
- Discard first 10 samples (warmup)
- Calculate mean of remaining 50 samples
- Run test 3 times, report mean, min, max

**Test Case**: `BE-PERF-006` in backend tests

### 6.2 Real-Time Metrics Accuracy

**Latency Targets**:
- Sensor → Backend recording: < 5ms
- Backend → WebSocket broadcast: < 50ms
- Frontend receive → Dashboard display: < 100ms
- **Total end-to-end**: < 200ms

**Accuracy Targets**:
- Throughput (pps): ±5% (e.g., if actual is 65,000 pps, recorded is 61,750–68,250)
- Latency (ms): ±10% (e.g., if node exec is 2.0ms, recorded is 1.8–2.2ms)
- CPU percent: ±10% absolute (e.g., if actual is 45%, recorded is 40.5–49.5%)

**Verification**: During `INT-E2E-002` load test, compare sampled true values (via instrumentation) vs dashboard-displayed values

### 6.3 Dashboard UX Metrics

- **Time-to-Interactive**: Dashboard fully functional within 2 seconds of page load
- **Update Latency**: Data displayed within 500ms of backend broadcast
- **Render Frame Rate**: 60 FPS maintained while updating metrics (no dropped frames)
- **No UI Freezes**: All animations and interactions responsive (< 100ms response time)

---

## Part 7: Test Execution Plan

### 7.1 Test Execution Order

1. **Phase 1 — Backend Unit Tests** (BE-UT-001 through BE-UT-006)
   - Duration: ~10 minutes
   - Dependency: None
   - Gate: Must pass 100% before Phase 2

2. **Phase 2 — Backend Integration Tests** (BE-IT-001 through BE-IT-007)
   - Duration: ~15 minutes
   - Dependency: Phase 1 passed
   - Gate: Must pass 100% before Phase 3

3. **Phase 3 — Backend API Tests** (BE-API-001 through BE-API-005)
   - Duration: ~10 minutes
   - Dependency: Phase 2 passed
   - Gate: Must pass 100% before Phase 4

4. **Phase 4 — Backend Performance Tests** (BE-PERF-001 through BE-PERF-006)
   - Duration: ~30 minutes (includes long load test)
   - Dependency: Phase 3 passed
   - Gate: Overhead < 1% required
   - **CRITICAL**: Run on isolated machine, no background processes

5. **Phase 5 — Backend Edge Cases** (BE-EDGE-001 through BE-EDGE-004)
   - Duration: ~10 minutes
   - Dependency: Phase 4 passed
   - Gate: Must pass 100%

6. **Phase 6 — Frontend Unit Tests** (FE-UT-001 through FE-UT-009)
   - Duration: ~15 minutes
   - Dependency: None (can run parallel with Phases 1–3)
   - Gate: Must pass 100% before Phase 7

7. **Phase 7 — Frontend Integration Tests** (FE-INT-001 through FE-INT-003)
   - Duration: ~10 minutes
   - Dependency: Phase 6 passed
   - Gate: Must pass 100%

8. **Phase 8 — Frontend E2E Smoke Tests** (FE-E2E-001 through FE-E2E-002)
   - Duration: ~5 minutes
   - Dependency: Phase 7 passed
   - Gate: Route must be accessible and functional

9. **Phase 9 — Frontend Performance Tests** (FE-PERF-001 through FE-PERF-003)
   - Duration: ~20 minutes
   - Dependency: Phase 8 passed
   - Gate: Frame rate > 55 FPS required

10. **Phase 10 — Frontend Edge Cases** (FE-EDGE-001 through FE-EDGE-003)
    - Duration: ~10 minutes
    - Dependency: Phase 9 passed
    - Gate: Must pass 100%

11. **Phase 11 — Integration Tests** (INT-E2E-001 through INT-E2E-008)
    - Duration: ~40 minutes (includes 60-sec load test)
    - Dependency: Phases 4 and 9 passed
    - Gate: <1% overhead, all metrics correct, no data loss
    - **CRITICAL**: Run with both backend and frontend running

### 7.2 Test Failure Escalation

| Failure | Action | Owner |
|---------|--------|-------|
| Unit test fails | Fix code, re-run unit tests, retry integration | @be-dev or @fe-dev |
| Integration test fails | Debug interaction, may require code change + unit test update | @be-dev + @fe-dev |
| Overhead > 1% | Profile hot path, optimize or redesign approach | @be-dev |
| E2E test fails | May indicate real deployment issue, escalate to @architecture | @qa |

### 7.3 Test Artifacts & Reporting

**Test Results Artifact**: `.opencode/plans/performance-monitoring/qa-report.md` (generated after all phases pass)

**Contents**:
- Summary: Pass/Fail for each test phase
- Coverage report: Code coverage % for backend and frontend
- Performance results: Overhead measurement, latency samples
- Screenshots/logs: Key dashboard states, error scenarios
- Recommendations: Any issues for follow-up

---

## Part 8: Mock Data Strategy

### 8.1 Backend Mock Data

**Used In**: Unit and integration tests, frontend parallel development

**Location**: `tests/fixtures/metrics_fixtures.py` (Python)

**Key Fixtures**:
- `mock_node_metric_sample()` — Returns realistic `NodeMetricsSample`
- `mock_ws_topic_sample()` — Returns realistic `WsTopicSample`
- `mock_system_metric_sample()` — Returns realistic `SystemMetricsSample`
- `mock_metrics_snapshot()` — Returns full `MetricsSnapshotModel`

### 8.2 Frontend Mock Data

**Used In**: Frontend unit tests, component development, manual testing

**Location**: `web/src/app/core/services/mocks/metrics-mock.service.ts` (TypeScript)

**Key Constant**: `MOCK_METRICS_SNAPSHOT` (from `api-spec.md §6`)

**Mock Service**: `MetricsMockService` (implements same interface as real service, emits evolving fake data)

---

## Part 9: Risk Mitigation

### 9.1 Known Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| GIL contention with high concurrency | Metrics recording could block Python threads | Use atomic counters for thread-safe ops; test with 10+ concurrent threads |
| WebSocket broadcast latency under high client load | Dashboard lag | Load test with 20+ concurrent WS clients; consider compression if needed |
| Three.js render stalls when updating large geometries | Dashboard displays stale FPS | Profile buffer mutation time; consider batching updates |
| Frontend stale data flag design | Users confused by reconnect banner | Clear messaging: "Data stale — reconnecting in Xs" with countdown |
| Browser PerformanceObserver not available | Missing long-task metrics | Graceful degradation: log warning, set `long_task_count = 0` |

### 9.2 Test Environment Requirements

**Backend**:
- Python 3.10+
- psutil available (or graceful skip)
- Asyncio event loop available
- No network constraints (local testing)

**Frontend**:
- Angular 20
- Chrome/Chromium for E2E tests
- No browser extensions that block WebSockets
- Hardware: >= 8GB RAM, SSD for test performance

**Integration**:
- Both backend and frontend running
- Network: localhost only (no latency)
- System under test: isolated machine with <5% baseline CPU usage

---

## Part 10: Test Maintenance & Updates

### 10.1 When Tests Must Be Updated

1. **API Schema Changes** — Update all affected test fixtures and mocks
2. **Performance Requirements Changed** — Recalibrate thresholds in performance tests
3. **Component Refactor** — Update component unit tests to match new structure
4. **New Feature Added** — Add new test cases for the feature

### 10.2 Test Code Guidelines

- **No hardcoded values** — Use `MOCK_*` constants for maintainability
- **Descriptive names** — Test names should state "given X, should do Y"
- **Setup/Verify separation** — Clear AAA (Arrange/Act/Assert) pattern
- **Documented edge cases** — Comments explaining why each edge case matters

---

## APPROVAL CHECKLIST

### For User Review:

- [ ] **Test Coverage**: 87% overall coverage acceptable for this feature?
- [ ] **Overhead Target**: <1% CPU overhead is the correct requirement?
- [ ] **Real-Time Latency**: <200ms end-to-end is reasonable?
- [ ] **Performance Thresholds**: FPS > 55, parse < 5ms, render < 16.67ms acceptable?
- [ ] **Edge Cases**: All 12 edge cases listed are relevant to your use case?
- [ ] **Test Count**: 74 total tests (18 backend unit, 12 backend integration, 8 E2E, 6 performance, 12 edge cases, 18 frontend unit) is sufficient?
- [ ] **Execution Timeline**: 150-minute total test execution time acceptable for CI/CD?
- [ ] **Mock Data**: Using `MOCK_METRICS_SNAPSHOT` from `api-spec.md §6` for frontend dev?

### For QA Sign-Off:

- [ ] Test plan is locked and ready for implementation
- [ ] All 74 test cases documented with clear pass/fail criteria
- [ ] Performance validation methodology documented and reproducible
- [ ] Edge cases comprehensive and cover non-happy paths
- [ ] Integration tests cover end-to-end data flow
- [ ] Approval from User + Architect obtained before proceeding to code

---

## Next Steps (Upon Approval)

1. **User Review** — Address any questions, adjust thresholds if needed
2. **QA Finalization** — Lock this document, do not modify without new review
3. **Dev Implementation** — @be-dev and @fe-dev implement according to this plan
4. **Test Implementation** — @qa writes all 74 test cases per this spec
5. **Test Execution** — 11-phase test plan executed in order
6. **Report Generation** — `qa-report.md` artifact created with full results

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-01  
**Status**: AWAITING USER APPROVAL  
**Author**: @qa  
