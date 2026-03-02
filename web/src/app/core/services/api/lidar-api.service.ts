import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { LidarListResponse, LidarConfig } from '../../models/lidar.model';
import { firstValueFrom } from 'rxjs';
import { LidarStoreService } from '../stores/lidar-store.service';

@Injectable({
  providedIn: 'root',
})
export class LidarApiService {
  private http = inject(HttpClient);
  private store = inject(LidarStoreService);

  async getLidars(): Promise<LidarListResponse> {
    const nodes = await firstValueFrom(this.http.get<any[]>(`${environment.apiUrl}/nodes`));
    const pipelinesRes = await firstValueFrom(
      this.http.get<{ pipelines: string[] }>(`${environment.apiUrl}/nodes/pipelines`),
    );

    const lidars = nodes
      .filter((n) => n.type === 'sensor')
      .map((n) => ({
        id: n.id,
        name: n.name,
        enabled: n.enabled,
        ...n.config,
      })) as LidarConfig[];

    const response = {
      lidars,
      available_pipelines: pipelinesRes.pipelines || [],
    };

    this.store.setState({
      lidars: response.lidars,
      availablePipelines: response.available_pipelines,
    });
    return response;
  }

  async saveLidar(config: any): Promise<any> {
    const payload = {
      id: config.id,
      name: config.name,
      type: 'sensor',
      category: 'Input',
      enabled: config.enabled ?? true,
      config: { ...config },
    };

    delete payload.config.id;
    delete payload.config.name;
    delete payload.config.enabled;

    const response = await firstValueFrom(this.http.post(`${environment.apiUrl}/nodes`, payload));
    return response;
  }

  async deleteLidar(id: string): Promise<any> {
    const response = await firstValueFrom(this.http.delete(`${environment.apiUrl}/nodes/${id}`));
    return response;
  }

  async reloadConfig(): Promise<any> {
    return await firstValueFrom(this.http.post(`${environment.apiUrl}/nodes/reload`, {}));
  }

  async setEnabled(id: string, enabled: boolean): Promise<any> {
    return await firstValueFrom(
      this.http.put(`${environment.apiUrl}/nodes/${encodeURIComponent(id)}/enabled`, {
        enabled: enabled,
      }),
    );
  }
}
