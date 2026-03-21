# Canvas Local Edit & Explicit Save — Technical Architecture

**Feature:** `canvas-local-edit`  
**Architect:** @architecture  
**Status:** Planning (Revised)  
**Date:** 2026-03-21  
**Revision:** v2 — Added standalone `Reload` action (runtime-only), renamed `Cancel` → `Sync` (pull backend config)

---

## 1. Overview & Design Rationale

The current canvas (`FlowCanvasComponent`) issues live backend API calls on every node drag, edge create, edge delete,
and node config save. This feature transforms that into a **local-edit-first** model: all mutations accumulate in
frontend signals, and a single `PUT /api/v1/dag/config` flush is the only backend contact during editing.

### Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Local state container | New `CanvasEditStoreService` (Signal store) | Keeps dirty-state isolated from `NodeStoreService` which is shared by other pages |
| DAG version field | `config_version` integer (monotonic increment) on backend | Simple, SQLite-friendly; no UUID-clock drift issues |
| Conflict detection | Optimistic lock: backend rejects 409 if stored version ≠ client base version | Per requirements; avoids distributed locks |
| Save payload | Full DAG snapshot (`nodes[]` + `edges[]` + `base_version`) | Atomic replace; no partial-update complexity |
| Reload trigger | Backend emits `reload_config()` inside the `PUT` handler | Reuses existing `NodeManager.reload_config()` |
| Navigation guard | Angular `CanDeactivateFn` + `beforeunload` event | Standard Angular pattern; no extra library |
| Frontend validation | Pure TS DFS cycle detector + required-field check | Zero network round trips; fast enough for <50 nodes |
| Top-bar action slot | `NavigationService.showActionsSlot` already exists; `<ng-content select="[meta-nav]">` in `HeaderComponent` | Avoids creating a new layout slot |
| **Reload button semantics** | Calls existing `POST /api/v1/nodes/reload`; does NOT alter frontend state | Restart runtime independently from local edit state |
| **Sync button semantics** | Calls `GET /api/v1/dag/config`; replaces local state after confirm-if-dirty | Replaces the old "Cancel/Revert" with an always-available control |

---

## 2. Backend Architecture

### 2.1 New Endpoint: `PUT /api/v1/dag/config`

This is the **only new backend endpoint**. It replaces all granular node/edge mutations for the save path.

```
PUT /api/v1/dag/config
```

**Request body** (`DagConfigSaveRequest` Pydantic model):
```json
{
  "base_version": 7,
  "nodes": [ { ...NodeRecord... }, ... ],
  "edges": [ { ...EdgeRecord... }, ... ]
}
```

**Processing pipeline (must be atomic):**
1. Acquire `_reload_lock` (already exists on `NodeManager` — reuse it to prevent concurrent saves/reloads)
2. Read `dag_config_version` from the single-row `dag_meta` table (new table — see §2.3)
3. If `current_version != base_version` → raise `HTTPException(409, ...)`
4. Within a single SQLAlchemy session transaction:
   a. Delete all existing edges via `EdgeRepository.save_all([])`
   b. Upsert all nodes via `NodeRepository.upsert()` loop; collect `{old_id → new_id}` map for client-generated IDs
   c. Save all edges via `EdgeRepository.save_all(edges)`
   d. Increment `dag_config_version` by 1
5. Call `await node_manager.reload_config()` (existing method) outside the DB transaction
6. Return `200` with new version + any node ID remapping

**GET companion** (also new, used for initial load and Sync):

```
GET /api/v1/dag/config
```

Returns current `nodes[]`, `edges[]`, and `config_version` integer.

### 2.2 Existing Endpoint: `POST /api/v1/nodes/reload` (Reload button)

The standalone **Reload** button calls the **already-existing** `POST /api/v1/nodes/reload` endpoint. No new endpoint
is required for the Reload action. This is a runtime-restart-only call and does not involve the DAG config version or
any DB changes. The frontend does not modify its local state based on this call's response.

### 2.3 `DagMeta` Table

A minimal single-row table to hold the monotonic version counter.

