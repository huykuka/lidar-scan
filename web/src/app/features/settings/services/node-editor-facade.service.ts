import { Injectable, inject } from '@angular/core';
import { NodesApiService } from '../../../core/services/api/nodes-api.service';
import { EdgesApiService } from '../../../core/services/api/edges-api.service';

import { NodeStoreService } from '../../../core/services/stores/node-store.service';
import { ToastService } from '../../../core/services/toast.service';
import {
  NodeConfig,
  NodeDefinition,
  PropertySchema,
} from '../../../core/models/node.model';
import {
  LidarConfigValidationRequest,
} from '../../../core/models/lidar-profile.model';

export interface NodeSavePayload {
  name: string;
  config: Record<string, any>;
  definition: NodeDefinition;
  existingNode: Partial<NodeConfig>;
}

@Injectable()
export class NodeEditorFacadeService {
  private nodesApi = inject(NodesApiService);
  private edgesApi = inject(EdgesApiService);
  private nodeStore = inject(NodeStoreService);
  private toast = inject(ToastService);

  private buildConfig(
    rawConfig: Record<string, any>,
    definition: NodeDefinition,
  ): Record<string, any> {
    const config: Record<string, any> = { ...rawConfig };

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
      return { valid: true };
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
        return { valid: false, message: result.errors[0] ?? 'Invalid LiDAR configuration.' };
      }
      if (result.warnings.length > 0) {
        this.toast.warning(result.warnings[0]);
      }
      return { valid: true };
    } catch {
      return { valid: true };
    }
  }

  async saveNode(payload: NodeSavePayload): Promise<boolean> {
    const { name, config: rawConfig, definition, existingNode } = payload;

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
          ? { op_type: definition.type, ...config }
          : config,
      x: existingNode.x ?? 100,
      y: existingNode.y ?? 100,
    };

    try {
      await this.nodesApi.upsertNode(nodePayload);

      const [nodes, edges] = await Promise.all([
        this.nodesApi.getNodes(),
        this.edgesApi.getEdges(),
      ]);
      this.nodeStore.setState({ nodes, edges });

      this.toast.success(`Node "${name}" saved.`);
      return true;
    } catch (error) {
      console.error('Failed to save node', error);
      this.toast.danger('Failed to save configuration.');
      return false;
    }
  }
}
