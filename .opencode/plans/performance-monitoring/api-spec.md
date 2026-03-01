# Performance Monitoring — API & Interface Specification

> **Role**: The authoritative contract between `@be-dev` and `@fe-dev`.
> **Rule**: `@fe-dev` MUST mock all responses from this spec while `@be-dev` implements.
> **Relates to**: `requirements.md`, `technical.md`

---

## 1. Transport Overview

| Channel | Protocol | Direction | Purpose |
|---|---|---|---|
| `WS /ws/system_metrics` | WebSocket JSON | Server → Client | 1 Hz push of `MetricsSnapshot` |
| `GET /api/metrics` | HTTP JSON | Client → Server | Full snapshot on demand |
| `GET /api/metrics/dag` | HTTP JSON | Client → Server | DAG-only snapshot on demand |
| `GET /api/metrics/websocket` | HTTP JSON | Client → Server | WebSocket metrics snapshot |
| `GET /api/health/performance` | HTTP JSON | Client → Server | Lightweight health probe |

All REST endpoints are **read-only (GET)**. No authentication required (developer tool only). All responses use `Content-Type: application/json`.

---

## 2. WebSocket Interface

### 2.1 Connection

```
URL: ws://{host}/ws/system_metrics
Binary Type: text (JSON frames only — NOT binary LIDR protocol)
Reconnect: exponential backoff, max 10 attempts
```

### 2.2 Server → Client Message: `MetricsSnapshot`

Sent at **1 Hz** (every 1000 ms). There is no client-to-server message format — this channel is push-only.

```json
{
  "timestamp": 1740825600.123,
  "dag": { ... },
  "websocket": { ... },
  "system": { ... },
  "endpoints": [ ... ]
}
```

Full schema defined in Section 4.

---

## 3. REST Endpoints

### 3.1 `GET /api/metrics`

**Description**: Returns a full `MetricsSnapshot` — identical payload to the WebSocket push. Use this for initial page load or one-off polling.

**Response `200 OK`**:
```json
{
  "timestamp": 1740825600.123,
  "dag": {
    "nodes": [
      {
        "node_id": "abc12345-abcd-...",
        "node_name": "SICK LiDAR Front",
        "node_type": "sick_lidar",
        "last_exec_ms": 2.14,
        "avg_exec_ms": 1.97,
        "calls_total": 8402,
        "throughput_pps": 65000.0,
        "last_point_count": 65536,
        "throttled_count": 12,
        "queue_depth": 3,
        "last_seen_ts": 1740825600.100
      }
    ],
    "total_nodes": 1,
    "running_nodes": 1
  },
  "websocket": {
    "topics": {
      "sick_lidar_front_abc12345": {
        "messages_per_sec": 10.0,
        "bytes_per_sec": 3145728.0,
        "active_connections": 1,
        "total_messages": 8402,
        "total_bytes": 26474790912
      }
    },
    "total_connections": 1
  },
  "system": {
    "cpu_percent": 14.5,
    "memory_used_mb": 312.4,
    "memory_total_mb": 16384.0,
    "memory_percent": 1.9,
    "thread_count": 18,
    "queue_depth": 3
  },
  "endpoints": [
    {
      "path": "/api/nodes",
      "method": "GET",
      "avg_latency_ms": 4.2,
      "calls_total": 150,
      "last_status_code": 200
    }
  ]
}
```

**Error Responses**:
- `503 Service Unavailable` — metrics collector not initialized (metrics disabled)

---

### 3.2 `GET /api/metrics/dag`

**Description**: DAG-only subset. Useful for the node table in the dashboard without transferring full system payload.

**Response `200 OK`**:
```json
{
  "timestamp": 1740825600.123,
  "nodes": [
    {
      "node_id": "abc12345-abcd-...",
      "node_name": "SICK LiDAR Front",
      "node_type": "sick_lidar",
      "last_exec_ms": 2.14,
      "avg_exec_ms": 1.97,
      "calls_total": 8402,
      "throughput_pps": 65000.0,
      "last_point_count": 65536,
      "throttled_count": 12,
      "queue_depth": 3,
      "last_seen_ts": 1740825600.100
    }
  ],
  "total_nodes": 1,
  "running_nodes": 1
}
```

---

### 3.3 `GET /api/metrics/websocket`

**Description**: WebSocket metrics only. Useful for diagnosing streaming performance.

**Response `200 OK`**:
```json
{
  "timestamp": 1740825600.123,
  "topics": {
    "sick_lidar_front_abc12345": {
      "messages_per_sec": 10.0,
      "bytes_per_sec": 3145728.0,
      "active_connections": 1,
      "total_messages": 8402,
      "total_bytes": 26474790912
    }
  },
  "total_connections": 1
}
```

