# Canvas Local Edit — Frontend Tasks

**Feature:** `canvas-local-edit`  
**Agent:** `@fe-dev`  
**References:**
- Requirements: `requirements.md`
- Technical design: `technical.md` (§5.0 for mandatory deletions)
- API contract: `api-spec.md` — **MUST MOCK** `DagApiService` while backend is in development

**Constraint:** All work inside `/web/` only. Standalone Components exclusively. No NgModules. Angular Signals for
state. RxJS only for HTTP + conflict event channel.

**Revision v2:** `Cancel` renamed to **`Sync`** (pull backend config, prompt if dirty). New **`Reload`** button added
(POST `/nodes/reload` — runtime restart only, never changes local state).

> **EXECUTION ORDER IS STRICT:**
> `Phase -1 (Purge)` → `Phase 0 (Scaffolding)` → `Phase 1 (Store)` → `Phase 2–3 (Refactor)` → `Phase 4–6 (Toolbar/Guard)` → `Phase 7 (Cleanup)`
>
> **Do NOT write new code before Phase -1 is complete and `tsc --noEmit` passes.**

---

## Phase -1 — MANDATORY DEAD CODE PURGE ⚠️

> **This phase is not optional.** All items below are hard deletions of obsolete code from the previous
> per-mutation-API-call flow and the old Cancel/Revert/dirty-via-output pattern. There is **no migration path,
> no feature flag, no backward compatibility layer**. Delete the symbols outright. Confirm `tsc --noEmit` passes
> after completing this phase before proceeding to Phase 0.

### -1.1 Delete obsolete symbols from `flow-canvas.component.ts`

File: `web/src/app/features/settings/components/flow-canvas/flow-canvas.component.ts`

- [x] **Delete** `hasUnsavedChangesChange = output<boolean>()` (line ~57) — dirty state is now owned by
  `CanvasEditStoreService.isDirty()`, not propagated upward via output
- [x] **Delete** `public hasUnsavedChanges = signal(false)` (line ~58) — same reason
- [x] **Delete** `private unsavedPositions = new Map<string, { x: number; y: number }>()` (line ~93) — replaced by
  `CanvasEditStoreService.moveNode()`
- [x] **Delete the entire `saveAllPositions()` method** (lines ~202–233) — there is no per-drag backend save in the
  new model
- [x] **Delete** all `this.unsavedPositions.set(...)`, `this.unsavedPositions.clear()`,
  `this.hasUnsavedChanges.set(...)`, and `this.hasUnsavedChangesChange.emit(...)` call sites (in
  `onCanvasMouseUp()` and the deleted `saveAllPositions()`)
- [x] **Delete** the `await this.edgesApi.createEdge(...)` call, the follow-up
  `Promise.all([nodesApi.getNodes(), edgesApi.getEdges()])`, and `nodeStore.setState(...)` inside `onPortDrop()`
  — the try/catch wrapping these calls is also removed (local ops are synchronous)
- [x] **Delete** `await this.edgesApi.deleteEdge(edgeId)` and `nodeStore.set('edges', ...)` inside `onDeleteEdge()`
- [x] **Delete** `await this.nodesApi.deleteNode(node.id)`, `nodeStore.set('nodes', ...)`, and
  `nodeStore.set('edges', ...)` inside `onDeleteNode()`
- [x] **Delete the entire `private async loadGraphData()` method** (lines ~468–488) — initial data load moves to
  `SettingsComponent` via `canvasEditStore.initFromBackend()`
- [x] **Delete** `this.loadGraphData()` call in `ngOnInit()` (keep `this.statusWs.connect()`)
- [x] **Delete** `await this.loadGraphData()` call inside `onToggleNodeEnabled()` (will be replaced in Phase 2.8)
- [x] **Delete** `private edgesApi = inject(EdgesApiService)` injection and its import — `EdgesApiService` is no
  longer called from this component
- [x] After deletions: run `cd web && npx tsc --noEmit` — fix any type errors before continuing

### -1.2 Delete obsolete symbols from `settings.component.ts`

File: `web/src/app/features/settings/settings.component.ts`

