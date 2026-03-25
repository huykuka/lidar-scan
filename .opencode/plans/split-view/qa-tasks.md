# Split-View Feature — QA Tasks

**Document Status**: Ready for QA  
**Created**: 2026-03-25  
**Author**: Architecture Agent  
**References**: `requirements.md`, `technical.md`, `api-spec.md`, `frontend-tasks.md`  
**Assigned to**: `@qa`

---

## QA Process Overview

1. **TDD Preparation** — Write failing tests before developer implementation (coordinate with `@fe-dev`)
2. **Unit Tests** — Service logic, pure utilities
3. **Integration Tests** — Component wiring, service interaction
4. **E2E Tests** — User-visible acceptance criteria
5. **Performance Tests** — FPS targets, memory leak detection
6. **Linter / Type-Check** — Pre-PR gate

---

## TDD Preparation (Run BEFORE Development)

These tests should be written first and confirmed to fail before `@fe-dev` begins each phase.

### Task QA-01: TDD — `lidr-parser.ts`

- [ ] Write unit test: `parseLidrFrame()` with valid LIDR buffer → returns correct `FramePayload`
- [ ] Write unit test: `parseLidrFrame()` with wrong magic bytes → returns `null`
- [ ] Write unit test: `parseLidrFrame()` with truncated buffer → returns `null` (no exception)
- [ ] Write unit test: `parseJsonPointCloud()` with flat array → returns `Float32Array`
- [ ] Write unit test: `parseJsonPointCloud()` with `{ points: [...] }` envelope → returns `Float32Array`
- [ ] Write unit test: `parseJsonPointCloud()` with unrecognised shape → returns `null`
- [ ] Confirm all 6 tests fail before FE-01 is implemented

---

### Task QA-02: TDD — `SplitLayoutStoreService`

- [ ] Write unit test: `addPane()` with 1 pane → paneCount becomes 2, fractions sum to 1
- [ ] Write unit test: `addPane()` with 4 panes → throws / no-ops (paneCount stays 4)
- [ ] Write unit test: `removePane()` with 2 panes → paneCount becomes 1, remaining pane fraction is 1
- [ ] Write unit test: `removePane()` with 1 pane → no-op (paneCount stays 1)
- [ ] Write unit test: `resizePane()` with valid delta → fractions updated, sum still 1
- [ ] Write unit test: `resizePane()` below MIN_PX → fraction clamped, no pane drops below threshold
- [ ] Write unit test: `setPaneOrientation()` → correct pane updated, others unchanged
- [ ] Write unit test: `loadFromStorage()` with corrupt JSON → resets to default, key cleared
- [ ] Write unit test: `loadFromStorage()` with `paneCount > 4` → resets to default
- [ ] Write unit test: `saveToStorage()` with `QuotaExceededError` → no exception thrown, `console.warn` called
- [ ] Write unit test: `resetToDefault()` → single perspective pane, paneCount = 1
- [ ] Confirm all tests fail before FE-02 is implemented

---

### Task QA-03: TDD — `PointCloudDataService`

- [ ] Write unit test: `syncConnections()` with new topic → `MultiWebsocketService.connect()` called
- [ ] Write unit test: `syncConnections()` with removed topic → `disconnect()` called, topic removed from `frames`
- [ ] Write unit test: incoming LIDR ArrayBuffer frame → `frames` signal updated with correct `FramePayload`
- [ ] Write unit test: WS complete (1001 close) → topic removed from `frames`, no reconnect attempted
- [ ] Write unit test: `ngOnDestroy()` → all subscriptions cleaned up, `disconnectAll()` called
- [ ] Confirm all tests fail before FE-03 is implemented

---

### Task QA-04: TDD — `SplitLayoutStoreService` keyboard shortcuts

