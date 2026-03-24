import {Injectable} from '@angular/core';
import {Observable, Subject} from 'rxjs';

interface TopicConnection {
  socket: WebSocket | null;
  subject: Subject<any>;
  url: string;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  reconnectAttempts: number;
  /** Set to true when the consumer calls disconnect() — suppresses reconnect. */
  intentionallyClosed: boolean;
}

const MAX_RECONNECT_ATTEMPTS = 100;
const RECONNECT_DELAY_MS = 1000;

/**
 * Service for managing multiple WebSocket connections simultaneously.
 * Each topic connection auto-reconnects on unexpected close (up to
 * MAX_RECONNECT_ATTEMPTS times). The returned Observable stays alive
 * across reconnects — consumers never need to re-subscribe.
 */
@Injectable({
  providedIn: 'root',
})
export class MultiWebsocketService {
  private connections: Map<string, TopicConnection> = new Map();

  /**
   * Connect to a WebSocket for a specific topic.
   * If already connected (or reconnecting), returns the existing Observable.
   * @param topic Topic identifier
   * @param url WebSocket URL
   * @returns Observable of messages for this topic
   */
  connect(topic: string, url: string): Observable<any> {
    const existing = this.connections.get(topic);
    if (existing) {
      return existing.subject.asObservable();
    }

    const conn: TopicConnection = {
      socket: null,
      subject: new Subject<any>(),
      url,
      reconnectTimer: null,
      reconnectAttempts: 0,
      intentionallyClosed: false,
    };
    this.connections.set(topic, conn);
    this.openSocket(topic, conn);
    return conn.subject.asObservable();
  }

  /**
   * Disconnect from a specific topic and stop any pending reconnect.
   * @param topic Topic identifier
   */
  disconnect(topic: string): void {
    const conn = this.connections.get(topic);
    if (!conn) return;

    conn.intentionallyClosed = true;
    this.clearReconnectTimer(conn);
    conn.socket?.close();
    conn.socket = null;
    conn.subject.complete();
    this.connections.delete(topic);
  }

  /**
   * Disconnect all WebSocket connections.
   */
  disconnectAll(): void {
    this.connections.forEach((_, topic) => this.disconnect(topic));
  }

  /**
   * Check if connected to a specific topic.
   * @param topic Topic identifier
   */
  isConnected(topic: string): boolean {
    const conn = this.connections.get(topic);
    return conn?.socket?.readyState === WebSocket.OPEN;
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  private openSocket(topic: string, conn: TopicConnection): void {
    try {
      const socket = new WebSocket(conn.url);
      socket.binaryType = 'arraybuffer';
      conn.socket = socket;

      socket.onopen = () => {
        conn.reconnectAttempts = 0;
      };

      socket.onmessage = (event) => {
        conn.subject.next(event.data);
      };

      socket.onerror = (error) => {
        console.error(`[MultiWebsocket] Error on topic "${topic}":`, error);
      };

      socket.onclose = (event: CloseEvent) => {
        conn.socket = null;

        if (conn.intentionallyClosed) {
          // Consumer called disconnect() — do not reconnect.
          return;
        }

        if (event.code === 1001) {
          // Server going away gracefully — complete the stream.
          conn.subject.complete();
          this.connections.delete(topic);
          return;
        }

        this.scheduleReconnect(topic, conn);
      };
    } catch (error) {
      console.error(`[MultiWebsocket] Failed to create socket for topic "${topic}":`, error);
      this.scheduleReconnect(topic, conn);
    }
  }

  private scheduleReconnect(topic: string, conn: TopicConnection): void {
    if (conn.intentionallyClosed) return;

    if (conn.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error(
        `[MultiWebsocket] Max reconnect attempts reached for topic "${topic}". Giving up.`,
      );
      conn.subject.error(new Error(`WebSocket "${topic}" disconnected after max retries`));
      this.connections.delete(topic);
      return;
    }

    conn.reconnectAttempts++;
    conn.reconnectTimer = setTimeout(() => {
      conn.reconnectTimer = null;
      if (!conn.intentionallyClosed && this.connections.has(topic)) {
        this.openSocket(topic, conn);
      }
    }, RECONNECT_DELAY_MS);
  }

  private clearReconnectTimer(conn: TopicConnection): void {
    if (conn.reconnectTimer !== null) {
      clearTimeout(conn.reconnectTimer);
      conn.reconnectTimer = null;
    }
  }
}
