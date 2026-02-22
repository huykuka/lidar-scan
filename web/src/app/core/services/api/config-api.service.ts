import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { firstValueFrom } from 'rxjs';
import {
  ConfigExport,
  ConfigValidationResponse,
  ConfigImportResponse,
} from '../../models/config.model';

@Injectable({
  providedIn: 'root',
})
export class ConfigApiService {
  private http = inject(HttpClient);

  /**
   * Export current configuration as JSON
   */
  async exportConfig(): Promise<ConfigExport> {
    return await firstValueFrom(
      this.http.get<ConfigExport>(`${environment.apiUrl}/config/export`),
    );
  }

  /**
   * Validate configuration before importing
   */
  async validateConfig(config: ConfigExport): Promise<ConfigValidationResponse> {
    return await firstValueFrom(
      this.http.post<ConfigValidationResponse>(
        `${environment.apiUrl}/config/validate`,
        config,
      ),
    );
  }

  /**
   * Import configuration
   * @param config Configuration to import
   * @param merge If true, merge with existing config. If false, replace existing config.
   */
  async importConfig(
    config: ConfigExport,
    merge: boolean = false,
  ): Promise<ConfigImportResponse> {
    return await firstValueFrom(
      this.http.post<ConfigImportResponse>(
        `${environment.apiUrl}/config/import?merge=${merge}`,
        config,
      ),
    );
  }
}
