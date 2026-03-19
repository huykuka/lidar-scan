import {Component, computed, inject, input, output, signal} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {FusionNodeStatus, LidarNodeStatus, NodeConfig, NodeDefinition, PropertySchema} from '@core/models/node.model';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodeRecordingControls} from './node-recording-controls/node-recording-controls';
import {NodeCalibrationControls} from './node-calibration-controls/node-calibration-controls';
import {NodeVisibilityToggleComponent} from '../../node-visibility-toggle/node-visibility-toggle.component';

export interface CanvasNode {
  id: string;
  type: string;
  data: NodeConfig;
  position: { x: number; y: number };
}

@Component({
  selector: 'app-flow-canvas-node',
  imports: [SynergyComponentsModule, NodeRecordingControls, NodeCalibrationControls, NodeVisibilityToggleComponent],
  templateUrl: './flow-canvas-node.component.html',
  styleUrl: './flow-canvas-node.component.css',
})
export class FlowCanvasNodeComponent {
  node = input.required<CanvasNode>();
  status = input<LidarNodeStatus | FusionNodeStatus | null>(null);
  isLoading = input<boolean>(false);
  isDragging = input<boolean>(false);
  isTogglingVisibility = input<boolean>(false);
  onEdit = output<void>();
  onToggleEnabled = output<boolean>();
  onToggleVisibility = output<boolean>();
  portDragStart = output<{ nodeId: string; portType: 'input' | 'output'; event: MouseEvent }>();
  portDrop = output<{ nodeId: string; portType: 'input' | 'output' }>();
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
  private nodeStore = inject(NodeStoreService);
  protected nodeDefinition = computed(() => {
    return this.nodeStore.nodeDefinitions().find((d) => d.type === this.node().data.type);
  });

  statusBadge(): {
    variant: 'primary' | 'success' | 'neutral' | 'warning' | 'danger';
    label: string;
  } {
    const status = this.status();
    const enabled = this.node().data.enabled;

    if (!enabled) {
      return {variant: 'neutral', label: 'Disabled'};
    }

    if (!status) {
      return {variant: 'warning', label: 'Unknown'};
    }

    const lidarStatus = status as LidarNodeStatus;
    if (lidarStatus.connection_status) {
      if (lidarStatus.connection_status === 'disconnected') {
        return {variant: 'danger', label: 'Disconnected'};
      }
      if (lidarStatus.connection_status === 'error') {
        return {variant: 'danger', label: 'Error'};
      }
      if (lidarStatus.connection_status === 'starting') {
        return {variant: 'warning', label: 'Starting'};
      }
    }

    if (status.last_error) {
      return {variant: 'danger', label: 'Error'};
    }

    if (status.running) {
      return {variant: 'success', label: 'Running'};
    }

    if (enabled && !status.running) {
      return {variant: 'warning', label: 'Starting'};
    }

    return {variant: 'neutral', label: 'Stopped'};
  }

  getNodeName(): string {
    return this.node().data.name || this.node().id;
  }


  isNodeEnabled(): boolean {
    return this.node().data.enabled || false;
  }

  getNodeIcon(): string {
    const definitionIcon = this.nodeDefinition()?.icon;
    return definitionIcon || 'settings_input_component';
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

  getStatusColorClass(): string {
    const badge = this.statusBadge();
    switch (badge.variant) {
      case 'success':
        return 'bg-syn-color-success-600';
      case 'warning':
        return 'bg-syn-color-warning-600';
      case 'danger':
        return 'bg-syn-color-danger-600';
      case 'primary':
        return 'bg-syn-color-primary-600';
      default:
        return 'bg-syn-color-neutral-400';
    }
  }

}
