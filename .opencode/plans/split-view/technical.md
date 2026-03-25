# Split-View Feature — Technical Architecture

**Document Status**: Architecture Complete  
**Created**: 2026-03-25  
**Author**: Architecture Agent  
**References**: `requirements.md`, `.opencode/rules/frontend.md`, `.opencode/rules/protocols.md`

---

## 1. Architectural Impact Analysis (GitNexus)

Impact analysis (`gitnexus_impact`) confirmed that both `WorkspacesComponent` and `PointCloudComponent` have **zero upstream callers** (risk: LOW). They are leaf nodes in the component tree. This means we can refactor `WorkspacesComponent` and extend `PointCloudComponent` without cascading breakages anywhere else in the codebase.

Key findings from code exploration:

| Symbol | Current role | Change required |
|---|---|---|
| `WorkspacesComponent` | Single-view orchestrator, owns one `viewChild` pointCloud ref, WebSocket subscriptions | **Refactor**: become a multi-view host, delegate WS data to a new service |
| `PointCloudComponent` | Renders one Three.js scene per instance | **Extend**: accept a `viewType` signal input to set orthographic vs. perspective camera |
| `MultiWebsocketService` | Per-topic WebSocket with auto-reconnect, returns `Observable<any>` | **Reuse as-is** — it already supports multi-topic; share single connection via multicasting |
| `WorkspaceStoreService` extends `SignalsSimpleStoreService` | Signals-based store for workspace-wide preferences | **Extend**: add `layout` signal to hold `ViewPane[]` array |
| `parseBinaryPointCloud()` private method in `WorkspacesComponent` | Decodes LIDR binary frames | **Extract** to a shared pure-function utility (`lidr-parser.ts`) for use by the new service |

---

## 2. Architecture Decision Records (ADRs)

### ADR-1: Split-Pane Library — Custom Implementation over `angular-split`

**Decision**: Custom CSS Flexbox/Grid divider — **no external library**.

**Rationale**:
- `angular-split` adds ~20 kB gzipped, introduces its own change-detection zone, and has poor compatibility with Angular 20 standalone-only components.
- The required behaviour (max 4 panes, auto-split-largest, 200px minimum, aspect-ratio split direction) is a finite, well-understood state machine that can be implemented in under 150 lines of service code.
- Full control over debounce, min-size constraints, and transition animations without monkey-patching.
- The existing `WorkspaceStoreService` pattern (`SignalsSimpleStoreService`) can host pane layout state natively.

**Implementation**: Flexbox rows/columns driven by Signals. A `ResizableDividerDirective` handles `pointermove` events on the divider handle `<div>`, writing pixel deltas directly to the layout signal. No third-party dependency.

---

### ADR-2: Three.js Context — Separate WebGLRenderer Per View

**Decision**: **One `THREE.WebGLRenderer` per `PointCloudComponent` instance** (max 4 = max 4 WebGL contexts).

**Rationale**:
- The browser cap on simultaneous WebGL contexts is 8–16 (Chrome/Firefox). With a hard maximum of 4 views, we are well within limits.
- Sharing a single renderer across multiple canvases (via `renderer.setViewport()` scissor trick) requires a single global animation loop that references all panes — this couples component lifecycle, makes `ngOnDestroy` cleanup fragile, and blocks independent `OrbitControls` instances.
- The current `PointCloudComponent.initThree()` creates its own renderer independently and disposes it in `ngOnDestroy`. This pattern composes perfectly: each `<app-point-cloud>` instance is completely self-contained.
- Context loss handling is already isolated per view.

**Memory profile**: 4 × ~32 MB GPU texture budget (conservatively) = ~128 MB VRAM. Acceptable on recommended hardware (1920×1080 desktop).

---

### ADR-3: BufferGeometry Sharing — Shared Read-Only Float32Array, Per-View BufferAttribute

**Decision**: **Share a single `Float32Array` source buffer** in `PointCloudDataService`, but each `PointCloudComponent` instance maintains its **own `THREE.BufferAttribute`** wrapping a per-view typed array copy.

