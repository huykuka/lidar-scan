import {Component, computed, effect, HostListener, inject, OnDestroy, OnInit, signal, untracked} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';

import {NodePlugin} from '@core/models';
import {NodeStoreService} from '@core/services/stores';
import {NodesApiService} from '@core/services/api';
import {DialogService, ToastService} from '@core/services';
import {NodePluginRegistry} from '@core/services/node-plugin-registry.service';
import {StatusWebSocketService} from '@core/services/status-websocket.service';
import {CanvasEditStoreService} from '@features/settings/services/canvas-edit-store.service';

import {FlowCanvasDragService} from './flow-canvas-drag';
import {CanvasNode, FlowCanvasNodeComponent} from './node/flow-canvas-node.component';
import {FlowCanvasPaletteComponent} from './palette/flow-canvas-palette.component';
import {FlowCanvasControlsComponent} from './controls/flow-canvas-controls.component';
import {FlowCanvasConnectionsComponent} from './connections/flow-canvas-connections.component';
import {FlowCanvasEmptyStateComponent} from './empty-state/flow-canvas-empty-state.component';
import {DynamicNodeEditorComponent} from '../dynamic-node-editor/dynamic-node-editor.component';

@Component({
  selector: 'app-flow-canvas',
  standalone: true,
  imports: [
    SynergyComponentsModule,
    FlowCanvasNodeComponent,
    FlowCanvasPaletteComponent,
    FlowCanvasControlsComponent,
    FlowCanvasConnectionsComponent,
    FlowCanvasEmptyStateComponent,
    DynamicNodeEditorComponent,
  ],
  providers: [FlowCanvasDragService],
  templateUrl: './flow-canvas.component.html',
  styleUrl: './flow-canvas.component.css',
})
export class FlowCanvasComponent implements OnInit, OnDestroy {
  protected drag = inject(FlowCanvasDragService);

  // ------ Store ------
  private nodeStore = inject(NodeStoreService);
  protected canvasEditStore = inject(CanvasEditStoreService);

  // ------ View state owned by the component ------
  protected drawerOpen = signal(false);
  protected availablePlugins = signal<NodePlugin[]>([]);
  protected panOffset = signal({ x: 0, y: 0 });
  protected zoom = signal(1);
  protected selectedCanvasNode = signal<CanvasNode | null>(null);
  /** Raw (unsnapped) drag accumulator — tracks continuous mouse movement so the
   *  node follows the cursor smoothly; snapping is applied only on drop. */
  private rawDragPos = signal<{ x: number; y: number } | null>(null);
  protected isTogglingVisibility = signal<string | null>(null);
  protected snapToGrid = signal(true);
  readonly gridSize = 20; // px — must match the SVG grid pattern size
  protected isPaletteLoading = signal(true);
  protected isCanvasLoading = signal(true);
  protected nodeLoadingStates = signal<Record<string, boolean>>({});

  // ------ Store-sourced signals (single source of truth) ------
  protected canvasNodes = this.canvasEditStore.canvasNodes;
  protected connections = this.canvasEditStore.connections;

  // ------ Derived from canvasNodes ------
  protected canvasWidth = computed(() => {
    const nodes = this.canvasNodes();
    if (!nodes.length) return '100%';
    const maxX = Math.max(...nodes.map((n) => n.position.x + 350));
    return `calc(max(100%, ${maxX}px) * ${this.zoom()})`;
  });
  protected canvasHeight = computed(() => {
    const nodes = this.canvasNodes();
    if (!nodes.length) return '100%';
    const maxY = Math.max(...nodes.map((n) => n.position.y + 250));
    return `calc(max(100%, ${maxY}px) * ${this.zoom()})`;
  });

  private nodesApi = inject(NodesApiService);
  private toast = inject(ToastService);
  private dialog = inject(DialogService);
  private pluginRegistry = inject(NodePluginRegistry);
  private statusWs = inject(StatusWebSocketService);
  protected nodesStatus = this.statusWs.status;

  constructor() {
    // Clear the canvas loading spinner once the store is initialized.
    effect(() => {
      if (this.canvasEditStore.isInitialized()) {
        untracked(() => this.isCanvasLoading.set(false));
      }
    });

    // Populate the node palette from registered plugins once definitions arrive.
    effect(() => {
      const definitions = this.nodeStore.nodeDefinitions();
      untracked(() => {
        this.availablePlugins.set(this.pluginRegistry.getAll());
        this.isPaletteLoading.set(false);
      });
    });
  }

  ngOnInit(): void {
    // WebSocket lifecycle is managed by SettingsComponent (the page owner).
    // FlowCanvasComponent only consumes the status signal.
  }

  ngOnDestroy(): void {
    // See ngOnInit — WebSocket is owned by SettingsComponent.
  }

