import {
  Component,
  computed,
  effect,
  HostListener,
  inject,
  OnDestroy,
  OnInit,
  signal,
  untracked,
} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {FlowCanvasDragService} from '@features/settings/components/flow-canvas/flow-canvas-drag';
import {
  CanvasNode,
  FlowCanvasNodeComponent,
} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {
  FlowCanvasPaletteComponent
} from '@features/settings/components/flow-canvas/palette/flow-canvas-palette.component';
import {
  Connection,
  FlowCanvasConnectionsComponent,
} from '@features/settings/components/flow-canvas/connections/flow-canvas-connections.component';
import {
  FlowCanvasEmptyStateComponent
} from '@features/settings/components/flow-canvas/empty-state/flow-canvas-empty-state.component';
import {
  DynamicNodeEditorComponent
} from '@features/settings/components/dynamic-node-editor/dynamic-node-editor.component';
import {NodePlugin} from '@core/models';
import {NodeStoreService} from '@core/services/stores';
import {NodesApiService} from '@core/services/api';
import {DialogService, ToastService} from '@core/services';
import {NodePluginRegistry} from '@core/services/node-plugin-registry.service';
import {StatusWebSocketService} from '@core/services/status-websocket.service';
import {NodeConfig} from '@core/models/node.model';
import {CanvasEditStoreService} from '@features/settings/services/canvas-edit-store.service';

