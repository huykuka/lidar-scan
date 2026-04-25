import {computed, inject, Injectable} from '@angular/core';
import {NodeStoreService} from '../stores/node-store.service';
import {VisionaryProfile} from '../../models/visionary-profile.model';
import {environment} from '../../../../environments/environment';

/**
 * Derives Visionary camera profiles from the visionary_sensor node definition's
 * `camera_model` options, loaded once via `GET /nodes/definitions`.
 */
@Injectable({
  providedIn: 'root',
})
export class VisionaryProfilesApiService {
  private nodeStore = inject(NodeStoreService);

  profiles = computed<VisionaryProfile[]>(() => {
    const definitions = this.nodeStore.nodeDefinitions();
    const visionaryDef = definitions.find((d) => d.type === 'visionary_sensor');
    if (!visionaryDef) return [];

    const cameraModelProp = visionaryDef.properties.find((p) => p.name === 'camera_model');
    if (!cameraModelProp?.options) return [];

    return cameraModelProp.options
      .filter((opt: Record<string, any>) => !opt['disabled'])
      .map((opt: Record<string, any>) => ({
        model_id: opt['value'] as string,
        display_name: opt['label'] as string,
        is_stereo: opt['is_stereo'] as boolean,
        acquisition_method: opt['acquisition_method'] as string,
        default_hostname: opt['default_hostname'] as string,
        cola_protocol: opt['cola_protocol'] as string,
        default_control_port: opt['default_control_port'] as number,
        default_streaming_port: opt['default_streaming_port'] as number,
        thumbnail_url: this.resolveAssetUrl(opt['thumbnail_url'] as string | undefined),
        icon_name: opt['icon_name'] as string | undefined,
        icon_color: opt['icon_color'] as string | undefined,
      }));
  });

  getProfileByModelId(modelId: string): VisionaryProfile | null {
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