---

### 3.4 `GET /api/health/performance`

**Description**: Lightweight health check. Returns a boolean summary without transferring large metric payloads. Intended for polling / monitoring readiness checks.

**Response `200 OK`**:
```json
{
  "metrics_enabled": true,
  "broadcaster_running": true,
  "system_probe_running": true,
  "node_count": 3,
  "version": "1.0.0"
}
```

**Response `200 OK` (metrics disabled)**:
```json
{
  "metrics_enabled": false,
  "broadcaster_running": false,
  "system_probe_running": false,
  "node_count": 0,
  "version": "1.0.0"
}
```

---

## 4. Canonical Data Schemas

### 4.1 `MetricsSnapshot` (Root envelope)

| Field | Type | Description |
|---|---|---|
| `timestamp` | `float` | Unix epoch seconds (UTC) at collection time |
| `dag` | `DagMetrics` | DAG processing metrics |
| `websocket` | `WebSocketMetrics` | WS streaming metrics |
| `system` | `SystemMetrics` | OS-level resource metrics |
| `endpoints` | `EndpointMetrics[]` | FastAPI route latency metrics |

---

### 4.2 `DagMetrics`

| Field | Type | Description |
|---|---|---|
| `nodes` | `DagNodeMetrics[]` | Per-node metric records |
| `total_nodes` | `int` | Total registered nodes in DAG |
| `running_nodes` | `int` | Nodes currently processing |

---

### 4.3 `DagNodeMetrics`

| Field | Type | Nullable | Description |
|---|---|---|---|
| `node_id` | `string` | No | UUID of the DAG node |
| `node_name` | `string` | No | Human-readable display name |
| `node_type` | `string` | No | Module type string (e.g. `"sick_lidar"`) |
| `last_exec_ms` | `float` | No | Wall-clock time of the last `on_input()` call (ms) |
| `avg_exec_ms` | `float` | No | Rolling 60-sample average execution time (ms) |
| `calls_total` | `int` | No | Total `on_input()` invocations since startup |
| `throughput_pps` | `float` | No | Points processed per second (last 1-sec window) |
| `last_point_count` | `int` | No | Number of points in the last processed frame |
| `throttled_count` | `int` | No | Frames dropped by throttle manager |
| `queue_depth` | `int` | No | Current depth of the multiprocessing data queue |
| `last_seen_ts` | `float` | No | Unix timestamp of last `on_input()` call |

---

### 4.4 `WebSocketMetrics`

| Field | Type | Description |
|---|---|---|
| `topics` | `Record<string, WsTopicMetrics>` | Per-topic stats keyed by topic name |
| `total_connections` | `int` | Total active WebSocket connections across all topics |

### 4.5 `WsTopicMetrics`

| Field | Type | Description |
|---|---|---|
| `messages_per_sec` | `float` | Messages broadcast in the last 1-sec window |
| `bytes_per_sec` | `float` | Bytes broadcast in the last 1-sec window |
| `active_connections` | `int` | Current subscriber count for this topic |
| `total_messages` | `int` | Total messages since startup |
| `total_bytes` | `int` | Total bytes since startup |

---

### 4.6 `SystemMetrics`

| Field | Type | Description |
|---|---|---|
| `cpu_percent` | `float` | Overall CPU utilization (0–100) |
| `memory_used_mb` | `float` | RSS memory used (megabytes) |
| `memory_total_mb` | `float` | Total physical memory (megabytes) |
| `memory_percent` | `float` | Memory utilization (0–100) |
| `thread_count` | `int` | Active Python thread count |
| `queue_depth` | `int` | Current items in the multiprocessing sensor queue |

---

### 4.7 `EndpointMetrics`

| Field | Type | Description |
|---|---|---|
| `path` | `string` | API route path (e.g. `"/api/nodes"`) |
| `method` | `string` | HTTP method (`"GET"`, `"POST"`, etc.) |
| `avg_latency_ms` | `float` | Rolling average latency (ms) |
| `calls_total` | `int` | Total calls since startup |
| `last_status_code` | `int` | HTTP status code of the last response |

---

## 5. Frontend-Only Data Shapes (never sent to backend)

These interfaces are defined in `web/src/app/core/models/metrics.model.ts` and used exclusively within the Angular application.

### 5.1 `FrontendMetricsPayload`

Produced by `ThreeJsMetricsCollector` and `ComponentPerfService`. Stored in `MetricsStore`.