**Rationale**:
- `THREE.BufferGeometry` is owned by a specific renderer context. Attempting to share a single `BufferGeometry` across two `THREE.Scene` instances from two separate renderers is explicitly unsupported by Three.js (context-specific GPU buffer handles).
- However, CPU-side `Float32Array` data can be shared. The data service will hold one `latestFrameBuffer: Float32Array` that views subscribe to.
- Each `PointCloudComponent` calls `.set()` on its own pre-allocated `Float32Array` (already the pattern in `updatePointsForTopic`). This copies ~1.2 MB (100k × 3 floats × 4 bytes) per view per frame. At 20 Hz data rate and 4 views, the copy overhead is 4 × 1.2 MB × 20 = ~96 MB/s memory bandwidth — well within modern CPU capabilities.
- LOD (adaptive density) for smaller views can reduce this further.

---

### ADR-4: State Management — Angular Signals in Dedicated Service

**Decision**: New **`SplitLayoutStoreService`** extending `SignalsSimpleStoreService` for layout state, plus **`PointCloudDataService`** for WebSocket + shared frame buffer, both `providedIn: 'root'`.

**Rationale**:
- The existing `WorkspaceStoreService` already demonstrates this exact pattern and works well.
- Separating layout state (pane geometry, orientations) from data state (selected topics, WebSocket frames) keeps concerns cleanly isolated.
- Angular Signals (`signal()`, `computed()`, `effect()`) propagate layout changes to templates with `OnPush` change detection, eliminating zone-based triggering overhead at 60 FPS.

---

### ADR-5: WebSocket Data Distribution — Fan-Out via Signal/Subject in Service

**Decision**: **One WebSocket subscription per topic** in `PointCloudDataService`. Data is stored in a `signal<FramePayload | null>` per topic. All active `PointCloudComponent` views `effect()`-subscribe to this signal.

**Rationale**:
- The current pattern (one WS connection per topic in `WorkspacesComponent`) is correct but tightly couples data plumbing to the view. With multiple view instances, each independently doing WS subscriptions would open duplicate connections.
- Moving WS management to a service singleton ensures one physical socket per topic regardless of how many views are open.
- Signal-based fan-out is zero-cost when no views are mounted (effects auto-untrack destroyed contexts).

---

### ADR-6: Layout Persistence — localStorage with Graceful Fallback

**Decision**: Persist `SplitLayoutStoreService` layout state to `localStorage` key `lidar_split_layout_v1`, completely independently of the existing `lidar_workspace_settings` key.

**Rationale**:
- Keeps concerns separate. The workspace store already persists topic/color/HUD prefs; layout is purely geometrical.
- Versioned key (`_v1`) allows safe schema migrations in future releases.
- The store's `effect()` persistence pattern is already proven by `WorkspaceStoreService` — reuse it exactly.
- Corrupt/missing data: wrap `JSON.parse` in try/catch, fall back to default single-perspective layout, clear the key, log to console only.

---

## 3. Component Architecture

### 3.1 New Directory Structure

```
web/src/app/features/workspaces/
├── workspaces.component.ts           ← REFACTORED (smart host, no longer owns WS)
├── workspaces.component.html         ← REFACTORED (multi-pane layout)
├── components/
│   ├── point-cloud/
│   │   └── point-cloud.component.ts  ← EXTENDED (viewType input, orthographic camera)
│   ├── split-pane/                   ← NEW
│   │   ├── split-pane-container.component.ts
│   │   └── resizable-divider.directive.ts
│   ├── viewport-overlay/             ← NEW
│   │   └── viewport-overlay.component.ts
│   ├── view-toolbar/                 ← NEW
│   │   └── view-toolbar.component.ts
│   ├── workspace-telemetry/          ← UNCHANGED
│   ├── workspace-controls/           ← UNCHANGED
│   └── workspace-view-controls/      ← UNCHANGED (moved into viewport-overlay)

web/src/app/core/services/
├── split-layout-store.service.ts     ← NEW
├── point-cloud-data.service.ts       ← NEW (extracts WS logic from WorkspacesComponent)
└── lidr-parser.ts                    ← NEW (pure utility, extracted from WorkspacesComponent)
```

---

### 3.2 Data Models

