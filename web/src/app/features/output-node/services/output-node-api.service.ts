import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
import {environment} from '@env/environment';
import {NodeConfig} from '@core/models/node.model';
import {WebhookConfig} from '@core/models/output-node.model';

/**
 * API service for Output Node — webhook config and node detail endpoints.
 */
@Injectable({
  providedIn: 'root',
})
export class OutputNodeApiService {
  private http = inject(HttpClient);

  /**
   * Fetch a single node by ID.
   * Uses the shared GET /api/v1/nodes/:nodeId endpoint.
   */
  async getNode(nodeId: string): Promise<NodeConfig> {
    return firstValueFrom(
      this.http.get<NodeConfig>(`${environment.apiUrl}/nodes/${nodeId}`),
    );
  }

  /**
   * Fetch webhook configuration for an Output Node.
   * GET /api/v1/nodes/:nodeId/webhook
   */
  async getWebhookConfig(nodeId: string): Promise<WebhookConfig> {
    return firstValueFrom(
      this.http.get<WebhookConfig>(`${environment.apiUrl}/nodes/${nodeId}/webhook`),
    );
  }

  /**
   * Update webhook configuration for an Output Node.
   * PATCH /api/v1/nodes/:nodeId/webhook
   */
  async updateWebhookConfig(
    nodeId: string,
    config: WebhookConfig,
  ): Promise<{status: string; node_id: string}> {
    return firstValueFrom(
      this.http.patch<{status: string; node_id: string}>(
        `${environment.apiUrl}/nodes/${nodeId}/webhook`,
        config,
      ),
    );
  }
}
