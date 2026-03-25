# Split-View Feature — API Specification

**Document Status**: Final  
**Created**: 2026-03-25  
**Author**: Architecture Agent  
**References**: `technical.md`, `.opencode/rules/protocols.md`

---

## Summary

The split-view feature is **frontend-only**. It introduces no new backend API endpoints and requires no changes to the existing LIDR WebSocket protocol or the REST API.

All new "API" surfaces in this document are:
1. **Internal Angular service APIs** — the TypeScript contracts between services and components
2. **localStorage contracts** — the schema for persisted layout
3. **Existing backend endpoints** — documented here for completeness / frontend mock reference

---

## 1. Existing Backend Endpoints (Unchanged — for Reference)

### 1.1 `GET /api/v1/topics`

Returns the list of available WebSocket topics that the backend DAG is currently broadcasting.

**Response** `200 OK`:
```json
["lidar_1", "lidar_fusion"]
```

**Used by**: `TopicApiService` → `WorkspaceStoreService` → `PointCloudDataService`  
**No changes required.**

---

### 1.2 `WS /ws/{topic}` — LIDR Binary Stream

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 4 | `char[4]` | Magic `"LIDR"` |
| 4 | 4 | `uint32` | Version (`1`) |
| 8 | 8 | `float64` | Unix timestamp (seconds) |
| 16 | 4 | `uint32` | Point count N |
| 20 | N×12 | `float32[N*3]` | Points (x, y, z) × N |

**Close codes**:
- `1001 Going Away` — topic removed by backend; client must NOT reconnect
- Any other code — network error; client should reconnect

**Used by**: `MultiWebsocketService` → `PointCloudDataService`  
**No changes required.**

---

## 2. Internal Angular Service API Contracts

These TypeScript interfaces define the contracts between all new and modified services/components. Frontend developers MUST treat these as the binding API.

---

### 2.1 Data Models (`core/services/split-layout-store.service.ts`)

```typescript
export type ViewOrientation = 'perspective' | 'top' | 'front' | 'side';
export type SplitAxis = 'horizontal' | 'vertical';

export interface ViewPane {
  /** Stable UUID generated at pane creation time */
  id: string;
  /** Camera/scene orientation for this pane */
  orientation: ViewOrientation;
  /**
   * Fractional size within its split group (0–1).
   * Sum of all pane fractions in a group must equal 1.0.
   */
  sizeFraction: number;
}

export interface SplitGroup {
  /** Direction of the flexbox split */
  axis: SplitAxis;
  /** Ordered array of panes in this group (left→right or top→bottom) */
  panes: ViewPane[];
}

export interface SplitLayoutState {
  /** V1: exactly one group at the top level (no nested splits) */
  groups: SplitGroup[];
  /** ID of the currently keyboard-focused pane, or null */
  focusedPaneId: string | null;
  /** Denormalised count of all active panes (1–4) */
  paneCount: number;
}
```

---

### 2.2 `SplitLayoutStoreService` Public API

```typescript
interface SplitLayoutStoreServiceAPI {
  /** Maximum allowed panes */
  readonly MAX_PANES: 4;
  /** Minimum pane dimension in pixels */
  readonly MIN_PX: 200;

  // Signal selectors
  readonly groups:        Signal<SplitGroup[]>;
  readonly focusedPaneId: Signal<string | null>;
  readonly paneCount:     Signal<number>;

  // Computed signals
  readonly allPanes:   Signal<ViewPane[]>;     // flatMap of all panes
  readonly canAddPane: Signal<boolean>;         // paneCount < MAX_PANES

  // Mutators
  addPane(orientation: ViewOrientation): void;
  removePane(paneId: string): void;
  setPaneOrientation(paneId: string, orientation: ViewOrientation): void;
  /**
   * Update the sizeFraction of paneId. The adjacent next-pane fraction is
   * adjusted proportionally. Enforces MIN_PX constraint on both sides.
   * @param paneId  - the pane being dragged
   * @param newFraction - desired new fraction (0–1)
   * @param containerPx - current total container size in px (for MIN_PX enforcement)
   */
  resizePane(paneId: string, newFraction: number, containerPx: number): void;
  setFocusedPane(paneId: string | null): void;
  resetToDefault(): void;
}
```

**Invariants enforced internally**:
- `paneCount` is always in `[1, 4]`
- `sizeFraction` of every pane ≥ `MIN_PX / containerPx` (clamped on resize)
- Sum of `sizeFraction` per group == `1.0` (redistributed on add/remove/resize)

---

### 2.3 Data Models (`core/services/point-cloud-data.service.ts`)

```typescript
export interface FramePayload {
  /** Unix timestamp in seconds (from LIDR header) */
  timestamp: number;
  /** Number of valid points in the `points` array */
  count: number;
  /** Flat [x0,y0,z0, x1,y1,z1, ...] in LiDAR coordinate space */
  points: Float32Array;
}
```

