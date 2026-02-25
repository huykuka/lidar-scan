import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { firstValueFrom } from 'rxjs';
import { Edge } from '../../models/node.model';

@Injectable({
  providedIn: 'root',
})
export class EdgesApiService {
  private http = inject(HttpClient);

  async getEdges(): Promise<Edge[]> {
    return await firstValueFrom(this.http.get<Edge[]>(`${environment.apiUrl}/edges`));
  }

  async createEdge(edge: {
    source_node: string;
    target_node: string;
    source_port?: string;
    target_port?: string;
  }): Promise<Edge> {
    return await firstValueFrom(this.http.post<Edge>(`${environment.apiUrl}/edges`, edge));
  }

  async deleteEdge(edgeId: string): Promise<any> {
    return await firstValueFrom(this.http.delete(`${environment.apiUrl}/edges/${edgeId}`));
  }

  async saveEdgesBulk(edges: Edge[]): Promise<any> {
    return await firstValueFrom(this.http.post(`${environment.apiUrl}/edges/bulk`, edges));
  }
}
