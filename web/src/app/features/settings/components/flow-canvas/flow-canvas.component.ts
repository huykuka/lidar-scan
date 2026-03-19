import {
  Component,
  computed,
  effect,
  HostListener,
  inject,
  OnDestroy,
  OnInit,
  output,
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
import {EdgesApiService, NodesApiService} from '@core/services/api';
import {DialogService, ToastService} from '@core/services';
import {NodePluginRegistry} from '@core/services/node-plugin-registry.service';
import {StatusWebSocketService} from '@core/services/status-websocket.service';
import {NodeConfig} from '@core/models/node.model';

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
  hasUnsavedChangesChange = output<boolean>();
  public hasUnsavedChanges = signal(false);
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
  protected nodes = this.nodeStore.nodes;
  protected edges = this.nodeStore.edges;
  private nodesApi = inject(NodesApiService);
  private edgesApi = inject(EdgesApiService);
  private toast = inject(ToastService);
  private dialog = inject(DialogService);
  private pluginRegistry = inject(NodePluginRegistry);
  private statusWs = inject(StatusWebSocketService);
  protected nodesStatus = this.statusWs.status;
  private unsavedPositions = new Map<string, { x: number; y: number }>();

  constructor() {
    effect(() => {
      const nodes = this.nodes();
      untracked(() => {
        this.mergeCanvasNodes(nodes);
        setTimeout(() => this.isCanvasLoading.set(false), 50);
      });
    });

    effect(() => {
      const edges = this.edges();
      untracked(() => this.updateConnections());
    });
  }

  ngOnInit(): void {
    this.loadGraphData();
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
        const fromX = fromNode.position.x + 192 + 6; // node width + tab center (6px)
        const fromY = fromNode.position.y + 16;      // header center (top-4)
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
      this.unsavedPositions.set(dropped.nodeId, dropped.position);
      this.hasUnsavedChanges.set(true);
      this.hasUnsavedChangesChange.emit(true);
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

  /**
   * Save all unsaved node positions to the backend
   * Called explicitly by the parent component (e.g., Save & Reload button)
   */
  async saveAllPositions(): Promise<void> {
    if (this.unsavedPositions.size === 0) {
      return; // Nothing to save
    }

    const savePromises: Promise<void>[] = [];

    this.unsavedPositions.forEach((position, nodeId) => {
      const node = this.nodes().find((n) => n.id === nodeId);
      if (node) {
        savePromises.push(
          this.nodesApi
            .upsertNode({
              ...node,
              x: position.x,
              y: position.y,
            })
            .then(() => {}),
        );
      }
    });

    try {
      await Promise.all(savePromises);
      this.unsavedPositions.clear();
      this.hasUnsavedChanges.set(false);
      this.hasUnsavedChangesChange.emit(false);
    } catch (error) {
      console.error('Failed to save node positions', error);
      throw error; // Re-throw to let parent handle
    }
  }

  /** Called when user starts dragging from an output port on a node. */
  onPortDragStart(event: { nodeId: string; portType: 'input' | 'output'; event: MouseEvent }) {
    if (event.portType !== 'output') return;
    this.drag.startConnectionDrag(event.nodeId);
  }

  /** Called when user releases on an input port on a node. */
  async onPortDrop(event: { nodeId: string; portType: 'input' | 'output' }) {
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

    // Check for duplicate edge
    const exists = this.edges().some(
      (e) => e.source_node === sourceId && e.target_node === targetId,
    );
    if (exists) {
      this.toast.danger('Connection already exists.');
      this.drag.cancelConnectionDrag();
      return;
    }

    try {
      await this.edgesApi.createEdge({ source_node: sourceId, target_node: targetId });
      const [nodes, edges] = await Promise.all([
        this.nodesApi.getNodes(),
        this.edgesApi.getEdges(),
      ]);
      this.nodeStore.setState({ nodes, edges });
      this.toast.success('Connection created.');
    } catch (err) {
      console.error('Failed to create edge', err);
      this.toast.danger('Failed to create connection.');
    } finally {
      this.drag.cancelConnectionDrag();
    }
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

  async onDeleteNode(node: CanvasNode) {
    const name = node.data.name || node.id;
    if (!(await this.dialog.confirm(`Are you sure you want to delete ${name}?`))) return;

    try {
      await this.nodesApi.deleteNode(node.id);

      // Remove node from local state
      this.nodeStore.set(
        'nodes',
        this.nodes().filter((n) => n.id !== node.id),
      );

      // Backend automatically deletes attached edges, we must also remove them locally
      this.nodeStore.set(
        'edges',
        this.edges().filter((e) => e.source_node !== node.id && e.target_node !== node.id),
      );

      this.toast.success(`${name} deleted.`);
    } catch (error) {
      console.error('Failed to delete node', error);
      this.toast.danger(`Failed to delete ${name}.`);
    }
  }

  async onDeleteEdge(edgeId: string) {
    if (!(await this.dialog.confirm('Are you sure you want to delete this connection?'))) return;
    try {
      await this.edgesApi.deleteEdge(edgeId);
      this.nodeStore.set(
        'edges',
        this.edges().filter((e) => e.id !== edgeId),
      );
      this.updateConnections();
      this.toast.success('Connection removed.');
    } catch (error) {
      console.error('Failed to delete connection', error);
      this.toast.danger('Failed to delete connection.');
    }
  }

  async onToggleNodeEnabled(node: CanvasNode, enabled: boolean) {
    this.nodeLoadingStates.update((states) => ({ ...states, [node.id]: true }));

    try {
      await this.nodesApi.setNodeEnabled(node.id, enabled);
      const name = node.data.name || node.id;
      this.toast.success(`${name} ${enabled ? 'enabled' : 'disabled'}.`);
      await this.loadGraphData();
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

      const name = node.data.name || node.id;
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
    const status = this.nodesStatus();
    if (!status) return null;
    return status.nodes.find((n: any) => n.id === node.id) || null;
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

  private async loadGraphData() {
    this.isPaletteLoading.set(true);
    this.isCanvasLoading.set(true);
    try {
      const [nodes, edges] = await Promise.all([
        this.nodesApi.getNodes(),
        this.edgesApi.getEdges(),
      ]);
      // loadFromBackend fetches definitions AND populates NodeStore + registry
      await this.pluginRegistry.loadFromBackend();
      this.availablePlugins.set(this.pluginRegistry.getAll());
      this.isPaletteLoading.set(false); // Palette has fetched its templates

      this.nodeStore.setState({ nodes, edges });
    } catch (error) {
      console.error('Failed to load graph data', error);
      this.toast.danger('Failed to load infrastructure graph.');
      this.isPaletteLoading.set(false);
      this.isCanvasLoading.set(false);
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
    const connections: Connection[] = [];
    const nodes = this.canvasNodes();
    const edges = this.edges();

    // Create a map for fast lookup of node instances by ID
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    edges.forEach((edge) => {
      const sourceNode = nodeMap.get(edge.source_node);
      const targetNode = nodeMap.get(edge.target_node);

      if (sourceNode && targetNode) {
        const path = this.calculatePath(sourceNode, targetNode);
        connections.push({
          id: edge.id,
          from: edge.source_node,
          to: edge.target_node,
          path,
        });
      }
    });

    this.connections.set(connections);
  }

  private calculatePath(fromNode: CanvasNode, toNode: CanvasNode): string {
    const fromX = fromNode.position.x + 192 + 6; // node width + tab center
    const fromY = fromNode.position.y + 16;      // header center (top-4)
    const toX = toNode.position.x - 6;           // target tab center
    const toY = toNode.position.y + 16;

    const controlPointOffset = Math.max(Math.abs(toX - fromX) * 0.5, 40);
    const cp1x = fromX + controlPointOffset;
    const cp1y = fromY;
    const cp2x = toX - controlPointOffset;
    const cp2y = toY;

    return `M ${fromX} ${fromY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${toX} ${toY}`;
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
