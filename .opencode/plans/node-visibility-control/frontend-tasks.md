# Frontend Implementation Tasks — Node Visibility Control

**Feature:** `node-visibility-control`  
**Assignee:** @fe-dev  
**References:**
- Requirements: `.opencode/plans/node-visibility-control/requirements.md`
- Technical Spec: `.opencode/plans/node-visibility-control/technical.md`
- API Contract: `.opencode/plans/node-visibility-control/api-spec.md`

---

## Rules Reminder

- All components MUST be Angular 20 **Standalone Components** — no `NgModule`.
- All scaffolding MUST use the Angular CLI: `cd web && ng g component ...`
- State management MUST use **Angular Signals** (`signal()`, `computed()`, `effect()`).
- RxJS is reserved for HTTP streams and WebSocket subscriptions only.
- All API calls MUST go through `core/services/api/` — never inject `HttpClient` in feature components.
- Smart components handle state/API calls. Presentation components use `input()` / `output()` only.
- **Mock all API responses from `api-spec.md`** until backend is ready.

---

## Phase 1 — Core Model & API Service

- [x] **FE-1.1** Update `NodeConfig` interface in `web/src/app/core/models/node.model.ts`
  - Add `visible: boolean` field (required, no default — backend always sends it)
  - Add `visible?: boolean` with `// defaults to true if omitted (legacy compat)` comment to handle older responses gracefully

- [x] **FE-1.2** Update `NodeStatus` interface in `web/src/app/core/models/node.model.ts`
  - Add `visible: boolean` field
  - Update `topic?: string | null` — the type must allow `null` when `visible=false`

- [x] **FE-1.3** Add `setNodeVisible()` method to `NodesApiService` in `web/src/app/core/services/api/nodes-api.service.ts`
  - Signature: `async setNodeVisible(id: string, visible: boolean): Promise<{ status: string }>`
  - Use `firstValueFrom(this.http.put(...))`
  - Target: `PUT ${environment.apiUrl}/nodes/${id}/visible` with body `{ visible }`

- [x] **FE-1.4** Add mock implementation for `setNodeVisible()` (for use while backend is pending)
  - Simulate 150ms delay with `await new Promise(resolve => setTimeout(resolve, 150))`
  - Simulate `400` error for a hardcoded system node ID to test error path
  - Document that mock must be removed once backend is deployed

---

## Phase 2 — State Store

- [x] **FE-2.1** Add `visibleNodes` computed selector to `NodeStoreService` in `web/src/app/core/services/stores/node-store.service.ts`
  - `visibleNodes = computed(() => this.nodes().filter(n => n.visible !== false))`
  - The `!== false` pattern ensures nodes without the field (legacy) are treated as visible

---

## Phase 3 — Presentation Component: `NodeVisibilityToggleComponent`

*This is a dumb/presentation component — no API calls, no store injection.*

- [x] **FE-3.1** Scaffold the component:
  ```bash
  cd web && ng g component features/settings/components/node-visibility-toggle --standalone
  ```

- [x] **FE-3.2** Implement `node-visibility-toggle.component.ts`
  - Input: `node = input.required<NodeConfig>()` (Signal input)
  - Output: `visibilityChanged = output<boolean>()`
  - On button click: emit `!this.node().visible`
  - While a pending toggle is in flight (communicated via an `isPending = input<boolean>(false)` input): disable the button

- [x] **FE-3.3** Implement `node-visibility-toggle.component.html` template
  - Use `syn-icon-button` from `SynergyComponentsModule`
  - Icon name: `'visibility'` when `node().visible !== false`, `'visibility_off'` when hidden
  - `title` attribute: `'Hide node'` / `'Show node'` for accessibility
  - Tailwind classes: full opacity when visible, `opacity-40` when hidden, `opacity-50 cursor-not-allowed` when `isPending`
  - Use `@if` control flow (NOT `*ngIf`)

- [x] **FE-3.4** Export `NodeVisibilityToggleComponent` from the settings components index (if one exists)

---

## Phase 4 — Smart Component Integration (Settings)

*The smart component that owns the node list in `features/settings` handles the API call and optimistic update.*

- [ ] **FE-4.1** Identify the correct parent smart component that renders the node list
  - Likely `features/settings/components/flow-canvas/` or `features/settings/settings.component.ts`
  - Read the component to determine the best integration point

- [ ] **FE-4.2** Inject `NodesApiService` and `NodeStoreService` in the smart component (if not already)

- [ ] **FE-4.3** Implement `toggleNodeVisibility(node: NodeConfig)` handler in the smart component
  - Follow the optimistic-update-with-rollback pattern from `technical.md §7.4`:
    1. Set `isTogglingVisibility.set(true)` — disables the toggle button
    2. Optimistically update `nodeStore.nodes` signal immediately
    3. Call `await nodesApi.setNodeVisible(node.id, newVisible)`
    4. On error: rollback the store to the previous value and show a toast error
    5. Set `isTogglingVisibility.set(false)` in a `finally` block

- [ ] **FE-4.4** Add `isTogglingVisibility = signal<string | null>(null)` to track which node ID is being toggled
  - Using the node ID (not a plain boolean) allows per-node pending state tracking if multiple nodes are in the list