```python
# app/db/models.py  — add below EdgeModel
class DagMetaModel(Base):
    __tablename__ = "dag_meta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    config_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

`ensure_schema()` in `migrate.py` must:
1. `Base.metadata.create_all()` to create the table
2. Insert the seed row `(id=1, config_version=0)` if it doesn't exist (`INSERT OR IGNORE`)

### 2.4 Version Bump Strategy

Every successful `PUT /api/v1/dag/config` increments `config_version` by 1 (in the same DB transaction as node/edge
writes). The `GET /api/v1/dag/config` response always returns the current version. This is a **monotonic integer
optimistic lock** — simple, no clock skew.

**Note:** The `POST /api/v1/nodes/reload` (Reload button) does NOT touch `config_version`. It is a runtime-only
restart.

### 2.5 Pydantic Schemas

Add to `app/api/v1/schemas/`:

```python
# app/api/v1/schemas/dag.py  (NEW FILE)
class DagConfigResponse(BaseModel):
    config_version: int
    nodes: List[NodeRecord]
    edges: List[EdgeRecord]

class DagConfigSaveRequest(BaseModel):
    base_version: int
    nodes: List[NodeRecord]
    edges: List[EdgeRecord]

class DagConfigSaveResponse(BaseModel):
    config_version: int          # new incremented version
    node_id_map: Dict[str, str]  # {temp_client_id: persisted_id} for new nodes
```

### 2.6 New Handler File

```
app/api/v1/dag/
  __init__.py
  handler.py  ← GET /api/v1/dag/config, PUT /api/v1/dag/config
  service.py  ← get_dag_config(), save_dag_config()
```

Register in `app/app.py` with the existing `v1_router`.

### 2.7 Concurrency Safety

The `_reload_lock` acquired at step 1 of the PUT handler prevents:
- Two simultaneous PUT saves racing
- PUT racing with an in-progress `POST /nodes/reload`

The 409 optimistic lock prevents:
- Two users saving diverged edits without awareness

### 2.8 Existing Endpoints Stay Unchanged

`POST /nodes`, `DELETE /nodes/{id}`, `POST /edges`, `DELETE /edges/{edge_id}`,
and **`POST /nodes/reload`** (Reload button) continue to exist unchanged. Only the **canvas save flow** is routed
through the new `PUT /api/v1/dag/config`.

---

## 3. Frontend Architecture

### 3.1 State Model

Two parallel stores:

```
NodeStoreService (existing, shared)
  └── nodes: Signal<NodeConfig[]>         ← "last saved" server state
  └── edges: Signal<Edge[]>               ← "last saved" server state

CanvasEditStoreService (NEW, feature-scoped)
  └── localNodes: WritableSignal<NodeConfig[]>   ← local edits
  └── localEdges: WritableSignal<Edge[]>          ← local edits
  └── baseVersion: WritableSignal<number>         ← version at last fetch/save
  └── isDirty: Signal<boolean>                    ← computed
  └── validationErrors: Signal<ValidationError[]> ← computed
  └── isSaving: WritableSignal<boolean>
  └── isSyncing: WritableSignal<boolean>          ← (renamed from isReverting)
  └── isReloading: WritableSignal<boolean>        ← NEW: tracks POST /nodes/reload in flight
```

`isDirty` is a `computed()` signal:
```typescript
isDirty = computed(() =>
  !deepEqual(this.localNodes(), this.nodeStore.nodes()) ||
  !deepEqual(this.localEdges(), this.nodeStore.edges())
);
```

**Invariant:** `NodeStoreService.nodes/edges` are only mutated from:
1. Initial load (`GET /api/v1/dag/config` at component init)
2. Successful Save (`PUT /api/v1/dag/config` → 200)
3. Sync/Pull (`GET /api/v1/dag/config` → refresh, replaces local state)

During editing, **only** `CanvasEditStoreService.localNodes/localEdges` are mutated.

### 3.2 New Service: `CanvasEditStoreService`

```
web/src/app/features/settings/services/canvas-edit-store.service.ts  (NEW)
```

**Responsibility:** owns local edit state; exposes `saveAndReload()`, `syncFromBackend()`, `reloadRuntime()`,
`validate()`. Provided via `providers: []` on `SettingsComponent` (feature-scoped, not root).

Key methods:

| Method | Behavior |
|---|---|
| `initFromBackend(config)` | Seeds both `localNodes/Edges` and `baseVersion`; resets dirty |
| `addNode(node)` | Pushes to `localNodes`; assigns temp client ID if new |
| `updateNode(id, patch)` | Immutable update in `localNodes` |
| `deleteNode(id)` | Removes from `localNodes`; cascades to `localEdges` |
| `addEdge(edge)` | Pushes to `localEdges` after duplicate check |
| `deleteEdge(id)` | Removes from `localEdges` |
| `moveNode(id, x, y)` | Updates position in `localNodes` |
| `validate()` | Returns `ValidationResult` (cycle check + required fields) |
| `saveAndReload()` | PUT → on 200: sync NodeStore, clear dirty; on 409: show conflict prompt |
| `syncFromBackend()` | Prompts if dirty → GET → re-seed local state, clear dirty |
| `reloadRuntime()` | POST `/nodes/reload` only; **does not touch local state at all** |

### 3.3 Three-Button Toolbar Design

The action toolbar renders three distinct controls:

```
[ Reload ]  [ Sync ]  [ Save & Reload ]
  ↓            ↓           ↓
