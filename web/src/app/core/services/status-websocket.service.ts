import {Injectable, signal} from '@angular/core';
import {environment} from '../../../environments/environment';
import {NodesStatusResponse} from '../models/node-status.model';
import {MOCK_SYSTEM_STATUS, startMockStatusCycling} from './mock-status.helper';

@Injectable({
  providedIn: 'root',
})
export class StatusWebSocketService {
  // Signal to expose status updates
  public status = signal<NodesStatusResponse | null>(null);
  public connected = signal<boolean>(false);
  private ws: WebSocket | null = null;
  private reconnectTimer: any = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000; // 2 seconds
  
  // Debounce state: prevents excess change-detection on rapid updates
  private _pending: NodesStatusResponse | null = null;
  private _debounceId: ReturnType<typeof setTimeout> | null = null;
  
  // Mock mode support
  private _mockCleanup: (() => void) | null = null;

  connect(): void {
    // Check if mock mode is enabled
    if ((environment as any).mockStatus === true) {
      console.warn('[StatusWebSocket] Mock mode enabled - using cycling mock data');
      this.status.set(MOCK_SYSTEM_STATUS);
      this.connected.set(true);
      this._mockCleanup = startMockStatusCycling(this.status);
      return;
    }
    
    if (this.ws?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    // Build WebSocket URL from HTTP API URL
    const wsUrl = environment.apiUrl.replace('http://', 'ws://').replace('https://', 'wss://');

    try {
      this.ws = new WebSocket(`${wsUrl}/ws/system_status`);

      this.ws.onopen = () => {
        this.connected.set(true);
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Store pending update
          this._pending = data;
          
          // Start debounce timer if not already running
          if (!this._debounceId) {
            this._debounceId = setTimeout(() => {
              if (this._pending) {
                this.status.set(this._pending);
              }
              this._pending = null;
              this._debounceId = null;
            }, 50); // 50ms debounce window
          }
        } catch (error) {
          console.error('[StatusWebSocket] Failed to parse message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[StatusWebSocket] Error:', error);
      };

      this.ws.onclose = () => {
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
    // Clean up mock cycling if active
    if (this._mockCleanup) {
      this._mockCleanup();
      this._mockCleanup = null;
    }
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    // Clear debounce timer
    if (this._debounceId) {
      clearTimeout(this._debounceId);
      this._debounceId = null;
    }
    this._pending = null;

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.connected.set(false);
    this.reconnectAttempts = 0;
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[StatusWebSocket] Max reconnect attempts reached. Giving up.');
      return;
    }

    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, this.reconnectDelay);
  }
}
