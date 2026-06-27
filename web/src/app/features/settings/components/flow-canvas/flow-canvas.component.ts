import {
  Component,
  computed,
  effect,
  HostListener,
  inject,
  input,
  OnDestroy,
  OnInit,
  signal,
  untracked,
  ChangeDetectionStrategy
} from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

import { NodePlugin } from '@core/models';
import { Edge } from '@core/models/node.model';
import { NodeStoreService } from '@core/services/stores';
import { NodesApiService } from '@core/services/api';
import { DialogService, ToastService } from '@core/services';
import { NodePluginRegistry } from '@core/services/node-plugin-registry.service';
import { NodeStatusService } from '@core/services/node-status.service';
import { SystemStatusService } from '@core/services/system-status.service';
import { CanvasEditStoreService } from '@features/settings/services/canvas-edit-store.service';
import { ThemeService } from '@core/services/theme.service';

import { CanvasNode, FlowCanvasNodeComponent } from './node/flow-canvas-node.component';
import { FlowCanvasPaletteComponent } from './palette/flow-canvas-palette.component';
import { FlowCanvasControlsComponent } from './controls/flow-canvas-controls.component';
import { FlowCanvasConnectionsComponent } from './connections/flow-canvas-connections.component';
import { FlowCanvasEmptyStateComponent } from './empty-state/flow-canvas-empty-state.component';
import { DynamicNodeEditorComponent } from '../dynamic-node-editor/dynamic-node-editor.component';
import { OutputViewerComponent } from '@features/settings/components/flow-canvas/output-viewer/output-viewer.component';
import { AuthService } from '@app/core/services/auth.service';

@Component({
  selector: 'app-flow-canvas',
  imports: [
    SynergyComponentsModule,
    FlowCanvasNodeComponent,
    FlowCanvasPaletteComponent,
    FlowCanvasControlsComponent,
    FlowCanvasConnectionsComponent,
    FlowCanvasEmptyStateComponent,
    DynamicNodeEditorComponent,
    OutputViewerComponent,
  ],
  templateUrl: './flow-canvas.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './flow-canvas.component.css',
})
export class FlowCanvasComponent implements OnInit, OnDestroy {
  // ------ Inputs ------
  readonly readOnly = input(false);
  readonly auth = inject(AuthService);
  // ------ Store ------
  private nodeStore = inject(NodeStoreService);
  protected canvasEditStore = inject(CanvasEditStoreService);
  private readonly themeService = inject(ThemeService);

  // ------ Theme-reactive canvas colors ------
  /** Grid dot color — reads Synergy token at runtime so it adapts in dark mode. */
  protected readonly gridDotColor = computed(() => {
    // Depend on theme signal so computed re-runs on theme change
    const _theme = this.themeService.theme();
    return (
      getComputedStyle(document.documentElement)
        .getPropertyValue('--syn-color-neutral-300')
        .trim() || '#d1d5db'
    );
  });
  protected canEdit = this.auth.canEdit;
  /** Active grid dot color (snap enabled) — slightly more visible */
  protected readonly gridDotColorActive = computed(() => {
    const _theme = this.themeService.theme();
    return (
      getComputedStyle(document.documentElement)
        .getPropertyValue('--syn-color-neutral-400')
        .trim() || '#9ca3af'
    );
  });

  /** Primary edge color for connections — Synergy primary-600 */
  protected readonly edgeColor = computed(() => {
    const _theme = this.themeService.theme();
    return (
      getComputedStyle(document.documentElement)
        .getPropertyValue('--syn-color-primary-600')
        .trim() || '#005aff'
    );
  });

  /** Faded overlay color for animated flow dash */
  protected readonly edgeFlowColor = computed(() => {
    const _theme = this.themeService.theme();
    return (
      getComputedStyle(document.documentElement)
        .getPropertyValue('--syn-color-primary-300')
        .trim() || '#80adff'
    );
  });

  // ------ View state owned by the component ------
  protected drawerOpen = signal(false);
  protected availablePlugins = signal<NodePlugin[]>([]);
  protected panOffset = signal({ x: 0, y: 0 });
  protected zoom = signal(1);
  /** Raw (unsnapped) drag accumulator — tracks continuous mouse movement so the
   *  node follows the cursor smoothly; snapping is applied only on drop. */
  private rawDragPos = signal<{ x: number; y: number } | null>(null);
  protected isTogglingVisibility = signal<string | null>(null);
  protected snapToGrid = signal(true);
  readonly gridSize = 20; // px — must match the SVG grid pattern size
  protected isPaletteLoading = signal(true);
  protected isCanvasLoading = signal(true);
  protected nodeLoadingStates = signal<Record<string, boolean>>({});

