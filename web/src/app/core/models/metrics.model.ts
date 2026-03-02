// Metrics TypeScript interfaces matching API specification from api-spec.md
// This file is the single source of truth for metrics data shapes in the frontend

// === BACKEND DATA SHAPES (from api-spec.md) ===

/**
 * Root envelope for all metrics data from backend
 * Sent via WebSocket at 1 Hz and available via REST GET /api/metrics
 */
export interface MetricsSnapshot {
  /** Unix epoch seconds (UTC) at collection time */
  timestamp: number;
  /** DAG processing metrics */
  dag: DagMetrics;
  /** WebSocket streaming metrics */
  websocket: WebSocketMetrics;
  /** OS-level resource metrics */
  system: SystemMetrics;
  /** FastAPI route latency metrics */
  endpoints: EndpointMetrics[];
}

/**
 * DAG processing metrics container
 */
export interface DagMetrics {
  /** Per-node metric records */
  nodes: DagNodeMetrics[];
  /** Total registered nodes in DAG */
  total_nodes: number;
  /** Nodes currently processing */
  running_nodes: number;
}

/**
 * Individual DAG node performance metrics
 */
export interface DagNodeMetrics {
  /** UUID of the DAG node */
  node_id: string;
  /** Human-readable display name */
  node_name: string;
  /** Module type string (e.g. "sick_lidar") */
  node_type: string;
  /** Wall-clock time of the last on_input() call (ms) */
  last_exec_ms: number;
  /** Rolling 60-sample average execution time (ms) */
  avg_exec_ms: number;
  /** Total on_input() invocations since startup */
  calls_total: number;
  /** Points processed per second (last 1-sec window) */
  throughput_pps: number;
  /** Number of points in the last processed frame */
  last_point_count: number;
  /** Frames dropped by throttle manager */
  throttled_count: number;
  /** Current depth of the multiprocessing data queue */
  queue_depth: number;
  /** Unix timestamp of last on_input() call */
  last_seen_ts: number;
}

/**
 * WebSocket streaming metrics container
 */
export interface WebSocketMetrics {
  /** Per-topic stats keyed by topic name */
  topics: Record<string, WsTopicMetrics>;
  /** Total active WebSocket connections across all topics */
  total_connections: number;
}

/**
 * Individual WebSocket topic performance metrics
 */
export interface WsTopicMetrics {
  /** Messages broadcast in the last 1-sec window */
  messages_per_sec: number;
  /** Bytes broadcast in the last 1-sec window */
  bytes_per_sec: number;
  /** Current subscriber count for this topic */
  active_connections: number;
  /** Total messages since startup */
  total_messages: number;
  /** Total bytes since startup */
  total_bytes: number;
}

/**
 * OS-level system resource metrics
 */
export interface SystemMetrics {
  /** Overall CPU utilization (0–100) */
  cpu_percent: number;
  /** RSS memory used (megabytes) */
  memory_used_mb: number;
  /** Total physical memory (megabytes) */
  memory_total_mb: number;
  /** Memory utilization (0–100) */
  memory_percent: number;
  /** Active Python thread count */
  thread_count: number;
  /** Current items in the multiprocessing sensor queue */
  queue_depth: number;
}

/**
 * FastAPI endpoint performance metrics
 */
export interface EndpointMetrics {
  /** API route path (e.g. "/api/nodes") */
  path: string;
  /** HTTP method ("GET", "POST", etc.) */
  method: string;
  /** Rolling average latency (ms) */
  avg_latency_ms: number;
  /** Total calls since startup */
  calls_total: number;
  /** HTTP status code of the last response */
  last_status_code: number;
}

/**
 * Health check response from GET /api/health/performance
 */
export interface PerformanceHealthResponse {
  /** Whether metrics collection is enabled */
  metrics_enabled: boolean;
  /** Whether the metrics broadcaster is running */
  broadcaster_running: boolean;
  /** Whether the system probe is running */
  system_probe_running: boolean;
  /** Number of nodes currently reporting metrics */
  node_count: number;
  /** Backend version string */
  version: string;
}

// === FRONTEND-ONLY DATA SHAPES ===

/**
 * Frontend performance metrics payload
 * Produced by ThreeJsMetricsCollector and ComponentPerfService
 * Stored in MetricsStore, never sent to backend
 */
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