- [x] **Delete** `protected hasUnsavedChanges = signal(false)` — replaced by `canvasEditStore.isDirty()`
- [x] **Delete the entire `onReloadConfig()` method** (lines ~85–101) — this method conflated "save positions"
  (now local-edit-only) with "reload runtime" (now `onReloadRuntime()`) and "pull config" (now `onSync()`).
  It must not exist in the new model
- [x] **Delete** all call sites of `onReloadConfig()` — including the call inside `onConfirmImport()` at line ~178
  (replace with `this.onSync()` after Phase 4.3 is complete, or inline a `dagApi.getDagConfig()` +
  `canvasEditStore.initFromBackend()` call if Sync is not yet wired)
- [x] **Delete** `private nodesApi = inject(NodesApiService)` and its import **if** `NodesApiService` is only used
  in `loadConfig()` and `onReloadConfig()`. (Verify: `nodesApi` is NOT used elsewhere in `settings.component.ts`;
  if it is, keep the injection)
- [x] **Delete the entire `loadConfig()` method** — it is replaced by
  `dagApi.getDagConfig()` → `canvasEditStore.initFromBackend()` in the new `ngOnInit()` flow
- [x] After deletions: run `cd web && npx tsc --noEmit` — fix any type errors before continuing

### -1.3 Delete obsolete template elements from `settings.component.html`

File: `web/src/app/features/settings/settings.component.html`

- [x] **Delete** the old `<syn-button (click)="onReloadConfig()" [disabled]="!flowCanvas().hasUnsavedChanges()"...>`
  button block (lines ~31–36 — the old single "Save & Reload" button that gated on `hasUnsavedChanges`)
- [x] **Delete** `(hasUnsavedChangesChange)="hasUnsavedChanges.set($event)"` from the `<app-flow-canvas>` binding
  (line ~55) — this output no longer exists on `FlowCanvasComponent`
- [x] **Preserve** `(cancel)="onCancelImport()"` on `<app-config-import-dialog>` — this is the import dialog's own
  cancel, unrelated to the canvas edit flow
- [x] After deletions: run `cd web && npx tsc --noEmit` and check template compilation — fix binding errors

### -1.4 Verify `viewChild(FlowCanvasComponent)` is still needed

- [x] Check if `protected flowCanvas = viewChild.required(FlowCanvasComponent)` in `settings.component.ts` is still
  referenced after deleting `onReloadConfig()`, `flowCanvas().hasUnsavedChanges()`, and
  `flowCanvas().saveAllPositions()`
- [x] If no remaining call sites reference `flowCanvas()` in `.ts`, **delete** the `viewChild` declaration and the
  `FlowCanvasComponent` import from `settings.component.ts`
- [x] If `flowCanvas()` is still referenced in the template for other reasons, retain it

### -1.5 Phase -1 completion gate

- [x] **`cd web && npx tsc --noEmit` — ZERO errors**
- [x] **`cd web && ng build --configuration=development` — ZERO errors** (template compilation check)
- [x] Confirm via `git diff --stat` that only the files listed in §-1.1–-1.4 were touched
- [x] Confirm no `Cancel` button, `Revert` button, `hasUnsavedChanges` output, `saveAllPositions` method,
  `loadGraphData` method, or `onReloadConfig` method remains in any settings-feature file

---

## Phase 0 — Scaffolding & Models

### 0.1 Create TypeScript DAG models

- [x] Create `web/src/app/core/models/dag.model.ts`:
  ```typescript
  import { NodeConfig, Edge } from './node.model';

  export interface DagConfigResponse {
    config_version: number;
    nodes: NodeConfig[];
    edges: Edge[];
  }

  export interface DagConfigSaveRequest {
    base_version: number;
    nodes: NodeConfig[];
    edges: Edge[];
  }

  export interface DagConfigSaveResponse {
    config_version: number;
    node_id_map: Record<string, string>;
  }

  export interface DagConflictError {
    status: 409;
    error: { detail: string };
  }
  ```
- [x] Export from `web/src/app/core/models/index.ts`

### 0.2 Create `DagApiService`

- [x] Run: `cd web && ng g service core/services/api/dag-api`
- [x] Implement `getDagConfig(): Promise<DagConfigResponse>` — calls `GET /api/v1/dag/config`
- [x] Implement `saveDagConfig(req: DagConfigSaveRequest): Promise<DagConfigSaveResponse>` — calls
  `PUT /api/v1/dag/config`