```typescript
// core/services/split-layout-store.service.ts

export type ViewOrientation = 'perspective' | 'top' | 'front' | 'side';
export type SplitAxis = 'horizontal' | 'vertical';

export interface ViewPane {
  id: string;           // UUID, stable across renders
  orientation: ViewOrientation;
  /** Size as a fraction of the split axis (0–1), e.g. 0.5 for 50% */
  sizeFraction: number;
}

export interface SplitGroup {
  axis: SplitAxis;
  panes: ViewPane[];
}

export interface SplitLayoutState {
  /** Array of groups. V1 supports exactly one top-level group (no nested splits). */
  groups: SplitGroup[];
  /** The focused pane id for keyboard navigation */
  focusedPaneId: string | null;
  /** Total number of panes (denormalised for quick checks) */
  paneCount: number;
}
```

**Constraints enforced by service methods**:
- `paneCount` ≤ 4
- Each `sizeFraction` ≥ `MIN_FRACTION` (derived from 200px / total container size, clamped dynamically)
- Fractions always sum to 1.0 within a group

---

### 3.3 `SplitLayoutStoreService`

```typescript
@Injectable({ providedIn: 'root' })
export class SplitLayoutStoreService extends SignalsSimpleStoreService<SplitLayoutState> {
  readonly MAX_PANES = 4;
  readonly MIN_PX = 200;
  private readonly STORAGE_KEY = 'lidar_split_layout_v1';

  // Public signal selectors
  groups      = this.select('groups');
  focusedPaneId = this.select('focusedPaneId');
  paneCount   = this.select('paneCount');

  // Derived / computed
  allPanes    = computed(() => this.groups().flatMap(g => g.panes));
  canAddPane  = computed(() => this.paneCount() < this.MAX_PANES);

  constructor() {
    super();
    this.loadFromStorage();
    // Persist on every state change
    effect(() => this.saveToStorage(this.state()));
  }

  addPane(orientation: ViewOrientation): void { /* split largest pane */ }
  removePane(paneId: string): void { /* redistribute space */ }
  setPaneOrientation(paneId: string, orientation: ViewOrientation): void {}
  resizePane(paneId: string, newFraction: number, containerPx: number): void { /* enforce MIN_PX */ }
  setFocusedPane(paneId: string | null): void {}
  resetToDefault(): void { /* single perspective pane */ }

  private loadFromStorage(): void { /* try/catch, fallback to default */ }
  private saveToStorage(state: SplitLayoutState): void { /* silent fail on QuotaExceededError */ }
  private getDefaultState(): SplitLayoutState { /* single perspective group */ }
}
```

---

### 3.4 `PointCloudDataService`

This service owns **all WebSocket connections** and makes the latest parsed frame available as a signal per topic. It replaces the WS plumbing currently inside `WorkspacesComponent`.

```typescript
@Injectable({ providedIn: 'root' })
export class PointCloudDataService implements OnDestroy {
  // Exposed signals: one per active topic
  readonly frames = signal<Map<string, FramePayload>>(new Map());
  readonly isConnected = signal(false);

  private wsService = inject(MultiWebsocketService);
  private workspaceStore = inject(WorkspaceStoreService);
  private subscriptions = new Map<string, Subscription>();
  private frameCountPerTopic = new Map<string, number>();
  private fpsInterval?: ReturnType<typeof setInterval>;

  constructor() {
    // React to topic selection changes → sync WebSocket connections
    effect(() => {
      const selectedTopics = this.workspaceStore.selectedTopics();
      this.syncConnections(selectedTopics);
    });

    this.fpsInterval = setInterval(() => this.updateFps(), 1000);
  }

  ngOnDestroy(): void {
    this.subscriptions.forEach(s => s.unsubscribe());
    this.wsService.disconnectAll();
    clearInterval(this.fpsInterval);
  }

  private syncConnections(topics: TopicConfig[]): void { /* connect/disconnect logic */ }
  private connectTopic(topic: string, url: string): void {
    // subscribe, call parseLidrFrame() on message, update frames signal
  }
  private updateFps(): void { /* update workspaceStore fps */ }
}
```

---

### 3.5 `lidr-parser.ts` (Pure Utility)