- [ ] **FE-4.5** Wire up `NodeVisibilityToggleComponent` in the node list template
  - Pass `[node]="nodeConfig"` Signal input
  - Pass `[isPending]="isTogglingVisibility() === node.id"` Signal input
  - Handle `(visibilityChanged)="toggleNodeVisibility(node)"` output event
  - Place the toggle button next to the existing enable/disable controls

- [ ] **FE-4.6** Apply dimming CSS to invisible node list rows
  - Wrap each node row in a `<div [class.opacity-50]="node.visible === false" [class.grayscale]="node.visible === false">`
  - Do NOT remove invisible nodes from the list — they must remain visible in settings with the dimmed state (requirement AC-13)

---

## Phase 5 — Workspace Topic Selector (Invisible Node Filtering)

- [ ] **FE-5.1** Verify `WorkspacesComponent.refreshTopics()` handles removed topics correctly
  - When a node is hidden, its topic disappears from `GET /api/v1/topics`
  - The `validSelectedTopics` filter in `refreshTopics()` already removes topics not in the new list
  - **Test manually**: hide a node while its topic is in `selectedTopics`; confirm the topic is removed from the selector and the Three.js scene

- [ ] **FE-5.2** Verify `MultiWebsocketService` handles `code=1001` close correctly
  - The existing `onclose` handler already calls `subject.complete()` for `code=1001`
  - Confirm `subject.error()` is NOT called for `code=1001` (it would trigger error state)
  - **No code change expected** — this is a verification task

- [ ] **FE-5.3** Verify `WorkspacesComponent.connectToTopic()` `complete()` callback handles topic removal
  - The `complete()` callback already calls `removePointCloud(topic)` and `workspaceStore.removeTopic(topic)`
  - **No code change expected** — this is a verification task
  - Document the verified behavior in a code comment

- [ ] **FE-5.4** Verify `PointCloudComponent.removePointCloud()` disposes GPU resources correctly
  - Confirm `geometry.dispose()` and `material.dispose()` are called
  - **No code change expected** — this is a verification task

---

## Phase 6 — Status WebSocket Consumer Update

- [ ] **FE-6.1** Update the `StatusWebSocketService` or its consumer to handle `visible` in node status
  - If `StatusWebSocketService` maps the raw WS payload to a typed model, update that model/mapping to include `visible`
  - Ensure `topic: null` in status payload does not cause errors in consumers that previously expected `topic: string`

- [ ] **FE-6.2** Confirm `WorkspacesComponent`'s `status` effect properly triggers `refreshTopics()`
  - The existing effect watches `statusWs.status()` and calls `refreshTopics()` when node IDs change
  - When a node is hidden, its topic disappears from `/api/v1/topics` but the node ID stays
  - **Enhancement needed**: also refresh topics when the node `visible` state changes in the status payload
  - Add a second comparison: `const visibilityKey = status.nodes.map(n => \`\${n.id}:\${n.visible}\`).sort().join(',')` alongside the existing `nodeIds` check

---

## Phase 7 — Accessibility & Polish

- [ ] **FE-7.1** Ensure `syn-icon-button` for visibility toggle has `aria-label` set correctly
  - `"Hide node ${node.name}"` when visible
  - `"Show node ${node.name}"` when hidden

- [ ] **FE-7.2** Add tooltip (via `title` attribute or Synergy `syn-tooltip`) showing the node's current visibility state

- [ ] **FE-7.3** Ensure keyboard navigation works for the visibility toggle
  - The `syn-icon-button` should be focusable and respond to `Enter`/`Space`

---

## Dependencies & Blockers

| Task | Blocked By | Note |
|---|---|---|
| FE-2.x (Store) | FE-1.1 (model must have `visible`) | — |
| FE-3.x (Presentation component) | FE-1.1 (uses `NodeConfig` type) | Can be built immediately using mock model |
| FE-4.x (Smart integration) | FE-1.3 (API method), FE-3.x (component) | Use mock `setNodeVisible()` until BE is ready |
| FE-5.x (Workspace) | Backend `1001` close behavior | Verification only — no code changes expected |
| FE-6.x (Status WS) | Backend status payload update | Mock the `visible` field in status payload |

---

## Definition of Done

All tasks are checked off AND:
- [ ] `NodeConfig` and `NodeStatus` types include `visible: boolean`
- [ ] `NodesApiService.setNodeVisible()` method exists and works
- [ ] Eye icon toggle button renders next to each node in the settings node list
- [ ] Clicking the toggle hides/shows the node with optimistic UI update
- [ ] Hidden nodes are visually dimmed in the settings node list
- [ ] Hidden node topics disappear from the workspace topic selector (via topic refresh)
- [ ] Three.js scene removes the point cloud for a hidden node (via `1001` close → `complete()` → `removePointCloud()`)
- [ ] No TypeScript compilation errors (`cd web && ng build --configuration production`)
- [ ] No new Angular template errors in browser console
- [ ] UI update completes within 100ms of click (optimistic update requirement)
