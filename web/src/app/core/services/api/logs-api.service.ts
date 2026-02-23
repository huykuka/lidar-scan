import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { LogEntry, LogFilterOptions, LogsResponse } from '../../models/log.model';
import { firstValueFrom, Observable } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class LogsApiService {
  private http = inject(HttpClient);

  /**
   * Fetch logs from REST endpoint with filtering and pagination
   */
  async getLogs(filters?: LogFilterOptions): Promise<LogEntry[]> {
    const params = new URLSearchParams();

    if (filters?.level) {
      params.append('level', filters.level);
    }
    if (filters?.search) {
      params.append('search', filters.search);
    }
    if (filters?.offset !== undefined) {
      params.append('offset', filters.offset.toString());
    }
    if (filters?.limit !== undefined) {
      params.append('limit', filters.limit.toString());
    }

    const url = `${environment.apiUrl}/logs${params.toString() ? '?' + params.toString() : ''}`;

    const response = await firstValueFrom(this.http.get<LogEntry[]>(url));

    return response;
  }

  /**
   * Connect to WebSocket for real-time log streaming
   */
  connectLogsWebSocket(level?: string, search?: string): Observable<string> {
    const apiUrl = environment.apiUrl;
    const wsUrlBase = apiUrl.replace(/^http/, 'ws');
    let wsUrl = `${wsUrlBase}/logs/ws`;

    const params = [];
    if (level) {
      params.push(`level=${encodeURIComponent(level)}`);
    }
    if (search) {
      params.push(`search=${encodeURIComponent(search)}`);
    }

    if (params.length > 0) {
      wsUrl += '?' + params.join('&');
    }

    return new Observable((observer) => {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        observer.next(JSON.stringify({ type: 'connected' }));
      };

      ws.onmessage = (event) => {
        try {
          observer.next(event.data);
        } catch (error) {
          observer.error(error);
        }
      };

      ws.onerror = (error) => {
        observer.error(error);
      };

      ws.onclose = () => {
        observer.complete();
      };

      // Return cleanup function
      return () => {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      };
    });
  }
}
