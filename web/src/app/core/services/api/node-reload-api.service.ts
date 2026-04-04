import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { NodeReloadResponse, ReloadStatusResponse } from '@core/models/status.model';

// ---------------------------------------------------------------------------
// Mock data — used when environment.production === false (dev/test mode)
// ---------------------------------------------------------------------------
const MOCK_NODE_RELOAD_RESPONSE: NodeReloadResponse = {
  node_id: 'mock-node-001',
  status: 'reloaded',
  duration_ms: 73,
  ws_topic: 'mock_sensor_mock_nod',
};

const MOCK_RELOAD_STATUS_RESPONSE: ReloadStatusResponse = {
  locked: false,
  reload_in_progress: false,
  active_reload_node_id: null,
  estimated_completion_ms: null,
};

// ---------------------------------------------------------------------------

@Injectable({
  providedIn: 'root',
})
export class NodeReloadApiService {
  private http = inject(HttpClient);

  /**
   * Triggers selective reload of a single node's runtime.
   * POST /api/v1/nodes/{nodeId}/reload
   */
  async reloadNode(nodeId: string): Promise<NodeReloadResponse> {
    return firstValueFrom(
      this.http.post<NodeReloadResponse>(
        `${environment.apiUrl}/nodes/${nodeId}/reload`,
        {},
      ),
    );
  }

  /**
   * Gets current reload lock status.
   * GET /api/v1/nodes/reload/status
   */
  async getReloadStatus(): Promise<ReloadStatusResponse> {
    return firstValueFrom(
      this.http.get<ReloadStatusResponse>(`${environment.apiUrl}/nodes/reload/status`),
    );
  }
}
