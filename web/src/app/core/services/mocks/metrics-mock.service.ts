// DEV ONLY — remove injection before production

import { Injectable, signal } from '@angular/core';
import { MetricsSnapshot } from '../../models/metrics.model';
import { MetricsStoreService } from '../stores/metrics-store.service';

/**
 * Mock data for frontend development - matches api-spec.md §6
 * Provides evolving fake data to enable dashboard development before backend is ready
 */
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

/**
 * Mock service that replaces MetricsWebSocketService during development
 * Feeds MetricsStore with evolving fake data at 1 Hz via setInterval
 * Implements same public interface as real MetricsWebSocketService
 */
@Injectable({
  providedIn: 'root',
})
export class MetricsMockService {
  private interval: any = null;
  private frameCounter = 0;

  // Same public interface as MetricsWebSocketService
  public connected = signal<boolean>(false);

  constructor(private metricsStore: MetricsStoreService) {}

  /**
   * Starts mock data generation at 1 Hz
   */
  connect(): void {
    if (this.interval) {
      return; // Already running
    }

    this.connected.set(true);
    console.log('[MetricsMock] Starting mock metrics feed at 1 Hz');

    this.interval = setInterval(() => {
      const snapshot = this.generateEvolvedSnapshot();
      this.metricsStore.update(snapshot);
      this.frameCounter++;
    }, 1000);
  }

  /**
   * Stops mock data generation
   */
  disconnect(): void {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    this.connected.set(false);
    this.frameCounter = 0;
    console.log('[MetricsMock] Stopped mock metrics feed');
  }

  /**
   * Generates a slightly randomized version of MOCK_METRICS_SNAPSHOT
   * Values evolve over time to simulate real system behavior
   */
  private generateEvolvedSnapshot(): MetricsSnapshot {
    const baseSnapshot = JSON.parse(JSON.stringify(MOCK_METRICS_SNAPSHOT)) as MetricsSnapshot;
    
    // Update timestamp
    baseSnapshot.timestamp = Date.now() / 1000;

    // Evolve DAG node metrics slightly
    baseSnapshot.dag.nodes.forEach(node => {
      // Randomize execution times slightly (±0.5ms)
      node.last_exec_ms += (Math.random() - 0.5) * 0.5;
      node.avg_exec_ms += (Math.random() - 0.5) * 0.2;
      
      // Ensure values stay positive
      node.last_exec_ms = Math.max(0.1, node.last_exec_ms);
      node.avg_exec_ms = Math.max(0.1, node.avg_exec_ms);
      
      // Increment counters
      node.calls_total += 1;
      
      // Vary throughput slightly (±10%)
      const baseThrough = node.node_type === 'sick_lidar' ? 65000 : 58000;
      node.throughput_pps = baseThrough + (Math.random() - 0.5) * baseThrough * 0.2;
      
      // Update last seen
      node.last_seen_ts = baseSnapshot.timestamp - Math.random() * 0.2;
    });

    // Evolve system metrics
    baseSnapshot.system.cpu_percent += (Math.random() - 0.5) * 5;
    baseSnapshot.system.cpu_percent = Math.max(0, Math.min(100, baseSnapshot.system.cpu_percent));
    
    baseSnapshot.system.memory_percent += (Math.random() - 0.5) * 2;
    baseSnapshot.system.memory_percent = Math.max(0, Math.min(100, baseSnapshot.system.memory_percent));
    
    // Update memory used based on percentage
    baseSnapshot.system.memory_used_mb = (baseSnapshot.system.memory_percent / 100) * baseSnapshot.system.memory_total_mb;

    // Evolve WebSocket metrics
    Object.values(baseSnapshot.websocket.topics).forEach(topic => {
      topic.messages_per_sec += (Math.random() - 0.5) * 2;
      topic.messages_per_sec = Math.max(1, topic.messages_per_sec);
      
      topic.total_messages += Math.floor(topic.messages_per_sec);
      topic.total_bytes += Math.floor(topic.bytes_per_sec);
    });

    return baseSnapshot;
  }
}