  // ------ Multi-selection state ------
  protected selectedNodeIds = signal<Set<string>>(new Set());
  private marqueeStart = signal<{ x: number; y: number } | null>(null);
  protected marqueeRect = signal<{ x: number; y: number; w: number; h: number } | null>(null);
  private clipboard = signal<{ nodes: CanvasNode[]; edges: Edge[] } | null>(null);

  // ------ Inline drag state (replaces FlowCanvasDragService) ------
  protected draggingNode = signal<CanvasNode | null>(null);
  private dragOffset = signal<{ x: number; y: number }>({ x: 0, y: 0 });
  protected paletteDragType = signal<string | null>(null);
  protected pendingConnection = signal<{
    fromNodeId: string;
    fromPortId: string;
    fromPortIndex: number;
  } | null>(null);
  protected pendingPath = signal<string | null>(null);
  protected isPanning = signal(false);

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
  private statusWs = inject(NodeStatusService);
  private systemStatus = inject(SystemStatusService);
  protected nodesStatus = this.statusWs.status;
  /** Set of node IDs currently undergoing a selective reload — used to show per-node spinner. */
  protected reloadingNodeIds = this.systemStatus.reloadingNodeIds;

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
    if (event.button === 1 || (event.button === 0 && event.shiftKey)) {
      this.isPanning.set(true);
      event.preventDefault();
      return;
    }

    if (event.button === 0) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      this.marqueeStart.set({
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
    }
  }