```typescript
// core/services/lidr-parser.ts

export interface FramePayload {
  timestamp: number;
  count: number;
  points: Float32Array;
}

/**
 * Parse a LIDR binary WebSocket frame.
 * Returns null if magic bytes do not match.
 */
export function parseLidrFrame(buffer: ArrayBuffer): FramePayload | null {
  const view = new DataView(buffer);
  const magic = String.fromCharCode(
    view.getUint8(0), view.getUint8(1),
    view.getUint8(2), view.getUint8(3)
  );
  if (magic !== 'LIDR') return null;
  return {
    timestamp: view.getFloat64(8, true),
    count: view.getUint32(16, true),
    points: new Float32Array(buffer.slice(20)),
  };
}
```

---

### 3.6 `PointCloudComponent` Extensions

The component keeps its existing Three.js internals intact. The following changes are **additive only** (no breakage to current usage):

```typescript
// New signal inputs
viewType   = input<ViewOrientation>('perspective');
viewId     = input<string>('');              // pane id, for keyed updates
adaptiveLod = input<boolean>(false);        // reduce density when true

// Internally: switch camera type based on viewType
private perspCamera!: THREE.PerspectiveCamera;
private orthoCamera!: THREE.OrthographicCamera;
// getter returns the active camera
private get activeCamera(): THREE.Camera { ... }
```

**Camera preset logic** (already partially exists — `setTopView()`, `setFrontView()`, `setSideView()` simply call `setView()` internally):

| `viewType` | Camera class | Position | `controls.enableRotate` |
|---|---|---|---|
| `perspective` | `PerspectiveCamera` (FOV 50) | (15, 15, 15) | `true` |
| `top` | `OrthographicCamera` | (0, 30, 0) | `false` |
| `front` | `OrthographicCamera` | (0, 0, 30) | `false` |
| `side` | `OrthographicCamera` | (30, 0, 0) | `false` |

The `OrthographicCamera` frustum is computed from the container aspect ratio and a dynamic zoom factor driven by `OrbitControls`.

**Adaptive LOD**: When `adaptiveLod()` is `true` (injected by parent when pane size < 50% workspace), the `MAX_POINTS` cap is reduced to 25 000, halving GPU vertex memory.

---

### 3.7 `SplitPaneContainerComponent` (Smart Component)

```typescript
@Component({
  selector: 'app-split-pane-container',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @for (group of groups(); track group.axis) {
      <div [class]="groupClass(group)">
        @for (pane of group.panes; track pane.id; let last = $last) {
          <!-- Viewport slot -->
          <div [id]="pane.id"
               [style.flex]="pane.sizeFraction"
               class="relative min-w-[200px] min-h-[200px] overflow-hidden">
            <app-point-cloud
              [viewType]="pane.orientation"
              [viewId]="pane.id"
              [adaptiveLod]="isSmallPane(pane)"
              [backgroundColor]="backgroundColor()"
              [pointSize]="pointSize()"
              [showAxes]="showAxes()"
              [showGrid]="showGrid()"
              class="w-full h-full"
            />
            <app-viewport-overlay [pane]="pane" />
          </div>

          <!-- Resizable divider (not rendered after last pane) -->
          @if (!last) {
            <div appResizableDivider
                 [axis]="group.axis"
                 [paneId]="pane.id"
                 class="split-divider"
            />
          }
        }
      </div>
    }
  `
})
export class SplitPaneContainerComponent {
  private layout = inject(SplitLayoutStoreService);
  private store = inject(WorkspaceStoreService);
  protected groups = this.layout.groups;
  protected backgroundColor = this.store.backgroundColor;
  protected pointSize = this.store.pointSize;
  protected showAxes = this.store.showAxes;
  protected showGrid = this.store.showGrid;

  protected groupClass(group: SplitGroup): string {
    return group.axis === 'horizontal'
      ? 'flex flex-row w-full h-full'
      : 'flex flex-col w-full h-full';
  }

