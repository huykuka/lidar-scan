import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { Observable, of } from 'rxjs';
import { catchError, delay, map } from 'rxjs/operators';
import { ExternalStateResponse } from '../../models/flow-control.model';

/**
 * API service for Flow Control module endpoints
 * Handles external state control for IF condition nodes
 */
@Injectable({
  providedIn: 'root',
})
export class FlowControlApiService {
  private http = inject(HttpClient);
  private readonly USE_MOCK = true; // Toggle to false when backend is ready

  /**
   * Set external state for an IF condition node
   * @param nodeId - The IF node ID
   * @param value - Boolean state value (true/false)
   * @returns Observable of external state response
   */
  setExternalState(nodeId: string, value: boolean): Observable<ExternalStateResponse> {
    if (this.USE_MOCK) {
      return this.mockSetExternalState(nodeId, value);
    }

    return this.http
      .post<ExternalStateResponse>(
        `${environment.apiUrl}/nodes/${nodeId}/flow-control/set`,
        { value }
      )
      .pipe(
        catchError((error) => {
          console.error('Failed to set external state:', error);
          throw error;
        })
      );
  }

  /**
   * Reset external state to false for an IF condition node
   * @param nodeId - The IF node ID
   * @returns Observable of external state response
   */
  resetExternalState(nodeId: string): Observable<ExternalStateResponse> {
    if (this.USE_MOCK) {
      return this.mockResetExternalState(nodeId);
    }

    return this.http
      .post<ExternalStateResponse>(
        `${environment.apiUrl}/nodes/${nodeId}/flow-control/reset`,
        {}
      )
      .pipe(
        catchError((error) => {
          console.error('Failed to reset external state:', error);
          throw error;
        })
      );
  }

  // Mock implementations for development
  private mockSetExternalState(nodeId: string, value: boolean): Observable<ExternalStateResponse> {
    console.log(`[MOCK] Setting external state for node ${nodeId} to ${value}`);
    
    // Simulate 404 error for non-existent nodes
    if (nodeId === 'non_existent_node') {
      return of(null).pipe(
        delay(150),
        map(() => {
          throw {
            status: 404,
            error: { detail: 'Node not found or not a flow control node' }
          };
        })
      );
    }

    return of({
      node_id: nodeId,
      state: value,
      timestamp: Date.now() / 1000,
    }).pipe(delay(200));
  }

  private mockResetExternalState(nodeId: string): Observable<ExternalStateResponse> {
    console.log(`[MOCK] Resetting external state for node ${nodeId}`);
    
    // Simulate 404 error for non-existent nodes
    if (nodeId === 'non_existent_node') {
      return of(null).pipe(
        delay(150),
        map(() => {
          throw {
            status: 404,
            error: { detail: 'Node not found or not a flow control node' }
          };
        })
      );
    }

    return of({
      node_id: nodeId,
      state: false,
      timestamp: Date.now() / 1000,
    }).pipe(delay(200));
  }
}
