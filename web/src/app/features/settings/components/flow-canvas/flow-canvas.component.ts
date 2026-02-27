import { Component, inject, signal, computed, effect, OnInit, OnDestroy, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeStoreService } from '../../../../core/services/stores/node-store.service';
import { NodeConfig, Edge } from '../../../../core/models/node.model';
import { NodesApiService } from '../../../../core/services/api/nodes-api.service';
import { EdgesApiService } from '../../../../core/services/api/edges-api.service';
import { ToastService } from '../../../../core/services/toast.service';
import { DialogService } from '../../../../core/services';
import { NodePluginRegistry } from '../../../../core/services/node-plugin-registry.service';
import { DynamicNodeEditorComponent } from '../dynamic-node-editor/dynamic-node-editor.component';
import { NodePlugin } from '../../../../core/models/node-plugin.model';
import { FlowCanvasNodeComponent, CanvasNode } from './node/flow-canvas-node.component';
import { FlowCanvasPaletteComponent } from './palette/flow-canvas-palette.component';
import {
  FlowCanvasConnectionsComponent,
  Connection,
} from './connections/flow-canvas-connections.component';
import { FlowCanvasEmptyStateComponent } from './empty-state/flow-canvas-empty-state.component';
import { StatusWebSocketService } from '../../../../core/services/status-websocket.service';

@Component({
  selector: 'app-flow-canvas',
  standalone: true,
  imports: [
    CommonModule,
    SynergyComponentsModule,
    FlowCanvasNodeComponent,
    FlowCanvasPaletteComponent,
    FlowCanvasConnectionsComponent,
    FlowCanvasEmptyStateComponent,
  ],
  templateUrl: './flow-canvas.component.html',
  styleUrl: './flow-canvas.component.css',
})
export class FlowCanvasComponent implements OnInit, OnDestroy {
  private nodeStore = inject(NodeStoreService);
  private nodesApi = inject(NodesApiService);
  private edgesApi = inject(EdgesApiService);
  private toast = inject(ToastService);
  private dialogService = inject(DialogService);
  private pluginRegistry = inject(NodePluginRegistry);
  private statusWs = inject(StatusWebSocketService);

  // Output for unsaved changes
  hasUnsavedChangesChange = output<boolean>();

  protected nodes = this.nodeStore.nodes;
  protected edges = this.nodeStore.edges;
  protected availablePlugins = signal<NodePlugin[]>([]);

  // Canvas state
  protected canvasNodes = signal<CanvasNode[]>([]);
  protected connections = signal<Connection[]>([]);
  protected isPanning = signal(false);
  protected panOffset = signal({ x: 0, y: 0 });
  protected zoom = signal(1);

  // Drag state
  protected draggingNode = signal<CanvasNode | null>(null);
  protected dragOffset = signal({ x: 0, y: 0 });

  // Canvas bounds for scrolling
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

  // Palette drag state (dragging from sidebar)
  protected paletteDragType = signal<string | null>(null);

  // Port-to-port connection drag state
  protected pendingConnection = signal<{
    fromNodeId: string;
    cursorX: number;
    cursorY: number;
  } | null>(null);
  protected pendingPath = signal<string | null>(null);

  // Node status — driven by WebSocket instead of HTTP polling
  protected nodesStatus = this.statusWs.status;
  
  // Track unsaved position changes
  private unsavedPositions = new Map<string, { x: number; y: number }>();
  public hasUnsavedChanges = signal(false);

  // Loading states
  protected isPaletteLoading = signal(true);
  protected isCanvasLoading = signal(true);
  protected nodeLoadingStates = signal<Record<string, boolean>>({});

  constructor() {
    // Watch for changes in node store
    effect(() => {
      const nodes = this.nodes();
      const edges = this.edges();

      // Re-initialize canvas nodes when data changes
      setTimeout(() => {
        this.initializeCanvasNodes();
        this.updateConnections();
        // Delay slightly so layout engine resolves DOM before removing loader
        setTimeout(() => this.isCanvasLoading.set(false), 50);
      }, 0);
    });
  }

  ngOnInit(): void {
    this.loadGraphData();
    this.statusWs.connect(); // subscribe to live status via WebSocket
  }

