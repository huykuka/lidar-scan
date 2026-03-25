# Split-View Feature — Frontend Tasks

**Document Status**: Ready for Development  
**Created**: 2026-03-25  
**Author**: Architecture Agent  
**References**: `requirements.md`, `technical.md`, `api-spec.md`  
**Assigned to**: `@fe-dev`

---

## Prerequisites & Setup

- [x] Read `technical.md` in full — the ADRs govern every implementation decision
- [x] Read `api-spec.md` — all TypeScript interfaces are binding contracts
- [x] Confirm Angular CLI is available: `cd web && ng version`
- [x] No new npm packages needed (no `angular-split`, no extra Three.js plugins)

---

## Phase 1 — Core Services

### Task FE-01: Create `lidr-parser.ts` pure utility

**File**: `web/src/app/core/services/lidr-parser.ts`

- [x] Create the file with `parseLidrFrame(buffer: ArrayBuffer): FramePayload | null`
- [x] Export the `FramePayload` interface (as defined in `api-spec.md §2.3`)
- [x] Copy parsing logic verbatim from `WorkspacesComponent.parseBinaryPointCloud()` — do NOT modify the parsing algorithm
- [x] Add `parseJsonPointCloud(payload: any): Float32Array | null` extracting the `extractPointsFromJson` logic
- [x] Ensure the function is a pure function (no side effects, no injections)

---

### Task FE-02: Scaffold `SplitLayoutStoreService`

```bash
cd web && ng g service core/services/split-layout-store --skip-tests=false
```

- [x] Run CLI scaffolding command above
- [x] Implement `SplitLayoutState`, `ViewPane`, `SplitGroup`, `ViewOrientation`, `SplitAxis` interfaces (from `api-spec.md §2.1`)
- [x] Extend `SignalsSimpleStoreService<SplitLayoutState>`
- [x] Implement all public mutators: `addPane()`, `removePane()`, `setPaneOrientation()`, `resizePane()`, `setFocusedPane()`, `resetToDefault()`
- [x] Implement `addPane()` split-largest algorithm (see `technical.md §3.14`)
- [x] Implement `removePane()` space-redistribution algorithm (see `technical.md §3.15`)
- [x] Implement `resizePane()` with `MIN_PX = 200` clamp (both panes protected)
- [x] Add computed signals: `allPanes`, `canAddPane`
- [x] Implement `loadFromStorage()` with full validation + fallback (see `api-spec.md §3`)
- [x] Implement `saveToStorage()` with silent `QuotaExceededError` catch + `console.warn()`
- [x] Wire `effect()` for auto-persistence in constructor
- [x] Export `const DEFAULT_SPLIT_LAYOUT: SplitLayoutState` (single perspective pane) for use in tests

---

### Task FE-03: Scaffold `PointCloudDataService`

```bash
cd web && ng g service core/services/point-cloud-data --skip-tests=false
```

- [x] Run CLI scaffolding command above
- [x] Declare `frames` signal (`signal<Map<string, FramePayload>>(new Map())`)
- [x] Declare `isConnected` signal
- [x] Inject `MultiWebsocketService`, `WorkspaceStoreService`, `TopicApiService`
- [x] Move `syncWebSocketConnections()` logic from `WorkspacesComponent` into this service (rename to `syncConnections()`)
- [x] Move `connectToTopic()` and `disconnectFromTopic()` logic here
- [x] Call `parseLidrFrame()` and `parseJsonPointCloud()` from `lidr-parser.ts` (do NOT re-implement parsing)
- [x] Update `frames` signal with each new decoded `FramePayload` (immutable Map update)
- [x] Move FPS counting logic from `WorkspacesComponent` here; continue writing to `WorkspaceStoreService.set('fps', ...)`
- [x] Move total `pointCount` update to this service
- [x] Implement `ngOnDestroy()`: unsubscribe all, `wsService.disconnectAll()`, `clearInterval(fpsInterval)`

---

## Phase 2 — `PointCloudComponent` Extensions

### Task FE-04: Add `viewType` and `adaptiveLod` inputs to `PointCloudComponent`

**File**: `web/src/app/features/workspaces/components/point-cloud/point-cloud.component.ts`

> **IMPORTANT**: All changes are purely additive. Do not remove or rename any existing methods.

