import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { firstValueFrom } from 'rxjs';
import {
  CalibrationTriggerRequest,
  CalibrationTriggerResponse,
  CalibrationAcceptRequest,
  CalibrationAcceptResponse,
  CalibrationRejectResponse,
  CalibrationHistoryResponse,
  CalibrationRollbackRequest,
  CalibrationRollbackResponse,
  CalibrationStatistics,
} from '../../models/calibration.model';

@Injectable({
  providedIn: 'root',
})
export class CalibrationApiService {
  private http = inject(HttpClient);

  /**
   * Trigger calibration on a calibration node
   */
  async triggerCalibration(
    nodeId: string,
    request: CalibrationTriggerRequest = {},
  ): Promise<CalibrationTriggerResponse> {
    return await firstValueFrom(
      this.http.post<CalibrationTriggerResponse>(
        `${environment.apiUrl}/calibration/${nodeId}/trigger`,
        request,
      ),
    );
  }

  /**
   * Accept pending calibration results
   */
  async acceptCalibration(
    nodeId: string,
    request: CalibrationAcceptRequest = {},
  ): Promise<CalibrationAcceptResponse> {
    return await firstValueFrom(
      this.http.post<CalibrationAcceptResponse>(
        `${environment.apiUrl}/calibration/${nodeId}/accept`,
        request,
      ),
    );
  }

  /**
   * Reject pending calibration results
   */
  async rejectCalibration(nodeId: string): Promise<CalibrationRejectResponse> {
    return await firstValueFrom(
      this.http.post<CalibrationRejectResponse>(
        `${environment.apiUrl}/calibration/${nodeId}/reject`,
        {},
      ),
    );
  }

  /**
   * Get calibration history for a sensor
   */
  async getHistory(sensorId: string, limit: number = 10): Promise<CalibrationHistoryResponse> {
    return await firstValueFrom(
      this.http.get<CalibrationHistoryResponse>(
        `${environment.apiUrl}/calibration/history/${sensorId}?limit=${limit}`,
      ),
    );
  }

  /**
   * Rollback sensor to a previous calibration
   */
  async rollback(
    sensorId: string,
    request: CalibrationRollbackRequest,
  ): Promise<CalibrationRollbackResponse> {
    return await firstValueFrom(
      this.http.post<CalibrationRollbackResponse>(
        `${environment.apiUrl}/calibration/rollback/${sensorId}`,
        request,
      ),
    );
  }

  /**
   * Get calibration statistics for a sensor
   */
  async getStatistics(sensorId: string): Promise<CalibrationStatistics> {
    return await firstValueFrom(
      this.http.get<CalibrationStatistics>(
        `${environment.apiUrl}/calibration/statistics/${sensorId}`,
      ),
    );
  }
}