  ngOnDestroy(): void {
    this.statusWs.disconnect();
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

  private initializeCanvasNodes() {
    const nodes: CanvasNode[] = [];

    this.nodes().forEach((node, index) => {
      nodes.push({
        id: node.id,
        type: node.category as 'sensor' | 'fusion' | 'operation',
        data: node,
        position: {
          x: node.x ?? (100 + (index % 4) * 300),
          y: node.y ?? (100 + Math.floor(index / 4) * 250),
        },
      });
    });

    this.canvasNodes.set(nodes);
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
    const fromX = fromNode.position.x + 296; // 288 (node width) + 8 (half port width outside)
    const fromY = fromNode.position.y + 44;
    const toX = toNode.position.x - 8;
    const toY = toNode.position.y + 44;

    const controlPointOffset = Math.max(Math.abs(toX - fromX) * 0.5, 40);
    const cp1x = fromX + controlPointOffset;
    const cp1y = fromY;
    const cp2x = toX - controlPointOffset;
    const cp2y = toY;

    return `M ${fromX} ${fromY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${toX} ${toY}`;
  }

  onCanvasMouseDown(event: MouseEvent) {
    if (event.button === 1 || (event.button === 0 && event.shiftKey)) {
      this.isPanning.set(true);
      event.preventDefault();
    }
  }

  onCanvasMouseMove(event: MouseEvent) {
    if (this.isPanning()) {
      this.panOffset.update((offset) => ({
        x: offset.x + event.movementX,
        y: offset.y + event.movementY,
      }));
    } else if (this.draggingNode()) {
      const node = this.draggingNode()!;
      const newPosition = {
        x: node.position.x + event.movementX / this.zoom(),
        y: node.position.y + event.movementY / this.zoom(),
      };

      this.canvasNodes.update((nodes) =>
        nodes.map((n) => (n.id === node.id ? { ...n, position: newPosition } : n)),
      );

      this.draggingNode.set({ ...node, position: newPosition });
      this.updateConnections();
    } else if (this.pendingConnection()) {
      // Update the live pending bezier path as the cursor moves
      const pending = this.pendingConnection()!;
      const canvasEl = event.currentTarget as HTMLElement;
      const rect = canvasEl.getBoundingClientRect();
      const toX = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
      const toY = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

      const fromNode = this.canvasNodes().find((n) => n.id === pending.fromNodeId);
      if (fromNode) {
        const fromX = fromNode.position.x + 296;
        const fromY = fromNode.position.y + 44;
        const cp = Math.max(Math.abs(toX - fromX) * 0.5, 40);
        this.pendingPath.set(
          `M ${fromX} ${fromY} C ${fromX + cp} ${fromY} ${toX - cp} ${toY} ${toX} ${toY}`,
        );
      }
    }
  }

  onCanvasMouseUp(event: MouseEvent) {
    if (this.isPanning()) {
      this.isPanning.set(false);
    }

    if (this.draggingNode()) {
      const node = this.draggingNode()!;
      // Mark position as unsaved
      this.unsavedPositions.set(node.id, node.position);
      this.hasUnsavedChanges.set(true);
      this.hasUnsavedChangesChange.emit(true);
      this.draggingNode.set(null);
      this.updateConnections();
    }

    // Cancel any pending port connection if released on empty canvas
    if (this.pendingConnection()) {
      this.pendingConnection.set(null);
      this.pendingPath.set(null);
    }

    if (this.paletteDragType()) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const x = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
      const y = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

      this.createNodeAtPosition(this.paletteDragType()!, { x, y });
      this.paletteDragType.set(null);
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
          this.nodesApi.upsertNode({
            ...node,
            x: position.x,
            y: position.y,
          }).then(() => {})
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
    this.pendingConnection.set({ fromNodeId: event.nodeId, cursorX: 0, cursorY: 0 });
  }

  /** Called when user releases on an input port on a node. */
  async onPortDrop(event: { nodeId: string; portType: 'input' | 'output' }) {
    const pending = this.pendingConnection();
    if (!pending || event.portType !== 'input') {
      this.pendingConnection.set(null);
      this.pendingPath.set(null);
      return;
    }

    const sourceId = pending.fromNodeId;
    const targetId = event.nodeId;

    if (sourceId === targetId) {
      this.pendingConnection.set(null);
      this.pendingPath.set(null);
      return;
    }

    // Check for duplicate edge
    const exists = this.edges().some(
      (e) => e.source_node === sourceId && e.target_node === targetId,
    );
    if (exists) {
      this.toast.danger('Connection already exists.');
      this.pendingConnection.set(null);
      this.pendingPath.set(null);
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
      this.pendingConnection.set(null);
      this.pendingPath.set(null);
    }
  }

  onCanvasWheel(event: WheelEvent) {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    this.zoom.update((z) => Math.max(0.1, Math.min(3, z * delta)));
  }

  onNodeMouseDown(event: MouseEvent, node: CanvasNode) {
    event.stopPropagation();
    this.draggingNode.set(node);
    this.dragOffset.set({ x: event.offsetX, y: event.offsetY });
  }

  onPluginDragStart(type: string, event: DragEvent) {
    this.paletteDragType.set(type);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'copy';
      event.dataTransfer.setData('text/plain', type);
    }
  }

  onPaletteDragStart(type: 'sensor' | 'fusion' | string, event: DragEvent) {
    this.onPluginDragStart(type, event);
  }

  onPaletteDragEnd() {
    this.paletteDragType.set(null);
  }

  onCanvasDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  }

  onCanvasDrop(event: DragEvent) {
    event.preventDefault();
    const type = this.paletteDragType();
    if (!type) return;

    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const x = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
    const y = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

    this.createNodeAtPosition(type, { x, y });
    this.paletteDragType.set(null);
  }

  private createNodeAtPosition(type: string, position: { x: number; y: number }) {
    const plugin = this.pluginRegistry.get(type);
    if (!plugin) {
      this.toast.danger(`Unknown node type: ${type}`);
      return;
    }

    const defaultData = plugin.createInstance();
    // Store position for new node
    this.nodeStore.set('selectedNode', { ...defaultData, x: position.x, y: position.y });
    this.dialogService.open(DynamicNodeEditorComponent, {
      label: `Add ${plugin.displayName}`,
    });
  }

  onEditNode(node: CanvasNode) {
    this.nodeStore.set('selectedNode', node.data);
    this.nodeStore.set('editMode', true);
    const plugin = this.pluginRegistry.get(node.data.type);
    const label = plugin?.displayName ?? node.data.name ?? node.data.type;
    this.dialogService.open(DynamicNodeEditorComponent, {
      label: `Edit ${label}`,
    });
  }

  async onDeleteNode(node: CanvasNode) {
    const name = node.data.name || node.id;
    if (!confirm(`Are you sure you want to delete ${name}?`)) return;

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
    if (!confirm('Are you sure you want to delete this connection?')) return;
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

  getNodeStatus(node: CanvasNode) {
    const status = this.nodesStatus();
    if (!status) return null;
    return status.nodes.find((n: any) => n.id === node.id) || null;
  }

  isNodeLoading(nodeId: string): boolean {
    return this.nodeLoadingStates()[nodeId] || false;
  }

  resetView() {
    this.panOffset.set({ x: 0, y: 0 });
    this.zoom.set(1);
  }
}
