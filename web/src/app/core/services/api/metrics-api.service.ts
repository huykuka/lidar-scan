import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, of } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { 
  MetricsSnapshot, 
  DagMetrics, 
  WebSocketMetrics, 
  PerformanceHealthResponse 
} from '../../models/metrics.model';

/**
 * Centralized HTTP service for REST metrics endpoints
 * Used for initial page-load snapshot before WebSocket is established
 * All methods handle errors gracefully by returning null observable
 */
@Injectable({ providedIn: 'root' })
export class MetricsApiService {
  private http = inject(HttpClient);

  /**
   * Gets full metrics snapshot from GET /api/metrics
   * @returns Observable<MetricsSnapshot> or null on error
   */
  getSnapshot(): Observable<MetricsSnapshot | null> {
    return this.http
      .get<MetricsSnapshot>(`${environment.apiUrl}/api/metrics`)
      .pipe(
        catchError((error) => {
          console.error('[MetricsApi] Failed to get snapshot:', error);
          return of(null);
        })
      );
  }

  /**
   * Gets DAG metrics only from GET /api/metrics/dag
   * @returns Observable<DagMetrics> or null on error
   */
  getDagMetrics(): Observable<DagMetrics | null> {
    return this.http
      .get<DagMetrics>(`${environment.apiUrl}/api/metrics/dag`)
      .pipe(
        catchError((error) => {
          console.error('[MetricsApi] Failed to get DAG metrics:', error);
          return of(null);
        })
      );
  }

  /**
   * Gets WebSocket metrics from GET /api/metrics/websocket
   * @returns Observable<WebSocketMetrics> or null on error
   */
  getWebSocketMetrics(): Observable<WebSocketMetrics | null> {
    return this.http
      .get<WebSocketMetrics>(`${environment.apiUrl}/api/metrics/websocket`)
      .pipe(
        catchError((error) => {
          console.error('[MetricsApi] Failed to get WebSocket metrics:', error);
          return of(null);
        })
      );
  }

  /**
   * Gets performance health check from GET /api/health/performance
   * @returns Observable<PerformanceHealthResponse> or null on error
   */
  getHealthPerformance(): Observable<PerformanceHealthResponse | null> {
    return this.http
      .get<PerformanceHealthResponse>(`${environment.apiUrl}/api/health/performance`)
      .pipe(
        catchError((error) => {
          console.error('[MetricsApi] Failed to get health performance:', error);
          return of(null);
        })
      );
  }
}