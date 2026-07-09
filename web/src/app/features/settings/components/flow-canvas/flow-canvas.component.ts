import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  HostListener,
  inject,
  input,
  OnDestroy,
  OnInit,
  output,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import {
  FCanvasComponent,
  FCreateConnectionEvent,
  FCreateNodeEvent,
  F_DRAG_SELECT_CONTROL_SCHEME,
  FFlowComponent,
  FFlowModule,
  FMoveNodesEvent,
  FZoomDirective,
  provideFFlow,
  withControlScheme,
  withConnectionFlow,
  F_SCROLL_PAN_CONTROL_SCHEME,
} from '@foblex/flow';

import { NodePlugin } from '@core/models';
import { Edge } from '@core/models/node.model';
import { NodeStoreService } from '@core/services/stores';
import { NodesApiService } from '@core/services/api';
import { DialogService, ToastService } from '@core/services';
import { NodePluginRegistry } from '@core/services/node-plugin-registry.service';
import { NodeStatusService } from '@core/services/node-status.service';
import { SystemStatusService } from '@core/services/system-status.service';
import { CanvasEditStoreService } from '@features/settings/services/canvas-edit-store.service';

import { CanvasNode, FlowCanvasNodeComponent } from './node/flow-canvas-node.component';
import { FlowCanvasPaletteComponent } from './palette/flow-canvas-palette.component';
import { FlowCanvasControlsComponent } from './controls/flow-canvas-controls.component';
import { FlowCanvasEmptyStateComponent } from './empty-state/flow-canvas-empty-state.component';
import { DynamicNodeEditorComponent } from '../dynamic-node-editor/dynamic-node-editor.component';
import { OutputViewerComponent } from '@features/settings/components/flow-canvas/output-viewer/output-viewer.component';
import { AuthService } from '@app/core/services/auth.service';

@Component({
  selector: 'app-flow-canvas',
  imports: [
    SynergyComponentsModule,
    FFlowModule,
    FlowCanvasNodeComponent,
    FlowCanvasPaletteComponent,
    FlowCanvasControlsComponent,
    FlowCanvasEmptyStateComponent,
    DynamicNodeEditorComponent,
    OutputViewerComponent,
  ],
  templateUrl: './flow-canvas.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [provideFFlow(withConnectionFlow('click'))],
  styleUrls: ['./flow-canvas.component.scss'],
})
export class FlowCanvasComponent {
  // ------ Inputs ------
  readonly readOnly = input(false);
  readonly previewedNodeIds = input<Set<string>>(new Set());

  // ------ Outputs ------
  onTogglePreview = output<CanvasNode>();

  // ------ Foblex view references ------
  private readonly _flow = viewChild.required(FFlowComponent);
  private readonly _canvas = viewChild(FCanvasComponent);
  private readonly _zoom = viewChild(FZoomDirective);

  // ------ Auth ------
  readonly auth = inject(AuthService);
  protected canEdit = this.auth.canEdit;

  // ------ Store ------
  private nodeStore = inject(NodeStoreService);
  protected canvasEditStore = inject(CanvasEditStoreService);

  // ------ View state ------
  protected drawerOpen = signal(false);
  protected availablePlugins = signal<NodePlugin[]>([]);
  protected snapToGrid = signal(true);
  protected minimapVisible = signal(
    localStorage.getItem('flow-canvas.minimapVisible') !== 'false'
  );
  readonly gridSize = 30;
  protected isPaletteLoading = signal(true);
  protected isCanvasLoading = signal(true);
  protected nodeLoadingStates = signal<Record<string, boolean>>({});
  protected isTogglingVisibility = signal<string | null>(null);

  // ------ Clipboard for copy/paste ------
  private clipboard = signal<{ nodes: CanvasNode[]; edges: Edge[] } | null>(null);

  // ------ Store-sourced signals ------
  protected canvasNodes = this.canvasEditStore.canvasNodes;
  protected connections = this.canvasEditStore.connections;

  // ------ API / service deps ------
  private nodesApi = inject(NodesApiService);
  private toast = inject(ToastService);
  private dialog = inject(DialogService);
  private pluginRegistry = inject(NodePluginRegistry);
  private statusWs = inject(NodeStatusService);
  private systemStatus = inject(SystemStatusService);
  protected nodesStatus = this.statusWs.status;
  protected reloadingNodeIds = this.systemStatus.reloadingNodeIds;

  constructor() {
    effect(() => {
      if (this.canvasEditStore.isInitialized()) {
        untracked(() => this.isCanvasLoading.set(false));
      }
    });

    effect(() => {
      const definitions = this.nodeStore.nodeDefinitions();
      untracked(() => {
        this.availablePlugins.set(this.pluginRegistry.getAll());
        this.isPaletteLoading.set(false);
      });
    });

    effect(() => {
      const visible = this.minimapVisible();
      localStorage.setItem('flow-canvas.minimapVisible', String(visible));
    });
  }
  // ------ Foblex lifecycle events ------