  protected isSmallPane(pane: ViewPane): boolean {
    // A pane is "small" if its fraction < 0.5 and total panes > 1
    return this.layout.paneCount() > 1 && pane.sizeFraction < 0.5;
  }
}
```

---

### 3.8 `ViewportOverlayComponent` (Dumb Component)

Renders inside each pane absolutely positioned. Contains orientation label, orientation dropdown, and close button.

```typescript
@Component({
  selector: 'app-viewport-overlay',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="absolute top-2 left-2 flex items-center gap-1 z-10 pointer-events-auto">
      <!-- Orientation label badge -->
      <span class="text-[10px] font-black uppercase tracking-widest
                   bg-black/50 text-white px-2 py-0.5 rounded-md select-none">
        {{ pane().orientation }}
      </span>

      <!-- Orientation switcher -->
      <syn-select size="small" [value]="pane().orientation"
                  (synChange)="changeOrientation($event)">
        <syn-option value="perspective">Perspective</syn-option>
        <syn-option value="top">Top</syn-option>
        <syn-option value="front">Front</syn-option>
        <syn-option value="side">Side</syn-option>
      </syn-select>
    </div>

    <!-- Close button -->
    <button
      class="absolute top-2 right-2 z-10 w-6 h-6 flex items-center justify-center
             rounded-full bg-black/50 text-white hover:bg-red-600 transition-colors
             disabled:opacity-30 disabled:cursor-not-allowed"
      [disabled]="isLastPane()"
      (click)="closePane()">
      ×
    </button>

    <!-- Empty state -->
    @if (!hasData()) {
      <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span class="text-4xl font-black uppercase text-white/20 tracking-widest">
          {{ pane().orientation | uppercase }} VIEW
        </span>
        <span class="text-sm text-white/30 mt-2">No point cloud loaded</span>
      </div>
    }

    <!-- Performance warning -->
    @if (adaptiveLodActive()) {
      <div class="absolute bottom-2 left-2 z-10 flex items-center gap-1
                  bg-yellow-500/80 text-black text-[10px] font-bold px-2 py-0.5 rounded">
        <syn-icon name="warning" class="text-xs"/>
        Rendering simplified for performance
      </div>
    }
  `
})
export class ViewportOverlayComponent {
  pane = input.required<ViewPane>();
  private layout = inject(SplitLayoutStoreService);
  private dataService = inject(PointCloudDataService);

  protected isLastPane = computed(() => this.layout.paneCount() === 1);
  protected adaptiveLodActive = computed(
    () => this.layout.paneCount() > 1 && this.pane().sizeFraction < 0.5
  );
  protected hasData = computed(
    () => this.dataService.frames().size > 0
  );

  changeOrientation(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as ViewOrientation;
    this.layout.setPaneOrientation(this.pane().id, value);
  }

  closePane(): void {
    this.layout.removePane(this.pane().id);
  }
}
```

---

### 3.9 `ViewToolbarComponent` (Smart Component)

Added above the split-pane area inside `workspaces.component.html`. Emits actions routed through `SplitLayoutStoreService`.

```typescript
@Component({
  selector: 'app-view-toolbar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex items-center gap-2 px-4 py-2 border-b border-syn-color-neutral-200
                bg-syn-color-neutral-50 shrink-0">
      <!-- Add view buttons -->
      <span class="text-xs font-semibold text-syn-color-neutral-600 mr-1">Add View:</span>

      @for (type of viewTypes; track type.value) {
        <syn-button size="small" variant="outline"
                    [disabled]="!canAdd()"
                    (click)="addView(type.value)">
          <syn-icon [name]="type.icon" slot="prefix"/>
          {{ type.label }}
        </syn-button>
      }

      <div class="flex-1"></div>

      <!-- Reset layout -->
      <syn-button size="small" variant="text" (click)="resetLayout()">
        <syn-icon name="restart_alt" slot="prefix"/>
        Reset Layout
      </syn-button>
    </div>
  `
})
export class ViewToolbarComponent {
  private layout = inject(SplitLayoutStoreService);
  protected canAdd = this.layout.canAddPane;

  readonly viewTypes = [
    { value: 'perspective' as ViewOrientation, label: 'Perspective', icon: 'view_in_ar' },
    { value: 'top' as ViewOrientation,         label: 'Top',         icon: 'vertical_align_top' },
    { value: 'front' as ViewOrientation,       label: 'Front',       icon: 'view_agenda' },
    { value: 'side' as ViewOrientation,        label: 'Side',        icon: 'view_sidebar' },
  ];

