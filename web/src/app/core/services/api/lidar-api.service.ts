import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {environment} from '../../../../environments/environment';
import {LidarConfig, LidarListResponse} from '../../models/lidar.model';
import {firstValueFrom} from 'rxjs';
import {LidarStoreService} from '../stores/lidar-store.service';
import {ZERO_POSE} from '../../models/pose.model';

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
        pose: n.pose ?? ZERO_POSE,
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

  async setEnabled(id: string, enabled: boolean): Promise<any> {
    return await firstValueFrom(
      this.http.put(`${environment.apiUrl}/nodes/${encodeURIComponent(id)}/enabled`, {
        enabled: enabled,
      }),
    );
  }
}