POST          GET          PUT
/nodes/       /dag/        /dag/
reload        config       config
(no state     (replace     (persist +
 change)       local)       reload)
```

**Enabled/disabled logic:**

| Button | Always Enabled | Disabled When |
|---|---|---|
| **Reload** | ✅ | `isReloading()` is true (in-flight) |
| **Sync** | ✅ | `isSyncing()` is true (in-flight) |
| **Save & Reload** | ❌ | `!isDirty()` OR `isSaving()` OR `!isValid()` |

The dirty-state amber badge is shown independently of button states.

### 3.4 Modifications to `FlowCanvasComponent`

The component currently calls API directly for most edit operations. It must be **refactored** to call
`CanvasEditStoreService` instead:

| Current direct API call | Replacement |
|---|---|
| `edgesApi.createEdge()` in `onPortDrop()` | `canvasEditStore.addEdge()` |
| `edgesApi.deleteEdge()` in `onDeleteEdge()` | `canvasEditStore.deleteEdge()` |
| `nodesApi.upsertNode()` in `NodeEditorFacadeService.saveNode()` | `canvasEditStore.addNode/updateNode()` |
| `nodesApi.deleteNode()` in `onDeleteNode()` | `canvasEditStore.deleteNode()` |
| `nodesApi.upsertNode()` in `saveAllPositions()` | `canvasEditStore.moveNode()` |

After refactor, **no API service calls remain inside `FlowCanvasComponent` except** visibility toggle
(`setNodeVisible`) and enable toggle (`setNodeEnabled`), which are live-action operations exempt from the local-edit
buffer.

The `canvasNodes` signal will be driven from `canvasEditStore.localNodes` instead of `nodeStore.nodes`.

### 3.5 Modifications to `NodeEditorFacadeService`

`saveNode()` currently calls `nodesApi.upsertNode()` + refreshes `nodeStore`. It must instead call
`canvasEditStore.addNode()` or `canvasEditStore.updateNode()` and return synchronously (no `await`). Sensor config
validation (LIDAR profile check) is still async and must still run before staging to local state.

### 3.6 New Top-Bar Action Area: Dirty State Indicator + Buttons

`SettingsComponent` calls `navService.setPageConfig({ ..., showActionsSlot: true })`. The existing
`<div id="page-actions-container">` in `main-layout.component.html` becomes the injection point for a new
`CanvasActionsComponent`.

**Simpler approach** (recommended): render the action bar directly inside `settings.component.html` as a fixed toolbar
row, using `@if (isDirty())` for the dirty indicator. This avoids portal complexity.

Template snippet (inside `settings.component.html`):
```html
<div class="flex items-center justify-between mb-2 shrink-0">
  @if (canvasEditStore.isDirty()) {
    <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-syn-color-warning-300 bg-syn-color-warning-50">
      <span class="text-syn-color-warning-600 text-base leading-none">●</span>
      <span class="text-xs font-semibold text-syn-color-warning-700">Unsaved changes</span>
    </div>
  } @else {
    <div></div>
  }
  <div class="flex items-center gap-2">
    <!-- Reload: runtime-only, never touches local state -->
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

    <!-- Sync: pull backend config, prompt if dirty -->
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

    <!-- Save & Reload: persist local edits then reload backend -->
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

