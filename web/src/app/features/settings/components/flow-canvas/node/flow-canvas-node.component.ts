import {
  ChangeDetectionStrategy,
  Component,
  computed,
  HostListener,
  inject,
  input,
  OnDestroy,
  OnInit,
  output,
  signal,
} from '@angular/core';

import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeConfig } from '@core/models/node.model';
import { NodeStatusUpdate } from '@core/models/node-status.model';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { NodeRecordingControls } from './node-recording-controls/node-recording-controls';
import { NodeVisibilityToggleComponent } from '../../node-visibility-toggle/node-visibility-toggle.component';

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
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './flow-canvas-node.component.css',
})
export class FlowCanvasNodeComponent implements OnInit, OnDestroy {
  node = input.required<CanvasNode>();
  status = input<NodeStatusUpdate | null>(null);
  liveStatus = input<boolean>(true);
  isLoading = input<boolean>(false);
  isDragging = input<boolean>(false);
  isTogglingVisibility = input<boolean>(false);
  isReloading = input<boolean>(false);
  isPreviewed = input<boolean>(false);
  onEdit = output<void>();
  onToggleEnabled = output<boolean>();
  onToggleVisibility = output<boolean>();
  onTogglePreview = output<void>();

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

  protected operationalIcon = computed<{ icon: string; css: string }>(() => {
    if (!this.liveStatus()) {
      return { icon: 'sync_disabled', css: 'text-syn-color-neutral-300 opacity-50' };
    }
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
        return { icon: 'error', css: 'text-syn-color-error-600' };
      default:
        return { icon: 'radio_button_unchecked', css: 'text-syn-color-neutral-300' };
    }
  });

  protected appBadge = computed<{ text: string; color: string } | null>(() => {
    const status = this.status();
    if (!status?.application_state) return null;

    const { label, value, color } = status.application_state;
    const displayValue = typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value);
    const hexColor = color ? (this.badgeColorMap[color] ?? color) : this.badgeColorMap['gray'];

    return {
      text: `${label}: ${displayValue}`,
      color: hexColor,
    };
  });

  protected pcdColor = computed<string | null>(() => {
    const config = this.node().data.config;
    const color = config?.['pcd_color'];
    return typeof color === 'string' && color.startsWith('#') ? color : null;
  });

  protected errorText = computed<string | null>(() => {
    const status = this.status();
    if (!status || status.operational_state !== 'ERROR') return null;
    return status.error_message ?? null;
  });

  protected cycleTimeLabel = computed<string | null>(() => {
    const ms = this.status()?.cycle_time_ms;
    if (ms == null) return null;
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms.toFixed(ms >= 10 ? 0 : 1)}ms`;
  });

  protected isWebsocketEnabled = computed(() => {
    const def = this.nodeDefinition();
    return def ? def.websocket_enabled : true;
  });

  /** True when the node definition declares at least one output port — used
   *  to conditionally show recording controls. */
  protected hasOutputPort = computed(() => {
    const def = this.nodeDefinition();
    return !!(def && def.outputs && def.outputs.length > 0);
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

  // -- Context Menu --
  contextMenuOpen = signal(false);
  contextMenuPos = signal({ x: 0, y: 0 });

  @HostListener('document:click')
  @HostListener('document:contextmenu')
  onDocumentClick(): void {
    if (this.contextMenuOpen()) {
      this.contextMenuOpen.set(false);
    }
  }

  onContextMenu(event: MouseEvent): void {
    event.preventDefault();
    event.stopPropagation();

    // Dispatch a custom event to close any other open menus
    document.dispatchEvent(new CustomEvent('node-menu:close-all'));

    if (!this.isWebsocketEnabled()) return;

    // Open on next tick so the document:click doesn't immediately close it
    setTimeout(() => {
      this.contextMenuPos.set({ x: event.offsetX, y: event.offsetY });
      this.contextMenuOpen.set(true);
    });
  }

  private closeMenuListener = () => {
    this.contextMenuOpen.set(false);
  };

  ngOnInit(): void {
    document.addEventListener('node-menu:close-all', this.closeMenuListener);
  }

  ngOnDestroy(): void {
    document.removeEventListener('node-menu:close-all', this.closeMenuListener);
  }

  onMenuAction(action: string): void {
    this.contextMenuOpen.set(false);
    if (action === 'preview') {
      this.onTogglePreview.emit();
    }
  }
}
