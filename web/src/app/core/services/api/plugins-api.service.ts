import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {environment} from '@env/environment';
import {firstValueFrom} from 'rxjs';

export interface PluginRecord {
  name: string;
  loaded: boolean;
  types: string[];
}

export interface PluginActionResponse {
  status: string;
  plugin: string;
  types: string[];
}

@Injectable({providedIn: 'root'})
export class PluginsApiService {
  private http = inject(HttpClient);

  listPlugins(): Promise<PluginRecord[]> {
    return firstValueFrom(
      this.http.get<PluginRecord[]>(`${environment.apiUrl}/nodes/plugins`),
    );
  }

  loadPlugin(name: string): Promise<PluginActionResponse> {
    return firstValueFrom(
      this.http.post<PluginActionResponse>(`${environment.apiUrl}/nodes/plugins/${name}/load`, {}),
    );
  }

  unloadPlugin(name: string): Promise<PluginActionResponse> {
    return firstValueFrom(
      this.http.delete<PluginActionResponse>(`${environment.apiUrl}/nodes/plugins/${name}`),
    );
  }

  uploadPlugin(file: File, autoLoad = true): Promise<PluginActionResponse> {
    const form = new FormData();
    form.append('file', file);
    return firstValueFrom(
      this.http.post<PluginActionResponse>(
        `${environment.apiUrl}/nodes/plugins/upload?auto_load=${autoLoad}`,
        form,
      ),
    );
  }
}
