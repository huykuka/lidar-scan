import { Injectable } from '@angular/core';
import { Subject, Observable } from 'rxjs';

export interface WebSocketMessage {
  topic: string;
  data: any;
}

/**
 * Service for managing multiple WebSocket connections simultaneously
 */
@Injectable({
  providedIn: 'root',
})
export class MultiWebsocketService {
  private connections: Map<
    string,
    {
      socket: WebSocket;
      subject: Subject<any>;
    }
  > = new Map();

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

    const subject = new Subject<any>();
    const socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';

    socket.onmessage = (event) => {
      subject.next(event.data);
    };

    socket.onerror = (error) => {
      console.error(`WebSocket error for topic ${topic}:`, error);
    };

    socket.onclose = () => {
      console.log(`WebSocket connection closed for topic: ${topic}`);
      this.connections.delete(topic);
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
}