```typescript
export interface FrontendMetricsPayload {
  /** Measured frames-per-second over the last 60 frames */
  fps: number;

  /** Average Three.js renderer.render() call time (ms) */
  avg_render_ms: number;

  /** Average BufferGeometry attribute write time (ms) */
  avg_buffer_mutation_ms: number;

  /** Count of long tasks (>50ms) observed in the last 1-sec window */
  long_task_count: number;

  /** Total long task blocking duration (ms) in the last 1-sec window */
  long_task_total_ms: number;

  /** WebSocket frames received per second, keyed by topic */
  ws_frames_per_sec: Record<string, number>;

  /** DataView parse latency per frame in ms, keyed by topic */
  ws_parse_latency_ms: Record<string, number>;

  /** Bytes received per second, keyed by topic */
  ws_bytes_per_sec: Record<string, number>;

  /** Unix timestamp (ms) when this snapshot was collected */
  collected_at: number;
}
```

---

### 5.2 `MetricsSnapshot` (TypeScript — mirrors backend)

```typescript
export interface MetricsSnapshot {
  timestamp: number;
  dag: DagMetrics;
  websocket: WebSocketMetrics;
  system: SystemMetrics;
  endpoints: EndpointMetrics[];
}

export interface DagMetrics {
  nodes: DagNodeMetrics[];
  total_nodes: number;
  running_nodes: number;
}

export interface DagNodeMetrics {
  node_id: string;
  node_name: string;
  node_type: string;
  last_exec_ms: number;
  avg_exec_ms: number;
  calls_total: number;
  throughput_pps: number;
  last_point_count: number;
  throttled_count: number;
  queue_depth: number;
  last_seen_ts: number;
}

export interface WebSocketMetrics {
  topics: Record<string, WsTopicMetrics>;
  total_connections: number;
}

export interface WsTopicMetrics {
  messages_per_sec: number;
  bytes_per_sec: number;
  active_connections: number;
  total_messages: number;
  total_bytes: number;
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  memory_percent: number;
  thread_count: number;
  queue_depth: number;
}

export interface EndpointMetrics {
  path: string;
  method: string;
  avg_latency_ms: number;
  calls_total: number;
  last_status_code: number;
}
```

---

## 6. Mock Data Specification (for `@fe-dev` parallel development)

`@fe-dev` MUST use the following mock response as the base for a `MetricsMockService` that implements the same interface as `MetricsWebSocketService`:

```typescript
// mock-metrics.ts  (placed in core/services/mocks/)
export const MOCK_METRICS_SNAPSHOT: MetricsSnapshot = {
  timestamp: Date.now() / 1000,
  dag: {
    nodes: [
      {
        node_id: "node-aaa-111",
        node_name: "SICK LiDAR Front",
        node_type: "sick_lidar",
        last_exec_ms: 2.14,
        avg_exec_ms: 1.97,
        calls_total: 8402,
        throughput_pps: 65000,
        last_point_count: 65536,
        throttled_count: 12,
        queue_depth: 3,
        last_seen_ts: Date.now() / 1000 - 0.1
      },
      {
        node_id: "node-bbb-222",
        node_name: "Voxel Downsample",
        node_type: "voxel_filter",
        last_exec_ms: 8.33,
        avg_exec_ms: 7.85,
        calls_total: 8390,
        throughput_pps: 58000,
        last_point_count: 32000,
        throttled_count: 0,
        queue_depth: 0,
        last_seen_ts: Date.now() / 1000 - 0.15
      }
    ],
    total_nodes: 2,
    running_nodes: 2
  },
  websocket: {
    topics: {
      "sick_lidar_front_node-aaa": {
        messages_per_sec: 10,
        bytes_per_sec: 3145728,
        active_connections: 1,
        total_messages: 8402,
        total_bytes: 26474790912
      }
    },
    total_connections: 1
  },
  system: {
    cpu_percent: 14.5,
    memory_used_mb: 312.4,
    memory_total_mb: 16384,
    memory_percent: 1.9,
    thread_count: 18,
    queue_depth: 3
  },
  endpoints: [
    {
      path: "/api/nodes",
      method: "GET",
      avg_latency_ms: 4.2,
      calls_total: 150,
      last_status_code: 200
    }
  ]
};
```

---

## 7. Error Handling

| Scenario | Backend Behavior | Frontend Behavior |
|---|---|---|
| Metrics disabled (`NullCollector`) | `GET /api/metrics` returns `503` | Dashboard shows "Metrics disabled" banner |
| WS connection lost | N/A | `MetricsWebSocketService` reconnects with backoff; store retains last values with `stale` flag |
| Snapshot serialization error | Log error, skip broadcast cycle | No new data; last snapshot remains displayed |
| Node not yet seen | Node absent from `dag.nodes` array | Dashboard shows only nodes that have reported |

---

## 8. Versioning

The `MetricsSnapshot` format is versioned via the `/api/health/performance` `version` field. Breaking changes to the schema require a version bump and update to this spec before any implementation proceeds.

Current schema version: **`1.0.0`**
