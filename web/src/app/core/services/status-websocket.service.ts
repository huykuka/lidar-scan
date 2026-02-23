import { Injectable, signal } from '@angular/core';
import { environment } from '../../../environments/environment';
import { NodesStatusResponse } from './api/nodes-api.service';

@Injectable({
  providedIn: 'root',
})
export class StatusWebSocketService {
  private ws: WebSocket | null = null;
  private reconnectTimer: any = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 2000; // 2 seconds

  // Signal to expose status updates
  public status = signal<NodesStatusResponse | null>(null);
  public connected = signal<boolean>(false);

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    // Build WebSocket URL from HTTP API URL
    const wsUrl = environment.apiUrl
      .replace('http://', 'ws://')
      .replace('https://', 'wss://');

    try {
      this.ws = new WebSocket(`${wsUrl}/ws/system_status`);

      this.ws.onopen = () => {
        console.log('[StatusWebSocket] Connected to system_status');
        this.connected.set(true);
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.status.set(data);
        } catch (error) {
          console.error('[StatusWebSocket] Failed to parse message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[StatusWebSocket] Error:', error);
      };

      this.ws.onclose = () => {
        console.log('[StatusWebSocket] Connection closed');
        this.connected.set(false);
        this.ws = null;
        this.attemptReconnect();
      };
    } catch (error) {
      console.error('[StatusWebSocket] Failed to create WebSocket:', error);
      this.attemptReconnect();
    }
  }

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
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error(
        '[StatusWebSocket] Max reconnect attempts reached. Giving up.'
      );
      return;
    }

    this.reconnectAttempts++;
    console.log(
      `[StatusWebSocket] Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`
    );

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, this.reconnectDelay);
  }
}
