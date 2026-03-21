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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

/**
 * Feature-scoped store for local canvas edits.
 *
 * IMPORTANT: This service must be provided via `providers: [CanvasEditStoreService]`
 * on SettingsComponent. It must NOT be `providedIn: 'root'`.
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

  // ------ Public read-only exposures ------
  readonly localNodes = this._localNodes.asReadonly();
  readonly localEdges = this._localEdges.asReadonly();
  readonly baseVersion = this._baseVersion.asReadonly();
  readonly isSaving = this._isSaving.asReadonly();
  readonly isSyncing = this._isSyncing.asReadonly();
  readonly isReloading = this._isReloading.asReadonly();
  readonly isInitialized = this._isInitialized.asReadonly();

  // ------ Conflict event channel ------
  readonly conflictDetected$ = new Subject<string>();

  // ------ Dependencies ------
  private readonly nodeStore = inject(NodeStoreService);
  private readonly dagApi = inject(DagApiService);
  private readonly toast = inject(ToastService);
  private readonly dialog = inject(DialogService);
  private readonly nodesApi = inject(NodesApiService);

  // ------ Computed: dirty ------
  readonly isDirty = computed(
    () =>
      !deepEqual(this._localNodes(), this.nodeStore.nodes()) ||
      !deepEqual(this._localEdges(), this.nodeStore.edges()),
  );

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

  // ---------------------------------------------------------------------------
  // initFromBackend
  // ---------------------------------------------------------------------------

  initFromBackend(config: DagConfigResponse): void {
    this._localNodes.set(structuredClone(config.nodes));
    this._localEdges.set(structuredClone(config.edges));
    this._baseVersion.set(config.config_version);
    this.nodeStore.setState({ nodes: config.nodes, edges: config.edges });
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
  }

  updateNode(id: string, patch: Partial<NodeConfig>): void {
    this._localNodes.update((nodes) =>
      nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    );
  }

  deleteNode(id: string): void {
    this._localNodes.update((nodes) => nodes.filter((n) => n.id !== id));
    this._localEdges.update((edges) =>
      edges.filter((e) => e.source_node !== id && e.target_node !== id),
    );
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
  // saveAndReload
  // ---------------------------------------------------------------------------

  async saveAndReload(): Promise<void> {
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
      this.toast.success('DAG saved and reloading…');
    } catch (error: any) {
      const is409 =
        error?.status === 409 ||
        (typeof error?.error?.detail === 'string' &&
          error.error.detail.toLowerCase().includes('version conflict'));

      if (is409) {
        const detail =
          error?.error?.detail ?? 'Version conflict. Another save has occurred.';
        this.conflictDetected$.next(detail);
      } else {
        const message =
          error?.error?.detail ?? error?.message ?? String(error);
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
}