  addView(orientation: ViewOrientation): void {
    this.layout.addPane(orientation);
  }

  resetLayout(): void {
    this.layout.resetToDefault();
  }
}
```

---

### 3.10 `ResizableDividerDirective`

Applied to the `<div>` between two panes. Uses `PointerEvents` API for unified mouse+touch handling.

```typescript
@Directive({
  selector: '[appResizableDivider]',
  host: {
    'class': 'resizable-divider',
    '(pointerdown)': 'onPointerDown($event)',
  }
})
export class ResizableDividerDirective {
  axis    = input.required<SplitAxis>();
  paneId  = input.required<string>();      // the pane immediately before this divider

  private layout = inject(SplitLayoutStoreService);
  private el = inject(ElementRef<HTMLElement>);
  private isDragging = false;
  private startPos = 0;
  private startFraction = 0;
  private containerSize = 0;

  onPointerDown(e: PointerEvent): void {
    this.el.nativeElement.setPointerCapture(e.pointerId);
    this.isDragging = true;
    this.startPos = this.axis() === 'horizontal' ? e.clientX : e.clientY;
    const container = this.el.nativeElement.parentElement!;
    this.containerSize = this.axis() === 'horizontal'
      ? container.clientWidth : container.clientHeight;
    const pane = this.layout.allPanes().find(p => p.id === this.paneId());
    this.startFraction = pane?.sizeFraction ?? 0.5;

    const onMove = (e: PointerEvent) => {
      if (!this.isDragging) return;
      const delta = (this.axis() === 'horizontal' ? e.clientX : e.clientY) - this.startPos;
      const newFraction = this.startFraction + (delta / this.containerSize);
      this.layout.resizePane(this.paneId(), newFraction, this.containerSize);
    };

    const onUp = () => {
      this.isDragging = false;
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
    };

    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  }
}
```

---

### 3.11 Keyboard Shortcut Service

```typescript
// New: core/services/workspace-keyboard.service.ts

@Injectable({ providedIn: 'root' })
export class WorkspaceKeyboardService implements OnDestroy {
  private layout = inject(SplitLayoutStoreService);
  private toast  = inject(ToastService);
  private listener = (e: KeyboardEvent) => this.handleKey(e);

  constructor() {
    document.addEventListener('keydown', this.listener);
  }

  ngOnDestroy(): void {
    document.removeEventListener('keydown', this.listener);
  }

  private handleKey(e: KeyboardEvent): void {
    if (!e.ctrlKey) return;

    switch (e.key) {
      case 't': case 'T':
        e.preventDefault(); this.tryAdd('top');       break;
      case 'f': case 'F':
        e.preventDefault(); this.tryAdd('front');     break;
      case 's': case 'S':
        // Guard: Ctrl+S is browser save — only intercept inside canvas focus
        if (document.activeElement?.tagName === 'CANVAS') {
          e.preventDefault(); this.tryAdd('side');
        }
        break;
      case '1': case '2': case '3': case '4':
        e.preventDefault();
        this.focusPane(parseInt(e.key, 10) - 1);
        break;
      case 'w': case 'W':
        e.preventDefault(); this.closeCurrentPane(); break;
    }
  }

  private tryAdd(orientation: ViewOrientation): void {
    if (!this.layout.canAddPane()) {
      this.toast.show('Maximum 4 views reached', 'warning');
      return;
    }
    this.layout.addPane(orientation);
  }

  private focusPane(index: number): void {
    const panes = this.layout.allPanes();
    if (panes[index]) this.layout.setFocusedPane(panes[index].id);
  }

