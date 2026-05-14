# Frontend Tasks: Application Node Results Storage

> References: [`requirements.md`](./requirements.md) · [`technical.md`](./technical.md) · [`api-spec.md`](./api-spec.md)

> **Note:** While backend is in progress, mock API responses from `api-spec.md` in `ResultsApiService`.

---

## Phase 1: API Service & Types

- [x] Define TypeScript interfaces in `core/models/results.model.ts`: `NodeResultSummary`, `ResultSummary`, `ResultDetail`, `PcdFileEntry`
  - `PcdFileEntry.path` is a **relative** path (e.g. `results/<node_id>/<result_id>/<label>.pcd`); frontend forms URL as `/data/${path}`
- [x] Create `core/services/api/results-api.service.ts` with:
  - [x] `getNodeIndex(): Observable<NodeResultSummary[]>`
  - [x] `getResultsByNode(nodeId: string): Observable<ResultSummary[]>`
  - [x] `getResultDetail(nodeId: string, resultId: string): Observable<ResultDetail>`
  - [x] `getPcdUrl(path: string): string` — accepts relative `PcdFileEntry.path`, returns `/data/${path}`; no download API or proxy
  - [x] `deleteResult(nodeId: string, resultId: string): Observable<void>`

## Phase 2: PCD Parser Service

- [x] Create `core/services/pcd-parser.service.ts`
  - [x] Parse PCD 0.7 ASCII and binary formats
  - [x] Extract `x y z r g b` fields from header (`FIELDS`, `SIZE`, `TYPE`, `COUNT`, `DATA`)
  - [x] Binary path: `ArrayBuffer` → `DataView`, little-endian float32 for xyz, uint8 for rgb
  - [x] Return: `{ positions: Float32Array, colors: Float32Array, pointCount: number }`
  - [x] Throw typed `PcdParseError` on malformed input (caught by viewer component)

## Phase 3: Shared Components (Dumb)

- [x] Scaffold `features/results/shared/metadata-table/` via Angular CLI
  - [x] `input()` Signal: `metadata: Record<string, unknown>`
  - [x] Renders flat key-value table using Synergy `syn-table` or Tailwind styled `<table>`
  - [x] Deeply nested values rendered as collapsed JSON string with "Expand" toggle
- [x] Scaffold `features/results/shared/pcd-viewer/` via Angular CLI
  - [x] `input()` Signal: `pcdUrl: string`
  - [x] On URL change: `effect()` fetches binary, calls `PcdParserService`, mutates Three.js `BufferGeometry` position + color attributes in-place (no geometry recreation)
  - [x] Canvas resizes with `ResizeObserver`
  - [x] Error state: renders `"Unable to render point cloud"` message in-place
  - [x] Loading state: spinner overlay during fetch + parse

## Phase 4: Feature Pages (Smart Components)

- [x] Scaffold `features/results/results-overview/` via Angular CLI
  - [x] Route: `/results`
  - [x] On init: fetch `getNodeIndex()`, store in `signal<NodeResultSummary[]>`
  - [x] Renders node cards (name, type icon, result count badge, relative timestamp)
  - [x] "Refresh" button re-fetches
  - [x] Empty state: "No application nodes with results available"
  - [x] Click card → `router.navigate(['/results', node.node_id])`

- [x] Scaffold `features/results/node-results-list/` via Angular CLI
  - [x] Route: `/results/:nodeId`
  - [x] `effect()` on route param → fetch `getResultsByNode(nodeId)`
  - [x] Table: Timestamp | Key Metadata (scalar fields from `metadata_summary`) | Status badge
  - [x] Status badge: Synergy `syn-badge` with color mapped to success/warning/error
  - [x] Breadcrumb: "Results > {node_name}"
  - [x] "Refresh" + empty state

- [x] Scaffold `features/results/result-detail/` via Angular CLI
  - [x] Route: `/results/:nodeId/:resultId`
  - [x] `effect()` on params → fetch `getResultDetail()`
  - [x] Tab bar for PCD files (if >1): Signal `activeLabel`; on change, update `PcdViewerComponent` input
  - [x] `<app-pcd-viewer>` + `<app-metadata-table>` side-by-side layout (Tailwind grid)
  - [x] Breadcrumb: "Results > {node_name} > {timestamp}"
  - [x] 404 handling: show "Result not found" with back link

## Phase 5: Routing

