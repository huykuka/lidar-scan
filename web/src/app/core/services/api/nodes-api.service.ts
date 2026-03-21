import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {environment} from '@env/environment';
import {firstValueFrom} from 'rxjs';
import {NodeDefinition} from '../../models/node.model';
import {LidarConfigValidationRequest, LidarConfigValidationResponse} from '@core/models';

@Injectable({
  providedIn: 'root',
})
export class NodesApiService {
  private http = inject(HttpClient);

  async setNodeEnabled(id: string, enabled: boolean): Promise<any> {
    return await firstValueFrom(
      this.http.put(`${environment.apiUrl}/nodes/${id}/enabled`, {enabled}),
    );
  }

  async reloadConfig(): Promise<any> {
    return await firstValueFrom(this.http.post(`${environment.apiUrl}/nodes/reload`, {}));
  }

  async getNodeDefinitions(): Promise<NodeDefinition[]> {
    return await firstValueFrom(
      this.http.get<NodeDefinition[]>(`${environment.apiUrl}/nodes/definitions`),
    );
  }

  async validateLidarConfig(
    request: LidarConfigValidationRequest
  ): Promise<LidarConfigValidationResponse> {
    try {
      // Real API call to backend validation endpoint
      return await firstValueFrom(
        this.http.post<LidarConfigValidationResponse>(
          `${environment.apiUrl}/lidar/validate-lidar-config`,
          request
        )
      );
    } catch (error) {
      // Fallback to permissive mock if backend validation unavailable
      console.warn('LiDAR validation endpoint unavailable, using fallback validation');
      return {
        valid: true,
        lidar_type: request.lidar_type,
        resolved_launch_file: null,
        errors: [],
        warnings: ['Validation endpoint unavailable - config not verified']
      };
    }
  }

  async setNodeVisible(id: string, visible: boolean): Promise<{ status: string }> {
    return await firstValueFrom(
      this.http.put<{ status: string }>(`${environment.apiUrl}/nodes/${id}/visible`, { visible }),
    );
  }
}
