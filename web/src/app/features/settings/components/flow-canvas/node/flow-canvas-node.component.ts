import {Component, ComponentRef, computed, effect, inject, input, output, signal, untracked, viewChild, ViewContainerRef} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {FusionNodeStatus, LidarNodeStatus, NodeConfig} from '@core/models/node.model';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodeRecordingControls} from './node-recording-controls/node-recording-controls';
import {NodeCalibrationControls} from './node-calibration-controls/node-calibration-controls';
import {NodePluginRegistry} from '@core/services/node-plugin-registry.service';
import {NodeCardComponent} from '@core/models/node-plugin.model';
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
  isExpanded = signal<boolean>(false);
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
  private pluginRegistry = inject(NodePluginRegistry);
  cardHost = viewChild('cardHost', { read: ViewContainerRef });
  private pluginCardRef = signal<ComponentRef<NodeCardComponent> | null>(null);

  constructor() {
    effect(() => {
      const isOpen = this.isExpanded();
      const nodeData = this.node();
      const container = this.cardHost();

      if (!isOpen || !container) {
        this.destroyPluginCard();
        return;
      }

      const plugin = this.pluginRegistry.get(nodeData.type);
      if (!plugin?.cardComponent) {
        this.destroyPluginCard();
        return;
      }

      const cardComponent = plugin.cardComponent;

      untracked(() => {
        const existing = this.pluginCardRef();
        if (existing && existing.instance.constructor === cardComponent) {
          return;
        }

        this.destroyPluginCard();
        const componentRef = container.createComponent(cardComponent);
        componentRef.setInput('node', nodeData);
        componentRef.setInput('status', this.status());
        this.pluginCardRef.set(componentRef);
      });
    });

    effect(() => {
      const nodeData = this.node();
      const currentStatus = this.status();
      const ref = this.pluginCardRef();
      if (!ref) return;
      ref.setInput('node', nodeData);
      ref.setInput('status', currentStatus);
    });
  }

  private destroyPluginCard(): void {
    const ref = this.pluginCardRef();
    if (ref) {
      ref.destroy();
      this.pluginCardRef.set(null);
    }
  }

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

}
