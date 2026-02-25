import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { firstValueFrom } from 'rxjs';
import { FusionStoreService } from '../stores/fusion-store.service';
import { FusionConfig } from '../../models/fusion.model';

export type { FusionConfig } from '../../models/fusion.model';

@Injectable({
  providedIn: 'root',
})
export class FusionApiService {
  private http = inject(HttpClient);
  private store = inject(FusionStoreService);

  async getFusions(): Promise<{ fusions: FusionConfig[] }> {
    const nodes = await firstValueFrom(this.http.get<any[]>(`${environment.apiUrl}/nodes`));

    const fusions = nodes
      .filter((n) => n.type === 'fusion')
      .map((n) => ({
        id: n.id,
        name: n.name,
        enabled: n.enabled,
        ...n.config,
      })) as FusionConfig[];

    const response = { fusions };
    this.store.setState({ fusions });
    return response;
  }

  async saveFusion(config: any): Promise<any> {
    const payload = {
      id: config.id,
      name: config.name,
      type: 'fusion',
      category: 'Processing',
      enabled: config.enabled ?? true,
      config: { ...config },
    };

    delete payload.config.id;
    delete payload.config.name;
    delete payload.config.enabled;

    const response = await firstValueFrom(
      this.http.post<any>(`${environment.apiUrl}/nodes`, payload),
    );
    await this.getFusions();
    return response;
  }

  async deleteFusion(id: string): Promise<any> {
    const response = await firstValueFrom(
      this.http.delete<any>(`${environment.apiUrl}/nodes/${id}`),
    );
    await this.getFusions();
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
