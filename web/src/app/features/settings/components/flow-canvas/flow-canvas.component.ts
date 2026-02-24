import { Component, inject, signal, computed, effect, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarStoreService } from '../../../../core/services/stores/lidar-store.service';
import { FusionStoreService } from '../../../../core/services/stores/fusion-store.service';
import { LidarConfig } from '../../../../core/models/lidar.model';
import { FusionConfig } from '../../../../core/models/fusion.model';
import {
  NodesApiService,
  NodesStatusResponse,
} from '../../../../core/services/api/nodes-api.service';
import { LidarApiService } from '../../../../core/services/api/lidar-api.service';
import { FusionApiService } from '../../../../core/services/api/fusion-api.service';
import { ToastService } from '../../../../core/services/toast.service';
import { DialogService } from '../../../../core/services';
import { LidarEditorComponent } from '../lidar-editor/lidar-editor';
import { FusionEditorComponent } from '../fusion-editor/fusion-editor';
import { NodePluginRegistry } from '../../../../core/services/node-plugin-registry.service';
import { NodePlugin } from '../../../../core/models/node-plugin.model';
import { FlowCanvasNodeComponent, CanvasNode } from './node/flow-canvas-node.component';
import { FlowCanvasPaletteComponent } from './palette/flow-canvas-palette.component';
import {
  FlowCanvasConnectionsComponent,
  Connection,
} from './connections/flow-canvas-connections.component';
import { FlowCanvasEmptyStateComponent } from './empty-state/flow-canvas-empty-state.component';

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
  private lidarStore = inject(LidarStoreService);
  private fusionStore = inject(FusionStoreService);
  private nodesApi = inject(NodesApiService);
  private lidarApi = inject(LidarApiService);
  private fusionApi = inject(FusionApiService);
  private toast = inject(ToastService);
  private dialogService = inject(DialogService);
  private pluginRegistry = inject(NodePluginRegistry);

  protected lidars = this.lidarStore.lidars;
  protected fusions = this.fusionStore.fusions;
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

  // Palette drag state (dragging from sidebar)
  protected paletteDragType = signal<string | null>(null);

  // Node status
  protected nodesStatus = signal<NodesStatusResponse | null>(null);
  private statusPollInterval: any = null;

  // Loading states
  protected nodeLoadingStates = signal<Record<string, boolean>>({});

  constructor() {
    // Watch for changes in lidar and fusion stores
    effect(() => {
      // Trigger on any change to lidars or fusions
      const lidars = this.lidars();
      const fusions = this.fusions();

      // Re-initialize canvas nodes when data changes
      // Use setTimeout to avoid signal update during effect
      setTimeout(() => {
        this.initializeCanvasNodes();
        this.updateConnections();
      }, 0);
    });
  }
  ngOnInit(): void {
    this.loadAvailablePlugins();

    // Initialize after data is loaded
    setTimeout(() => {
      this.initializeCanvasNodes();
      this.updateConnections();
    }, 100);

    this.startStatusPolling();
  }

  ngOnDestroy(): void {
    this.stopStatusPolling();
  }

  private loadAvailablePlugins() {
    this.availablePlugins.set(this.pluginRegistry.getAll());
  }

  private initializeCanvasNodes() {
    const nodes: CanvasNode[] = [];

    // Add lidars
    this.lidars().forEach((lidar, index) => {
      nodes.push({
        id: lidar.id || `lidar-${index}`,
        type: 'sensor',
        data: lidar,
        position: this.loadNodePosition(lidar.id || `lidar-${index}`) || {
          x: 100 + (index % 3) * 300,
          y: 100 + Math.floor(index / 3) * 200,
        },
      });
    });

    // Add fusions
    this.fusions().forEach((fusion, index) => {
      nodes.push({
        id: fusion.id || `fusion-${index}`,
        type: 'fusion',
        data: fusion,
        position: this.loadNodePosition(fusion.id || `fusion-${index}`) || {
          x: 100 + (index % 3) * 300,
          y: 400 + Math.floor(index / 3) * 200,
        },
      });
    });

    this.canvasNodes.set(nodes);
  }

  private loadNodePosition(nodeId: string): { x: number; y: number } | null {
    const stored = localStorage.getItem(`node-position-${nodeId}`);
    return stored ? JSON.parse(stored) : null;
  }

  private saveNodePosition(nodeId: string, position: { x: number; y: number }) {
    localStorage.setItem(`node-position-${nodeId}`, JSON.stringify(position));
  }

  private updateConnections(): void {
    const connections: Connection[] = [];
    const nodes = this.canvasNodes();

    // Create a map for fast lookups
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    // Find all fusion nodes and their sensor connections
    nodes.forEach((node) => {
      if (node.type === 'fusion') {
        const fusion = node.data as FusionConfig;
        const sensorIds = fusion.sensor_ids || [];

        // Create connections from each sensor to this fusion
        sensorIds.forEach((sensorId) => {
          const sensorNode = nodeMap.get(sensorId);
          if (sensorNode && sensorNode.type === 'sensor') {
            const path = this.calculatePath(sensorNode, node);
            connections.push({
              from: sensorId,
              to: node.id,
              path,
            });
          }
        });
      }
    });

    this.connections.set(connections);
  }

  // Calculate connection path (cached in connection object)
  private calculatePath(fromNode: CanvasNode, toNode: CanvasNode): string {
    // Node card dimensions
    const nodeWidth = 256; // w-64 = 16rem = 256px
    const nodeHeight = 200; // approximate height

    // Calculate port positions (right side of sensor, left side of fusion)
    const fromX = fromNode.position.x + nodeWidth;
    const fromY = fromNode.position.y + nodeHeight / 2;
    const toX = toNode.position.x;
    const toY = toNode.position.y + nodeHeight / 2;

    // Create smooth cubic bezier curve
    const controlPointOffset = Math.abs(toX - fromX) * 0.5;
    const cp1x = fromX + controlPointOffset;
    const cp1y = fromY;
    const cp2x = toX - controlPointOffset;
    const cp2y = toY;

    return `M ${fromX} ${fromY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${toX} ${toY}`;
  }

  private startStatusPolling() {
    this.statusPollInterval = setInterval(async () => {
      try {
        const status = await this.nodesApi.getNodesStatus();
        this.nodesStatus.set(status);
      } catch (error) {
        console.error('Failed to fetch node status', error);
      }
    }, 2000);

    this.nodesApi
      .getNodesStatus()
      .then((status) => this.nodesStatus.set(status))
      .catch(console.error);
  }

  private stopStatusPolling() {
    if (this.statusPollInterval) {
      clearInterval(this.statusPollInterval);
      this.statusPollInterval = null;
    }
  }

  // Canvas interaction handlers
  onCanvasMouseDown(event: MouseEvent) {
    if (event.button === 1 || (event.button === 0 && event.shiftKey)) {
      // Middle mouse or Shift+Left mouse for panning
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
      // Update dragging node position
      const node = this.draggingNode()!;
      const newPosition = {
        x: node.position.x + event.movementX / this.zoom(),
        y: node.position.y + event.movementY / this.zoom(),
      };

      this.canvasNodes.update((nodes) =>
        nodes.map((n) => (n.id === node.id ? { ...n, position: newPosition } : n)),
      );

      this.draggingNode.set({ ...node, position: newPosition });

      // Update connections while dragging (throttled)
      this.updateConnections();
    }
  }

  onCanvasMouseUp(event: MouseEvent) {
    if (this.isPanning()) {
      this.isPanning.set(false);
    }

    if (this.draggingNode()) {
      const node = this.draggingNode()!;
      this.saveNodePosition(node.id, node.position);
      this.draggingNode.set(null);
      // Final connection update after drag ends
      this.updateConnections();
    }

    // Handle palette drop
    if (this.paletteDragType()) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const x = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
      const y = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

      const type = this.paletteDragType()!;
      this.createNodeAtPosition(type, { x, y });

      this.paletteDragType.set(null);
    }
  }

  onCanvasWheel(event: WheelEvent) {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    this.zoom.update((z) => Math.max(0.1, Math.min(3, z * delta)));
  }

  // Node interaction handlers
  onNodeMouseDown(event: MouseEvent, node: CanvasNode) {
    event.stopPropagation();
    this.draggingNode.set(node);
    this.dragOffset.set({
      x: event.offsetX,
      y: event.offsetY,
    });
  }

  // Palette drag handlers
  onPluginDragStart(type: string, event: DragEvent) {
    this.paletteDragType.set(type);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'copy';
      event.dataTransfer.setData('text/plain', type);
    }
  }

  onPaletteDragStart(type: 'sensor' | 'fusion', event: DragEvent) {
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

  // Create new nodes
  private createNodeAtPosition(type: string, position: { x: number; y: number }) {
    if (type === 'sensor') {
      this.createSensorAtPosition(position);
    } else if (type === 'fusion') {
      this.createFusionAtPosition(position);
    } else {
      // Handle custom plugin types
      this.toast.warning(`Custom node type "${type}" not yet implemented in backend.`);
    }
  }

  private createSensorAtPosition(position: { x: number; y: number }) {
    this.lidarStore.set('selectedLidar', {});
    this.lidarStore.set('editMode', false);
    this.dialogService.open(LidarEditorComponent, {
      label: 'Add Sensor',
    });
  }

  private createFusionAtPosition(position: { x: number; y: number }) {
    this.fusionStore.set('selectedFusion', {});
    this.fusionStore.set('editMode', false);
    this.dialogService.open(FusionEditorComponent, {
      label: 'Add Fusion',
    });
  }

  // Node actions
  onEditNode(node: CanvasNode) {
    if (node.type === 'sensor') {
      this.lidarStore.set('selectedLidar', node.data as LidarConfig);
      this.lidarStore.set('editMode', true);
      this.dialogService.open(LidarEditorComponent, {
        label: 'Edit Sensor',
      });
    } else {
      this.fusionStore.set('selectedFusion', node.data as FusionConfig);
      this.fusionStore.set('editMode', true);
      this.dialogService.open(FusionEditorComponent, {
        label: 'Edit Fusion',
      });
    }
  }

  async onDeleteNode(node: CanvasNode) {
    const name = (node.data as any).name || node.id;
    if (!confirm(`Are you sure you want to delete ${name}?`)) return;

    try {
      if (node.type === 'sensor') {
        await this.lidarApi.deleteLidar(node.id);
      } else {
        await this.fusionApi.deleteFusion(node.id);
      }

      this.canvasNodes.update((nodes) => nodes.filter((n) => n.id !== node.id));
      localStorage.removeItem(`node-position-${node.id}`);
      this.toast.success(`${name} deleted.`);
    } catch (error) {
      console.error('Failed to delete node', error);
      this.toast.danger(`Failed to delete ${name}.`);
    }
  }

  async onToggleNodeEnabled(node: CanvasNode, enabled: boolean) {
    this.nodeLoadingStates.update((states) => ({ ...states, [node.id]: true }));

    try {
      if (node.type === 'sensor') {
        await this.lidarApi.setEnabled(node.id, enabled);
      } else {
        await this.fusionApi.setEnabled(node.id, enabled);
      }

      const name = (node.data as any).name || node.id;
      this.toast.success(`${name} ${enabled ? 'enabled' : 'disabled'}.`);

      // Refresh data
      await Promise.all([this.lidarApi.getLidars(), this.fusionApi.getFusions()]);
      this.initializeCanvasNodes();
      this.updateConnections();
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

    if (node.type === 'sensor') {
      return status.lidars.find((l) => l.id === node.id) || null;
    } else {
      return status.fusions.find((f) => f.id === node.id) || null;
    }
  }

  isNodeLoading(nodeId: string): boolean {
    return this.nodeLoadingStates()[nodeId] || false;
  }

  // Reset view
  resetView() {
    this.panOffset.set({ x: 0, y: 0 });
    this.zoom.set(1);
  }

  // Auto layout nodes
  autoLayoutNodes() {
    const nodes = this.canvasNodes();
    const sensorNodes = nodes.filter((n) => n.type === 'sensor');
    const fusionNodes = nodes.filter((n) => n.type === 'fusion');

    // Layout sensors in a grid at the top
    const sensorColumns = 3;
    sensorNodes.forEach((node, index) => {
      const col = index % sensorColumns;
      const row = Math.floor(index / sensorColumns);
      const newPosition = {
        x: 100 + col * 300,
        y: 100 + row * 220,
      };

      this.canvasNodes.update((nodes) =>
        nodes.map((n) => (n.id === node.id ? { ...n, position: newPosition } : n)),
      );
      this.saveNodePosition(node.id, newPosition);
    });

    // Layout fusions below sensors
    const fusionColumns = 3;
    fusionNodes.forEach((node, index) => {
      const col = index % fusionColumns;
      const row = Math.floor(index / fusionColumns);
      const newPosition = {
        x: 100 + col * 300,
        y: 400 + row * 220,
      };

      this.canvasNodes.update((nodes) =>
        nodes.map((n) => (n.id === node.id ? { ...n, position: newPosition } : n)),
      );
      this.saveNodePosition(node.id, newPosition);
    });

    this.updateConnections();
    this.toast.success('Nodes arranged automatically');
  }

  // Clear all saved positions and re-initialize
  clearAllPositions() {
    if (!confirm('Reset all node positions? This will clear your custom layout.')) return;

    const nodes = this.canvasNodes();
    nodes.forEach((node) => {
      localStorage.removeItem(`node-position-${node.id}`);
    });

    this.initializeCanvasNodes();
    this.updateConnections();
    this.resetView();
    this.toast.success('Layout reset to default');
  }
}
