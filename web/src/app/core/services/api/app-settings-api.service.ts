import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
import {environment} from '@env/environment';

export type SettingType = 'bool' | 'int' | 'string' | 'select' | 'secret';
export type SettingValue = boolean | number | string | null;

export interface AppSetting {
  key: string;
  label: string;
  type: SettingType;
  description: string;
  placeholder: string;
  unit: string | null;
  min: number | null;
  max: number | null;
  depends_on: string | null;
  options: string[] | null;
  /** Always null for secrets */
  value: SettingValue;
  /** Secrets only: whether a value is stored */
  is_set: boolean | null;
  default: SettingValue;
  /** True when the stored value overrides the default */
  modified: boolean;
}

export interface AppSettingCategory {
  id: string;
  label: string;
  icon: string;
  description: string;
  settings: AppSetting[];
}

export interface AppSettingsResponse {
  categories: AppSettingCategory[];
  /** False when the server has no SETTINGS_ENCRYPTION_KEY, so secrets cannot be saved */
  encryption_available: boolean;
  /** Why encryption is unavailable (missing or invalid key), when it is */
  encryption_error: string | null;
}

export interface StorageTestResult {
  configured: boolean;
  authenticated: boolean;
  backend: string;
  bucket: string | null;
  reason: string | null;
}

@Injectable({providedIn: 'root'})
export class AppSettingsApiService {
  private http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/app-settings`;

  get(): Promise<AppSettingsResponse> {
    return firstValueFrom(this.http.get<AppSettingsResponse>(this.url));
  }

  update(values: Record<string, SettingValue>, reset: string[]): Promise<AppSettingsResponse> {
    return firstValueFrom(this.http.put<AppSettingsResponse>(this.url, {values, reset}));
  }

  testStorage(): Promise<StorageTestResult> {
    return firstValueFrom(this.http.post<StorageTestResult>(`${this.url}/storage/test`, {}));
  }
}
