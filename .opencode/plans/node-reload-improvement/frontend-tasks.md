# Node Reload Improvement — Frontend Tasks

> **Reference documents**:
> - Requirements: `.opencode/plans/node-reload-improvement/requirements.md`
> - Technical blueprint: `.opencode/plans/node-reload-improvement/technical.md`
> - API contracts: `.opencode/plans/node-reload-improvement/api-spec.md`

> **CLI constraint**: Use Angular CLI for all component/service scaffolding (`cd web && ng g ...`).
> **Mock mode**: All API work must use mock data from `api-spec.md` until the backend is ready. Do NOT block on backend completion.

---

## Phase 1: Model and Type Updates

### 1.1 Update DAG models
- [ ] Update `web/src/app/core/models/dag.model.ts`:
  - [ ] Add `reload_mode: 'selective' | 'full' | 'none'` to `DagConfigSaveResponse` interface
  - [ ] Add `reloaded_node_ids: string[]` to `DagConfigSaveResponse` interface
  - [ ] Verify existing `DagConfigSaveRequest` is unchanged (it is)

### 1.2 Update status models
- [ ] Update (or create) `web/src/app/core/models/status.model.ts`:
  - [ ] Add `ReloadEvent` interface with fields: `node_id: string | null`, `status: 'reloading' | 'ready' | 'error'`, `error_message: string | null`, `reload_mode: 'selective' | 'full'`, `timestamp: number`
  - [ ] Add optional `reload_event?: ReloadEvent` to `SystemStatusBroadcast` interface
  - [ ] Re-export `ReloadEvent` from `web/src/app/core/models/index.ts`

---

## Phase 2: API Service Updates

### 2.1 `DagApiService` — mock mode for new response fields
- [ ] Update `web/src/app/core/services/api/dag-api.service.ts`:
  - [ ] Update `MOCK_SAVE_RESPONSE` constant to include `reload_mode: 'selective'` and `reloaded_node_ids: ['mock-node-001']`
  - [ ] The actual API call (`http.put`) needs no changes — new response fields are additive

### 2.2 Create `NodeReloadApiService` — new service for manual reload endpoint
- [ ] Generate: `cd web && ng g service core/services/api/node-reload-api`
- [ ] Implement `reloadNode(nodeId: string): Promise<NodeReloadResponse>`:
  - Calls `POST /api/v1/nodes/{nodeId}/reload`
  - Mock mode: returns `MOCK_NODE_RELOAD_RESPONSE` from `api-spec.md` after 150ms delay
- [ ] Implement `getReloadStatus(): Promise<ReloadStatusResponse>`:
  - Calls `GET /api/v1/nodes/reload/status`
  - Mock mode: returns `{ locked: false, reload_in_progress: false, ... }`
- [ ] Add new models `NodeReloadResponse` and `ReloadStatusResponse` to `status.model.ts`

---

## Phase 3: SystemStatusService — Reload Event Handling

### 3.1 Parse `reload_event` from incoming `system_status` broadcasts
- [x] Update `web/src/app/core/services/system-status.service.ts`:
  - [x] Add private signal: `private _reloadingNodeIds = signal<Set<string>>(new Set())`
  - [x] Add private signal: `private _lastReloadEvent = signal<ReloadEvent | null>(null)`
  - [x] Expose as readonly: `readonly reloadingNodeIds = this._reloadingNodeIds.asReadonly()`
  - [x] Expose as readonly: `readonly lastReloadEvent = this._lastReloadEvent.asReadonly()`
  - [x] In the WebSocket message handler (`onmessage` / Observable subscription), add:
    ```typescript
    if (broadcast.reload_event) {
      this._lastReloadEvent.set(broadcast.reload_event);
      const event = broadcast.reload_event;
      if (event.node_id && event.status === 'reloading') {
        this._reloadingNodeIds.update(ids => new Set([...ids, event.node_id!]));
      } else if (event.node_id && (event.status === 'ready' || event.status === 'error')) {
        this._reloadingNodeIds.update(ids => {
          const next = new Set(ids);
          next.delete(event.node_id!);
          return next;
        });
      } else if (!event.node_id) {
        // Full reload — clear all reload indicators
        this._reloadingNodeIds.set(new Set());
      }
    }
    ```
  - [x] Clear `_reloadingNodeIds` on WebSocket disconnect / reconnect events

### 3.2 Add mock replay in dev mode
- [x] Add a `triggerMockReloadSequence(nodeId: string): void` method (dev/test only, guarded by `!environment.production`)
  - Uses `setTimeout` to simulate reloading → ready sequence from `api-spec.md` mock data

---

## Phase 4: `CanvasEditStoreService` — Debounce and Reload Feedback

### 4.1 Add 150ms debounce to `saveAndReload()`
- [x] Update `web/src/app/features/settings/services/canvas-edit-store.service.ts`:
  - [x] Add private field: `private _saveDebounceTimer: ReturnType<typeof setTimeout> | null = null`
  - [x] Wrap the `saveAndReload()` implementation in a 150ms debounce:
  - [x] Ensure `_saveDebounceTimer` is cleared in `ngOnDestroy` or service cleanup

### 4.2 Update 409 handling for reload-in-progress vs version conflict
- [x] In `_executeSaveAndReload()` error handling:

### 4.3 Show appropriate success toast based on `reload_mode`
- [x] Update the success path in `_executeSaveAndReload()`

---

## Phase 5: Node Reload Visual Indicator

