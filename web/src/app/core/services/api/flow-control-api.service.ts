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

  /**
   * Set external state for an IF condition node
   * @param nodeId - The IF node ID
   * @param value - Boolean state value (true/false)
   * @returns Observable of external state response
   */
  setExternalState(nodeId: string, value: boolean): Observable<ExternalStateResponse> {

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
}
