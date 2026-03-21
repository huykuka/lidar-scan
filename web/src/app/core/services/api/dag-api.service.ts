import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  DagConfigResponse,
  DagConfigSaveRequest,
  DagConfigSaveResponse,
} from '../../models/dag.model';

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
};

// ---------------------------------------------------------------------------

@Injectable({
  providedIn: 'root',
})
export class DagApiService {
  private http = inject(HttpClient);

  async getDagConfig(): Promise<DagConfigResponse> {
    if (environment.useMockDag) {
      await new Promise((r) => setTimeout(r, 300));
      return structuredClone(MOCK_DAG_CONFIG);
    }
    return firstValueFrom(
      this.http.get<DagConfigResponse>(`${environment.apiUrl}/dag/config`),
    );
  }

  async saveDagConfig(req: DagConfigSaveRequest): Promise<DagConfigSaveResponse> {
    if (environment.useMockDag) {
      // Simulate 409 conflict when base_version === 0 (for testing)
      if (req.base_version === 0) {
        throw {
          status: 409,
          error: {
            detail: 'Version conflict: base_version=0 but current version is 3.',
          },
        };
      }
      await new Promise((r) => setTimeout(r, 800));
      return { ...MOCK_SAVE_RESPONSE };
    }
    return firstValueFrom(
      this.http.put<DagConfigSaveResponse>(`${environment.apiUrl}/dag/config`, req),
    );
  }
}