### 5.1 Update `FlowCanvasNodeComponent` to accept reload state
- [x] Locate `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.ts`
- [x] Add signal input: `readonly isReloading = input<boolean>(false)`
- [x] In the component template, apply conditional Tailwind classes when `isReloading()` is true:
  - Apply `animate-pulse` and `opacity-70` on the node card container element
  - Add a small spinner badge: use a Synergy UI spinner or a Tailwind CSS `animate-spin` element
  - **Do NOT** change node size, position, or port connector locations (would break edge rendering)
  - **Do NOT** use `ngIf` / `@if` to show/hide the entire node card (would cause DOM re-flow)
- [x] Add an accessible label: `aria-label="Node is reloading"` on the spinner element

### 5.2 Pass reload state from `FlowCanvasComponent` to each node
- [x] Update `web/src/app/features/settings/components/flow-canvas/flow-canvas.component.ts`:
  - [x] Inject `SystemStatusService`
  - [x] Read `systemStatus.reloadingNodeIds` signal
  - [x] Add computed signal: `reloadingNodeIdsSet = this.systemStatus.reloadingNodeIds`
  - [x] Pass `[isReloading]="reloadingNodeIdsSet().has(canvasNode.data.id)"` to each `<app-flow-canvas-node>`
- [x] Do NOT trigger `@for` track change or node re-render for non-reloading nodes — only the specific node's input signal changes

### 5.3 Visual design specification
- **Reloading state**: `animate-pulse opacity-70` on node card + small spinner icon (top-right corner of node badge)
- **Spinner**: `<div class="animate-spin h-3 w-3 border border-t-transparent border-current rounded-full"></div>` (Tailwind only, no custom CSS)
- **Ready state** (reload complete): Remove classes, brief 200ms transition via `transition-opacity duration-200`
- **Error state** (`reload_event.status === 'error'`): Red border `ring-2 ring-red-500` for 3 seconds then auto-remove
- **Full reload** (`node_id === null`): No per-node indicator — the existing full-DAG reload UX handles this

---

## Phase 6: Settings Component Updates

### 6.1 Display reload mode in toolbar or feedback area
- [x] Update `web/src/app/features/settings/settings.component.ts`:
  - [x] Inject `SystemStatusService`
  - [x] Add computed signal that reads `lastReloadEvent` and derives a status text
  - [x] In the template: show a subtle status line below the Save button when reload is in progress, e.g.:
    - "Reloading node…" (selective)
    - "Reloading DAG…" (full)
    - Disappears when `ready` event arrives

### 6.2 Disable Save button during reload
- [x] In `settings.component.html`, bind the Save button disabled state:
  ```html
  [disabled]="canvasEditStore.isSaving() || systemStatus.reloadingNodeIds().size > 0"
  ```

---

## Phase 7: Unit Tests

### 7.1 Tests for model additions
- [ ] Add type-check tests (or update existing) in `web/src/app/core/models/` ensuring:
  - `DagConfigSaveResponse` accepts `reload_mode` and `reloaded_node_ids`
  - `SystemStatusBroadcast` accepts optional `reload_event`

### 7.2 Tests for `SystemStatusService` reload signal
- [ ] Create or update `system-status.service.spec.ts`:
  - [ ] `should add node_id to reloadingNodeIds on reloading event`
  - [ ] `should remove node_id from reloadingNodeIds on ready event`
  - [ ] `should remove node_id from reloadingNodeIds on error event`
  - [ ] `should clear all reloadingNodeIds on full reload event (node_id null)`

### 7.3 Tests for `CanvasEditStoreService` debounce
- [ ] Update `canvas-edit-store.service.spec.ts`:
  - [ ] `should debounce rapid consecutive saveAndReload calls (only one HTTP request)` — use `fakeAsync` + `tick(150)`
  - [ ] `should show "reload in progress" warning toast on 409 lock conflict`
  - [ ] `should show correct toast message for selective vs full reload_mode`

### 7.4 Tests for `FlowCanvasNodeComponent` reload indicator
- [ ] Update or create `flow-canvas-node.component.spec.ts`:
  - [ ] `should show animate-pulse class when isReloading input is true`
  - [ ] `should not show animate-pulse class when isReloading input is false`
  - [ ] `should render spinner element when isReloading is true`
  - [ ] `should apply error ring class on error reload event` (via simulated signal)

---

## Phase 8: Lint and Build Verification

- [ ] Run `cd web && ng lint` — zero new warnings or errors
- [ ] Run `cd web && ng build` — zero compilation errors
- [ ] Verify Angular strict template mode is satisfied (no `any` types, no implicit undefined)
- [ ] Check bundle size delta — `reload_event` parsing should add <1KB

---

## Dependencies & Order of Operations

```
Phase 1 (Models) → must complete first (all other phases depend on types)
Phase 2 (API Service) → depends on Phase 1
Phase 3 (SystemStatusService) → depends on Phase 1; can run parallel with Phase 2
Phase 4 (CanvasEditStore) → depends on Phase 2; can run parallel with Phase 3
Phase 5 (Visual Indicator) → depends on Phase 3
Phase 6 (Settings Component) → depends on Phase 3 and Phase 4
Phase 7 (Tests) — TDD: write failing tests before implementation
Phase 8 (Lint/Build) — last step before PR
```

## Blocked Tasks

- End-to-end reload indicator testing requires the backend selective reload endpoint (`POST /nodes/{id}/reload`) to be live. Use the mock mode in `NodeReloadApiService` and `SystemStatusService.triggerMockReloadSequence()` for development and unit testing.
- Do NOT change the WebSocket connection management in `MultiWebsocketService` — it already handles `1001` close frames correctly per `protocols.md`.
