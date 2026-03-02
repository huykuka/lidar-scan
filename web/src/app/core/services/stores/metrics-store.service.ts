import { Injectable, computed, signal } from '@angular/core';
import { 
  MetricsSnapshot, 
  DagMetrics, 
  WebSocketMetrics, 
  SystemMetrics, 
  EndpointMetrics, 
  FrontendMetricsPayload 
} from '../../models/metrics.model';

/**
 * Signal-based store for performance metrics data.
 * Single write point for all metrics data in the frontend.
 * Follows Angular Signals architecture with private writable signals and public read-only views.
 */
@Injectable({ providedIn: 'root' })
export class MetricsStoreService {
  // Private writable signals using # private field syntax
  readonly #dagMetrics = signal<DagMetrics | null>(null);
  readonly #wsMetrics = signal<WebSocketMetrics | null>(null);
  readonly #systemMetrics = signal<SystemMetrics | null>(null);
  readonly #endpointMetrics = signal<EndpointMetrics[] | null>(null);
  readonly #frontendMetrics = signal<FrontendMetricsPayload | null>(null);
  readonly #lastUpdatedAt = signal<number | null>(null);
  readonly #isStale = signal<boolean>(false);

  // Public read-only signals exposed via .asReadonly()
  readonly dagMetrics = this.#dagMetrics.asReadonly();
  readonly wsMetrics = this.#wsMetrics.asReadonly();
  readonly systemMetrics = this.#systemMetrics.asReadonly();
  readonly endpointMetrics = this.#endpointMetrics.asReadonly();
  readonly frontendMetrics = this.#frontendMetrics.asReadonly();
  readonly lastUpdatedAt = this.#lastUpdatedAt.asReadonly();
  readonly isStale = this.#isStale.asReadonly();

  // Computed derived signals
  readonly totalPointsPerSec = computed(() => {
    const dag = this.#dagMetrics();
    if (!dag?.nodes) return 0;
    return dag.nodes.reduce((sum, node) => sum + node.throughput_pps, 0);
  });

  readonly worstNodeLatencyMs = computed(() => {
    const dag = this.#dagMetrics();
    if (!dag?.nodes || dag.nodes.length === 0) return null;
    return Math.max(...dag.nodes.map(node => node.avg_exec_ms));
  });

  readonly activeNodeCount = computed(() => {
    const dag = this.#dagMetrics();
    return dag?.running_nodes || 0;
  });

  // Public methods
  
  /**
   * Updates all backend metrics from a snapshot and resets stale state
   * @param snapshot Full metrics snapshot from backend WebSocket or REST
   */
  update(snapshot: MetricsSnapshot): void {
    this.#dagMetrics.set(snapshot.dag);
    this.#wsMetrics.set(snapshot.websocket);
    this.#systemMetrics.set(snapshot.system);
    this.#endpointMetrics.set(snapshot.endpoints);
    this.#lastUpdatedAt.set(snapshot.timestamp);
    this.#isStale.set(false);
  }

  /**
   * Updates frontend-specific metrics payload
   * @param payload Frontend metrics from ThreeJsMetricsCollector and ComponentPerfService
   */
  updateFrontend(payload: FrontendMetricsPayload): void;
  updateFrontend(partialPayload: Partial<FrontendMetricsPayload>): void;
  updateFrontend(payload: FrontendMetricsPayload | Partial<FrontendMetricsPayload>): void {
    if (this.isPartialPayload(payload)) {
      // Partial update - merge with existing frontend metrics
      const current = this.#frontendMetrics();
      if (current) {
        this.#frontendMetrics.set({ ...current, ...payload });
      } else {
        // If no existing frontend metrics, create a base payload with defaults
        const basePayload: FrontendMetricsPayload = {
          fps: 0,
          avg_render_ms: 0,
          avg_buffer_mutation_ms: 0,
          long_task_count: 0,
          long_task_total_ms: 0,
          ws_frames_per_sec: {},
          ws_parse_latency_ms: {},
          ws_bytes_per_sec: {},
          collected_at: Date.now(),
          ...payload
        };
        this.#frontendMetrics.set(basePayload);
      }
    } else {
      // Full update
      this.#frontendMetrics.set(payload);
    }
  }

  /**
   * Marks metrics as stale (WebSocket disconnected)
   */
  markStale(): void {
    this.#isStale.set(true);
  }

  /**
   * Type guard to check if payload is partial
   */
  private isPartialPayload(
    payload: FrontendMetricsPayload | Partial<FrontendMetricsPayload>
  ): payload is Partial<FrontendMetricsPayload> {
    // If any required field is missing, it's a partial payload
    return (
      payload.fps === undefined ||
      payload.avg_render_ms === undefined ||
      payload.avg_buffer_mutation_ms === undefined ||
      payload.collected_at === undefined
    );
  }
}