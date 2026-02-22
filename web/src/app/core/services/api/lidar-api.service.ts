import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { LidarListResponse } from '../../models/lidar.model';
import { firstValueFrom } from 'rxjs';
import { LidarStoreService } from '../stores/lidar-store.service';

@Injectable({
  providedIn: 'root',
})
export class LidarApiService {
  private http = inject(HttpClient);
  private store = inject(LidarStoreService);

  async getLidars(): Promise<LidarListResponse> {
    const response = await firstValueFrom(
      this.http.get<LidarListResponse>(`${environment.apiUrl}/lidars`),
    );
    this.store.setState({
      lidars: response.lidars,
      availablePipelines: response.available_pipelines,
    });
    return response;
  }

  async saveLidar(config: any): Promise<any> {
    const response = await firstValueFrom(
      this.http.post(`${environment.apiUrl}/lidars`, config),
    );
    return response;
  }

  async deleteLidar(id: string): Promise<any> {
    const response = await firstValueFrom(
      this.http.delete(`${environment.apiUrl}/lidars/${id}`),
    );
    return response;
  }

  async reloadConfig(): Promise<any> {
    return await firstValueFrom(
      this.http.post(`${environment.apiUrl}/lidars/reload`, {}),
    );
  }

  async setEnabled(id: string, enabled: boolean): Promise<any> {
    return await firstValueFrom(
      this.http.post(
        `${environment.apiUrl}/lidars/${encodeURIComponent(id)}/enabled?enabled=${enabled}`,
        {},
      ),
    );
  }
}
