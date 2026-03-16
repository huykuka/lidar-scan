import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {environment} from '../../../../environments/environment';
import {firstValueFrom} from 'rxjs';
import {
  CalibrationAcceptRequest,
  CalibrationAcceptResponse,
  CalibrationHistoryResponse,
  CalibrationRejectResponse,
  CalibrationRollbackRequest,
  CalibrationRollbackResponse,
  CalibrationStatistics,
  CalibrationTriggerRequest,
  CalibrationTriggerResponse,
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
   * @param sensorId - Sensor ID to get history for
   * @param limit - Maximum number of records to return
   * @param sourceSensorId - Optional: Filter by canonical leaf sensor ID
   * @param runId - Optional: Filter by calibration run ID
   */
  async getHistory(
    sensorId: string, 
    limit: number = 10,
    sourceSensorId?: string,
    runId?: string
  ): Promise<CalibrationHistoryResponse> {
    let url = `${environment.apiUrl}/calibration/history/${sensorId}?limit=${limit}`;
    
    // NEW: Add optional query parameters for filtering
    if (sourceSensorId) {
      url += `&source_sensor_id=${encodeURIComponent(sourceSensorId)}`;
    }
    if (runId) {
      url += `&run_id=${encodeURIComponent(runId)}`;
    }
    
    return await firstValueFrom(
      this.http.get<CalibrationHistoryResponse>(url),
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
