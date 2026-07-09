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

  // ------ Undo/Redo state ------
  private _undoStack: { nodes: NodeConfig[]; edges: Edge[] }[] = [];
  private _redoStack: { nodes: NodeConfig[]; edges: Edge[] }[] = [];
  private static readonly MAX_HISTORY = 50;

  readonly canUndo = signal(false);
  readonly canRedo = signal(false);

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

  // ------ Computed: edge view-model for Foblex f-connection ------
  //
  // Foblex owns path rendering; we just map edges to the connector-ID format
  // that the canvas template expects: "<nodeId>__out__<portId>" → "<nodeId>__in".
  readonly connections = computed<Connection[]>(() => {
    const nodes = this._canvasNodes();
    const edges = this._localEdges();
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    return edges.flatMap((edge) => {
      const sourceNode = nodeMap.get(edge.source_node);
      const targetNode = nodeMap.get(edge.target_node);
      if (!sourceNode || !targetNode) return [];

      // Determine port color based on port id (true/false branching)
      const portId = edge.source_port ?? 'out';
      let color: string | undefined;
      if (portId === 'true') color = '#16a34a';
      else if (portId === 'false') color = '#f97316';

      // Connector IDs must match what the template builds via buildSourceConnectorId /
      // buildTargetConnectorId in FlowCanvasComponent.
      const from = `${edge.source_node}__out__${portId}`;
      const to = `${edge.target_node}__in`;

      return [{ id: edge.id, from, to, color }];
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

  /** Batch-update canvas node positions (for multi-node drag). */
  updateCanvasNodesPositions(updates: Map<string, { x: number; y: number }>): void {
    this._canvasNodes.update((nodes) =>
      nodes.map((n) => {
        const pos = updates.get(n.id);
        return pos ? { ...n, position: pos } : n;
      }),
    );
  }

  /** Batch-delete multiple nodes and their connected edges. */
  deleteNodes(ids: Set<string>): void {
    this._localNodes.update((nodes) => nodes.filter((n) => !ids.has(n.id)));
    this._localEdges.update((edges) =>
      edges.filter((e) => !ids.has(e.source_node) && !ids.has(e.target_node)),
    );
    this._mergeCanvasNodes(this._localNodes());
  }

  /** Batch-move multiple nodes (persists to localNodes). */
  moveNodes(updates: Map<string, { x: number; y: number }>): void {
    this._localNodes.update((nodes) =>
      nodes.map((n) => {
        const pos = updates.get(n.id);
        return pos ? { ...n, x: pos.x, y: pos.y } : n;
      }),
    );
    this._mergeCanvasNodes(this._localNodes());
  }

  // ---------------------------------------------------------------------------
  // Undo / Redo
  // ---------------------------------------------------------------------------

  /** Call before any mutation to snapshot current state for undo. */
  pushUndoState(): void {
    this._undoStack.push(this._snapshot());
    if (this._undoStack.length > CanvasEditStoreService.MAX_HISTORY) {
      this._undoStack.shift();
    }
    this._redoStack = [];
    this._syncHistorySignals();
  }

  undo(): void {
    if (this._undoStack.length === 0) return;
    this._redoStack.push(this._snapshot());
    const prev = this._undoStack.pop()!;
    this._restoreSnapshot(prev);
    this._syncHistorySignals();
  }

  redo(): void {
    if (this._redoStack.length === 0) return;
    this._undoStack.push(this._snapshot());
    const next = this._redoStack.pop()!;
    this._restoreSnapshot(next);
    this._syncHistorySignals();
  }

  /** Reset to the last saved backend state (clears undo/redo). */
  resetToSaved(): void {
    const nodes = this.nodeStore.nodes();
    const edges = this.nodeStore.edges();
    this._localNodes.set(structuredClone(nodes));
    this._localEdges.set(structuredClone(edges));
    this._mergeCanvasNodes(this._localNodes());
    this._undoStack = [];
    this._redoStack = [];
    this._syncHistorySignals();
  }

  private _snapshot(): { nodes: NodeConfig[]; edges: Edge[] } {
    return {
      nodes: structuredClone(this._localNodes()),
      edges: structuredClone(this._localEdges()),
    };
  }

  private _restoreSnapshot(snap: { nodes: NodeConfig[]; edges: Edge[] }): void {
    this._localNodes.set(snap.nodes);
    this._localEdges.set(snap.edges);
    this._mergeCanvasNodes(this._localNodes());
  }

  private _syncHistorySignals(): void {
    this.canUndo.set(this._undoStack.length > 0);
    this.canRedo.set(this._redoStack.length > 0);
  }

  // ---------------------------------------------------------------------------
  // applyChanges (sync to backend with 150ms debounce)
  // ---------------------------------------------------------------------------

  private _applyDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  /**
   * Syncs local changes to the backend.
   * Local edits are already in _localNodes and _localEdges.
   * Call this when user hits "Apply" to persist to backend.
   */
  async applyChanges(): Promise<void> {
    if (this._applyDebounceTimer) {
      clearTimeout(this._applyDebounceTimer);
    }
    return new Promise((resolve) => {
      this._applyDebounceTimer = setTimeout(async () => {
        this._applyDebounceTimer = null;
        await this._executeApplyChanges();
        resolve();
      }, 150);
    });
  }

  private async _executeApplyChanges(): Promise<void> {
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

  /** Snap a value to the nearest grid line. */
  snapValue(value: number, enabled: boolean): number {
    if (!enabled) return value;
    return Math.round(value / GRID_SIZE) * GRID_SIZE;
  }
  
}
