# Node Status Standardization — Frontend Tasks

**Owner**: `@fe-dev`  
**Reference**: `technical.md` (architecture), `api-spec.md` (schema contract)  
**Branch**: `feature/node-status-standardization`  
**Mock data**: Use `api-spec.md § 5` while backend is in progress.

Update checkboxes from `[ ]` to `[x]` as each step completes.

---

## Phase 1 — Models & Service Infrastructure

### Task F1: Create TypeScript Status Model

**File**: `web/src/app/core/models/node-status.model.ts` *(new)*

- [x] F1.1 — Create `node-status.model.ts` containing `OperationalState` type literal union, `ApplicationState`, `NodeStatusUpdate`, `NodesStatusResponse` interfaces — exactly as in `api-spec.md § 1.2`
- [x] F1.2 — Export all types from `web/src/app/core/models/index.ts`
- [x] F1.3 — Remove old `NodeStatus`, `LidarNodeStatus`, `FusionNodeStatus` from `node.model.ts` — superseded by `NodeStatusUpdate`
- [x] F1.4 — Resolve all TypeScript compilation errors from the removed types: `ng build --configuration development`

---

### Task F2: Update StatusWebSocketService

**File**: `web/src/app/core/services/status-websocket.service.ts` *(modified)*

- [x] F2.1 — Update `status` signal type to `NodesStatusResponse | null` using the new `NodeStatusUpdate` array shape
- [x] F2.2 — Add 50 ms debounce before updating the signal (prevents excess change-detection on rapid updates):
  ```typescript
  private _pending: NodesStatusResponse | null = null;
  private _debounceId: ReturnType<typeof setTimeout> | null = null;
  ```
  On each `onmessage`: store in `_pending`; if no timer running, start a 50 ms timeout that flushes `_pending` into the signal.
- [x] F2.3 — Write unit tests `status-websocket.service.spec.ts`:
  - [x] `should parse NodeStatusUpdate array from a WebSocket JSON message`
  - [x] `should debounce rapid messages and update signal only once within the 50ms window`

---

### Task F3: Add nodeStatusMap to NodeStoreService

**File**: `web/src/app/core/services/stores/node-store.service.ts` *(modified)*

- [x] F3.1 — Inject `StatusWebSocketService` (if not already present)
- [x] F3.2 — Add computed signal:
  ```typescript
  nodeStatusMap = computed<Map<string, NodeStatusUpdate>>(() => {
    const statuses = this.statusWebSocket.status()?.nodes ?? [];
    return new Map(statuses.map(s => [s.node_id, s]));
  });
  ```
- [x] F3.3 — Unit tests:
  - [x] `should build a Map keyed by node_id`
  - [x] `should return empty Map when status is null`

---

## Phase 2 — FlowCanvasNodeComponent

### Task F4: Update Component TypeScript

**File**: `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.ts` *(modified)*

- [x] F4.1 — Change `status` input type to `NodeStatusUpdate | null`
- [x] F4.2 — Add `badgeColorMap` constant (semantic name → CSS hex):
  ```typescript
  protected readonly badgeColorMap: Record<string, string> = {
    green: '#16a34a', blue: '#2563eb', orange: '#d97706',
    red:   '#dc2626', gray: '#6b7280',
  };
  ```
- [x] F4.3 — Add `operationalIcon` computed signal:
  - `INITIALIZE` → `{ icon: 'hourglass_empty', css: 'text-syn-color-warning-600 animate-pulse' }`
  - `RUNNING`    → `{ icon: 'play_circle',     css: 'text-syn-color-success-600' }`
  - `STOPPED`    → `{ icon: 'pause_circle',    css: 'text-syn-color-neutral-400' }`
  - `ERROR`      → `{ icon: 'error',           css: 'text-syn-color-danger-600' }`
  - `null`       → `{ icon: 'radio_button_unchecked', css: 'text-syn-color-neutral-300' }`
- [x] F4.4 — Add `appBadge` computed signal: returns `{ text: "${label}: ${value}", color: hex }` from `status()?.application_state`, or `null` if absent. Booleans → `"true"` / `"false"` strings.
- [x] F4.5 — Add `errorText` computed signal: returns `status()?.error_message` only when `operational_state === 'ERROR'`, else `null`
- [x] F4.6 — Remove obsolete helpers: `statusBadge()`, `getFrameAge()`, `isFrameStale()`, `getStatusColorClass()`, `ifStateIcon()`, `ifStatus`
- [x] F4.7 — Remove `IfNodeStatus` import from `flow-control.model.ts` if now unused

---

### Task F5: Update HTML Template

**File**: `flow-canvas-node.component.html` *(modified)*

Three isolated changes to the existing template:

**Change 1 — Header: replace status dot with operational icon**
- [x] F5.1 — Remove `<div class="w-2.5 h-2.5 rounded-full ...">` (the status dot at line 64)
- [x] F5.2 — Add before the node-name `<span>`:
  ```html
  <syn-icon
    [name]="operationalIcon().icon"
    [class]="operationalIcon().css + ' text-[14px] shrink-0'"
    [title]="status()?.operational_state ?? 'Unknown'"
  />
  ```