  onCanvasMouseDown(event: MouseEvent) {
    this.selectedCanvasNode.set(null);
    if (event.button === 1 || (event.button === 0 && event.shiftKey)) {
      this.drag.startPan();
      event.preventDefault();
    }
  }

  onCanvasMouseMove(event: MouseEvent) {
    if (this.drag.isPanning()) {
      this.panOffset.update((offset) => ({
        x: offset.x + event.movementX,
        y: offset.y + event.movementY,
      }));
    } else if (this.drag.draggingNode()) {
      const node = this.drag.draggingNode()!;
      // Accumulate raw (unsnapped) delta so the node follows the cursor exactly.
      const prev = this.rawDragPos() ?? node.position;
      const raw = {
        x: prev.x + event.movementX / this.zoom(),
        y: prev.y + event.movementY / this.zoom(),
      };
      this.rawDragPos.set(raw);
      // Update the view-model position directly in the store for smooth rendering.
      this.canvasEditStore.updateCanvasNodePosition(node.id, raw);
      this.drag.updateDraggingNode({ ...node, position: raw });
    } else if (this.drag.pendingConnection()) {
      const pending = this.drag.pendingConnection()!;
      const canvasEl = event.currentTarget as HTMLElement;
      const rect = canvasEl.getBoundingClientRect();
      const toX = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
      const toY = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

      const fromNode = this.canvasNodes().find((n) => n.id === pending.fromNodeId);
      if (fromNode) {
        const def = this.nodeStore.nodeDefinitions().find((d) => d.type === fromNode.data.type);
        const outputPorts = def?.outputs ?? [];
        const totalOutputs = outputPorts.length;

        const fromX = fromNode.position.x + 192 + 6;
        const fromY = fromNode.position.y + this._portY(pending.fromPortIndex, totalOutputs);
        const cp = Math.max(Math.abs(toX - fromX) * 0.5, 40);
        this.drag.updateConnectionPath(
          `M ${fromX} ${fromY} C ${fromX + cp} ${fromY} ${toX - cp} ${toY} ${toX} ${toY}`,
        );
      }
    }
  }