**Page title dirty indicator:** When `isDirty()` is true, `SettingsComponent` updates the title via
`navService.setHeadline('Settings ●')` using an `effect()`.

### 3.7 Frontend Validation Engine

New utility module:

```
web/src/app/features/settings/utils/dag-validator.ts  (NEW)
```

Exported pure functions:
- `detectCycles(nodes, edges): string[]` — DFS topological sort; returns list of cycle descriptions
- `validateRequiredFields(nodes, definitions): ValidationError[]` — checks `PropertySchema.required === true` for all
  nodes
- `validateEdgeTypes(edges, nodes, definitions): ValidationError[]` — optional for v1 (type compatibility)

These are called inside `CanvasEditStoreService.validate()` and as a `computed()` signal on the store.

### 3.8 Navigation Guard

New guard:
```
web/src/app/core/guards/unsaved-changes.guard.ts  (NEW)
```

```typescript
export const unsavedChangesGuard: CanDeactivateFn<any> = async (component) => {
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

Applied to the `settings` route in `app.routes.ts`:
```typescript
{ path: 'settings', canDeactivate: [unsavedChangesGuard], loadComponent: ... }
```

**Browser `beforeunload`** is handled in `SettingsComponent`:
```typescript
@HostListener('window:beforeunload', ['$event'])
onBeforeUnload(event: BeforeUnloadEvent) {
  if (this.canvasEditStore.isDirty()) {
    event.preventDefault();
  }
}
```

### 3.9 Conflict Dialog (409 Handler)

When `saveAndReload()` receives a 409, `CanvasEditStoreService` emits on a conflict Subject.
`SettingsComponent` subscribes and shows a `DialogService.confirm()`:

```
"The DAG was modified by another process. Your unsaved changes are preserved but cannot be saved.
Click 'Sync' to discard your changes and fetch the latest configuration."
[Sync & Discard My Changes]  [Stay & Keep Editing]
```

If user chooses Sync → calls `syncFromBackend()` (bypasses the confirm prompt since we are already in a conflict
context).

### 3.10 New API Service: `DagApiService`

```
web/src/app/core/services/api/dag-api.service.ts  (NEW)
```

```typescript
@Injectable({ providedIn: 'root' })
export class DagApiService {
  async getDagConfig(): Promise<DagConfigResponse>
  async saveDagConfig(req: DagConfigSaveRequest): Promise<DagConfigSaveResponse>
}
```

The **Reload** button uses the **existing** `NodesApiService.reload()` (or equivalent) — no new API method is needed.

`DagConfigResponse`, `DagConfigSaveRequest`, `DagConfigSaveResponse` are TypeScript interfaces mirroring the backend
Pydantic models (see §2.5).

---

## 4. Data Flow Diagrams

### 4.1 Edit Action (No API Calls)

```
User drags node
      │
      ▼
FlowCanvasComponent.onCanvasMouseUp()
      │
      ▼
CanvasEditStoreService.moveNode(id, x, y)   ← mutates localNodes signal only
      │
      ▼
isDirty computed() → true
      │
      ▼
SettingsComponent dirty indicator shown
(No network requests)
```

### 4.2 Save & Reload Happy Path

```
User clicks "Save & Reload"
      │
      ▼
CanvasEditStoreService.validate()
      │ errors? → show error toast, abort
      ▼
isSaving.set(true)
PUT /api/v1/dag/config { base_version, nodes, edges }
      │
      ▼ 200 OK { config_version: N+1, node_id_map }
      │
      ├── Apply node_id_map to localNodes (replace temp IDs)
      ├── NodeStoreService.setState({ nodes: localNodes, edges: localEdges })
      ├── baseVersion.set(N+1)
      ├── isDirty recomputes → false
      └── toast.success("DAG saved and reloading…")
      │
      ▼ Backend: reload_config() runs async
      │  WebSocket topics reset per protocol.md rules
      ▼
isSaving.set(false)
```

### 4.3 Sync (Pull Backend Config → Discard Local Edits)

```
User clicks "Sync"
      │
      ▼
if isDirty():
  DialogService.confirm("You have unsaved changes. Syncing will discard them. Continue?")
  │ dismissed → no-op, local edits preserved
  ▼ confirmed
else:
  proceed immediately (no prompt)
      │
      ▼
