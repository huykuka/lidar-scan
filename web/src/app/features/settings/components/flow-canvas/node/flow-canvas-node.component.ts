import { Component, computed, inject, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import {
  NodeConfig,
  LidarNodeStatus,
  FusionNodeStatus,
} from '../../../../../core/models/node.model';
import { NodeStoreService } from '../../../../../core/services/stores/node-store.service';
import { NodeRecordingControls } from './node-recording-controls/node-recording-controls';
import { NodeCalibrationControls } from './node-calibration-controls/node-calibration-controls';

export interface CanvasNode {
  id: string;
  type: string;
  data: NodeConfig;
  position: { x: number; y: number };
}

@Component({
  selector: 'app-flow-canvas-node',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule, NodeRecordingControls, NodeCalibrationControls],
  templateUrl: './flow-canvas-node.component.html',
  styleUrl: './flow-canvas-node.component.css',
})
export class FlowCanvasNodeComponent {
  private nodeStore = inject(NodeStoreService);

  node = input.required<CanvasNode>();
  status = input<LidarNodeStatus | FusionNodeStatus | null>(null);
  isLoading = input<boolean>(false);
  isDragging = input<boolean>(false);

  protected nodeDefinition = computed(() => {
    return this.nodeStore.nodeDefinitions().find((d) => d.type === this.node().data.type);
  });

  protected hasInputPort = computed(() => {
    const def = this.nodeDefinition();
    return def && def.inputs && def.inputs.length > 0;
  });

  protected hasOutputPort = computed(() => {
    const def = this.nodeDefinition();
    return def && def.outputs && def.outputs.length > 0;
  });

  protected nodeCategory = computed(() => {
    const categoryFromDefinition = this.nodeDefinition()?.category?.toLowerCase();
    if (categoryFromDefinition) return categoryFromDefinition;

    const categoryFromData = this.node().data.category?.toLowerCase();
    if (categoryFromData) return categoryFromData;

    return this.node().type?.toLowerCase() ?? 'unknown';
  });

  protected isCalibrationNode = computed(() => this.nodeCategory() === 'calibration');
  protected isSensorCategory = computed(() => this.nodeCategory() === 'sensor');
  protected isFusionCategory = computed(() => this.nodeCategory() === 'fusion');
  protected isOperationCategory = computed(() => this.nodeCategory() === 'operation');

  onEdit = output<void>();
  onToggleEnabled = output<boolean>();

  portDragStart = output<{ nodeId: string; portType: 'input' | 'output'; event: MouseEvent }>();
  portDrop = output<{ nodeId: string; portType: 'input' | 'output' }>();

  isExpanded = signal<boolean>(false);

  statusBadge(): {
    variant: 'primary' | 'success' | 'neutral' | 'warning' | 'danger';
    label: string;
  } {
    const status = this.status();
    const enabled = this.node().data.enabled;

    if (!enabled) {
      return { variant: 'neutral', label: 'Disabled' };
    }

    if (!status) {
      return { variant: 'warning', label: 'Unknown' };
    }

    const lidarStatus = status as LidarNodeStatus;
    if (lidarStatus.connection_status) {
      if (lidarStatus.connection_status === 'disconnected') {
        return { variant: 'danger', label: 'Disconnected' };
      }
      if (lidarStatus.connection_status === 'error') {
        return { variant: 'danger', label: 'Error' };
      }
      if (lidarStatus.connection_status === 'starting') {
        return { variant: 'warning', label: 'Starting' };
      }
    }

    if (status.last_error) {
      return { variant: 'danger', label: 'Error' };
    }

    if (status.running) {
      return { variant: 'success', label: 'Running' };
    }

    if (enabled && !status.running) {
      return { variant: 'warning', label: 'Starting' };
    }

    return { variant: 'neutral', label: 'Stopped' };
  }

  getNodeName(): string {
    return this.node().data.name || this.node().id;
  }

  getNodeDriver(): string {
    return (this.node().data.config as any).driver || 'N/A';
  }