- [x] F5.3 — Remove the existing `@if (isIfConditionNode() && ifStateIcon())` block (no longer needed)
- [x] F5.4 — Remove the frame-age badge `@if (status() && getFrameAge())` block

**Change 2 — Body: passive error display**
- [x] F5.5 — Replace `@if (status()?.last_error)` condition with `@if (errorText())`
- [x] F5.6 — Replace `{{ status()?.last_error }}` binding with `{{ errorText() }}`
- [x] F5.7 — Add `[title]="errorText()"` to the error `<span>` for full text on hover
- [x] F5.8 — Keep existing `line-clamp-2` and danger colour classes unchanged

**Change 3 — Bottom-right badge (Node-RED style)**
- [x] F5.9 — Add after the last child of the host `<div>`:
  ```html
  @if (appBadge()) {
    <div class="absolute -bottom-3 right-1 flex items-center gap-1
                bg-white border rounded-full px-1.5 py-0.5 shadow-sm text-[9px] font-mono z-10">
      <span class="truncate max-w-[80px]">{{ appBadge()!.text }}</span>
      <div class="w-2 h-2 rounded-full shrink-0"
           [style.background-color]="appBadge()!.color"></div>
    </div>
  }
  ```
- [x] F5.10 — Verify the host `<div>` has `relative` class (it does in the current template)

---

### Task F6: Update FlowCanvasComponent Wiring

**File**: `web/src/app/features/settings/components/flow-canvas/flow-canvas.component.ts` *(modified)*

- [x] F6.1 — Inject `NodeStoreService` if not already present
- [x] F6.2 — Change per-node status lookup to `nodeStore.nodeStatusMap().get(node.id) ?? null` (returns `NodeStatusUpdate | null`)
- [x] F6.3 — Pass the result to `[status]` on `<app-flow-canvas-node>` — the type now matches the updated input

---

### Task F7: CalibrationControls Status Binding

**File**: `node-calibration-controls/node-calibration-controls.ts` *(check and update if needed)*

- [x] F7.1 — Check if this component uses the old `NodeStatus` type for its `status` input
- [x] F7.2 — If yes, update to `NodeStatusUpdate | null`; derive calibration activity from `status?.application_state?.value === true`

---

## Phase 3 — Development Mock

### Task F8: Mock Data for Parallel Dev

- [ ] F8.1 — While backend is in progress, create a dev-only helper that pre-seeds `StatusWebSocketService.status` signal with `MOCK_SYSTEM_STATUS` from `api-spec.md § 5`
- [ ] F8.2 — Gate behind `environment.mockStatus === true`
- [ ] F8.3 — Cycle through all four `operational_state` values on a 3-second timer to test all visual states
- [ ] F8.4 — Manual verification: every node type renders the correct icon, badge, and error text in each state

---

## Phase 4 — Tests

### Task F9: Component Unit Tests

**File**: `flow-canvas-node.component.spec.ts`

- [ ] F9.1 — Mock `NodeStoreService.nodeStatusMap` to return controlled `NodeStatusUpdate` values
- [ ] F9.2 — `should display hourglass_empty icon with animate-pulse for INITIALIZE`
- [ ] F9.3 — `should display play_circle icon for RUNNING`
- [ ] F9.4 — `should display pause_circle icon for STOPPED`
- [ ] F9.5 — `should display error icon for ERROR`
- [ ] F9.6 — `should render application state badge when application_state is present`
- [ ] F9.7 — `should NOT render badge when application_state is absent`
- [ ] F9.8 — `should display error text in body when operational_state is ERROR`
- [ ] F9.9 — `should NOT display error text when operational_state is RUNNING`
- [ ] F9.10 — `should apply correct hex color from badgeColorMap for each named color`
- [ ] F9.11 — `should fall back to gray hex when application_state.color is undefined`
- [ ] F9.12 — `should format boolean value as "true"/"false" string in badge text`

---

### Task F10: Build Verification

- [ ] F10.1 — `ng build --configuration production` — zero TypeScript errors, zero warnings from removed types
- [ ] F10.2 — `ng test --watch=false` — all unit tests pass
- [ ] F10.3 — No unused imports remain from old `NodeStatus` types

---

## Task Summary Checklist

```
Phase 1 — Models & Service Infrastructure
  [ ] F1 — node-status.model.ts
  [ ] F2 — StatusWebSocketService debounce + type update
  [ ] F3 — NodeStoreService nodeStatusMap

Phase 2 — FlowCanvasNodeComponent
  [ ] F4 — Component TypeScript (new signals, remove old helpers)
  [ ] F5 — HTML (operational icon, error body, app-state badge)
  [ ] F6 — FlowCanvasComponent status wiring
  [ ] F7 — CalibrationControls binding check

Phase 3 — Mock
  [ ] F8 — Dev mock data

Phase 4 — Tests
  [ ] F9  — Component unit tests (12 cases)
  [ ] F10 — Build verification
```
