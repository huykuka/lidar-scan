import {computed, inject, Injectable} from '@angular/core';
import {NodeStoreService} from '../stores/node-store.service';
import {LidarProfile} from '../../models/lidar-profile.model';
import {environment} from '../../../../environments/environment';

/**
 * Derives LiDAR profiles from the sensor node definition's `lidar_type` options,
 * which are loaded once via `GET /nodes/definitions`. No separate HTTP call needed.
 */
@Injectable({
  providedIn: 'root',
})
export class LidarProfilesApiService {
  private nodeStore = inject(NodeStoreService);

  profiles = computed<LidarProfile[]>(() => {
    const definitions = this.nodeStore.nodeDefinitions();
    const sensorDef = definitions.find((d) => d.type === 'sensor');
    if (!sensorDef) return [];

    const lidarTypeProp = sensorDef.properties.find((p) => p.name === 'lidar_type');
    if (!lidarTypeProp?.options) return [];

    return lidarTypeProp.options
      .filter((opt: Record<string, any>) => !opt['disabled'])
      .map((opt: Record<string, any>) => ({
        model_id: opt['value'] as string,
        display_name: opt['label'] as string,
        launch_file: opt['launch_file'] as string,
        default_hostname: opt['default_hostname'] as string,
        port_arg: opt['port_arg'] as string,
        default_port: opt['default_port'] as number,
        has_udp_receiver: opt['has_udp_receiver'] as boolean,
        has_imu_udp_port: opt['has_imu_udp_port'] as boolean,
        scan_layers: opt['scan_layers'] as number,
        thumbnail_url: this.resolveAssetUrl(opt['thumbnail_url'] as string | undefined),
        icon_name: opt['icon_name'] as string | undefined,
        icon_color: opt['icon_color'] as string | undefined,
      }));
  });

  getProfileByModelId(modelId: string): LidarProfile | null {
    return this.profiles().find((profile) => profile.model_id === modelId) || null;
  }

  private resolveAssetUrl(thumbnailUrl: string | undefined): string | undefined {
    if (!thumbnailUrl) return undefined;
    if (thumbnailUrl.startsWith('/')) {
      return `${environment.apiUrl.replace('/api/v1', '')}${thumbnailUrl}`;
    }
    return thumbnailUrl;
  }
}