- [x] **MOCK IMPLEMENTATION** (until backend is ready): implement both methods using mock data per
  `api-spec.md §Frontend Mock Data`. Switch via `environment.useMockDag` flag
- [x] Export from `web/src/app/core/services/api/index.ts`

> **Note:** The `Reload` button calls `POST /api/v1/nodes/reload` via the **existing** `NodesApiService` (or equivalent
> existing service). No new method is added to `DagApiService` for this.

### 0.3 Create `dag-validator.ts` utility

- [x] Create `web/src/app/features/settings/utils/dag-validator.ts`
- [x] Implement `detectCycles(nodes: NodeConfig[], edges: Edge[]): string[]`:
  - Build adjacency list from `edges` (source_node → target_node)
  - DFS with `visited` + `inStack` sets
  - Return array of human-readable cycle descriptions (e.g. `"Node A → Node B → Node A"`)
- [x] Implement `validateRequiredFields(nodes: NodeConfig[], definitions: NodeDefinition[]): ValidationError[]`:
  - For each node, find its `NodeDefinition`
  - For each `PropertySchema` where `required === true`, check `node.config[prop.name]` is non-null/non-empty
  - Return `{ nodeId, nodeName, field, message }[]`
- [x] Export `ValidationError` interface from the same file:
  ```typescript
  export interface ValidationError {
    nodeId: string;
    nodeName: string;
    field?: string;
    message: string;
  }
  ```

---

## Phase 1 — `CanvasEditStoreService`

### 1.1 Scaffold the service

- [x] Run: `cd web && ng g service features/settings/services/canvas-edit-store`
- [x] Change `providedIn: 'root'` → remove `providedIn`; service will be feature-scoped

### 1.2 Define the state model

- [x] Add internal signals:
  ```typescript
  private _localNodes = signal<NodeConfig[]>([]);
  private _localEdges = signal<Edge[]>([]);
  private _baseVersion = signal<number>(0);
  private _isSaving = signal<boolean>(false);
  private _isSyncing = signal<boolean>(false);       // renamed from isReverting
  private _isReloading = signal<boolean>(false);     // NEW: tracks POST /nodes/reload
  ```
- [x] Add public readonly exposures (`asReadonly()`) for all signals above
- [x] Inject `NodeStoreService`, `DagApiService`, `ToastService`, `DialogService`

### 1.3 Implement `isDirty` computed signal

- [x] Import or implement `deepEqual(a, b): boolean` (use `JSON.stringify` comparison; sufficient for <50 nodes)
- [x] `isDirty = computed(() => !deepEqual(this._localNodes(), this.nodeStore.nodes()) || !deepEqual(this._localEdges(), this.nodeStore.edges()))`

### 1.4 Implement `validationErrors` computed signal

- [x] `validationErrors = computed(() => { const cycle = detectCycles(...); const req = validateRequiredFields(...); return [...cycle, ...req]; })`
- [x] `isValid = computed(() => this.validationErrors().length === 0)`

### 1.5 Implement `initFromBackend(config: DagConfigResponse)`

- [x] Sets `_localNodes.set(structuredClone(config.nodes))`
- [x] Sets `_localEdges.set(structuredClone(config.edges))`
- [x] Sets `_baseVersion.set(config.config_version)`
- [x] Calls `this.nodeStore.setState({ nodes: config.nodes, edges: config.edges })`

### 1.6 Implement local mutation methods

- [x] `addNode(node: Partial<NodeConfig>)`:
  - Assign temp ID `__new__${Date.now()}` if no `id` provided
  - Push to `_localNodes`
- [x] `updateNode(id: string, patch: Partial<NodeConfig>)`:
  - Immutable update: `_localNodes.update(nodes => nodes.map(n => n.id === id ? {...n, ...patch} : n))`
- [x] `deleteNode(id: string)`:
  - Remove from `_localNodes`
  - Cascade: remove from `_localEdges` where `source_node === id || target_node === id`
- [x] `addEdge(edge: Edge)`:
  - Duplicate check: abort if edge with same `source_node + source_port + target_node` exists
  - Assign `id: '__edge__' + Date.now()` if no ID
  - Push to `_localEdges`