- [ ] Write unit test: `Ctrl+T` event → `addPane('top')` called on service
- [ ] Write unit test: `Ctrl+W` with paneCount > 1 and focusedPaneId set → `removePane()` called
- [ ] Write unit test: `Ctrl+W` with paneCount === 1 → no-op
- [ ] Write unit test: keyboard shortcut when `canAddPane()` is false → toast shown, `addPane` NOT called
- [ ] Confirm all tests fail before FE-09 is implemented

---

## Unit Tests (Run After Each Phase Completes)

### Task QA-05: `lidr-parser.ts` unit tests — final pass

- [ ] All 6 TDD tests from QA-01 pass
- [ ] Add edge case: buffer with 0 points (count = 0) → valid `FramePayload` with empty `Float32Array`
- [ ] Code coverage ≥ 90% for `lidr-parser.ts`

---

### Task QA-06: `SplitLayoutStoreService` unit tests — final pass

- [ ] All 11 TDD tests from QA-02 pass
- [ ] Add: `addPane()` with aspect-ratio wider-than-tall → axis becomes `horizontal`
- [ ] Add: `addPane()` with aspect-ratio taller-than-wide → axis becomes `vertical`
- [ ] Add: `canAddPane` computed signal reflects `paneCount < 4` correctly
- [ ] Add: `allPanes` computed signal returns flat array of all panes
- [ ] Code coverage ≥ 95% for `SplitLayoutStoreService`

---

### Task QA-07: `PointCloudDataService` unit tests — final pass

- [ ] All 5 TDD tests from QA-03 pass
- [ ] Add: `isConnected` signal is `true` when ≥1 active topic, `false` when 0
- [ ] Add: FPS counter accumulates frame count per topic correctly (mock `setInterval`)
- [ ] Code coverage ≥ 90% for `PointCloudDataService`

---

### Task QA-08: `WorkspaceKeyboardService` unit tests — final pass

- [ ] All 4 TDD tests from QA-04 pass
- [ ] Add: `Ctrl+1` focuses first pane, `Ctrl+2` focuses second, etc.
- [ ] Add: `Ctrl+F` does NOT fire when `document.activeElement` is an input/form element
- [ ] Code coverage ≥ 85% for `WorkspaceKeyboardService`

---

### Task QA-09: `PointCloudComponent` unit tests — viewType extension

- [ ] `viewType = 'top'` → `activeCamera` is `OrthographicCamera`
- [ ] `viewType = 'perspective'` → `activeCamera` is `PerspectiveCamera`
- [ ] `adaptiveLod = true` → `MAX_POINTS_LOD` cap applied in `updatePointsForTopic()`
- [ ] `adaptiveLod = false` → `MAX_POINTS` cap applied
- [ ] `viewType` change via signal → `initCamera()` called, camera position updated
- [ ] Existing tests (if any) still pass unmodified

---

## Integration Tests

### Task QA-10: `SplitPaneContainerComponent` + `SplitLayoutStoreService` integration

- [ ] Create `TestBed` with both classes and mock `WorkspaceStoreService`
- [ ] Start with default state (1 pane) → template renders 1 `<app-point-cloud>`
- [ ] Call `addPane('top')` → template renders 2 `<app-point-cloud>` + 1 divider
- [ ] Call `removePane(id)` → template returns to 1 `<app-point-cloud>`, no divider
- [ ] Verify `app-viewport-overlay` is rendered for each pane
- [ ] Verify close button is disabled when `paneCount === 1`

---

### Task QA-11: `ViewportOverlayComponent` orientation switcher integration

- [ ] Simulate `synChange` event on orientation `<syn-select>` → `setPaneOrientation()` called with correct args
- [ ] Simulate click on close button → `removePane()` called with correct pane ID
- [ ] Empty state renders when `PointCloudDataService.frames` is empty map
- [ ] Empty state hidden when `frames` has at least one entry
- [ ] Performance warning badge visible when `adaptiveLodActive()` is `true`
- [ ] Performance warning badge hidden when `adaptiveLodActive()` is `false`

---

### Task QA-12: `WorkspacesComponent` refactor integration