  onFlowLoaded(): void {
    this._zoom()?.reset();
  }

  /** Returns the current zoom level from FZoomDirective for the controls display. */
  protected get zoomValue(): number {
    return this._zoom()?.getZoomValue() ?? 1;
  }

  // ------ Node drag/move — Foblex grid snap handles position snapping via [vCellSize]/[hCellSize] ------

  onMoveNodes(event: FMoveNodesEvent): void {
    this.canvasEditStore.pushUndoState();
    const updates = new Map<string, { x: number; y: number }>();
    for (const node of event.nodes) {
      updates.set(node.id, { x: node.position.x, y: node.position.y });
    }
    this.canvasEditStore.moveNodes(updates);
  }

  // ------ Palette drag-to-canvas (fExternalItem → fCreateNode) ------

  onCreateNode(event: FCreateNodeEvent): void {
    if (this.readOnly()) return;
    this.canvasEditStore.pushUndoState();
    const type = event.data as string;
    // Snap drop position to grid when snap is on
    const raw = { x: event.externalItemRect.x, y: event.externalItemRect.y };
    const position = this.snapToGrid()
      ? {
          x: Math.round(raw.x / this.gridSize) * this.gridSize,
          y: Math.round(raw.y / this.gridSize) * this.gridSize,
        }
      : raw;
    this._createNodeAtPosition(type, position);
  }

  // ------ Connection creation (fDraggable port drag) ------

  onCreateConnection(event: FCreateConnectionEvent): void {
    if (this.readOnly()) return;
    this.canvasEditStore.pushUndoState();

    const sourceConnectorId = event.sourceId;
    const targetConnectorId = event.targetId;
    if (!sourceConnectorId || !targetConnectorId) return;

    // Connector IDs are encoded as "<nodeId>__out__<portId>" and "<nodeId>__in"
    const sourceNodeId = this._nodeIdFromConnector(sourceConnectorId);
    const targetNodeId = this._nodeIdFromConnector(targetConnectorId);
    const sourcePortId = this._portIdFromConnector(sourceConnectorId);

    if (!sourceNodeId || !targetNodeId || sourceNodeId === targetNodeId) return;

    this.canvasEditStore.addEdge({
      source_node: sourceNodeId,
      source_port: sourcePortId,
      target_node: targetNodeId,
      target_port: 'in',
    });
  }

  // ------ Node actions ------

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
    this.canvasEditStore.pushUndoState();
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
    this.canvasEditStore.pushUndoState();
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

  // ------ Drawer ------

  onDrawerClose() {
    this.drawerOpen.set(false);
  }

  onEditorSave() {
    this.drawerOpen.set(false);
  }

  onDrawerRequestClose(event: Event) {
    if ((event as CustomEvent).detail?.source === 'overlay') {
      event.preventDefault();
    }
  }

  // ------ Controls ------

  fitToScreen() {
    this._canvas()?.fitToScreen();
  }

  resetScaleAndCenter() {
    this._canvas()?.resetScaleAndCenter();
  }

  zoomIn() {
    this._zoom()?.zoomIn();
  }

  zoomOut() {
    this._zoom()?.zoomOut();
  }

  undo() {
    this.canvasEditStore.undo();
  }

  redo() {
    this.canvasEditStore.redo();
  }

  resetToSaved() {
    this.canvasEditStore.resetToSaved();
    this.toast.success('Canvas reset to last saved state.');
  }

  // ------ Keyboard shortcuts ------