- [x] `deleteEdge(id: string)`:
  - `_localEdges.update(edges => edges.filter(e => e.id !== id))`
- [x] `moveNode(id: string, x: number, y: number)`:
  - `updateNode(id, { x, y })`

### 1.7 Implement `saveAndReload()`

- [x] Guard: if `!isDirty()` return
- [x] Guard: if `!isValid()` — show `ToastService.danger('Fix validation errors before saving.')` with first error; return
- [x] `_isSaving.set(true)`
- [x] Call `dagApi.saveDagConfig({ base_version: _baseVersion(), nodes: _localNodes(), edges: _localEdges() })`
- [x] **On 200 success:**
  - Apply `node_id_map`: remap any `__new__*` IDs in `_localNodes` and `_localEdges`
  - `_baseVersion.set(response.config_version)`
  - `nodeStore.setState({ nodes: _localNodes(), edges: _localEdges() })`
  - `toast.success('DAG saved and reloading…')`
- [x] **On 409 error:**
  - Emit on `conflictDetected$` Subject (a `Subject<string>` for the error message detail)
- [x] **On other HTTP error:**
  - `toast.danger('Save failed: ' + errorMessage)`
- [x] **Finally:** `_isSaving.set(false)`

### 1.8 Implement `syncFromBackend(skipConfirm = false)`

> Renamed from `cancelAndRevert()`. Now prompts only when dirty (and `skipConfirm` is false).

- [x] If `isDirty()` and `!skipConfirm`:
  - Prompt via `DialogService.confirm('You have unsaved changes. Syncing will discard them and load the latest backend configuration. Continue?')`
  - If dismissed → return without action
- [x] If not dirty OR `skipConfirm === true` OR confirm was accepted:
  - `_isSyncing.set(true)`
  - Call `dagApi.getDagConfig()`
  - Call `initFromBackend(response)`
  - `toast.success('Synced with backend.')`
  - `_isSyncing.set(false)`

### 1.9 Implement `reloadRuntime()`

> **NEW method.** Calls `POST /api/v1/nodes/reload` only. Does NOT alter `localNodes`, `localEdges`, `baseVersion`, or
> `isDirty` in any way.

- [x] `_isReloading.set(true)`
- [x] Call the existing `nodesApiService.reload()` (or equivalent `POST /api/v1/nodes/reload`)
- [x] **On success:** `toast.success('DAG runtime reloaded successfully.')`
- [x] **On error:** `toast.danger('Reload failed: ' + errorMessage)`
- [x] **Finally:** `_isReloading.set(false)`
- [x] **CRITICAL assertion:** Verify `_localNodes`, `_localEdges`, `_baseVersion`, and `isDirty` are not mutated by
  this method under any code path — including error paths. Add a unit test assertion to enforce this.

### 1.10 Expose `conflictDetected$`

- [x] `readonly conflictDetected$ = new Subject<string>()`
- [x] Make it public so `SettingsComponent` can subscribe

---

## Phase 2 — Refactor `FlowCanvasComponent`

> **CRITICAL:** Phase -1 must be complete before starting Phase 2. The deleted symbols have already been removed;
> this phase replaces them with the new `CanvasEditStoreService`-based equivalents.

### 2.1 Inject `CanvasEditStoreService`

- [x] Add `private canvasEditStore = inject(CanvasEditStoreService);` to `FlowCanvasComponent`
- [x] `NodesApiService` injection is kept (still used for `setNodeVisible`, `setNodeEnabled`)

### 2.2 Drive `canvasNodes` from local state

- [x] Change the `effect()` that calls `mergeCanvasNodes(nodes)` to read from `canvasEditStore.localNodes()` instead
  of `nodeStore.nodes()`
- [x] Change the `effect()` that calls `updateConnections()` to read from `canvasEditStore.localEdges()` instead of
  `nodeStore.edges()`

### 2.3 Replace `onPortDrop()` (edge creation)

> Phase -1 deleted the old API-calling body. Now wire the replacement.