- [x] Add lazy-loaded routes to app router:
  ```
  /results         → ResultsOverviewComponent
  /results/:nodeId → NodeResultsListComponent
  /results/:nodeId/:resultId → ResultDetailComponent
  ```
- [x] Add "Results" navigation link in app shell/sidebar

## Phase 6: Tests

- [x] `ResultsApiService`: unit test each method with `HttpClientTestingModule`
- [x] `PcdParserService`: unit test ASCII parse, binary parse, malformed input → error
- [x] `MetadataTableComponent`: renders flat + nested metadata correctly
- [x] `PcdViewerComponent`: loads valid URL, renders error on parse failure, does not recreate geometry on input change
- [x] `ResultsOverviewComponent`: displays node cards, refresh triggers new API call
- [x] `NodeResultsListComponent`: table renders, breadcrumb correct
- [x] `ResultDetailComponent`: tab switching changes active PCD URL, metadata panel visible; `activePcdUrl` always `/data/${entry.path}`, never from download API

## Phase 8: PCD URL Convention (Architectural Doc)

- [x] **`PcdFileEntry` shape locked**: backend returns `{ label, path }` where `path` is always relative (`results/<node_id>/<result_id>/<label>.pcd`)
- [x] **URL formation rule enforced**: frontend always forms `/data/${entry.path}` — never uses download API or proxy; rule documented in:
  - `web/README.md` (project-level developer docs)
  - `core/models/results.model.ts` (JSDoc on `PcdFileEntry.path`)
  - `core/services/api/results-api.service.ts` (JSDoc on `getPcdUrl`)
  - `features/results/shared/pcd-viewer/pcd-viewer.component.ts` (maintainer note on `pcdUrl` input)
- [x] **`getPcdUrl` signature updated**: now accepts `path: string` (not `nodeId, resultId, label`)
- [x] **`result-detail.component.ts`**: `activePcdUrl` derives from `entry.path` directly, no longer calls `getPcdUrl(nodeId, resultId, label)`
- [x] **All specs updated**: mock `PcdFileEntry` uses `path` (relative), `getPcdUrl` spy updated to new signature

## Phase 7: ID-Free UI Audit

- [x] `ResultsOverviewComponent`: render `node_name` not `node_id`; humanize `node_type` snake_case → Title Case
- [x] `NodeResultsListComponent`: breadcrumb shows `node_name`; fallback to `'Unnamed'` (never raw `nodeId`)
- [x] `ResultDetailComponent`: breadcrumb shows `node_name`; fallback to `'Unnamed'`; `resultBreadcrumb` computed as `<Node Name> — <timestamp>`
- [x] Tests updated: assert raw IDs (`node_id`, `result_id`) are never present in rendered DOM
- [x] Tests added: "Unnamed" fallback when node not in index, humanized `node_type` display

## Phase 9: PCD Color Override (JSON-Provided Color)

- [x] Add optional `color?: string` field to `PcdFileEntry` interface in `core/models/results.model.ts` (with JSDoc rendering contract)
- [x] Add `color = input<string>('')` Signal to `PcdViewerComponent`
- [x] Implement `applyMaterialColor(overrideColor)` in `PcdViewerComponent`:
  - When `color` is non-empty: `PointsMaterial.color = new THREE.Color(color)`, `vertexColors = false` (ignores per-point RGB from PCD binary)
  - When `color` is empty: `PointsMaterial.color = white`, `vertexColors = true` (uses per-point RGB from PCD)
  - Sets `material.needsUpdate = true` after each change
- [x] Set `POINT_SIZE = 0.01` for all clouds (replaces previous 0.05)
- [x] Add `activePcdColor` getter in `ResultDetailComponent` sourced from `entry.color`
- [x] Bind `[color]="activePcdColor"` on `<app-pcd-viewer>` in `result-detail.component.html`
- [x] Update mock data in `ResultsApiService` with distinct hex colors per PCD label
- [x] Tests: `PcdViewerComponent` spec updated — validates `vertexColors=false` + correct `material.color` when color input provided, `vertexColors=true` + white when empty, `size=0.01` in both cases, and that material color is not overwritten by vertex data after load
- [x] Document rendering contract in JSDoc: `PcdFileEntry.color`, `PcdViewerComponent.color` input, `applyMaterialColor`, and `ResultDetailComponent.activePcdColor`
