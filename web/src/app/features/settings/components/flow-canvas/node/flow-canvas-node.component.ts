import {Component, computed, inject, input, OnInit, output, signal} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {FusionNodeStatus, LidarNodeStatus, NodeConfig, NodeDefinition, PortSchema, PropertySchema} from '@core/models/node.model';
import {IfNodeStatus} from '@core/models/flow-control.model';
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
export class FlowCanvasNodeComponent implements OnInit{
  node = input.required<CanvasNode>();
  status = input<LidarNodeStatus | FusionNodeStatus | null>(null);
  isLoading = input<boolean>(false);
  isDragging = input<boolean>(false);
  isTogglingVisibility = input<boolean>(false);
  onEdit = output<void>();
  onToggleEnabled = output<boolean>();
  onToggleVisibility = output<boolean>();
  portDragStart = output<{ nodeId: string; portType: 'input' | 'output'; portId: string; portIndex: number; event: MouseEvent }>();
  portDrop = output<{ nodeId: string; portType: 'input' | 'output' }>();
  protected hasInputPort = computed(() => {
    const def = this.nodeDefinition();
    return def && def.inputs && def.inputs.length > 0;
  });
  protected hasOutputPort = computed(() => {
    const def = this.nodeDefinition();
    return def && def.outputs && def.outputs.length > 0;
  });
  protected outputPorts = computed<PortSchema[]>(() => {
    const def = this.nodeDefinition();
    return def?.outputs ?? [];
  });
  protected nodeCategory = computed(() => {
    const categoryFromDefinition = this.nodeDefinition()?.category?.toLowerCase();
    if (categoryFromDefinition) return categoryFromDefinition;

    const categoryFromData = this.node().data.category?.toLowerCase();
    if (categoryFromData) return categoryFromData;

    return this.node().type?.toLowerCase() ?? 'unknown';
  });
  protected isCalibrationNode = computed(() => this.nodeCategory() === 'calibration');
  protected isIfConditionNode = computed(() => this.nodeCategory() === 'flow_control');
  
  /**
   * Get IF condition status if this is an IF node
   */
  protected ifStatus = computed(() => {
    if (!this.isIfConditionNode()) return null;
    return this.status() as IfNodeStatus | null;
  });
  
  /**
   * Get icon indicator for IF condition nodes
   * Shows visual state with colored icons instead of text
   */
  protected ifStateIcon = computed(() => {
    const ifSt = this.ifStatus();
    if (!ifSt) return null;
    
    if (ifSt.state === true) {
      return { 
        name: 'check_circle', 
        color: 'text-syn-color-success-600',
        title: 'Routing to TRUE port'
      };
    } else if (ifSt.state === false) {
      return { 
        name: 'cancel', 
        color: 'text-syn-color-danger-600',
        title: 'Routing to FALSE port'
      };
    }
    
    return { 
      name: 'radio_button_unchecked', 
      color: 'text-syn-color-neutral-400',
      title: 'No routing state yet'
    };
  });
  
  /** True when the node definition has WebSocket streaming enabled (default: true when definition is absent). */
  protected isWebsocketEnabled = computed(() => {
    const def = this.nodeDefinition();
    // When no definition is found, default to true (backward-compat with unknown types)
    return def ? def.websocket_enabled !== false : true;
  });
  private nodeStore = inject(NodeStoreService);
  protected nodeDefinition = computed(() => {
    return this.nodeStore.nodeDefinitions().find((d) => d.type === this.node().data.type);
  });

  ngOnInit(): void {
    console.log(this.node())
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

  /**
   * Calculate Y position for an output port based on its index
   * Ports are distributed evenly across the node height
   */
  getOutputPortY(portIndex: number, totalPorts: number): number {
    if (totalPorts === 1) {
      return 16; // Single port: center at top-4 (original position)
    }
    // Multiple ports: distribute evenly
    const nodeHeight = 80; // Approximate node height in pixels
    const spacing = nodeHeight / (totalPorts + 1);
    return spacing * (portIndex + 1);
  }

  /**
   * Get port color based on port ID for multi-port nodes
   */
  getPortColorClass(portId: string): string {
    if (portId === 'true') {
      return 'bg-green-600'; // Green for true port
    } else if (portId === 'false') {
      return 'bg-orange-500'; // Orange for false port
    }
    return 'bg-syn-color-primary-600'; // Default blue for single-port nodes
  }

}