- [x] **Add** call to `this.canvasEditStore.addEdge({ source_node: sourceId, source_port: pending.fromPortId, target_node: targetId, target_port: 'in' })`
- [x] Keep the duplicate-edge check (it now checks `canvasEditStore.localEdges()`)
- [x] The operation is now synchronous; remove any `async` / `try/catch` around it

### 2.4 Replace `onDeleteEdge()`

> Phase -1 deleted the API call. Now wire the replacement.

- [x] **Add** `this.canvasEditStore.deleteEdge(edgeId)` (keep `dialog.confirm` before deleting)

### 2.5 Replace `onDeleteNode()`

> Phase -1 deleted the API call and direct nodeStore mutations. Now wire the replacement.

- [x] **Add** `this.canvasEditStore.deleteNode(node.id)` (cascade handled inside the store; keep `dialog.confirm`)

### 2.6 Replace drag-end position save

> Phase -1 deleted `unsavedPositions`, `saveAllPositions()`, and the dirty output/signal. Now wire the replacement.

- [x] In `onCanvasMouseUp()`, when `dropped` is truthy: call
  `this.canvasEditStore.moveNode(dropped.nodeId, dropped.position.x, dropped.position.y)`

### 2.7 Replace `createNodeAtPosition()` new-node flow

- [x] The node creation currently opens the drawer, then `NodeEditorFacadeService.saveNode()` calls the API
- [x] Change to: after drawer saves (see Phase 3), the data flows into `canvasEditStore.addNode()` instead of API

### 2.8 Fix `onToggleNodeEnabled()` post-toggle refresh

> Phase -1 deleted the `loadGraphData()` call inside `onToggleNodeEnabled()`. Replace with a targeted update.

- [x] After `await this.nodesApi.setNodeEnabled(node.id, enabled)` succeeds, call
  `this.canvasEditStore.updateNode(node.id, { enabled })` to keep `localNodes` in sync without a full backend fetch
- [x] Confirm `isDirty()` is NOT set to `true` by this live-action update (it is a pass-through, not a local edit)

---

## Phase 3 — Refactor `NodeEditorFacadeService`

### 3.1 Change `saveNode()` to stage locally

- [x] Inject `CanvasEditStoreService`
- [x] Keep async LIDAR profile validation (`validateSensorConfig`) — this still runs
- [x] **Remove** `await this.nodesApi.upsertNode(nodePayload)` call
- [x] **Remove** `Promise.all([nodesApi.getNodes(), edgesApi.getEdges()])` refresh
- [x] **Replace** with:
  - If `existingNode.id` exists and is not a temp ID → `canvasEditStore.updateNode(existingNode.id, nodePayload)`
  - If new node → `canvasEditStore.addNode(nodePayload)`
- [x] Change return type from `Promise<boolean>` to `boolean` (sync after removing await)
- [x] Keep `toast.success('Node staged for save.')` (change copy from "saved" to "staged")

---

## Phase 4 — `SettingsComponent` Action Toolbar & Handlers

### 4.1 Provide `CanvasEditStoreService` in `SettingsComponent`

- [x] Add `providers: [CanvasEditStoreService]` to the `@Component` decorator
- [x] Inject: `protected canvasEditStore = inject(CanvasEditStoreService);`

### 4.2 Refactor initial load to use `GET /api/v1/dag/config`

> Phase -1 deleted `loadConfig()`. Implement the replacement.

- [x] In `ngOnInit()`, replace the deleted `loadConfig()` call with:
  - Call `dagApi.getDagConfig()`
  - Call `canvasEditStore.initFromBackend(response)` with the result
  - Handle loading/error state as before

### 4.3 Add action handlers

- [x] `onSaveAndReload()` → calls `canvasEditStore.saveAndReload()`
- [x] `onSync()` → calls `canvasEditStore.syncFromBackend()` (handles dirty-confirm internally)
- [x] `onReloadRuntime()` → calls `canvasEditStore.reloadRuntime()` (NEW handler — runtime-only, no state change)
- [x] Update `onConfirmImport()` to call `this.onSync()` (replacing the deleted `this.onReloadConfig()` call) so
  that after a config import, the canvas is refreshed from the backend

### 4.4 Add `beforeunload` guard

