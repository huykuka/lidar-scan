import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { firstValueFrom } from 'rxjs';
import { NodeConfig, NodesStatusResponse, NodeDefinition } from '../../models/node.model';
import { LidarConfigValidationRequest, LidarConfigValidationResponse } from '../../models/lidar-profile.model';

@Injectable({
  providedIn: 'root',
})
export class NodesApiService {
  private http = inject(HttpClient);

  async getNodes(): Promise<NodeConfig[]> {
    return await firstValueFrom(this.http.get<NodeConfig[]>(`${environment.apiUrl}/nodes`));
  }

  async getNode(id: string): Promise<NodeConfig> {
    return await firstValueFrom(this.http.get<NodeConfig>(`${environment.apiUrl}/nodes/${id}`));
  }

  async upsertNode(node: Partial<NodeConfig>): Promise<{ status: string; id: string }> {
    return await firstValueFrom(
      this.http.post<{ status: string; id: string }>(`${environment.apiUrl}/nodes`, node),
    );
  }

  async setNodeEnabled(id: string, enabled: boolean): Promise<any> {
    return await firstValueFrom(
      this.http.put(`${environment.apiUrl}/nodes/${id}/enabled`, { enabled }),
    );
  }

  async deleteNode(id: string): Promise<any> {
    return await firstValueFrom(this.http.delete(`${environment.apiUrl}/nodes/${id}`));
  }

  async reloadConfig(): Promise<any> {
    return await firstValueFrom(this.http.post(`${environment.apiUrl}/nodes/reload`, {}));
  }

  async getNodesStatus(): Promise<NodesStatusResponse> {
    return await firstValueFrom(
      this.http.get<NodesStatusResponse>(`${environment.apiUrl}/nodes/status/all`),
    );
  }

  async getNodeDefinitions(): Promise<NodeDefinition[]> {
    return await firstValueFrom(
      this.http.get<NodeDefinition[]>(`${environment.apiUrl}/nodes/definitions`),
    );
  }

  async validateLidarConfig(
    request: LidarConfigValidationRequest
  ): Promise<LidarConfigValidationResponse> {
    // Mock for development (until backend TASK-B5 is deployed)
    return { 
      valid: true, 
      lidar_type: request.lidar_type, 
      resolved_launch_file: null, 
      errors: [], 
      warnings: [] 
    };
    
    // TODO: Uncomment when backend is ready
    // return await firstValueFrom(
    //   this.http.post<LidarConfigValidationResponse>(
    //     `${environment.apiUrl}/lidar/validate-lidar-config`,
    //     request
    //   )
    // );
  }
}
