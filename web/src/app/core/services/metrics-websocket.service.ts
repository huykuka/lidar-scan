import { Injectable, signal } from '@angular/core';
import { environment } from '../../../environments/environment';
import { MetricsSnapshot } from '../models/metrics.model';
import { MetricsStoreService } from './stores/metrics-store.service';

/**
 * WebSocket client for performance metrics streaming
 * Connects to ws://{apiBase}/ws/system_metrics and feeds data into MetricsStore
 * Follows the same architecture pattern as StatusWebSocketService
 */
@Injectable({
  providedIn: 'root',
})
export class MetricsWebSocketService {
  private ws: WebSocket | null = null;
  private reconnectTimer: any = null;
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 10;
  private reconnectDelay = 2000; // Initial delay 2 seconds
  private readonly maxReconnectDelay = 30000; // Max delay 30 seconds

  // Public signal to expose connection status
  public connected = signal<boolean>(false);

  constructor(private metricsStore: MetricsStoreService) {}

  /**
   * Establishes WebSocket connection to system_metrics topic
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    try {
      // Use environment wsUrl function for WebSocket connection
      const wsUrl = environment.wsUrl('system_metrics');

      this.ws = new WebSocket(wsUrl);
      // Note: JSON messages are received as text by default, no need to set binaryType

      this.ws.onopen = () => {
        console.log('[MetricsWebSocket] Connected to system_metrics');
        this.connected.set(true);
        this.reconnectAttempts = 0;
        this.reconnectDelay = 2000; // Reset delay on successful connection
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Type guard - check if data has timestamp field (basic validation)
          if (this.isValidMetricsSnapshot(data)) {
            this.metricsStore.update(data as MetricsSnapshot);
          } else {
            console.warn('[MetricsWebSocket] Invalid metrics snapshot received:', data);
          }
        } catch (error) {
          console.error('[MetricsWebSocket] Failed to parse message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[MetricsWebSocket] WebSocket error:', error);
      };

      this.ws.onclose = () => {
        console.log('[MetricsWebSocket] Connection closed');
        this.connected.set(false);
        this.metricsStore.markStale();
        this.ws = null;
        this.attemptReconnect();
      };
    } catch (error) {
      console.error('[MetricsWebSocket] Failed to create WebSocket:', error);
      this.attemptReconnect();
    }
  }

  /**
   * Disconnects from WebSocket and clears reconnect timer
   */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.connected.set(false);
    this.reconnectAttempts = 0;
    this.reconnectDelay = 2000; // Reset delay
  }

  /**
   * Attempts reconnection with exponential backoff
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[MetricsWebSocket] Max reconnect attempts reached. Giving up.');
      return;
    }

    this.reconnectAttempts++;
    console.log(
      `[MetricsWebSocket] Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${this.reconnectDelay}ms...`
    );

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, this.reconnectDelay);

    // Exponential backoff: double the delay for next attempt, capped at 30s
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
  }

  /**
   * Type guard to validate incoming metrics data
   * Basic check for timestamp field existence
   */
  private isValidMetricsSnapshot(data: any): boolean {
    return data && typeof data === 'object' && 'timestamp' in data && typeof data.timestamp === 'number';
  }
}