- [ ] Add `viewType = input<ViewOrientation>('perspective')` signal input
- [ ] Add `viewId = input<string>('')` signal input
- [ ] Add `adaptiveLod = input<boolean>(false)` signal input
- [ ] Declare `private orthoCamera!: THREE.OrthographicCamera`
- [ ] Add private getter `get activeCamera(): THREE.Camera` that returns either `perspCamera` or `orthoCamera` depending on `viewType()`
- [ ] Rename existing `private camera` to `private perspCamera` (adjust all internal references)
- [ ] In `initThree()`: initialize both `perspCamera` and `orthoCamera`; configure OrthographicCamera frustum from container aspect ratio
- [ ] Add `private initCamera(viewType: ViewOrientation): void` — sets position and `controls.enableRotate` per the table in `technical.md §3.6`
- [ ] Add `effect()` in constructor: when `viewType()` changes → call `initCamera(viewType())`
- [ ] In `animate()`: replace `this.camera` references with `this.activeCamera`
- [ ] In `syncSize()`: update both cameras' aspect/frustum on resize
- [ ] In `ngOnDestroy()`: dispose both cameras
- [ ] Implement adaptive LOD: add `private readonly MAX_POINTS_LOD = 25_000` constant; use `this.adaptiveLod() ? this.MAX_POINTS_LOD : this.MAX_POINTS` in `updatePointsForTopic()`
- [ ] Wire `PointCloudDataService` injection; add `effect()` to subscribe to `frames()` signal and call `updatePointsForTopic()` for all active topics
- [ ] Verify existing `setTopView()`, `setFrontView()`, `setSideView()` still work (they now delegate to `initCamera()` internally)

---

## Phase 3 — Split-Pane UI Components

### Task FE-05: Scaffold `ResizableDividerDirective`

```bash
cd web && ng g directive features/workspaces/components/split-pane/resizable-divider --skip-tests=false
```

- [x] Run CLI scaffolding command above
- [x] Implement `axis` and `paneId` signal inputs (required)
- [x] Implement `onPointerDown(e: PointerEvent)` host listener
- [x] Use `setPointerCapture` / `releasePointerCapture` for reliable drag across viewport boundaries
- [x] Compute delta from `startPos` and call `SplitLayoutStoreService.resizePane()` on `pointermove`
- [x] Bind cursor style via host binding: `cursor: col-resize` (horizontal) or `row-resize` (vertical)
- [x] Add `not-allowed` cursor when resize would violate min-size (read back from store after resize call)
- [x] Clean up event listeners in `pointerup`

---

### Task FE-06: Scaffold `SplitPaneContainerComponent`

```bash
cd web && ng g component features/workspaces/components/split-pane/split-pane-container --skip-tests=false
```

- [x] Run CLI scaffolding command above
- [x] Set `changeDetection: ChangeDetectionStrategy.OnPush`
- [x] Inject `SplitLayoutStoreService`, `WorkspaceStoreService`
- [x] Implement template per `technical.md §3.7` using `@for ... track pane.id`
- [x] Pass `[viewType]`, `[viewId]`, `[adaptiveLod]`, `[backgroundColor]`, `[pointSize]`, `[showAxes]`, `[showGrid]` to each `<app-point-cloud>`
- [x] Implement `groupClass(group): string` helper for flex direction
- [x] Implement `isSmallPane(pane): boolean` helper for LOD decision
- [x] Apply `transition: flex 250ms ease-in-out` to pane divs via Tailwind `transition-all duration-[250ms]`
- [x] Enforce `min-w-[200px] min-h-[200px]` Tailwind classes on each pane div
- [x] Import `ResizableDividerDirective`, `ViewportOverlayComponent`, `PointCloudComponent`

---

### Task FE-07: Scaffold `ViewportOverlayComponent`

```bash
cd web && ng g component features/workspaces/components/viewport-overlay/viewport-overlay --skip-tests=false
```

- [x] Run CLI scaffolding command above
- [x] Set `changeDetection: ChangeDetectionStrategy.OnPush`
- [x] Implement `pane = input.required<ViewPane>()` signal input
- [x] Inject `SplitLayoutStoreService`, `PointCloudDataService`
- [x] Implement orientation badge (top-left corner): `text-[10px] font-black uppercase`
- [x] Implement `<syn-select>` orientation dropdown using Synergy Design System (`SynergyComponentsModule`)
- [x] Implement close button (top-right): disabled when `isLastPane()`, Synergy-styled
- [x] Implement empty-state overlay: shown when `!hasData()`; full-height centred text
- [x] Implement performance warning badge: shown when `adaptiveLodActive()` is true
- [x] Implement `changeOrientation(event: Event)` calling `layout.setPaneOrientation()`
- [x] Implement `closePane()` calling `layout.removePane(pane().id)`
- [x] Use `@if` / `@switch` Angular control flow syntax only (no `*ngIf`)

