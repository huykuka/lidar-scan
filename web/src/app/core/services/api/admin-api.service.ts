import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {environment} from '@env/environment';
import {firstValueFrom} from 'rxjs';

export interface NodeTypeRecord {
  type: string;
  display_name: string;
  category: string;
  description: string;
  icon: string;
  enabled: boolean;
}

export interface NodeTypeToggleResponse {
  status: string;
  type: string;
  enabled: boolean;
  disabled_instances: string[];
}

@Injectable({providedIn: 'root'})
export class AdminApiService {
  private http = inject(HttpClient);

  async getNodeTypes(): Promise<NodeTypeRecord[]> {
    return firstValueFrom(
      this.http.get<NodeTypeRecord[]>(`${environment.apiUrl}/nodes/definitions/registry`),
    );
  }

  async setNodeTypeEnabled(nodeType: string, enabled: boolean): Promise<NodeTypeToggleResponse> {
    return firstValueFrom(
      this.http.put<NodeTypeToggleResponse>(
        `${environment.apiUrl}/nodes/definitions/${nodeType}/enabled`,
        {enabled},
      ),
    );
  }
}