  private closeCurrentPane(): void {
    const id = this.layout.focusedPaneId();
    if (id && this.layout.paneCount() > 1) this.layout.removePane(id);
  }
}
```

---

### 3.12 `WorkspacesComponent` Refactored Template

```html
<!-- workspaces.component.html -->
<div class="flex flex-col flex-1 h-full w-full min-h-0 animate-in fade-in duration-500">

  <!-- Responsive guard: <1024px -->
  @if (isNarrowScreen()) {
    <div class="flex flex-col items-center justify-center flex-1 text-center p-8">
      <syn-icon name="desktop_windows" class="text-4xl text-syn-color-neutral-400 mb-4"/>
      <p class="text-syn-color-neutral-600 font-semibold">
        Split-view requires desktop screen (min. 1024px width)
      </p>
    </div>
  } @else {
    <!-- View toolbar -->
    <app-view-toolbar />

    <!-- Main split-pane area + cockpit -->
    <div class="flex flex-row gap-4 flex-1 h-full w-full min-h-0">
      <div class="flex-1 h-full relative bg-[#2a2a2b] rounded-2xl overflow-hidden
                  border border-syn-color-neutral-300">
        <app-split-pane-container class="w-full h-full" />
        <app-workspace-telemetry />
      </div>

      <!-- Control Cockpit (unchanged) -->
      <div [ngClass]="showCockpit() ? 'w-90 opacity-100' : 'w-0 opacity-0 -ml-4'"
           class="hidden lg:block overflow-hidden transition-all duration-500 ease-in-out shrink-0">
        <app-workspace-controls class="block w-90 h-full transition-opacity duration-300"/>
      </div>
    </div>
  }
</div>
```

`WorkspacesComponent` now only handles: responsive guard signal, cockpit toggle, and wiring `WorkspaceKeyboardService` via injection (no other logic — all delegated).

---

### 3.13 WebSocket Data Flow (Multi-View)

```
Backend LIDR Frame (binary WS)
        │
        ▼
MultiWebsocketService.connect(topic, url)   ← singleton, one socket per topic
        │  Observable<ArrayBuffer>
        ▼
PointCloudDataService.syncConnections()
  │  subscribes to Observable, calls parseLidrFrame()
  │
  ├─► frames signal updated: Map<topic, FramePayload>
  │
  └─► WorkspaceStoreService.set('fps', ...)  / set('pointCount', ...)

PointCloudComponent instances (per view pane):
  effect(() => {
    const frame = dataService.frames().get(topicForThisView);
    if (frame) this.updatePointsForTopic(topic, frame.points, frame.count);
  });
```

**Key invariant**: One physical WebSocket per topic. N views consuming the same topic each receive the same `FramePayload` object (shared reference to the same `Float32Array`). Each view calls `.set()` on its own buffer in `updatePointsForTopic()` — this is the only copy operation.

---

### 3.14 `addPane()` — Split Algorithm

```
function addPane(orientation):
  1. If paneCount >= 4: throw/guard (toolbar button disabled)
  2. Find the pane with the largest sizeFraction (ties: first added)
  3. Determine split axis:
       if largestPane.clientWidth > largestPane.clientHeight → split 'horizontal'
       else → split 'vertical'
  4. Split largestPane.sizeFraction equally between old and new pane
  5. If group axis differs from chosen split axis and paneCount was 1:
       change group.axis
  6. Generate new pane id (crypto.randomUUID())
  7. Insert new ViewPane into group.panes after the target pane
  8. Update paneCount
```

---

### 3.15 `removePane()` — Space Redistribution Algorithm

```
function removePane(paneId):
  1. Guard: if paneCount === 1 → no-op
  2. Find pane index in group.panes
  3. Distribute removed pane's sizeFraction proportionally to remaining panes
     (each gets += removedFraction * (ownFraction / sumRemainingFractions))
  4. Splice pane from array
  5. If paneCount drops to 1, reset group.axis to 'horizontal' (neutral)
  6. Update paneCount