- [x] Add to `SettingsComponent`:
  ```typescript
  @HostListener('window:beforeunload', ['$event'])
  onBeforeUnload(event: BeforeUnloadEvent) {
    if (this.canvasEditStore.isDirty()) {
      event.preventDefault();
    }
  }
  ```

### 4.5 Subscribe to conflict events

- [x] In `ngOnInit()` (or constructor `effect()`), subscribe to `canvasEditStore.conflictDetected$`:
  ```typescript
  this.canvasEditStore.conflictDetected$.pipe(takeUntilDestroyed()).subscribe(detail => {
    this.dialog.confirm({
      title: 'DAG Conflict Detected',
      message: `Another save has occurred. Your unsaved changes are preserved but cannot be saved.
                Click "Sync & Discard" to load the latest configuration.`,
      confirmLabel: 'Sync & Discard My Changes',
      cancelLabel: 'Stay & Keep Editing',
      variant: 'neutral'
    }).then(confirmed => {
      if (confirmed) this.canvasEditStore.syncFromBackend(true); // skipConfirm=true
    });
  });
  ```

### 4.6 Add dirty indicator title effect

- [x] Add an `effect()`:
  ```typescript
  effect(() => {
    const dirty = this.canvasEditStore.isDirty();
    this.navService.setPageConfig({
      title: dirty ? 'Settings ●' : 'Settings',
      subtitle: 'Configure LiDAR sensors, fusion nodes, and recording settings',
      showActionsSlot: false,
    });
  });
  ```

---

## Phase 5 — Template Updates

### 5.1 Update `settings.component.html`

> Phase -1 deleted the old single "Save & Reload" button and the `(hasUnsavedChangesChange)` binding.
> Now add the full 3-button toolbar in their place.

- [x] Add the 3-button toolbar (dirty-state indicator + Reload + Sync + Save & Reload) above the flow canvas:
  ```html
  <div class="flex items-center justify-between mb-2 shrink-0">
    @if (canvasEditStore.isDirty()) {
      <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-md border
                  border-syn-color-warning-300 bg-syn-color-warning-50">
        <span class="text-syn-color-warning-600 text-base leading-none">●</span>
        <span class="text-xs font-semibold text-syn-color-warning-700">Unsaved changes</span>
      </div>
    } @else {
      <div></div>
    }

    <div class="flex items-center gap-2">
      <!-- Reload: restarts backend runtime only, never touches local state -->
      <syn-button
        size="small"
        variant="text"
        [disabled]="canvasEditStore.isReloading()"
        (click)="onReloadRuntime()"
      >
        @if (canvasEditStore.isReloading()) {
          <syn-spinner slot="prefix" />
          Reloading…
        } @else {
          Reload
        }
      </syn-button>

      <!-- Sync: pull latest backend config, prompt if dirty -->
      <syn-button
        size="small"
        variant="outline"
        [disabled]="canvasEditStore.isSyncing()"
        (click)="onSync()"
      >
        @if (canvasEditStore.isSyncing()) {
          <syn-spinner slot="prefix" />
          Syncing…
        } @else {
          Sync
        }
      </syn-button>

      <!-- Save & Reload: persist local edits + reload backend -->
      <syn-button
        size="small"
        variant="filled"
        [disabled]="!canvasEditStore.isDirty() || canvasEditStore.isSaving() || !canvasEditStore.isValid()"
        (click)="onSaveAndReload()"
      >
        @if (canvasEditStore.isSaving()) {
          <syn-spinner slot="prefix" />
          Saving…
        } @else {
          Save &amp; Reload
        }
      </syn-button>
    </div>
  </div>
  ```
- [x] Confirm the `<app-flow-canvas>` binding has **no** `(hasUnsavedChangesChange)` attribute (deleted in Phase -1)
- [x] Confirm there is **no** `Cancel` or `Revert` button anywhere in this template

---

## Phase 6 — Navigation Guard

### 6.1 Create the guard

