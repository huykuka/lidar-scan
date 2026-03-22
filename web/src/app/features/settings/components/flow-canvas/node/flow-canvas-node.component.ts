import {Component, computed, inject, input, output} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {NodeConfig, PortSchema} from '@core/models/node.model';
import {NodeStatusUpdate} from '@core/models/node-status.model';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodeRecordingControls} from './node-recording-controls/node-recording-controls';
import {NodeVisibilityToggleComponent} from '../../node-visibility-toggle/node-visibility-toggle.component';

export interface CanvasNode {
  id: string;
  type: string;
  data: NodeConfig;
  position: { x: number; y: number };
}

@Component({
  selector: 'app-flow-canvas-node',
  imports: [SynergyComponentsModule, NodeRecordingControls, NodeVisibilityToggleComponent],
  templateUrl: './flow-canvas-node.component.html',
  styleUrl: './flow-canvas-node.component.css',
})
export class FlowCanvasNodeComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);
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

  /**
   * Map semantic color names from application_state to CSS hex colors
   */
  protected readonly badgeColorMap: Record<string, string> = {
    green: '#16a34a',
    blue: '#2563eb',
    orange: '#d97706',
    red: '#dc2626',
    gray: '#6b7280',
  };

  /**
   * Compute operational state icon and styling
   */
  protected operationalIcon = computed<{ icon: string; css: string }>(() => {
    const status = this.status();
    if (!status) {
      return { icon: 'radio_button_unchecked', css: 'text-syn-color-neutral-300' };
    }

    switch (status.operational_state) {
      case 'INITIALIZE':
        return { icon: 'hourglass_empty', css: 'text-syn-color-warning-600 animate-pulse' };
      case 'RUNNING':
        return { icon: 'play_circle', css: 'text-syn-color-success-600' };
      case 'STOPPED':
        return { icon: 'pause_circle', css: 'text-syn-color-neutral-400' };
      case 'ERROR':
        return { icon: 'error', css: 'text-syn-color-danger-600' };
      default:
        return { icon: 'radio_button_unchecked', css: 'text-syn-color-neutral-300' };
    }
  });

  /**
   * Compute application-specific state badge (Node-RED style bottom-right badge)
   */
  protected appBadge = computed<{ text: string; color: string } | null>(() => {
    const status = this.status();
    if (!status?.application_state) return null;

    const { label, value, color } = status.application_state;

    // Convert boolean values to strings
    const displayValue = typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value);

    // Map semantic color to hex, defaulting to gray if not provided
    const hexColor = color ? (this.badgeColorMap[color] ?? color) : this.badgeColorMap['gray'];

    return {
      text: `${label}: ${displayValue}`,
      color: hexColor,
    };
  });

  /**
   * Compute error message (only when operational_state is ERROR)
   */
  protected errorText = computed<string | null>(() => {
    const status = this.status();
    if (!status || status.operational_state !== 'ERROR') return null;
    return status.error_message ?? null;
  });

  /** True when the node definition has WebSocket streaming enabled (default: true when definition is absent). */
  protected isWebsocketEnabled = computed(() => {
    const def = this.nodeDefinition();
    // When no definition is found, default to true (backward-compat with unknown types)
    return def ? def.websocket_enabled : true;
  });
  private nodeStore = inject(NodeStoreService);
  protected nodeDefinition = computed(() => {
    return this.nodeStore.nodeDefinitions().find((d) => d.type === this.node().data.type);
  });


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


}