---

### Task FE-08: Scaffold `ViewToolbarComponent`

```bash
cd web && ng g component features/workspaces/components/view-toolbar/view-toolbar --skip-tests=false
```

- [x] Run CLI scaffolding command above
- [x] Set `changeDetection: ChangeDetectionStrategy.OnPush`
- [x] Inject `SplitLayoutStoreService`
- [x] Declare `viewTypes` array with `{ value, label, icon }` entries for all 4 orientations (use Synergy icons from `technical.md §3.9`)
- [x] Render "Add View:" label + 4 `<syn-button>` components using `SynergyComponentsModule`
- [x] Bind `[disabled]="!canAdd()"` on all add buttons
- [x] Implement "Reset Layout" `<syn-button>` calling `layout.resetToDefault()`
- [x] Use Tailwind `flex items-center gap-2 px-4 py-2 border-b` for toolbar layout
- [x] Show brief `ToastService` notification "Maximum 4 views reached" (inject `ToastService`) — but only from the **keyboard service**, not from button clicks (buttons are already disabled)

---

### Task FE-09: Scaffold `WorkspaceKeyboardService`

```bash
cd web && ng g service core/services/workspace-keyboard --skip-tests=false
```

- [x] Run CLI scaffolding command above
- [x] Inject `SplitLayoutStoreService`, `ToastService`
- [x] Register `keydown` listener on `document` in constructor
- [x] Implement all shortcuts from `requirements.md §Keyboard Shortcuts`:
  - `Ctrl+T` → add Top view
  - `Ctrl+F` → add Front view
  - `Ctrl+S` → add Side view (**only when canvas has focus** — guard with `document.activeElement?.tagName === 'CANVAS'` to avoid browser save conflict)
  - `Ctrl+1–4` → focus pane by index
  - `Ctrl+W` → close focused pane (only if `paneCount > 1`)
- [x] Show toast "Maximum 4 views reached" when `canAddPane()` is false on shortcut press
- [x] Deregister listener in `ngOnDestroy()`

---

## Phase 4 — Refactor `WorkspacesComponent`

### Task FE-10: Refactor `WorkspacesComponent`

**File**: `web/src/app/features/workspaces/workspaces.component.ts`

- [ ] Remove `viewChild.required<PointCloudComponent>('pointCloud')` — no longer a single reference
- [ ] Remove all WebSocket subscription fields and logic (`wsSubscriptions`, `frameCountPerTopic`, `fpsUpdateInterval`, `syncWebSocketConnections`, `connectToTopic`, `disconnectFromTopic`, `handleWsMessage`, `parseBinaryPointCloud`, `extractPointsFromJson`)
- [ ] Remove the `effect()` for `selectedTopics` — now handled by `PointCloudDataService`
- [ ] Inject `PointCloudDataService` (this ensures it starts up and manages WS connections)
- [ ] Inject `WorkspaceKeyboardService` (this ensures it registers keyboard listeners)
- [ ] Add `protected isNarrowScreen = signal(window.innerWidth < 1024)` with `matchMedia` listener
- [ ] Keep the `effect()` for `NodeStatusService` status changes and `refreshTopics()` calls (unchanged)
- [ ] Keep cockpit toggle methods (`toggleCockpit`, `closeCockpit`)
- [ ] Remove `resetCamera`, `setTopView`, `setFrontView`, `setSideView`, `setIsometricView`, `fitToPoints`, `captureScreenshot`, `clearPoints`, `toggleGrid`, `toggleAxes` — these are now handled per-pane inside `ViewportOverlayComponent`/`SplitPaneContainerComponent`
- [ ] Update template (per `technical.md §3.12`): replace single `<app-point-cloud>` with `<app-view-toolbar>` + `<app-split-pane-container>`
- [ ] Remove `WorkspaceViewControlsComponent` import (its actions are now per-pane in overlay)
- [ ] Add `SplitPaneContainerComponent`, `ViewToolbarComponent` to imports array
- [ ] Keep `WorkspaceTelemetryComponent`, `WorkspaceControlsComponent`, `SynergyComponentsModule`, `NgClass` imports

---

## Phase 5 — Responsive, Error Handling & Polish

### Task FE-11: Responsive narrow-screen guard

