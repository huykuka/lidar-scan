import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { firstValueFrom } from 'rxjs';

export interface LidarNodeStatus {
  id: string;
  name: string;
  enabled: boolean;
  mode: 'real' | 'sim';
  topic_prefix: string;
  raw_topic: string;
  processed_topic: string | null;
  running: boolean;
  connection_status: 'starting' | 'connected' | 'disconnected' | 'error' | 'unknown';
  last_frame_at: number | null;
  frame_age_seconds: number | null;
  last_error: string | null;
}

export interface FusionNodeStatus {
  id: string;
  topic: string;
  sensor_ids: string[];
  enabled: boolean;
  running: boolean;
  last_broadcast_at: number | null;
  broadcast_age_seconds: number | null;
  last_error: string | null;
}

export interface NodesStatusResponse {
  lidars: LidarNodeStatus[];
  fusions: FusionNodeStatus[];
}

@Injectable({
  providedIn: 'root',
})
export class NodesApiService {
  private http = inject(HttpClient);

  async getNodesStatus(): Promise<NodesStatusResponse> {
    return await firstValueFrom(
      this.http.get<NodesStatusResponse>(`${environment.apiUrl}/nodes/status`),
    );
  }
}