isSyncing.set(true)
GET /api/v1/dag/config
      │
      ▼ { config_version, nodes, edges }
      │
      ├── NodeStoreService.setState({ nodes, edges })
      ├── canvasEditStore.initFromBackend(response)
      └── isDirty → false
      │
      ▼
isSyncing.set(false)
toast.success('Synced with backend.')
```

### 4.4 Reload (Runtime Restart Only — No Config Pull, No State Change)

```
User clicks "Reload"
      │
      ▼
isReloading.set(true)
POST /api/v1/nodes/reload
      │
      ▼ 200 OK (or error)
      │
      ├── [success] toast.success("DAG runtime reloaded.")
      └── [error]   toast.danger("Reload failed: " + message)
      │
      ▼
isReloading.set(false)

NOTE: localNodes, localEdges, isDirty, baseVersion — ALL UNCHANGED
```

### 4.5 Conflict (409)

```
PUT /api/v1/dag/config → 409 { detail: "Version conflict..." }
      │
      ▼
isSaving.set(false)
conflictDetected$.next()
      │
      ▼
SettingsComponent shows conflict dialog
      │
      ├── "Sync & Discard" → syncFromBackend(skipConfirm: true)
      └── "Stay"          → no-op (local edits preserved, user can keep editing)
```

---

## 5. Component / File Touch List

### ⚠️ MANDATORY PRE-WORK: Dead Code Deletions (Do This First)

> **These deletions are REQUIRED and non-optional. They MUST be completed before any new code is written.**
> There is no backward compatibility layer, no migration path, no feature flag. Delete the symbols outright.

#### 5.0.1 Delete from `flow-canvas.component.ts`

The following symbols implement the old per-mutation-API-call pattern and the old dirty-tracking via
`unsavedPositions`. They are entirely superseded by `CanvasEditStoreService` and must be **deleted**:

| Symbol / Code | Reason for Deletion |
|---|---|
| `hasUnsavedChangesChange = output<boolean>()` | Replaced by `CanvasEditStoreService.isDirty()` |
| `public hasUnsavedChanges = signal(false)` | Replaced by `CanvasEditStoreService.isDirty()` |
| `private unsavedPositions = new Map<...>()` | Replaced by `CanvasEditStoreService.moveNode()` |
| `async saveAllPositions(): Promise<void>` (entire method) | Replaced by local-edit buffer; no per-drag API call |
| All `this.unsavedPositions.set(...)` / `this.unsavedPositions.clear()` call sites | No longer needed |
| All `this.hasUnsavedChanges.set(...)` / `this.hasUnsavedChangesChange.emit(...)` call sites | No longer needed |
| `await this.edgesApi.createEdge(...)` + `Promise.all([getNodes, getEdges])` + `nodeStore.setState(...)` inside `onPortDrop()` | Replaced by `canvasEditStore.addEdge()` |
| `await this.edgesApi.deleteEdge(...)` + `nodeStore.set('edges', ...)` inside `onDeleteEdge()` | Replaced by `canvasEditStore.deleteEdge()` |
| `await this.nodesApi.deleteNode(...)` + `nodeStore.set('nodes/edges', ...)` inside `onDeleteNode()` | Replaced by `canvasEditStore.deleteNode()` |
| `private async loadGraphData()` (entire method) | Data loading moves to `SettingsComponent` via `CanvasEditStoreService.initFromBackend()` |
| `this.loadGraphData()` call in `ngOnInit()` | Removed with `loadGraphData()` |
| `await this.loadGraphData()` call inside `onToggleNodeEnabled()` | Replaced: after toggle, refresh `localNodes` via `canvasEditStore.updateNode()` for the single field |
| Direct injection of `EdgesApiService` (if only used for deleted operations) | Remove import and inject call |

#### 5.0.2 Delete from `settings.component.ts`

| Symbol / Code | Reason for Deletion |
|---|---|
| `protected hasUnsavedChanges = signal(false)` | Replaced by `canvasEditStore.isDirty()` |
| `async onReloadConfig()` (entire method) | Replaced by `onReloadRuntime()` (runtime-only) + `onSync()` (config pull). The old method combined both concerns incorrectly and called the old `saveAllPositions()` flow. |
| `flowCanvas.hasUnsavedChanges()` and `flowCanvas.saveAllPositions()` call sites | Removed with `onReloadConfig()` |
| `await this.nodesApi.getNodes()` inside `loadConfig()` | `loadConfig()` is replaced entirely by `dagApi.getDagConfig()` + `canvasEditStore.initFromBackend()` |
| `private nodesApi = inject(NodesApiService)` (if not used elsewhere in the component) | Remove injection |
| The `isLoading`/`loadConfig()` orchestration via `nodeStore.set('isLoading', ...)` | Replaced by `CanvasEditStoreService` initialization flow |

#### 5.0.3 Delete from `settings.component.html`

| Template Code | Reason for Deletion |
|---|---|
| `<syn-button (click)="onReloadConfig()" [disabled]="!flowCanvas().hasUnsavedChanges()"...>Save & Reload</syn-button>` (old single-button implementation, lines 31–36) | Replaced by the new 3-button toolbar defined in §3.6 |
| `(hasUnsavedChangesChange)="hasUnsavedChanges.set($event)"` binding on `<app-flow-canvas>` | Output deleted from `FlowCanvasComponent` |

> **Note:** The `(cancel)="onCancelImport()"` binding on `<app-config-import-dialog>` is **NOT** related to the
> canvas edit flow and must be **preserved** — it closes the config import dialog.

#### 5.0.4 Confirm No Orphaned Imports

After the deletions above, verify these are cleaned up if no longer referenced in the relevant files:

- `EdgesApiService` import in `flow-canvas.component.ts` (if `createEdge`/`deleteEdge` were its only uses)
- `NodesApiService` import in `settings.component.ts` (if `getNodes`/`reloadConfig` were its only uses; keep if still
  used for `setNodeEnabled`/`setNodeVisible` delegation)
- `viewChild(FlowCanvasComponent)` in `settings.component.ts` (if no longer needed after `saveAllPositions()` and
  `hasUnsavedChanges()` access are removed)

---

### Backend (New Files)

| File | Change |
|---|---|
| `app/api/v1/dag/__init__.py` | NEW |
| `app/api/v1/dag/handler.py` | NEW — GET + PUT /dag/config |
| `app/api/v1/dag/service.py` | NEW — get_dag_config(), save_dag_config() |
| `app/api/v1/schemas/dag.py` | NEW — DagConfigResponse, DagConfigSaveRequest, DagConfigSaveResponse |
| `app/db/models.py` | ADD DagMetaModel class |
| `app/db/migrate.py` | ADD dag_meta table creation + seed row |
| `app/app.py` | REGISTER dag router |

### Backend (Modified Files)

| File | Change |
|---|---|
| `app/api/v1/schemas/common.py` | ADD `ConflictResponse` Pydantic model |

> `POST /api/v1/nodes/reload` is **unchanged** — already exists for the Reload button.

### Frontend (New Files)

| File | Change |
|---|---|
| `web/src/app/features/settings/services/canvas-edit-store.service.ts` | NEW |
| `web/src/app/core/services/api/dag-api.service.ts` | NEW |
| `web/src/app/features/settings/utils/dag-validator.ts` | NEW |
| `web/src/app/core/guards/unsaved-changes.guard.ts` | NEW |
| `web/src/app/core/models/dag.model.ts` | NEW — TS interfaces for DAG API types |

### Frontend (Modified Files — after deletions in §5.0)

| File | Change |
|---|---|
| `web/src/app/features/settings/components/flow-canvas/flow-canvas.component.ts` | **DELETE** dead symbols (§5.0.1); REFACTOR remaining edit actions to `CanvasEditStoreService` |
| `web/src/app/features/settings/services/node-editor-facade.service.ts` | CHANGE `saveNode()` to stage locally |
| `web/src/app/features/settings/settings.component.ts` | **DELETE** dead symbols (§5.0.2); ADD dirty bar, Save/Sync/Reload handlers, navigation guard |
| `web/src/app/features/settings/settings.component.html` | **DELETE** old toolbar elements (§5.0.3); ADD 3-button action toolbar |
| `web/src/app/core/services/navigation.service.ts` | No change needed (showActionsSlot already exists) |
| `web/src/app/app.routes.ts` | ADD canDeactivate guard to settings route |
| `web/src/app/core/services/api/index.ts` | EXPORT DagApiService |
| `web/src/app/core/services/stores/node-store.service.ts` | ADD `baseVersion` field to NodeState (optional — can live in CanvasEditStoreService) |

---

## 6. Angular Patterns & Constraints

- **Standalone Components exclusively** — no NgModules added
- **Angular Signals** for all state management (`signal()`, `computed()`, `effect()`)
- **RxJS** only for `conflictDetected$` Subject (one-shot event channel) and HTTP calls inside `DagApiService`
- `CanvasEditStoreService` is **feature-scoped** (`providers: [CanvasEditStoreService]` on `SettingsComponent`) so each
  navigation to `/settings` gets a fresh instance
- Deep equality check: use a minimal `deepEqual()` utility (JSON.stringify comparison is acceptable for node graphs of
  <50 nodes; ~0.2ms)
- `FlowCanvasComponent` must be refactored to **only consume** `CanvasEditStoreService.localNodes/localEdges` for
  canvas rendering — not `NodeStoreService.nodes/edges`
- The **Reload** action uses the existing `NodesApiService` (or a direct `HttpClient` call in `DagApiService`). No new
  service method is mandatory — delegate to whatever existing service wraps `POST /api/v1/nodes/reload`.

---

## 7. Performance & Scale Targets

| Metric | Target |
|---|---|
| Dirty indicator latency | < 100ms from any edit action |
| Validation on save (50 nodes) | < 50ms (pure TS, no DOM) |
| `PUT /dag/config` round-trip | < 3s for < 50 nodes |
| Canvas re-render after save | < 200ms (Signal propagation) |
| No API calls during editing | Zero network requests in DevTools during local edits |
| **Reload button round-trip** | < 2s for `POST /nodes/reload` |
| **Sync button round-trip** | < 2s for `GET /dag/config` + canvas re-render |

---

## 8. Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Dead code deletion leaves dangling references** (e.g., template still binds `(hasUnsavedChangesChange)` after output is removed) | HIGH | Deletion is Phase 0 in `frontend-tasks.md`; `tsc --noEmit` must pass before Phase 1 begins |
| `NodeEditorFacadeService.saveNode()` has async LIDAR validation — must still run before staging | MEDIUM | Keep the async validation call; only skip the `nodesApi.upsertNode()` backend call |
| `onPortDrop()` currently awaits `edgesApi.createEdge()` and then refreshes nodes+edges from backend | HIGH | Remove the await-and-refresh pattern (see §5.0.1); all is local now |
| `onDeleteNode()` removes from `nodeStore` directly — must change to local buffer | HIGH | Redirect to `canvasEditStore.deleteNode()` (see §5.0.1) |
| `canvasNodes` signal driven from `nodeStore.nodes()` — will render saved state, not local edits | CRITICAL | Drive `canvasNodes` from `canvasEditStore.localNodes()` |
| `loadGraphData()` deletion: `onToggleNodeEnabled()` currently calls it for refresh | MEDIUM | After delete-then-re-inject, update `onToggleNodeEnabled()` to call `canvasEditStore.updateNode()` for the single toggled field instead |
| Visibility toggle and enable toggle are live-action — must NOT go through local buffer | MEDIUM | Keep `nodesApi.setNodeVisible()` / `setNodeEnabled()` as live calls; apply optimistic update to `localNodes` only for visible/enabled fields |
| Navigation guard: `canDeactivate` with Signal-based service requires Angular 17+ injection context | LOW | Use `inject()` inside the guard function — supported in Angular 20 |
| 409 on save leaves local state intact — user may be confused | MEDIUM | Conflict dialog directs user to "Sync"; no "Cancel" option exists |
| **Reload button pressed while user has unsaved edits** | LOW | By design: Reload does NOT touch local state. The dirty indicator remains visible. No risk of data loss. |
| **Sync accidentally triggers without confirmation** | LOW | `syncFromBackend()` always checks `isDirty()` before skipping prompt; `skipConfirm` flag only used in conflict dialog path. |

---

## 9. Out of Scope (per requirements)

- Undo/redo stack
- Auto-save to localStorage
- Real-time collaborative editing (no CRDT, no operational transforms)
- Incremental / per-node save
- Change diff/preview view
- Conflict merge UI (user must sync and re-apply)