  onCanvasMouseMove(event: MouseEvent) {
    if (this.isPanning()) {
      this.panOffset.update((offset) => ({
        x: offset.x + event.movementX,
        y: offset.y + event.movementY,
      }));
    } else if (this.draggingNode()) {
      const deltaX = event.movementX / this.zoom();
      const deltaY = event.movementY / this.zoom();

      const node = this.draggingNode()!;
      const prev = this.rawDragPos() ?? node.position;
      const raw = { x: prev.x + deltaX, y: prev.y + deltaY };
      this.rawDragPos.set(raw);

      const selected = this.selectedNodeIds();
      if (selected.size > 1) {
        const updates = new Map<string, { x: number; y: number }>();
        for (const cn of this.canvasNodes()) {
          if (selected.has(cn.id)) {
            updates.set(cn.id, { x: cn.position.x + deltaX, y: cn.position.y + deltaY });
          }
        }
        this.canvasEditStore.updateCanvasNodesPositions(updates);
      } else {
        this.canvasEditStore.updateCanvasNodePosition(node.id, raw);
      }

      this.draggingNode.set({ ...node, position: raw });
    } else if (this.marqueeStart() && !this.pendingConnection()) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const current = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      const start = this.marqueeStart()!;
      this.marqueeRect.set({
        x: Math.min(start.x, current.x),
        y: Math.min(start.y, current.y),
        w: Math.abs(current.x - start.x),
        h: Math.abs(current.y - start.y),
      });
    } else if (this.pendingConnection()) {
      const pending = this.pendingConnection()!;
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

    const node = this.draggingNode();
    if (node) {
      const selected = this.selectedNodeIds();
      if (selected.size > 1) {
        const updates = new Map<string, { x: number; y: number }>();
        for (const cn of this.canvasNodes()) {
          if (selected.has(cn.id)) {
            updates.set(cn.id, this._snapPos(cn.position));
          }
        }
        this.canvasEditStore.moveNodes(updates);
      } else {
        const snapped = this._snapPos(node.position);
        this.canvasEditStore.moveNode(node.id, snapped.x, snapped.y);
      }
      this.draggingNode.set(null);
      this.rawDragPos.set(null);
    }

    const marquee = this.marqueeRect();
    const wasMarquee = marquee && (marquee.w > 5 || marquee.h > 5);
    if (wasMarquee) {
      this._applyMarqueeSelection(marquee!, event.ctrlKey || event.metaKey);
    } else if (this.marqueeStart() && !node) {
      if (!event.ctrlKey && !event.metaKey) {
        this.selectedNodeIds.set(new Set());
      }
    }
    this.marqueeStart.set(null);
    this.marqueeRect.set(null);

    if (this.pendingConnection()) {
      this.pendingConnection.set(null);
      this.pendingPath.set(null);
    }

    if (this.paletteDragType()) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const rawX = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
      const rawY = (event.clientY - rect.top - this.panOffset().y) / this.zoom();
      this.createNodeAtPosition(this.paletteDragType()!, this._snapPos({ x: rawX, y: rawY }));
      this.paletteDragType.set(null);
    }
  }

  onPortDragStart(event: {
    nodeId: string;
    portType: 'input' | 'output';
    portId: string;
    portIndex: number;
    event: MouseEvent;
  }) {
    if (event.portType !== 'output') return;
    event.event.preventDefault();
    this.pendingConnection.set({
      fromNodeId: event.nodeId,
      fromPortId: event.portId,
      fromPortIndex: event.portIndex,
    });
  }

  onPortDrop(event: { nodeId: string; portType: 'input' | 'output' }) {
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

    const exists = this.canvasEditStore
      .localEdges()
      .some(
        (e) =>
          e.source_node === sourceId &&
          e.target_node === targetId &&
          e.source_port === pending.fromPortId,
      );
    if (exists) {
      this.toast.danger('Connection already exists.');
      this.pendingConnection.set(null);
      this.pendingPath.set(null);
      return;
    }

    // Validate allowed_source_categories on the target node's input ports
    const targetNode = this.canvasEditStore.localNodes().find((n) => n.id === targetId);
    const targetDef = targetNode
      ? this.nodeStore.nodeDefinitions().find((d) => d.type === targetNode.type)
      : null;
    if (targetDef) {
      const restrictedInputs = targetDef.inputs.filter(
        (p) => p.allowed_source_categories && p.allowed_source_categories.length > 0,
      );
      if (restrictedInputs.length > 0) {
        const sourceNode = this.canvasEditStore.localNodes().find((n) => n.id === sourceId);
        const sourceCategory = sourceNode?.category?.toLowerCase() ?? '';
        const allowed = restrictedInputs.some((p) =>
          p.allowed_source_categories!.map((c) => c.toLowerCase()).includes(sourceCategory),
        );
        if (!allowed) {
          const categories = restrictedInputs
            .flatMap((p) => p.allowed_source_categories ?? [])
            .join(', ');
          this.toast.danger(`This node only accepts connections from ${categories} nodes.`);
          this.pendingConnection.set(null);
          this.pendingPath.set(null);
          return;
        }
      }
    }

    this.canvasEditStore.addEdge({
      source_node: sourceId,
      source_port: pending.fromPortId,
      target_node: targetId,
      target_port: 'in',
    });
    this.pendingConnection.set(null);
    this.pendingPath.set(null);
  }

  onCanvasWheel(event: WheelEvent) {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    this.zoom.update((z) => Math.max(0.1, Math.min(3, z * delta)));
  }

  onNodeMouseDown(event: MouseEvent, node: CanvasNode) {
    event.stopPropagation();
    this.marqueeStart.set(null);

    if (event.ctrlKey || event.metaKey) {
      this.selectedNodeIds.update((ids) => {
        const next = new Set(ids);
        if (next.has(node.id)) {
          next.delete(node.id);
        } else {
          next.add(node.id);
        }
        return next;
      });
      return;
    }

    if (!this.selectedNodeIds().has(node.id)) {
      this.selectedNodeIds.set(new Set([node.id]));
    }

    this.rawDragPos.set({ x: node.position.x, y: node.position.y });
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

  onPaletteDragEnd() {
    this.selectedNodeIds.set(new Set());
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
    const rawX = (event.clientX - rect.left - this.panOffset().x) / this.zoom();
    const rawY = (event.clientY - rect.top - this.panOffset().y) / this.zoom();

    this.createNodeAtPosition(type, this._snapPos({ x: rawX, y: rawY }));
    this.paletteDragType.set(null);
  }

  onEditNode(node: CanvasNode) {
    this.nodeStore.set('selectedNode', node.data);
    this.nodeStore.set('editMode', true);
    this.drawerOpen.set(true);
  }

  async onDeleteNode(node: CanvasNode) {
    const name = node.data.name || node.id;
    const confirmed = await this.dialog.confirm({
      title: 'Delete Node',
      message: `Are you sure you want to delete ${name}?`,
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;
    this.canvasEditStore.deleteNode(node.id);
    this.toast.success(`${name} deleted.`);
  }

  async onDeleteEdge(edgeId: string) {
    const confirmed = await this.dialog.confirm({
      title: 'Delete Connection',
      message: 'Are you sure you want to delete this connection?',
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;
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
    if (this.drawerOpen()) return;
    const tag = (event.target as HTMLElement)?.tagName?.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

    const ctrl = event.ctrlKey || event.metaKey;
    if (this.canEdit()) {
      if (ctrl && event.key === 'a') {
        event.preventDefault();
        this.selectedNodeIds.set(new Set(this.canvasNodes().map((n) => n.id)));
        return;
      }

      if (ctrl && event.key === 'c') {
        event.preventDefault();
        this._copySelectedNodes();
        return;
      }

      if (ctrl && event.key === 'v') {
        event.preventDefault();
        this._pasteNodes();
        return;
      }
    }

    if (event.key === 'Delete' || event.key === 'Backspace') {
      const selected = this.selectedNodeIds();
      if (selected.size === 0) return;
      event.preventDefault();
      this._deleteSelectedNodes();
    }
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

  onEditorSave() {
    // Just close drawer — local edits already in _localNodes/_localEdges
    // User must hit Apply button in settings panel to sync with backend
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

  // ------ Multi-selection helpers ------

  private _applyMarqueeSelection(
    marquee: { x: number; y: number; w: number; h: number },
    additive: boolean,
  ): void {
    const panX = this.panOffset().x;
    const panY = this.panOffset().y;
    const z = this.zoom();
    const canvasLeft = (marquee.x - panX) / z;
    const canvasTop = (marquee.y - panY) / z;
    const canvasRight = (marquee.x + marquee.w - panX) / z;
    const canvasBottom = (marquee.y + marquee.h - panY) / z;

    const nodeWidth = 192;
    const nodeHeight = 80;
    const hit = new Set<string>();
    for (const node of this.canvasNodes()) {
      if (
        node.position.x < canvasRight &&
        node.position.x + nodeWidth > canvasLeft &&
        node.position.y < canvasBottom &&
        node.position.y + nodeHeight > canvasTop
      ) {
        hit.add(node.id);
      }
    }

    if (additive) {
      this.selectedNodeIds.update((ids) => {
        const next = new Set(ids);
        for (const id of hit) next.add(id);
        return next;
      });
    } else {
      this.selectedNodeIds.set(hit);
    }
  }

  private _copySelectedNodes(): void {
    const selected = this.selectedNodeIds();
    if (selected.size === 0) return;
    const nodes = this.canvasNodes().filter((n) => selected.has(n.id));
    const edges = this.canvasEditStore
      .localEdges()
      .filter((e) => selected.has(e.source_node) && selected.has(e.target_node));
    this.clipboard.set({ nodes: structuredClone(nodes), edges: structuredClone(edges) });
    this.toast.success(`Copied ${nodes.length} node(s).`);
  }

  private _pasteNodes(): void {
    const clip = this.clipboard();
    if (!clip || clip.nodes.length === 0) return;

    const offset = 40;
    const idMap = new Map<string, string>();

    for (const node of clip.nodes) {
      const newId = `__new__${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      idMap.set(node.id, newId);
      this.canvasEditStore.addNode({
        id: newId,
        name: `${node.data.name} (copy)`,
        type: node.data.type,
        category: node.data.category,
        enabled: node.data.enabled,
        visible: node.data.visible,
        config: structuredClone(node.data.config),
        pose: node.data.pose ? structuredClone(node.data.pose) : undefined,
        x: node.position.x + offset,
        y: node.position.y + offset,
      });
    }

    for (const edge of clip.edges) {
      const src = idMap.get(edge.source_node);
      const tgt = idMap.get(edge.target_node);
      if (src && tgt) {
        this.canvasEditStore.addEdge({
          source_node: src,
          source_port: edge.source_port,
          target_node: tgt,
          target_port: edge.target_port,
        });
      }
    }

    this.selectedNodeIds.set(new Set(idMap.values()));

    this.clipboard.update((c) => {
      if (!c) return c;
      return {
        ...c,
        nodes: c.nodes.map((n) => ({
          ...n,
          position: { x: n.position.x + offset, y: n.position.y + offset },
        })),
      };
    });

    this.toast.success(`Pasted ${clip.nodes.length} node(s).`);
  }

  private async _deleteSelectedNodes(): Promise<void> {
    const selected = this.selectedNodeIds();
    if (selected.size === 0) return;
    const count = selected.size;
    const msg =
      count === 1
        ? 'Are you sure you want to delete this node?'
        : `Are you sure you want to delete ${count} nodes?`;
    const confirmed = await this.dialog.confirm({
      title: 'Delete Selected Nodes',
      message: msg,
      confirmLabel: count === 1 ? 'Delete Node' : `Delete ${count} Nodes`,
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;
    this.canvasEditStore.deleteNodes(selected);
    this.selectedNodeIds.set(new Set());
    this.toast.success(`${count} node(s) deleted.`);
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
