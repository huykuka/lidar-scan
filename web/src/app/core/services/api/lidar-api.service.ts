import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { LidarListResponse } from '../../models/lidar.model';
import { firstValueFrom } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class LidarApiService {
  private http = inject(HttpClient);

  async getLidars(): Promise<LidarListResponse> {
    return await firstValueFrom(this.http.get<LidarListResponse>(`${environment.apiUrl}/lidars`));
  }

  async saveLidar(config: any): Promise<any> {
    return await firstValueFrom(this.http.post(`${environment.apiUrl}/lidars`, config));
  }

  async deleteLidar(id: string): Promise<any> {
    return await firstValueFrom(this.http.delete(`${environment.apiUrl}/lidars/${id}`));
  }

  async reloadConfig(): Promise<any> {
    return await firstValueFrom(this.http.post(`${environment.apiUrl}/lidars/reload`, {}));
  }
}