- [x] Create `web/src/app/core/guards/unsaved-changes.guard.ts`:
  ```typescript
  import { inject } from '@angular/core';
  import { CanDeactivateFn } from '@angular/router';
  import { CanvasEditStoreService } from '@features/settings/services/canvas-edit-store.service';
  import { DialogService } from '@core/services/dialog.service';

  export const unsavedChangesGuard: CanDeactivateFn<unknown> = async () => {
    const store = inject(CanvasEditStoreService);
    if (!store.isDirty()) return true;
    const dialog = inject(DialogService);
    return dialog.confirm({
      title: 'Unsaved Changes',
      message: 'You have unsaved changes on the canvas. Leaving will discard them.',
      confirmLabel: 'Leave & Discard',
      cancelLabel: 'Stay',
      variant: 'danger'
    });
  };
  ```

### 6.2 Register in `app.routes.ts`

- [x] Open `web/src/app/app.routes.ts`
- [x] Import `unsavedChangesGuard`
- [x] Add `canDeactivate: [unsavedChangesGuard]` to the `settings` route:
  ```typescript
  {
    path: 'settings',
    canDeactivate: [unsavedChangesGuard],
    loadComponent: () => import('./features/settings/settings.component').then(m => m.SettingsComponent),
  }
  ```

---

## Phase 7 — Cleanup & Polish

### 7.1 Validation error display

- [ ] In `flow-canvas.component.html` or a new `canvas-errors.component.ts`, display
  `canvasEditStore.validationErrors()` as a dismissible inline alert below the canvas toolbar
- [ ] Only show errors when `isDirty()` AND `!isValid()`

### 7.2 Loading state of `FlowCanvasComponent`

- [x] Confirm `loadGraphData()` call is removed from `FlowCanvasComponent.ngOnInit()` (done in Phase -1) — initial
  data is now loaded in `SettingsComponent` via `CanvasEditStoreService.initFromBackend()`
- [x] Keep `statusWs.connect()` call in `ngOnInit()`

### 7.3 Export update

- [x] Update `web/src/app/core/services/stores/index.ts` — no new exports needed from stores (service is
  feature-scoped)

### 7.4 Final dead-code scan

- [x] Run: `rg -n "hasUnsavedChanges|saveAllPositions|onReloadConfig|cancelAndRevert|isReverting|loadGraphData|unsavedPositions" web/src/app/features/settings/` — expect **zero** matches
- [x] Run: `rg -n "Cancel|Revert" web/src/app/features/settings/settings.component.html` — expect **zero** matches
  (the word "Cancel" in `onCancelImport` is acceptable in `.ts`; the template must have no Canvas-related Cancel button)
- [x] Confirm toolbar has exactly **3 buttons** in the canvas toolbar area: `Reload`, `Sync`, `Save & Reload`

---

## Dependency Notes

- **Phase -1 must complete before Phase 0–7** — dead code must be gone before new code is written
- **Phase 0 must complete before Phase 1–3** (service/model scaffolding first)
- **Phase 1 (CanvasEditStoreService) must complete before Phase 2–4** (all consumers depend on it)
- **Phase 2 and Phase 3 can proceed in parallel** after Phase 1 is done
- **Phase 4 depends on Phase 1 and 2**
- **Frontend mocks** (Phase 0.2) allow Phase 1–6 to be developed and tested before backend is ready
- **Phase 6 (guard) can be done independently** at any point after Phase 0
- **`reloadRuntime()`** (Phase 1.9) depends only on the existing `NodesApiService` — no backend work needed

## Testing Notes (unit)

- `CanvasEditStoreService` should have unit tests for:
  - `isDirty()` correctly reflects node/edge differences
  - `deleteNode()` cascades to edges
  - `addEdge()` prevents duplicates
  - `saveAndReload()` calls `DagApiService.saveDagConfig()` with correct payload
  - `saveAndReload()` handles 409 by emitting on `conflictDetected$`
  - `syncFromBackend()` calls `DagApiService.getDagConfig()` and resets state
  - `syncFromBackend()` prompts when dirty and skips prompt when clean (or `skipConfirm=true`)
  - **`reloadRuntime()` does NOT mutate `_localNodes`, `_localEdges`, `_baseVersion`, or `isDirty`**
  - **`reloadRuntime()` calls `POST /nodes/reload`** (via existing service) exactly once
  - **`reloadRuntime()` sets `isReloading()` true during call and false after** (both success and error)
- `dag-validator.ts` should have pure unit tests for cycle detection and required field validation
- `unsavedChangesGuard` should have a unit test: returns `true` when clean, shows dialog when dirty
