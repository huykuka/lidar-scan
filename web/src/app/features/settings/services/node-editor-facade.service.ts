import {inject, Injectable} from '@angular/core';
import {NodesApiService} from '@core/services/api/nodes-api.service';
import {ToastService} from '@core/services';
import {NodeConfig, NodeDefinition, PropertySchema,} from '@core/models/node.model';
import {LidarConfigValidationRequest,} from '@core/models';
import {Pose} from '@core/models/pose.model';
import {CanvasEditStoreService} from '@features/settings/services/canvas-edit-store.service';

export interface NodeSavePayload {
  name: string;
  config: Record<string, any>;
  definition: NodeDefinition;
  existingNode: Partial<NodeConfig>;
  pose?: Pose;
}

@Injectable()
export class NodeEditorFacadeService {
  private nodesApi = inject(NodesApiService);
  private toast = inject(ToastService);
  private canvasEditStore = inject(CanvasEditStoreService);

  async saveNode(payload: NodeSavePayload): Promise<boolean> {
    const {name, config: rawConfig, definition, existingNode, pose} = payload;

    const validation = await this.validateSensorConfig(rawConfig, definition);
    if (!validation.valid) {
      this.toast.danger(validation.message!);
      return false;
    }

    const config = this.buildConfig(rawConfig, definition);

    const nodePayload: Partial<NodeConfig> = {
      id: existingNode.id,
      name,
      type: definition.type,
      category: definition.category,
      enabled: existingNode.enabled ?? true,
      config:
        definition.category === 'operation'
          ? {op_type: definition.type, ...config}
          : config,
      pose,
      x: existingNode.x ?? 100,
      y: existingNode.y ?? 100,
    };

    // Phase 3: stage locally instead of calling the API
    const isTempId = !existingNode.id || existingNode.id.startsWith('__new__');
    if (!isTempId && existingNode.id) {
      this.canvasEditStore.updateNode(existingNode.id, nodePayload);
    } else {
      this.canvasEditStore.addNode(nodePayload);
    }

    this.toast.success(`Node "${name}" staged for save.`);
    return true;
  }

  private buildConfig(
    rawConfig: Record<string, any>,
    definition: NodeDefinition,
  ): Record<string, any> {
    const config: Record<string, any> = {...rawConfig};

    definition.properties.forEach((prop: PropertySchema) => {
      if (prop.type === 'vec3') {
        config[prop.name] = [
          Number(rawConfig[prop.name][0]),
          Number(rawConfig[prop.name][1]),
          Number(rawConfig[prop.name][2]),
        ];
      }
    });

    return config;
  }

  private async validateSensorConfig(
    config: Record<string, any>,
    definition: NodeDefinition,
  ): Promise<{ valid: boolean; message?: string }> {
    if (definition.type !== 'sensor' || config['mode'] !== 'real') {
      return {valid: true};
    }

    const req: LidarConfigValidationRequest = {
      lidar_type: config['lidar_type'],
      hostname: config['hostname'],
      udp_receiver_ip: config['udp_receiver_ip'] || undefined,
      port: config['port'] || undefined,
      imu_udp_port: config['imu_udp_port'] || undefined,
    };

    try {
      const result = await this.nodesApi.validateLidarConfig(req);
      if (!result.valid) {
        return {valid: false, message: result.errors[0] ?? 'Invalid LiDAR configuration.'};
      }
      if (result.warnings.length > 0) {
        this.toast.warning(result.warnings[0]);
      }
      return {valid: true};
    } catch {
      return {valid: true};
    }
  }
}