  @HostListener('document:keydown', ['$event'])
  onKeyDown(event: KeyboardEvent) {
    if (this.drawerOpen()) return;
    const tag = (event.target as HTMLElement)?.tagName?.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

    const ctrl = event.ctrlKey || event.metaKey;
    if (this.canEdit()) {
      if (ctrl && event.key === 'z') {
        event.preventDefault();
        this.undo();
        return;
      }
      if (ctrl && (event.key === 'y' || (event.shiftKey && event.key === 'Z'))) {
        event.preventDefault();
        this.redo();
        return;
      }
      if (ctrl && event.key === 'a') {
        event.preventDefault();
        this._flow().select(
          this.canvasNodes().map((n) => n.id),
          [],
          false,
        );
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
      const sel = this._flow().getSelection();
      if ((sel.fNodeIds?.length ?? 0) === 0) return;
      event.preventDefault();
      this._deleteSelectedNodes();
    }
  }

  // ------ Copy / Paste — use Foblex getSelection() as authoritative source ------

  private _copySelectedNodes(): void {
    const sel = this._flow().getSelection();
    const nodeIds = new Set(sel.fNodeIds ?? []);
    if (nodeIds.size === 0) return;

    const nodes = this.canvasNodes().filter((n) => nodeIds.has(n.id));
    const edges = this.canvasEditStore
      .localEdges()
      .filter((e) => nodeIds.has(e.source_node) && nodeIds.has(e.target_node));

    this.clipboard.set({ nodes: structuredClone(nodes), edges: structuredClone(edges) });
    this.toast.success(`Copied ${nodes.length} node(s).`);
  }

  private _pasteNodes(): void {
    const clip = this.clipboard();
    if (!clip || clip.nodes.length === 0) return;
    this.canvasEditStore.pushUndoState();

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

    const newNodeIds = [...idMap.values()];
    // Select the pasted nodes so the user can immediately move them
    this._flow().select(newNodeIds, [], true);

    // Advance clipboard offset so chained Ctrl+V pastes spread out further
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
    const sel = this._flow().getSelection();
    const nodeIds = new Set(sel.fNodeIds ?? []);
    if (nodeIds.size === 0) return;
    const count = nodeIds.size;
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
    this.canvasEditStore.pushUndoState();
    this.canvasEditStore.deleteNodes(nodeIds);
    this.toast.success(`${count} node(s) deleted.`);
  }

  // ------ Connector ID helpers ------

  /**
   * Build the source connector ID for a given node + port.
   * Format: "<nodeId>__out__<portId>"
   */
  buildSourceConnectorId(nodeId: string, portId: string): string {
    return `${nodeId}__out__${portId}`;
  }

  /**
   * Build the target (input) connector ID for a node.
   * Format: "<nodeId>__in"
   */
  buildTargetConnectorId(nodeId: string): string {
    return `${nodeId}__in`;
  }

  private _nodeIdFromConnector(connectorId: string): string {
    // "<nodeId>__out__<portId>" or "<nodeId>__in"
    const outIdx = connectorId.indexOf('__out__');
    if (outIdx !== -1) return connectorId.slice(0, outIdx);
    const inIdx = connectorId.indexOf('__in');
    if (inIdx !== -1) return connectorId.slice(0, inIdx);
    return connectorId;
  }

  private _portIdFromConnector(connectorId: string): string {
    const outIdx = connectorId.indexOf('__out__');
    if (outIdx !== -1) return connectorId.slice(outIdx + '__out__'.length);
    return 'out';
  }

  // ------ Node creation ------

  private _createNodeAtPosition(type: string, position: { x: number; y: number }) {
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

  // ------ Port helpers (used in template for fConnector wiring) ------

  hasInputPort(node: CanvasNode): boolean {
    const def = this.nodeStore.nodeDefinitions().find((d) => d.type === node.data.type);
    return !!(def && def.inputs && def.inputs.length > 0);
  }

  isInputMultiple(node: CanvasNode): boolean {
    const def = this.nodeStore.nodeDefinitions().find((d) => d.type === node.data.type);
    return !!def?.inputs?.[0]?.multiple;
  }

  getOutputPorts(node: CanvasNode): Array<{ id: string; label: string }> {
    const def = this.nodeStore.nodeDefinitions().find((d) => d.type === node.data.type);
    return def?.outputs ?? [];
  }

  getInputPortLabel(node: CanvasNode): string {
    const def = this.nodeStore.nodeDefinitions().find((d) => d.type === node.data.type);
    return def?.inputs?.[0]?.label ?? 'Input';
  }

  getOutputPortY(portIndex: number, totalPorts: number): number {
    if (totalPorts === 1) return 16;
    const nodeHeight = 80;
    const spacing = nodeHeight / (totalPorts + 1);
    return spacing * (portIndex + 1);
  }

  /**
   * Returns the Foblex fCanBeConnectedTo allow-list for a source (output) connector.
   *
   * Strategy: scan all node definitions. For each definition whose input ports declare
   * `allowed_source_categories` containing the source node's category, add that
   * definition's own category to the allow-list. Foblex then matches this list against
   * the [fConnectorCategory] set on target input connectors (which is the target node's
   * own category).
   *
   * If a definition has input ports with NO restrictions, any source can connect — so
   * when there are unrestricted definitions the allow-list is empty (= no restriction).
   */
  getAllowedTargetCategories(node: CanvasNode): string[] {
    const sourceCategory = node.data.category?.toLowerCase() ?? '';
    const definitions = this.nodeStore.nodeDefinitions();

    // If any definition has unrestricted inputs, don't restrict at all
    const hasUnrestrictedTargets = definitions.some(
      (def) =>
        def.inputs.length > 0 && def.inputs.every((p) => !p.allowed_source_categories?.length),
    );
    if (hasUnrestrictedTargets) return [];

    // Collect categories of definitions whose inputs accept sourceCategory
    const allowed = new Set<string>();
    for (const def of definitions) {
      if (!def.inputs.length) continue;
      const accepts = def.inputs.some(
        (p) =>
          !p.allowed_source_categories?.length ||
          p.allowed_source_categories.map((c) => c.toLowerCase()).includes(sourceCategory),
      );
      if (accepts) allowed.add(def.category.toLowerCase());
    }
    return [...allowed];
  }
}