- [ ] Implement `isNarrowScreen` signal in `WorkspacesComponent` using `window.matchMedia`
- [ ] Template `@if (isNarrowScreen())` shows the "Split-view requires desktop screen (min. 1024px width)" message
- [ ] Message styled with Synergy icon `desktop_windows` + Tailwind `flex flex-col items-center justify-center`
- [ ] Verify that stored layout in `SplitLayoutStoreService` is **not cleared** when going narrow — only visually hidden
- [ ] Verify that returning to wide screen restores the stored layout without refresh

---

### Task FE-12: Error boundary in `PointCloudComponent`

- [ ] Add `hasError = signal(false)` and `errorMessage = signal('')` to `PointCloudComponent`
- [ ] Wrap `initThree()` call in `ngAfterViewInit()` with try/catch; on error: set signals, log to console
- [ ] Add error overlay to `PointCloudComponent` template: `@if (hasError())` shows centred error card
- [ ] Error card uses Synergy `<syn-icon name="error">` + error message text, Tailwind styled
- [ ] Ensure error in one pane does not prevent other panes from rendering (each has independent `ngAfterViewInit`)

---

### Task FE-13: Transition debounce & animation polish

- [ ] Add `isTransitioning = signal(false)` to `SplitLayoutStoreService`
- [ ] In `addPane()` and `removePane()`: set `isTransitioning(true)`, schedule `setTimeout(() => this.set('isTransitioning', false), 300)`
- [ ] In `addPane()`: guard — if `isTransitioning()` is true, return early (debounce rapid add)
- [ ] Apply `transition-all duration-[250ms] ease-in-out` Tailwind class on pane flex containers
- [ ] Verify no visual tearing on rapid add/remove in manual testing

---

### Task FE-14: `WorkspaceViewControlsComponent` audit

- [ ] Review which controls are still needed at the workspace level vs. per-pane
- [ ] The global controls (grid toggle, axes toggle, HUD toggle) remain in `WorkspaceControlsComponent` (cockpit) — no change needed
- [ ] The per-view controls (camera views, fit, reset, screenshot, clear) are now per-pane; verify they are accessible via `ViewportOverlayComponent`'s orientation-preset buttons
- [ ] Remove `<app-workspace-view-controls>` from `workspaces.component.html` if now fully superseded
- [ ] **Do NOT delete** `WorkspaceViewControlsComponent` class file — it may be needed for the cockpit or future use

---

## Phase 6 — Validation & Integration

### Task FE-15: Manual integration smoke test

- [ ] Launch `ng serve` with a running backend
- [ ] Add 2 views → verify layout splits correctly
- [ ] Add 3rd and 4th view → verify split-largest logic
- [ ] Attempt 5th view → verify button disabled + toast (keyboard)
- [ ] Drag divider → verify smooth resize with min 200px constraint
- [ ] Change orientation via dropdown → verify camera switches
- [ ] Close view → verify space redistributed
- [ ] Close last view → verify close button disabled
- [ ] Reload page → verify layout restored from localStorage
- [ ] Open DevTools → corrupt `lidar_split_layout_v1` → reload → verify fallback to single view, no error shown
- [ ] Resize browser below 1024px → verify narrow-screen message
- [ ] Resize above 1024px → verify layout restores
- [ ] Test all keyboard shortcuts

---

## Dependencies Between Tasks

```
FE-01 (parser utility)
  └─► FE-03 (PointCloudDataService)
        └─► FE-04 (PointCloudComponent data wiring)
              └─► FE-06 (SplitPaneContainer)
                    └─► FE-10 (WorkspacesComponent refactor)

FE-02 (SplitLayoutStoreService)
  └─► FE-05 (ResizableDividerDirective)
  └─► FE-06 (SplitPaneContainerComponent)
  └─► FE-07 (ViewportOverlayComponent)
  └─► FE-08 (ViewToolbarComponent)
  └─► FE-09 (WorkspaceKeyboardService)

All of Phase 3 must complete before FE-10.
FE-10 must complete before FE-11–14.
FE-15 requires all other tasks complete.
```

---

## Acceptance Criteria Cross-Reference

| Requirement | Tasks |
|---|---|
| US-1: Add orthometric views | FE-08, FE-02 |
| US-2: Resize and arrange | FE-05, FE-02 |
| US-3: Independent cameras | FE-04 |
| US-4: Persistent layout | FE-02 (localStorage) |
| US-5: Switch orientations | FE-07 |
| US-6: Keyboard navigation | FE-09 |
| US-7: 60 FPS performance | FE-04 (LOD), FE-03 (single WS) |
| Responsive <1024px guard | FE-11 |
| Error handling per-view | FE-12 |
| Transition debounce | FE-13 |