---

### 2.4 `PointCloudDataService` Public API

```typescript
interface PointCloudDataServiceAPI {
  /**
   * Latest decoded frame per topic.
   * Keyed by topic name (e.g. "lidar_1").
   * Empty map = no data / disconnected.
   */
  readonly frames: Signal<Map<string, FramePayload>>;

  /**
   * True when at least one topic WS is currently OPEN.
   */
  readonly isConnected: Signal<boolean>;
}
```

**Notes**:
- Service automatically syncs WebSocket connections when `WorkspaceStoreService.selectedTopics` signal changes.
- FPS and point-count totals are still written to `WorkspaceStoreService` by this service.
- Consumers (`PointCloudComponent`) use `effect()` to react to `frames` signal changes.

---

### 2.5 `PointCloudComponent` Extended Input API

New signal inputs added to the existing component (all backward-compatible, all have defaults):

```typescript
interface PointCloudComponentInputs {
  // ── Existing inputs (unchanged) ──────────────────────────────────────────
  pointSize:       InputSignal<number>;          // default: 0.1
  showGrid:        InputSignal<boolean>;          // default: true
  showAxes:        InputSignal<boolean>;          // default: true
  backgroundColor: InputSignal<string>;           // default: '#000000'

  // ── New inputs ────────────────────────────────────────────────────────────
  /**
   * Orientation controls which camera type and initial position to use.
   * 'perspective' → PerspectiveCamera (FOV 50)
   * 'top'|'front'|'side' → OrthographicCamera, looking along the respective axis
   */
  viewType:   InputSignal<ViewOrientation>;       // default: 'perspective'

  /**
   * Stable pane identifier. Used by the component to subscribe to the correct
   * topic data from PointCloudDataService via the focused topic.
   * If empty string, falls back to first available topic.
   */
  viewId:     InputSignal<string>;                // default: ''

  /**
   * When true, the component caps MAX_POINTS at MAX_POINTS_LOD (25 000)
   * to reduce GPU load in smaller panes.
   */
  adaptiveLod: InputSignal<boolean>;              // default: false
}
```

---

### 2.6 `ViewportOverlayComponent` Input API

```typescript
interface ViewportOverlayComponentInputs {
  /** The pane model for this overlay instance */
  pane: InputSignal<ViewPane>;   // required
}
```

---

### 2.7 `ResizableDividerDirective` Input API

```typescript
interface ResizableDividerInputs {
  /** Split axis of the parent group */
  axis:   InputSignal<SplitAxis>;   // required
  /** ID of the pane immediately before this divider */
  paneId: InputSignal<string>;      // required
}
```

---

## 3. localStorage Contract

### Key: `lidar_split_layout_v1`

**Stored value**: JSON serialisation of `SplitLayoutState`.

**Schema**:
```json
{
  "groups": [
    {
      "axis": "horizontal",
      "panes": [
        { "id": "uuid-v4", "orientation": "perspective", "sizeFraction": 0.5 },
        { "id": "uuid-v4", "orientation": "top",         "sizeFraction": 0.5 }
      ]
    }
  ],
  "focusedPaneId": null,
  "paneCount": 2
}
```

**Validation on load**:
| Check | On failure |
|---|---|
| `JSON.parse()` throws | Clear key, use default state, `console.warn()` |
| `groups` missing or empty | Clear key, use default state |
| `paneCount` > 4 or < 1 | Clear key, use default state |
| Any `sizeFraction` < 0 or > 1 | Normalise fractions to equal distribution |
| `orientation` not in allowed set | Reset to `'perspective'` |

**Existing key** `lidar_workspace_settings` is **unchanged** — topics, colors, HUD prefs remain there.

---

## 4. Mock Data for Development

While developing the split-pane layout (before `PointCloudDataService` is complete), the frontend can use the following mock `FramePayload` to verify rendering:

```typescript
// Development mock — inject in PointCloudDataService constructor during dev
const mockFrame: FramePayload = {
  timestamp: Date.now() / 1000,
  count: 1000,
  points: (() => {
    const arr = new Float32Array(1000 * 3);
    for (let i = 0; i < 1000; i++) {
      arr[i * 3]     = (Math.random() - 0.5) * 20;  // x
      arr[i * 3 + 1] = (Math.random() - 0.5) * 20;  // y
      arr[i * 3 + 2] = (Math.random() - 0.5) * 5;   // z
    }
    return arr;
  })(),
};
```

---

## 5. No Backend Changes Checklist

| Item | Status |
|---|---|
| New REST endpoint needed | ❌ No |
| New WebSocket topic/message type needed | ❌ No |
| Backend DAG node changes required | ❌ No |
| Database schema changes required | ❌ No |
| Docker/environment variable changes required | ❌ No |
| `requirements.txt` / Python dependency changes | ❌ No |