@Component({
  selector: 'app-flow-canvas',
  standalone: true,
  imports: [
    SynergyComponentsModule,
    FlowCanvasNodeComponent,
    FlowCanvasPaletteComponent,
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
  protected drawerOpen = signal(false);
  protected availablePlugins = signal<NodePlugin[]>([]);
  protected canvasNodes = signal<CanvasNode[]>([]);
  protected connections = signal<Connection[]>([]);
  protected panOffset = signal({ x: 0, y: 0 });
  protected zoom = signal(1);
  protected selectedCanvasNode = signal<CanvasNode | null>(null);
  protected isTogglingVisibility = signal<string | null>(null);
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
  protected isPaletteLoading = signal(true);
  protected isCanvasLoading = signal(true);
  protected nodeLoadingStates = signal<Record<string, boolean>>({});

  private nodeStore = inject(NodeStoreService);
  // Phase 2.2: drive canvasNodes + connections from the local-edit store
  protected canvasEditStore = inject(CanvasEditStoreService);
  protected nodes = this.canvasEditStore.localNodes;
  protected edges = this.canvasEditStore.localEdges;
  private nodesApi = inject(NodesApiService);
  private toast = inject(ToastService);
  private dialog = inject(DialogService);
  private pluginRegistry = inject(NodePluginRegistry);
  private statusWs = inject(StatusWebSocketService);
  protected nodesStatus = this.statusWs.status;

  constructor() {
    // Phase 2.2: react to localNodes from the store
    effect(() => {
      const nodes = this.nodes();
      untracked(() => {
        this.mergeCanvasNodes(nodes);
        this.isCanvasLoading.set(false);
      });
    });

    // Phase 2.2: react to localEdges from the store
    effect(() => {
      const edges = this.edges();
      untracked(() => this.updateConnections());
    });

    // Phase 7.2: derive availablePlugins from nodeStore.nodeDefinitions()
    // nodeDefinitions are populated by NodePluginRegistry.loadFromBackend() which
    // is now called in SettingsComponent.ngOnInit() before initFromBackend().
    effect(() => {
      const definitions = this.nodeStore.nodeDefinitions();
      if (definitions.length > 0) {
        untracked(() => {
          this.availablePlugins.set(this.pluginRegistry.getAll());
          this.isPaletteLoading.set(false);
        });
      }
    });
  }

  ngOnInit(): void {
    this.statusWs.connect();
  }

  ngOnDestroy(): void {
    this.statusWs.disconnect();
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
      const newPosition = {
        x: node.position.x + event.movementX / this.zoom(),
        y: node.position.y + event.movementY / this.zoom(),
      };

      this.canvasNodes.update((nodes) =>
        nodes.map((n) => (n.id === node.id ? { ...n, position: newPosition } : n)),
      );

      this.drag.updateDraggingNode({ ...node, position: newPosition });
      this.updateConnections();
    } else if (this.drag.pendingConnection()) {
      // Update the live pending bezier path as the cursor moves
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

        const fromX = fromNode.position.x + 192 + 6; // node width + tab center (6px)
        const fromY = fromNode.position.y + this.calculatePortY(pending.fromPortIndex, totalOutputs);
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
      // Phase 2.6: persist final drag position into the local-edit store
      this.canvasEditStore.moveNode(dropped.nodeId, dropped.position.x, dropped.position.y);
      this.updateConnections();
    }

    // Cancel any pending port connection if released on empty canvas
    if (this.drag.pendingConnection()) {
      this.drag.cancelConnectionDrag();
    }

    if (this.drag.paletteDragType()) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const x = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
      const y = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

      this.createNodeAtPosition(this.drag.paletteDragType()!, { x, y });
      this.drag.endPaletteDrag();
    }
  }

  /** Called when user starts dragging from an output port on a node. */
  onPortDragStart(event: { nodeId: string; portType: 'input' | 'output'; portId: string; portIndex: number; event: MouseEvent }) {
    if (event.portType !== 'output') return;
    this.drag.startConnectionDrag(event.nodeId, event.portId, event.portIndex);
  }

  /** Called when user releases on an input port on a node. */
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

    // Phase 2.3: Check for duplicate edge against localEdges, then stage locally
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
    const x = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
    const y = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

    this.createNodeAtPosition(type, { x, y });
    this.drag.endPaletteDrag();
  }

  onEditNode(node: CanvasNode) {
    this.nodeStore.set('selectedNode', node.data);
    this.nodeStore.set('editMode', true);
    this.drawerOpen.set(true);
  }

  // Phase 2.5: deleteNode now delegates to the store
  async onDeleteNode(node: CanvasNode) {
    const name = node.data.name || node.id;
    if (!(await this.dialog.confirm(`Are you sure you want to delete ${name}?`))) return;

    this.canvasEditStore.deleteNode(node.id);
    this.toast.success(`${name} deleted.`);
  }

  // Phase 2.4: deleteEdge now delegates to the store
  async onDeleteEdge(edgeId: string) {
    if (!(await this.dialog.confirm('Are you sure you want to delete this connection?'))) return;
    this.canvasEditStore.deleteEdge(edgeId);
    this.updateConnections();
    this.toast.success('Connection removed.');
  }

  // Phase 2.8: after live enable/disable, sync localNodes via the store
  async onToggleNodeEnabled(node: CanvasNode, enabled: boolean) {
    this.nodeLoadingStates.update((states) => ({ ...states, [node.id]: true }));

    try {
      await this.nodesApi.setNodeEnabled(node.id, enabled);
      const name = node.data.name || node.id;
      this.toast.success(`${name} ${enabled ? 'enabled' : 'disabled'}.`);
      // Keep localNodes in sync without marking isDirty (pass-through update)
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
    // Set pending state for this specific node
    this.isTogglingVisibility.set(node.id);

    // Get current nodes for optimistic update and rollback
    const currentNodes = this.nodes();

    try {
      // Optimistic update: update local state immediately
      this.nodeStore.set(
        'nodes',
        currentNodes.map((n) => (n.id === node.id ? { ...n, visible } : n)),
      );

      // Call backend API
      await this.nodesApi.setNodeVisible(node.id, visible);
    } catch (error) {
      console.error('Failed to toggle node visibility', error);

      // Rollback optimistic update on error
      this.nodeStore.set('nodes', currentNodes);
    } finally {
      // Clear pending state
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

  onDrawerClose() {
    this.drawerOpen.set(false);
  }

  onDrawerRequestClose(event: Event) {
    if ((event as CustomEvent).detail?.source === 'overlay') {
      event.preventDefault();
    }
  }

  private mergeCanvasNodes(nodes: NodeConfig[]): void {
    const existing = new Map(this.canvasNodes().map((n) => [n.id, n]));
    const incoming = new Set(nodes.map((n) => n.id));

    const merged: CanvasNode[] = nodes.map((node, index) => {
      const prev = existing.get(node.id);
      return {
        id: node.id,
        type: (node.category || node.type || 'unknown').toLowerCase(),
        data: node,
        position: prev
          ? prev.position
          : {
              x: node.x ?? 100 + (index % 4) * 300,
              y: node.y ?? 100 + Math.floor(index / 4) * 250,
            },
      };
    });

    const prevIds = [...existing.keys()];
    const structurallyChanged =
      merged.length !== prevIds.length || prevIds.some((id) => !incoming.has(id));

    if (structurallyChanged) {
      this.canvasNodes.set(merged);
      this.updateConnections();
    } else {
      const mergedById = new Map(merged.map((m) => [m.id, m]));
      this.canvasNodes.update((current) =>
        current.map((n) => {
          const updated = mergedById.get(n.id);
          return updated ? { ...n, data: updated.data } : n;
        }),
      );
    }
  }

  private updateConnections(): void {
    const nodes = this.canvasNodes();
    const edges = this.edges();
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const prev = new Map(this.connections().map((c) => [c.id, c]));

    const next: Connection[] = [];

    edges.forEach((edge) => {
      const sourceNode = nodeMap.get(edge.source_node);
      const targetNode = nodeMap.get(edge.target_node);
      if (!sourceNode || !targetNode) return;

      const sourceDef = this.nodeStore.nodeDefinitions().find((d) => d.type === sourceNode.data.type);
      const outputPorts = sourceDef?.outputs ?? [];
      const portIndex = outputPorts.findIndex((p) => p.id === edge.source_port);
      const totalOutputs = outputPorts.length;

      let color = '#6366f1';
      if (edge.source_port === 'true') color = '#16a34a';
      else if (edge.source_port === 'false') color = '#f97316';

      const path = this.calculatePath(sourceNode, targetNode, portIndex >= 0 ? portIndex : 0, totalOutputs);

      const existing = prev.get(edge.id);
      if (existing && existing.path === path && existing.color === color) {
        // Path and color unchanged — reuse the same object reference so Angular's
        // @for track keeps the DOM node alive and the draw-in animation does NOT replay.
        next.push(existing);
      } else {
        next.push({ id: edge.id, from: edge.source_node, to: edge.target_node, path, color });
      }
    });

    this.connections.set(next);
  }

  private calculatePath(fromNode: CanvasNode, toNode: CanvasNode, fromPortIndex: number = 0, totalOutputPorts: number = 1): string {
    const fromX = fromNode.position.x + 192 + 6; // node width + tab center
    const fromY = fromNode.position.y + this.calculatePortY(fromPortIndex, totalOutputPorts);
    const toX = toNode.position.x - 6;           // target tab center
    const toY = toNode.position.y + 16;

    const controlPointOffset = Math.max(Math.abs(toX - fromX) * 0.5, 40);
    const cp1x = fromX + controlPointOffset;
    const cp1y = fromY;
    const cp2x = toX - controlPointOffset;
    const cp2y = toY;

    return `M ${fromX} ${fromY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${toX} ${toY}`;
  }

  /**
   * Calculate Y position for a port based on its index and total count
   * Matches the logic in FlowCanvasNodeComponent.getOutputPortY()
   */
  private calculatePortY(portIndex: number, totalPorts: number): number {
    if (totalPorts === 1) {
      return 16; // Single port: center at top-4 (original position)
    }
    // Multiple ports: distribute evenly
    const nodeHeight = 80; // Approximate node height in pixels
    const spacing = nodeHeight / (totalPorts + 1);
    return spacing * (portIndex + 1);
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
}