  onCanvasMouseUp(event: MouseEvent) {
    if (this.drag.isPanning()) {
      this.drag.endPan();
    }

    const dropped = this.drag.endNodeDrag();
    if (dropped) {
      // Snap the final position before persisting to the store.
      const snapped = this._snapPos(dropped.position);
      this.canvasEditStore.moveNode(dropped.nodeId, snapped.x, snapped.y);
      this.rawDragPos.set(null);
    }

    if (this.drag.pendingConnection()) {
      this.drag.cancelConnectionDrag();
    }

    if (this.drag.paletteDragType()) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const rawX = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
      const rawY = (event.clientY - rect.top - this.panOffset().y) / this.zoom();
      this.createNodeAtPosition(this.drag.paletteDragType()!, this._snapPos({ x: rawX, y: rawY }));
      this.drag.endPaletteDrag();
    }
  }

  onPortDragStart(event: { nodeId: string; portType: 'input' | 'output'; portId: string; portIndex: number; event: MouseEvent }) {
    if (event.portType !== 'output') return;
    this.drag.startConnectionDrag(event.nodeId, event.portId, event.portIndex);
  }

  onPortDrop(event: { nodeId: string; portType: 'input' | 'output' }) {
    const pending = this.drag.pendingConnection();
    if (!pending || event.portType !== 'input') {
      this.drag.cancelConnectionDrag();
      return;
    }

    const sourceId = pending.fromNodeId;
    const targetId = event.nodeId;

    if (sourceId === targetId) {
      this.drag.cancelConnectionDrag();
      return;
    }

    const exists = this.canvasEditStore.localEdges().some(
      (e) => e.source_node === sourceId && e.target_node === targetId && e.source_port === pending.fromPortId,
    );
    if (exists) {
      this.toast.danger('Connection already exists.');
      this.drag.cancelConnectionDrag();
      return;
    }

    this.canvasEditStore.addEdge({
      source_node: sourceId,
      source_port: pending.fromPortId,
      target_node: targetId,
      target_port: 'in',
    });
    this.drag.cancelConnectionDrag();
  }

  onCanvasWheel(event: WheelEvent) {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    this.zoom.update((z) => Math.max(0.1, Math.min(3, z * delta)));
  }

  onNodeMouseDown(event: MouseEvent, node: CanvasNode) {
    event.stopPropagation();
    this.selectedCanvasNode.set(node);
    this.rawDragPos.set({ x: node.position.x, y: node.position.y });
    this.drag.startNodeDrag(node, event.offsetX, event.offsetY);
  }

  onPluginDragStart(type: string, event: DragEvent) {
    this.drag.startPaletteDrag(type, event);
  }

  onPaletteDragEnd() {
    this.selectedCanvasNode.set(null);
    this.drag.endPaletteDrag();
  }

  onCanvasDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  }

  onCanvasDrop(event: DragEvent) {
    event.preventDefault();
    const type = this.drag.paletteDragType();
    if (!type) return;

    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const rawX = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
    const rawY = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

    this.createNodeAtPosition(type, this._snapPos({ x: rawX, y: rawY }));
    this.drag.endPaletteDrag();
  }

  onEditNode(node: CanvasNode) {
    this.nodeStore.set('selectedNode', node.data);
    this.nodeStore.set('editMode', true);
    this.drawerOpen.set(true);
  }

  async onDeleteNode(node: CanvasNode) {
    const name = node.data.name || node.id;
    if (!(await this.dialog.confirm(`Are you sure you want to delete ${name}?`))) return;
    this.canvasEditStore.deleteNode(node.id);
    this.toast.success(`${name} deleted.`);
  }

  async onDeleteEdge(edgeId: string) {
    if (!(await this.dialog.confirm('Are you sure you want to delete this connection?'))) return;
    this.canvasEditStore.deleteEdge(edgeId);
    this.toast.success('Connection removed.');
  }

  async onToggleNodeEnabled(node: CanvasNode, enabled: boolean) {
    this.nodeLoadingStates.update((states) => ({ ...states, [node.id]: true }));
    try {
      await this.nodesApi.setNodeEnabled(node.id, enabled);
      const name = node.data.name || node.id;
      this.toast.success(`${name} ${enabled ? 'enabled' : 'disabled'}.`);
      this.canvasEditStore.updateNode(node.id, { enabled });
    } catch (error) {
      console.error('Failed to toggle node', error);
      this.toast.danger(`Failed to update node.`);
    } finally {
      this.nodeLoadingStates.update((states) => {
        const newStates = { ...states };
        delete newStates[node.id];
        return newStates;
      });
    }
  }

  async onToggleNodeVisibility(node: CanvasNode, visible: boolean) {
    this.isTogglingVisibility.set(node.id);
    this.canvasEditStore.updateNode(node.id, { visible });
    try {
      await this.nodesApi.setNodeVisible(node.id, visible);
    } catch (error) {
      console.error('Failed to toggle node visibility', error);
      this.canvasEditStore.updateNode(node.id, { visible: !visible });
    } finally {
      this.isTogglingVisibility.set(null);
    }
  }

  getNodeStatus(node: CanvasNode) {
    return this.nodeStore.nodeStatusMap().get(node.id) ?? null;
  }

  isNodeLoading(nodeId: string): boolean {
    return this.nodeLoadingStates()[nodeId] || false;
  }

  isNodeTogglingVisibility(nodeId: string): boolean {
    return this.isTogglingVisibility() === nodeId;
  }

  @HostListener('document:keydown', ['$event'])
  onKeyDown(event: KeyboardEvent) {
    if (event.key !== 'Delete' && event.key !== 'Backspace') return;
    if (this.drawerOpen()) return;

    const tag = (event.target as HTMLElement)?.tagName?.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

    const selected = this.selectedCanvasNode();
    if (!selected) return;

    event.preventDefault();
    this.onDeleteNode(selected);
  }

  resetView() {
    this.panOffset.set({ x: 0, y: 0 });
    this.zoom.set(1);
  }

  zoomIn() {
    this.zoom.update((z) => Math.min(3, z * 1.1));
  }

  zoomOut() {
    this.zoom.update((z) => Math.max(0.1, z * 0.9));
  }

  onDrawerClose() {
    this.drawerOpen.set(false);
  }

  onDrawerRequestClose(event: Event) {
    if ((event as CustomEvent).detail?.source === 'overlay') {
      event.preventDefault();
    }
  }

  private createNodeAtPosition(type: string, position: { x: number; y: number }) {
    const plugin = this.pluginRegistry.get(type);
    if (!plugin) {
      this.toast.danger(`Unknown node type: ${type}`);
      return;
    }
    const defaultData = plugin.createInstance();
    this.nodeStore.set('selectedNode', { ...defaultData, x: position.x, y: position.y });
    this.nodeStore.set('editMode', false);
    this.drawerOpen.set(true);
  }

  /** Y offset of a port within its node (must match store's _portY). */
  private _portY(portIndex: number, totalPorts: number): number {
    if (totalPorts === 1) return 16;
    const nodeHeight = 80;
    const spacing = nodeHeight / (totalPorts + 1);
    return spacing * (portIndex + 1);
  }

  private _snap(value: number): number {
    if (!this.snapToGrid()) return value;
    return Math.round(value / 20) * 20;
  }

  private _snapPos(pos: { x: number; y: number }): { x: number; y: number } {
    return { x: this._snap(pos.x), y: this._snap(pos.y) };
  }
}