```

---

## 4. Performance Strategy

### 4.1 60 FPS Target

| Factor | Current (1 view) | Multi-View (4 views) | Mitigation |
|---|---|---|---|
| WebSocket frames | 1 buffer decode | 1 buffer decode | Single WS per topic in service |
| CPU Float32Array copies | 0 (in-place set) | 4× per frame | Each copy is `memcpy` at ~20 GB/s; 4×1.2 MB = ~0.24 ms |
| GPU vertex upload | 1× per frame | 4× per frame | Each view's `needsUpdate=true` triggers driver DMA |
| `OrbitControls.update()` | 1× per rAF | 4× per rAF | Negligible; pure CPU vector math |
| `renderer.render()` | 1× per rAF | 4× per rAF | Main GPU cost. Each view has independent rAF loop |
| `requestAnimationFrame` loops | 1 | 4 | Browser schedules all rAF callbacks per vblank; no stutter risk up to 4 |

### 4.2 Adaptive LOD

When `adaptiveLodActive()` returns `true` for a `PointCloudComponent`:
- `MAX_POINTS` is capped at `25_000` (vs. `50_000` default)
- The overlay shows the performance warning badge
- The threshold: pane `sizeFraction < 0.5` **and** `paneCount > 1`

The LOD logic lives entirely in `PointCloudComponent.updatePointsForTopic()`:
```typescript
const effectiveMax = this.adaptiveLod() ? MAX_POINTS_LOD : MAX_POINTS;
const limit = Math.min(count * 3, effectiveMax * 3);
```

### 4.3 ResizeObserver Debouncing

Each `PointCloudComponent` already uses `ResizeObserver → syncSize()`. No change needed. The `SplitPaneContainerComponent` flex layout naturally propagates size changes to children on divider drag.

### 4.4 Animation Sequencing

View add/remove operations set a `isTransitioning` boolean in the layout store for 300 ms. During transition, `addPane()` calls are debounced (dropped). CSS transitions are `transition: flex 250ms ease-in-out` on each pane `<div>`.

---

## 5. Error Handling

| Scenario | Handling |
|---|---|
| Three.js init fails in one view | `try/catch` in `ngAfterViewInit`, sets `hasError = true` signal, overlay shows error card; other views unaffected |
| WebSocket disconnect during multi-view | `MultiWebsocketService` handles auto-reconnect; all views show "Disconnected" via `frames.size === 0` empty state |
| localStorage corrupt | `try/catch` in `loadFromStorage()`, fallback to `getDefaultState()`, `localStorage.removeItem(STORAGE_KEY)`, `console.warn()` |
| localStorage quota exceeded | `try/catch` around `localStorage.setItem()` in `saveToStorage()`, silent fail with `console.warn()` |
| Max views exceeded via keyboard shortcut | `ToastService` brief notification "Maximum 4 views reached" |
| View resize below 200px minimum | `SplitLayoutStoreService.resizePane()` clamps `newFraction` so neither pane drops below `MIN_PX / containerSize` |

---

## 6. Responsive Behaviour

```typescript
// workspaces.component.ts
protected isNarrowScreen = signal(window.innerWidth < 1024);

constructor() {
  const mq = window.matchMedia('(min-width: 1024px)');
  mq.addEventListener('change', (e) => {
    this.isNarrowScreen.set(!e.matches);
  });
}
```

- When `isNarrowScreen()` becomes `true`:
  - Layout is **not destroyed** — `SplitLayoutStoreService` state is preserved
  - `@if (isNarrowScreen())` hides the split-pane, shows the narrow-screen message
  - Single fallback view rendered when narrow (the default app behaviour)
- When `isNarrowScreen()` becomes `false`: the stored multi-view layout re-renders automatically.

---

## 7. `ChangeDetectionStrategy.OnPush` Boundaries

| Component | CD Strategy | Notes |
|---|---|---|
| `WorkspacesComponent` | `OnPush` | Driven by signals |
| `SplitPaneContainerComponent` | `OnPush` | Groups signal drives render |
| `PointCloudComponent` | `OnPush` + imperative Three.js | `rAF` loop is independent of Angular CD |
| `ViewportOverlayComponent` | `OnPush` | Inputs are signals |
| `ViewToolbarComponent` | `OnPush` | All state from `SplitLayoutStoreService` |
| `ResizableDividerDirective` | N/A | Event handler only, no template |
| `WorkspaceKeyboardService` | N/A | No template |

---

## 8. Backend Changes

**No backend changes required.**

The split-view feature is entirely frontend. The backend continues to serve:
- `GET /api/v1/topics` — list of available topics (unchanged)
- `WS /ws/{topic}` — LIDR binary stream per topic (unchanged)

The single-WS-per-topic pattern in `PointCloudDataService` is a refactor of existing client-side logic. No new protocol messages, no new API endpoints, no DAG changes.
