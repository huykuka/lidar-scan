import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
import {environment} from '@env/environment';
import {DagConfigResponse, DagConfigSaveRequest, DagConfigSaveResponse,} from '@core/models';

// ---------------------------------------------------------------------------
// Mock data — used when environment.useMockDag === true
// ---------------------------------------------------------------------------
const MOCK_DAG_CONFIG: DagConfigResponse = {
  config_version: 1,
  nodes: [
    {
      id: 'mock-node-001',
      name: 'Mock Sensor',
      type: 'sensor',
      category: 'sensor',
      enabled: true,
      visible: true,
      config: { lidar_type: 'multiscan', hostname: '192.168.1.10', port: 2115 },
      pose: { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 },
      x: 100,
      y: 150,
    },
  ],
  edges: [],
};

const MOCK_SAVE_RESPONSE: DagConfigSaveResponse = {
  config_version: 2,
  node_id_map: {},
  reload_mode: 'selective',
  reloaded_node_ids: ['mock-node-001'],
};

// ---------------------------------------------------------------------------

@Injectable({
  providedIn: 'root',
})
export class DagApiService {
  private http = inject(HttpClient);

  async getDagConfig(): Promise<DagConfigResponse> {
    return firstValueFrom(
      this.http.get<DagConfigResponse>(`${environment.apiUrl}/dag/config`),
    );
  }

  async saveDagConfig(req: DagConfigSaveRequest): Promise<DagConfigSaveResponse> {
    return firstValueFrom(
      this.http.put<DagConfigSaveResponse>(`${environment.apiUrl}/dag/config`, req),
    );
  }
}