- [ ] Verify `PointCloudDataService` is injected and initialised on component init
- [ ] Verify `WorkspaceKeyboardService` is injected and keyboard listener registered
- [ ] Narrow-screen (`isNarrowScreen = true`) → split-pane hidden, narrow message visible
- [ ] Wide-screen (`isNarrowScreen = false`) → split-pane visible, narrow message hidden
- [ ] `NodeStatusService` status change still triggers `refreshTopics()` (regression check)

---

### Task QA-13: localStorage persistence integration

- [ ] Add 2 panes, reload page (via router navigation) → 2 panes restored
- [ ] Change orientation of second pane, reload → orientation persisted
- [ ] Simulate corrupt JSON in `lidar_split_layout_v1` → single default pane shown, no error in UI
- [ ] Simulate missing `lidar_split_layout_v1` → single default pane shown, no error
- [ ] Verify `lidar_workspace_settings` (existing key) is not affected by layout persistence

---

## E2E / Acceptance Tests

### Task QA-14: View Management E2E

- [ ] Open workspace → single perspective view visible
- [ ] Click "Top" add button → 2 views visible (perspective + top), divider present
- [ ] Click "Front" add button → 3 views visible
- [ ] Click "Side" add button → 4 views visible
- [ ] All 4 "Add View" buttons are disabled (grayed out) when 4 views active
- [ ] Click close (×) on a view → view removed, space redistributed, remaining views visible
- [ ] Last remaining view has close button disabled (grayed out)
- [ ] Click "Reset Layout" → returns to single perspective view

---

### Task QA-15: Resize & Layout E2E

- [ ] Drag divider right → left pane grows, right pane shrinks (proportionally)
- [ ] Drag divider to extreme left (min size) → pane stops at 200px, cursor shows `not-allowed`
- [ ] Drag divider to extreme right (min size) → pane stops at 200px on right side
- [ ] Verify smooth CSS transition during add/remove (no instant jump)
- [ ] Browser window resize → views scale proportionally

---

### Task QA-16: Orientation Switching E2E

- [ ] Open orientation dropdown on a pane → all 4 options visible
- [ ] Select "Top" → pane switches to orthographic top-down camera
- [ ] Select "Perspective" → pane switches back to perspective camera
- [ ] Verify pane's position in layout is unchanged after orientation switch
- [ ] Verify other panes are unaffected by orientation change in one pane

---

### Task QA-17: Independent Camera Controls E2E

- [ ] Orbit (drag) in perspective view → other views remain stationary
- [ ] Zoom in top view → other views' zoom unchanged
- [ ] Pan in front view → other views' pan unchanged

---

### Task QA-18: Keyboard Shortcuts E2E

- [ ] `Ctrl+T` → Top view added (or toast shown if at max)
- [ ] `Ctrl+F` → Front view added (or toast shown if at max)
- [ ] `Ctrl+1` → first pane gains keyboard focus (no visual indicator per spec)
- [ ] `Ctrl+2` → second pane focused (when 2+ panes exist)
- [ ] `Ctrl+W` → focused pane closed (when 2+ panes exist)
- [ ] `Ctrl+W` with 1 pane → no effect
- [ ] At max 4 views: `Ctrl+T` → toast "Maximum 4 views reached" appears briefly

---

### Task QA-19: Empty State E2E

- [ ] Disconnect from all topics (no point cloud loaded) → each view shows orientation label + "No point cloud loaded"
- [ ] Reconnect to topic → empty state disappears, point cloud renders

---

### Task QA-20: Responsive E2E

- [ ] Resize browser to 1023px width → split-view message shown, single view visible
- [ ] Resize back to 1200px → multi-view layout restored with previous configuration
- [ ] Verify layout preferences are preserved (not lost) during narrow-screen mode

---

### Task QA-21: WebSocket Edge Cases E2E

- [ ] Disconnect WebSocket mid-session (kill backend) → all views show empty/disconnected state
- [ ] Restart backend → all views resume updating without page reload
- [ ] Verify no duplicate WebSocket connections opened (check Network tab → max 1 WS per topic)

