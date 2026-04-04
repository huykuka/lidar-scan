import {computed, inject, Injectable, signal} from '@angular/core';
import {Subject} from 'rxjs';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {DagApiService} from '@core/services/api/dag-api.service';
import {ToastService} from '@core/services/toast.service';
import {DialogService} from '@core/services/dialog.service';
import {NodesApiService} from '@core/services/api/nodes-api.service';
import {Edge, NodeConfig} from '@core/models/node.model';
import {DagConfigResponse} from '@core/models/dag.model';
import {detectCycles, validateRequiredFields, ValidationError,} from '@features/settings/utils/dag-validator';
import {CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {Connection} from '@features/settings/components/flow-canvas/connections/flow-canvas-connections.component';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

const GRID_SIZE = 20; // must match canvas SVG grid pattern size

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

/**
 * Feature-scoped store for local canvas edits.
 *
 * IMPORTANT: This service must be provided via `providers: [CanvasEditStoreService]`
 * on SettingsComponent. It must NOT be `providedIn: 'root'`.
 *
 * This store is the single source of truth for both the edit draft (localNodes /
 * localEdges) and the derived canvas view state (canvasNodes / connections).
 * FlowCanvasComponent reads those signals directly instead of maintaining its
 * own parallel copies.
 */
@Injectable()
export class CanvasEditStoreService {
  // ------ Internal state ------
  private _localNodes = signal<NodeConfig[]>([]);
  private _localEdges = signal<Edge[]>([]);
  private _baseVersion = signal<number>(0);
  private _isSaving = signal<boolean>(false);
  private _isSyncing = signal<boolean>(false);
  private _isReloading = signal<boolean>(false);
  /** True once initFromBackend() has been called at least once. Used by the canvas to distinguish
   *  the initial empty-signal state (before HTTP completes) from a real empty node list. */
  private _isInitialized = signal<boolean>(false);

  // ------ View-layer state (owned here, consumed by FlowCanvasComponent) ------
  /** Mutable view-model for nodes on the canvas. Written by mergeCanvasNodes()
   *  and directly mutated during drag to keep rendering smooth. */
  private _canvasNodes = signal<CanvasNode[]>([]);

  // ------ Public read-only exposures ------
  readonly localNodes = this._localNodes.asReadonly();
  readonly localEdges = this._localEdges.asReadonly();
  readonly baseVersion = this._baseVersion.asReadonly();
  readonly isSaving = this._isSaving.asReadonly();
  readonly isSyncing = this._isSyncing.asReadonly();
  readonly isReloading = this._isReloading.asReadonly();
  readonly isInitialized = this._isInitialized.asReadonly();

  /** Derived canvas view-model nodes (position + data wrapped for the template). */
  readonly canvasNodes = this._canvasNodes.asReadonly();

  // ------ Conflict event channel ------
  readonly conflictDetected$ = new Subject<string>();

  // ------ Dependencies ------
  private readonly nodeStore = inject(NodeStoreService);
  private readonly dagApi = inject(DagApiService);
  private readonly toast = inject(ToastService);
  private readonly dialog = inject(DialogService);
  private readonly nodesApi = inject(NodesApiService);

  // ------ Computed: dirty ------
  /**
   * True when local edits diverge from the last-known backend state.
   * Returns false before initFromBackend() completes to prevent the
   * "Unsaved" badge from flashing during initial canvas loading.
   */
  readonly isDirty = computed(() => {
    if (!this._isInitialized()) return false;
    return (
      !deepEqual(this._localNodes(), this.nodeStore.nodes()) ||
      !deepEqual(this._localEdges(), this.nodeStore.edges())
    );
  });

  // ------ Computed: validation ------
  readonly validationErrors = computed<ValidationError[]>(() => {
    const cycleErrors = detectCycles(this._localNodes(), this._localEdges());
    const reqErrors = validateRequiredFields(
      this._localNodes(),
      this.nodeStore.nodeDefinitions(),
    );
    return [...cycleErrors, ...reqErrors];
  });

  readonly isValid = computed(() => this.validationErrors().length === 0);

  // ------ Computed: SVG connection paths (derived from canvasNodes + localEdges) ------
  readonly connections = computed<Connection[]>(() => {
    const nodes = this._canvasNodes();
    const edges = this._localEdges();
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    return edges.flatMap((edge) => {
      const sourceNode = nodeMap.get(edge.source_node);
      const targetNode = nodeMap.get(edge.target_node);
      if (!sourceNode || !targetNode) return [];

      const sourceDef = this.nodeStore.nodeDefinitions().find((d) => d.type === sourceNode.data.type);
      const outputPorts = sourceDef?.outputs ?? [];
      const portIndex = outputPorts.findIndex((p) => p.id === edge.source_port);

      let color = '#6366f1';

      const path = this._calculatePath(sourceNode, targetNode, portIndex >= 0 ? portIndex : 0, outputPorts.length);
      return [{ id: edge.id, from: edge.source_node, to: edge.target_node, path, color }];
    });
  });

  // ---------------------------------------------------------------------------
  // initFromBackend
  // ---------------------------------------------------------------------------

  initFromBackend(config: DagConfigResponse): void {
    const nodes = structuredClone(config.nodes);
    const edges = structuredClone(config.edges);

    // Set the nodeStore (baseline) FIRST so that isDirty never sees a
    // transient mismatch between _localNodes and nodeStore.nodes().
    this.nodeStore.setState({ nodes, edges });
    this._localNodes.set(nodes);
    this._localEdges.set(edges);
    this._baseVersion.set(config.config_version);
    this._mergeCanvasNodes(nodes);
    this._isInitialized.set(true);
  }

  // ---------------------------------------------------------------------------
  // Local mutation methods
  // ---------------------------------------------------------------------------

  addNode(node: Partial<NodeConfig>): void {
    const newNode: NodeConfig = {
      id: node.id ?? `__new__${Date.now()}`,
      name: node.name ?? 'New Node',
      type: node.type ?? 'unknown',
      category: node.category ?? 'unknown',
      enabled: node.enabled ?? true,
      visible: node.visible ?? true,
      config: node.config ?? {},
      pose: node.pose,
      x: node.x ?? 100,
      y: node.y ?? 100,
    };
    this._localNodes.update((nodes) => [...nodes, newNode]);
    this._mergeCanvasNodes(this._localNodes());
  }

  updateNode(id: string, patch: Partial<NodeConfig>): void {
    this._localNodes.update((nodes) =>
      nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    );
    this._mergeCanvasNodes(this._localNodes());
  }

  deleteNode(id: string): void {
    this._localNodes.update((nodes) => nodes.filter((n) => n.id !== id));
    this._localEdges.update((edges) =>
      edges.filter((e) => e.source_node !== id && e.target_node !== id),
    );
    this._mergeCanvasNodes(this._localNodes());
  }

  addEdge(edge: Edge): void {
    const duplicate = this._localEdges().some(
      (e) =>
        e.source_node === edge.source_node &&
        e.source_port === edge.source_port &&
        e.target_node === edge.target_node,
    );
    if (duplicate) return;

    const newEdge: Edge = {
      ...edge,
      id: edge.id ?? `__edge__${Date.now()}`,
    };
    this._localEdges.update((edges) => [...edges, newEdge]);
  }

  deleteEdge(id: string): void {
    this._localEdges.update((edges) => edges.filter((e) => e.id !== id));
  }

  moveNode(id: string, x: number, y: number): void {
    this.updateNode(id, { x, y });
  }

  // ---------------------------------------------------------------------------
  // Canvas view-model helpers (used by FlowCanvasComponent during drag)
  // ---------------------------------------------------------------------------

  /** Directly update canvasNodes position for a node being dragged (smooth, no store roundtrip). */
  updateCanvasNodePosition(id: string, position: { x: number; y: number }): void {
    this._canvasNodes.update((nodes) =>
      nodes.map((n) => (n.id === id ? { ...n, position } : n)),
    );
  }

  // ---------------------------------------------------------------------------
  // saveAndReload (with 150ms debounce)
  // ---------------------------------------------------------------------------

  private _saveDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  async saveAndReload(): Promise<void> {
    if (this._saveDebounceTimer) {
      clearTimeout(this._saveDebounceTimer);
    }
    return new Promise((resolve) => {
      this._saveDebounceTimer = setTimeout(async () => {
        this._saveDebounceTimer = null;
        await this._executeSaveAndReload();
        resolve();
      }, 150);
    });
  }

  private async _executeSaveAndReload(): Promise<void> {
    if (!this.isDirty()) return;

    if (!this.isValid()) {
      const firstError = this.validationErrors()[0];
      this.toast.danger(firstError?.message ?? 'Fix validation errors before saving.');
      return;
    }

    this._isSaving.set(true);
    try {
      const response = await this.dagApi.saveDagConfig({
        base_version: this._baseVersion(),
        nodes: this._localNodes(),
        edges: this._localEdges(),
      });

      // Apply node_id_map: remap temp IDs in localNodes and localEdges
      const idMap = response.node_id_map ?? {};
      if (Object.keys(idMap).length > 0) {
        this._localNodes.update((nodes) =>
          nodes.map((n) => (idMap[n.id] ? { ...n, id: idMap[n.id] } : n)),
        );
        this._localEdges.update((edges) =>
          edges.map((e) => ({
            ...e,
            source_node: idMap[e.source_node] ?? e.source_node,
            target_node: idMap[e.target_node] ?? e.target_node,
          })),
        );
      }

      this._baseVersion.set(response.config_version);
      this.nodeStore.setState({
        nodes: this._localNodes(),
        edges: this._localEdges(),
      });
      this._mergeCanvasNodes(this._localNodes());

      // Show appropriate toast based on reload_mode from response
      const mode = (response as any).reload_mode as 'selective' | 'full' | 'none' | undefined;
      const reloadedIds: string[] = (response as any).reloaded_node_ids ?? [];
      if (mode === 'selective') {
        this.toast.success(`Configuration saved. Reloading ${reloadedIds.length} node(s)…`);
      } else if (mode === 'full') {
        this.toast.success('Configuration saved. Reloading DAG…');
      } else {
        this.toast.success('Configuration saved.');
      }
    } catch (error: any) {
      const detail = error?.error?.detail ?? '';
      const isVersionConflict = detail.toLowerCase().includes('version conflict');
      const isLockConflict = detail.toLowerCase().includes('reload is already in progress');

      if (isVersionConflict || error?.status === 409 && !isLockConflict && !detail) {
        this.conflictDetected$.next(detail || 'Version conflict. Another save has occurred.');
      } else if (isLockConflict) {
        this.toast.warning('A reload is already in progress. Please wait a moment and try again.');
      } else {
        const message = detail || (error?.message ?? String(error));
        this.toast.danger(`Save failed: ${message}`);
      }
    } finally {
      this._isSaving.set(false);
    }
  }

  // ---------------------------------------------------------------------------
  // syncFromBackend
  // ---------------------------------------------------------------------------

  async syncFromBackend(skipConfirm = false): Promise<void> {
    if (this.isDirty() && !skipConfirm) {
      const confirmed = await this.dialog.confirm(
        'You have unsaved changes. Syncing will discard them and load the latest backend configuration. Continue?',
      );
      if (!confirmed) return;
    }

    this._isSyncing.set(true);
    try {
      const response = await this.dagApi.getDagConfig();
      this.initFromBackend(response);
      this.toast.success('Synced with backend.');
    } catch (error: any) {
      const message = error?.message ?? String(error);
      this.toast.danger(`Sync failed: ${message}`);
    } finally {
      this._isSyncing.set(false);
    }
  }

  // ---------------------------------------------------------------------------
  // reloadRuntime
  // ---------------------------------------------------------------------------

  /**
   * Calls POST /api/v1/nodes/reload only.
   * CRITICAL: Does NOT alter _localNodes, _localEdges, _baseVersion, or isDirty.
   */
  async reloadRuntime(): Promise<void> {
    this._isReloading.set(true);
    try {
      await this.nodesApi.reloadConfig();
      this.toast.success('DAG runtime reloaded successfully.');
    } catch (error: any) {
      const message = error?.message ?? String(error);
      this.toast.danger(`Reload failed: ${message}`);
    } finally {
      this._isReloading.set(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Private: canvas view-model derivation
  // ---------------------------------------------------------------------------

  private _mergeCanvasNodes(nodes: NodeConfig[]): void {
    const existing = new Map(this._canvasNodes().map((n) => [n.id, n]));
    const incoming = new Set(nodes.map((n) => n.id));

    const merged: CanvasNode[] = nodes.map((node, index) => {
      const prev = existing.get(node.id);
      // Prefer backend-supplied coordinates if present; fall back to the current
      // canvas position (preserves drag positions not yet persisted) or a default grid slot.
      const position =
        node.x != null && node.y != null
          ? { x: node.x, y: node.y }
          : prev
            ? prev.position
            : { x: 100 + (index % 4) * 300, y: 100 + Math.floor(index / 4) * 250 };

      return {
        id: node.id,
        type: (node.category || node.type || 'unknown').toLowerCase(),
        data: node,
        position,
      };
    });

    const prevIds = [...existing.keys()];
    const structurallyChanged =
      merged.length !== prevIds.length || prevIds.some((id) => !incoming.has(id));

    if (structurallyChanged) {
      this._canvasNodes.set(merged);
    } else {
      const mergedById = new Map(merged.map((m) => [m.id, m]));
      this._canvasNodes.update((current) =>
        current.map((n) => {
          const updated = mergedById.get(n.id);
          if (!updated) return n;
          return { ...n, data: updated.data, position: updated.position };
        }),
      );
    }
  }

  private _calculatePath(
    fromNode: CanvasNode,
    toNode: CanvasNode,
    fromPortIndex: number = 0,
    totalOutputPorts: number = 1,
  ): string {
    const fromX = fromNode.position.x + 192 + 6;
    const fromY = fromNode.position.y + this._portY(fromPortIndex, totalOutputPorts);
    const toX = toNode.position.x - 6;
    const toY = toNode.position.y + 16;

    const cp = Math.max(Math.abs(toX - fromX) * 0.5, 40);
    return `M ${fromX} ${fromY} C ${fromX + cp} ${fromY}, ${toX - cp} ${toY}, ${toX} ${toY}`;
  }

  /** Y offset of a port within its node, matching FlowCanvasNodeComponent.getOutputPortY(). */
  private _portY(portIndex: number, totalPorts: number): number {
    if (totalPorts === 1) return 16;
    const nodeHeight = 80;
    const spacing = nodeHeight / (totalPorts + 1);
    return spacing * (portIndex + 1);
  }

  /** Snap a value to the nearest grid line. */
  snapValue(value: number, enabled: boolean): number {
    if (!enabled) return value;
    return Math.round(value / GRID_SIZE) * GRID_SIZE;
  }
  
}
