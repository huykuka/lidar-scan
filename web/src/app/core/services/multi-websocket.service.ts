import { Injectable, inject } from '@angular/core';
import { Subject, Observable } from 'rxjs';
import { MetricsStoreService } from './stores/metrics-store.service';

export interface WebSocketMessage {
  topic: string;
  data: any;
}

interface TopicStats {
  framesThisSec: number;
  bytesThisSec: number;
  parseTimes: number[]; // max 60 entries
}

/**
 * Service for managing multiple WebSocket connections simultaneously
 * Extended with per-topic performance metrics collection
 */
@Injectable({
  providedIn: 'root',
})
export class MultiWebsocketService {
  private metricsStore = inject(MetricsStoreService);
  
  private connections: Map<
    string,
    {
      socket: WebSocket;
      subject: Subject<any>;
    }
  > = new Map();

  // Metrics tracking
  private topicStats = new Map<string, TopicStats>();
  private flushInterval: any = null;

  constructor() {
    // Start metrics flush interval at 1 Hz
    this.flushInterval = setInterval(() => {
      this.flushMetrics();
    }, 1000);
  }

  /**
   * Connect to a WebSocket for a specific topic
   * @param topic Topic identifier
   * @param url WebSocket URL
   * @returns Observable of messages for this topic
   */
  connect(topic: string, url: string): Observable<any> {
    // If already connected, return existing observable
    if (this.connections.has(topic)) {
      return this.connections.get(topic)!.subject.asObservable();
    }

    // Initialize topic stats
    this.topicStats.set(topic, {
      framesThisSec: 0,
      bytesThisSec: 0,
      parseTimes: []
    });

    const subject = new Subject<any>();
    const socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';

    socket.onmessage = (event) => {
      // Record metrics: parse timing and frame/byte counts
      const t0 = performance.now();
      
      // Track frame and byte counts
      const stats = this.topicStats.get(topic);
      if (stats) {
        stats.framesThisSec++;
        stats.bytesThisSec += event.data.byteLength || event.data.length || 0;
      }

      // Emit the message (existing behavior unchanged)
      subject.next(event.data);
      
      // Record parse time after processing
      const parseMs = performance.now() - t0;
      if (stats) {
        stats.parseTimes.push(parseMs);
        // Maintain max 60 entries
        if (stats.parseTimes.length > 60) {
          stats.parseTimes.shift();
        }
      }
    };

    socket.onerror = (error) => {
      console.error(`WebSocket error for topic ${topic}:`, error);
    };

    socket.onclose = () => {
      console.log(`WebSocket connection closed for topic: ${topic}`);
      this.connections.delete(topic);
      this.topicStats.delete(topic);
      subject.complete();
    };

    this.connections.set(topic, { socket, subject });
    return subject.asObservable();
  }

  /**
   * Disconnect from a specific topic
   * @param topic Topic identifier
   */
  disconnect(topic: string): void {
    const connection = this.connections.get(topic);
    if (!connection) return;

    connection.socket.close();
    connection.subject.complete();
    this.connections.delete(topic);
    this.topicStats.delete(topic);
  }

  /**
   * Disconnect all WebSocket connections
   */
  disconnectAll(): void {
    this.connections.forEach((connection, topic) => {
      connection.socket.close();
      connection.subject.complete();
    });
    this.connections.clear();
    this.topicStats.clear();
    
    // Clear flush interval
    if (this.flushInterval) {
      clearInterval(this.flushInterval);
      this.flushInterval = null;
    }
  }

  /**
   * Check if connected to a specific topic
   * @param topic Topic identifier
   */
  isConnected(topic: string): boolean {
    const connection = this.connections.get(topic);
    return connection?.socket.readyState === WebSocket.OPEN;
  }

  /**
   * Get all active topic connections
   */
  getActiveTopics(): string[] {
    return Array.from(this.connections.keys());
  }

  /**
   * Flushes accumulated WebSocket client metrics to MetricsStore
   * Called every 1 second by internal interval
   */
  private flushMetrics(): void {
    const ws_frames_per_sec: Record<string, number> = {};
    const ws_bytes_per_sec: Record<string, number> = {};
    const ws_parse_latency_ms: Record<string, number> = {};

    // Compute metrics for each active topic
    this.topicStats.forEach((stats, topic) => {
      ws_frames_per_sec[topic] = stats.framesThisSec;
      ws_bytes_per_sec[topic] = stats.bytesThisSec;
      
      // Average parse latency
      if (stats.parseTimes.length > 0) {
        const avgParseMs = stats.parseTimes.reduce((sum, t) => sum + t, 0) / stats.parseTimes.length;
        ws_parse_latency_ms[topic] = avgParseMs;
      } else {
        ws_parse_latency_ms[topic] = 0;
      }

      // Reset counters for next window
      stats.framesThisSec = 0;
      stats.bytesThisSec = 0;
      // Keep parse times for rolling average (don't reset)
    });

    // Only update if there are active topics
    if (Object.keys(ws_frames_per_sec).length > 0) {
      // Partial update to MetricsStore
      this.metricsStore.updateFrontend({
        ws_frames_per_sec,
        ws_bytes_per_sec,
        ws_parse_latency_ms
      });
    }
  }
}