---

## Performance Tests

### Task QA-22: 60 FPS target with 4 views

**Setup**: 4 active views, live LIDR stream with ~100k points, 1920×1080 display

- [ ] Instrument: Add FPS measurement using `THREE.js` clock or Chrome DevTools frame timeline
- [ ] Target: ≥ 54 FPS (90% of 60 FPS per requirements) in quad-view mode
- [ ] Measure: Compare FPS single-view vs. quad-view — delta must be ≤ 10%
- [ ] Record result in `qa-report.md`

---

### Task QA-23: WebSocket data processing overhead

- [ ] Use `performance.mark()` / `performance.measure()` around `parseLidrFrame()` + `updatePointsForTopic()` calls
- [ ] Target: ≤ 5ms total WS processing overhead per frame across all views
- [ ] Record result in `qa-report.md`

---

### Task QA-24: Memory leak detection — repeated add/remove

- [ ] Take Chrome DevTools heap snapshot (baseline)
- [ ] Perform 50× add-view / remove-view cycles
- [ ] Take second heap snapshot
- [ ] Compare: `THREE.WebGLRenderer` count must return to 1 after all removes
- [ ] Compare: `THREE.BufferGeometry` count must return to 1 after all removes
- [ ] Heap delta must be < 5 MB (ruling out meaningful leaks)
- [ ] Record result in `qa-report.md`

---

### Task QA-25: Transition animation smoothness

- [ ] Add/remove view while recording Chrome Performance trace
- [ ] Verify no frames > 33 ms during 250 ms transition window
- [ ] Record result in `qa-report.md`

---

## Linter & Type-Check Verification

### Task QA-26: Pre-PR frontend linter pass

- [ ] Run: `cd web && ng lint`
- [ ] Zero errors, zero warnings on new/modified files
- [ ] Confirm all new components use `ChangeDetectionStrategy.OnPush`
- [ ] Confirm no `NgModule` usage in new files (standalone only)
- [ ] Confirm no `*ngIf` / `*ngFor` structural directives (use `@if` / `@for`)

---

### Task QA-27: Pre-PR TypeScript type-check

- [ ] Run: `cd web && npx tsc --noEmit`
- [ ] Zero type errors
- [ ] Confirm `ViewOrientation` type is used everywhere (no plain `string` for orientation values)

---

### Task QA-28: Pre-PR backend linter (for completeness)

- [ ] Run: `cd .. && python -m ruff check app/` (or project-defined command)
- [ ] Zero new errors or warnings (backend files should be unchanged — this is a regression check)

---

## Coordination & Sign-Off

### Task QA-29: Developer coordination — feature complete verification

- [ ] Confirm with `@fe-dev` that all tasks in `frontend-tasks.md` are marked `[x]`
- [ ] Confirm with `@be-dev` that all tasks in `backend-tasks.md` are marked `[x]`
- [ ] Confirm no regressions in existing workspace functionality (single-view mode still works)
- [ ] Confirm `WorkspaceViewControlsComponent` existing behaviour intact (regression)
- [ ] Confirm `WorkspaceControlsComponent` cockpit still opens/closes correctly

---

### Task QA-30: Write `qa-report.md`

- [ ] Document FPS benchmark results (QA-22)
- [ ] Document WebSocket overhead measurements (QA-23)
- [ ] Document memory leak test results (QA-24)
- [ ] Document any deviations from acceptance criteria
- [ ] Record final pass/fail decision

---

## Test Coverage Summary Targets

| Module | Coverage Target |
|---|---|
| `lidr-parser.ts` | ≥ 90% |
| `SplitLayoutStoreService` | ≥ 95% |
| `PointCloudDataService` | ≥ 90% |
| `WorkspaceKeyboardService` | ≥ 85% |
| `PointCloudComponent` (new paths) | ≥ 80% |
| `SplitPaneContainerComponent` | ≥ 80% (integration only) |
| `ViewportOverlayComponent` | ≥ 80% (integration only) |