  isNodeEnabled(): boolean {
    return this.node().data.enabled || false;
  }

  getNodeIcon(): string {
    const definitionIcon = this.nodeDefinition()?.icon;
    return definitionIcon || 'settings_input_component';
  }

  getConfigProperties(): {
    label: string;
    value: string;
    isBadge?: boolean;
    badgeVariant?: 'primary' | 'success' | 'neutral' | 'warning' | 'danger';
  }[] {
    const dataConfig = this.node().data.config as any;
    const config = dataConfig.op_config ? { ...dataConfig.op_config } : { ...dataConfig };

    delete config.op_type;
    delete config.topic;
    delete config.sensor_ids;

    if (this.isOperationCategory() && dataConfig.op_type) {
      config['algorithm'] = dataConfig.op_type;
    }

    const params: {
      label: string;
      value: string;
      isBadge?: boolean;
      badgeVariant?: 'primary' | 'success' | 'neutral' | 'warning' | 'danger';
    }[] = [];

    const processValue = (key: string, val: any) => {
      if (val === undefined || val === null || val === '') return;

      if (typeof val === 'object' && !Array.isArray(val)) {
        Object.entries(val).forEach(([subKey, subVal]) => {
          processValue(`${key}_${subKey}`, subVal);
        });
        return;
      }

      let displayVal = '';
      if (Array.isArray(val)) {
        displayVal = `[${val.map((v) => (typeof v === 'number' ? v.toFixed(1) : v)).join(',')}]`;
      } else if (typeof val === 'number') {
        if (key.toLowerCase().includes('port') || Number.isInteger(val)) {
          displayVal = val.toString();
        } else {
          displayVal = val.toFixed(2);
        }
      } else {
        displayVal = String(val);
      }

      if (key === 'pcd_path') {
        displayVal = displayVal.split('/').pop() || displayVal;
      }
      if (key === 'pipeline_name' && displayVal === 'none') return;

      let label = key.replace(/_/g, ' ');
      label = label.charAt(0).toUpperCase() + label.slice(1);

      let isBadge = false;
      let badgeVariant: 'primary' | 'success' | 'neutral' | 'warning' | 'danger' = 'primary';

      if (key === 'mode') {
        isBadge = true;
        badgeVariant = val === 'real' ? 'primary' : 'neutral';
        displayVal = val === 'real' ? 'Hardware' : 'Simulation';
      }

      params.push({ label, value: displayVal, isBadge, badgeVariant });
    };

    Object.entries(config).forEach(([key, val]) => {
      processValue(key, val);
    });

    return params.slice(0, 20);
  }

  getFrameAge(): string | null {
    const status = this.status();
    if (!status) {
      return null;
    }

    let age: number | null = null;
    if ('frame_age_seconds' in status) {
      age = (status as LidarNodeStatus).frame_age_seconds ?? null;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds ?? null;
    }

    if (age === null) {
      return null;
    }

    if (age < 1) {
      return '<1s';
    } else if (age < 60) {
      return `${Math.floor(age)}s`;
    } else {
      return `${Math.floor(age / 60)}m`;
    }
  }

  isFrameStale(): boolean {
    const status = this.status();
    if (!status) {
      return false;
    }

    let age: number | null = null;
    if ('frame_age_seconds' in status) {
      age = (status as LidarNodeStatus).frame_age_seconds ?? null;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds ?? null;
    }

    if (age === null) {
      return false;
    }

    return age > 5 && age <= 60;
  }

  isFrameVeryStale(): boolean {
    const status = this.status();
    if (!status) {
      return false;
    }

    let age: number | null = null;
    if ('frame_age_seconds' in status) {
      age = (status as LidarNodeStatus).frame_age_seconds ?? null;
    } else if ('broadcast_age_seconds' in status) {
      age = (status as FusionNodeStatus).broadcast_age_seconds ?? null;
    }

    if (age === null) {
      return false;
    }

    return age > 60;
  }
}
