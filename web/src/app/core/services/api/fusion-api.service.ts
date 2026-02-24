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
    const response = await firstValueFrom(
      this.http.get<{ fusions: FusionConfig[] }>(`${environment.apiUrl}/fusions`),
    );
    this.store.setState({
      fusions: response.fusions,
    });
    return response;
  }

  async saveFusion(config: any): Promise<any> {
    const response = await firstValueFrom(
      this.http.post<any>(`${environment.apiUrl}/fusions`, config),
    );
    await this.getFusions();
    return response;
  }

  async deleteFusion(id: string): Promise<any> {
    const response = await firstValueFrom(
      this.http.delete<any>(`${environment.apiUrl}/fusions/${id}`),
    );
    await this.getFusions();
    return response;
  }

  async setEnabled(id: string, enabled: boolean): Promise<any> {
    return await firstValueFrom(
      this.http.post(
        `${environment.apiUrl}/fusions/${encodeURIComponent(id)}/enabled?enabled=${enabled}`,
        {},
      ),
    );
  }
}
