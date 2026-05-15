# Technical Design: Application Node Results Storage

## Static File Serving

PCD result files are publicly accessible via HTTP without auth (dev posture):

```
GET http://<host>/data/results/<node_id>/<result_id>/<label>.pcd
```

`app/app.py` mounts `StaticFiles(directory="data")` at `/data` **after** all API routes and before the SPA fallback. The `data/` directory is created on startup if absent. `/data/` is also added to `PROTECTED_PREFIXES` so the SPA 404-fallback handler never intercepts these URLs.

---

## Architecture Overview

A **service-based, schema-free persistence layer** attached to the existing DAG orchestrator lifecycle. Nodes call a shared `ResultsStorageService` at the end of processing. The frontend renders results fully dynamically based on what the backend declares.

```
Application Node (on_input)
    └──► ResultsStorageService.save_result()
              ├── write PCD files to disk (threadpool)
              ├── commit DB record (SQLite transaction)
              └── return result_id

REST API (FastAPI)
    ├── GET /api/v1/results               → node index
    ├── GET /api/v1/results/{node_id}     → run history
    ├── GET /api/v1/results/{node_id}/{result_id}       → detail
    └── DELETE /api/v1/results/{node_id}/{result_id}    → admin

    NOTE: No /pcd/{label} proxy/download endpoint exists.
    PCD files are accessed directly via the static /data/ mount:
      GET /data/results/{node_id}/{result_id}/{label}.pcd
    The detail endpoint returns { label, path } entries where path is
    relative to /data/.  Frontend forms the URL as /data/${path}.

DAG Orchestrator (node delete hook)
    └──► ResultsStorageService.delete_results_by_node()
              ├── DB DELETE WHERE node_id = ?
              └── shutil.rmtree(data/results/{node_id}/)
```

---

## Data Model

### SQLite Table: `application_results`

```sql
CREATE TABLE IF NOT EXISTS application_results (
    result_id  TEXT PRIMARY KEY,           -- UUID4
    node_id    TEXT NOT NULL,
    timestamp  REAL NOT NULL,              -- Unix epoch float
    metadata   TEXT NOT NULL DEFAULT '{}', -- JSON, minified
    pcd_files  TEXT NOT NULL DEFAULT '[]', -- JSON: [{label, path}]
    status     TEXT NOT NULL DEFAULT 'success' -- 'success'|'warning'|'error'
);
CREATE INDEX IF NOT EXISTS idx_results_node_ts
    ON application_results(node_id, timestamp DESC);
```

- **No FK to nodes table** — nodes are DAG runtime objects, not DB entities. Lifecycle enforced by orchestrator hook.
- `pcd_files` stores paths **relative** to `data/results/` for portability, plus a `color` hex string per entry.
- `metadata` is free-form JSON. No schema validation enforced by storage service.

### PCD Color Mapping (`app/schemas/results.py`)

Each `PcdFileEntry` carries a `color: str` (hex) assigned at save time via `pcd_color_for_label()`:

| Label   | Color | Hex       |
|---------|-------|-----------|
| empty   | blue  | `#2196F3` |
| loaded  | red   | `#F44336` |
| merged  | green | `#4CAF50` |
| (other) | grey  | `#9E9E9E` |

Color is persisted in `pcd_files_json` alongside `label` and `path`. On read, missing `color` (legacy records) falls back to `pcd_color_for_label(label)` for backward compatibility.

### Disk Layout

```
data/results/
  {node_id}/
    {result_id}/
      {label}.pcd       # e.g. empty.pcd, loaded.pcd, merged.pcd
      {label}.pcd
```

- Labels are sanitized (`re.sub(r'[^a-zA-Z0-9_-]', '_', label)`) before becoming filenames.
- PCD format: **Open3D binary PCD** (format 0.7, little-endian). Fields: `x y z r g b` (float32 + uint8 packed as float or separate).
- RGB encoding: Open3D `PointCloud` with `colors` set by node before passing to storage service. Storage service calls `open3d.io.write_point_cloud()` with `write_ascii=False`.

---

## Backend Components

### `app/services/results_storage.py` — `ResultsStorageService`

**Key design decisions:**
- Singleton injected into nodes via constructor or DAG orchestrator dependency.
- Heavy file I/O (`open3d.io.write_point_cloud`) runs via `asyncio.to_thread()`.
- SQLite accessed via a single shared `aiosqlite` connection (or synchronous `sqlite3` inside `asyncio.to_thread` for simplicity).
- `threading.Lock` guards concurrent writes to same node directory.

**Interface:**
```python
class ResultsStorageService:
    async def save_result(
        self,
        node_id: str,
        pcds: List[Tuple[str, o3d.geometry.PointCloud]],  # (label, colored_pcd)
        metadata: Dict[str, Any],
        status: Literal["success", "warning", "error"] = "success",
    ) -> str:  # returns result_id

    async def get_node_index(self) -> List[NodeResultSummary]:
        """Returns all node_ids that have results + counts + latest_ts."""

    async def get_results_by_node(
        self, node_id: str, limit: int = 100, offset: int = 0
    ) -> List[ResultSummary]:

    async def get_result_detail(self, node_id: str, result_id: str) -> ResultDetail:

    async def delete_results_by_node(self, node_id: str) -> int:
        """Called by orchestrator on node delete. Returns count deleted."""

    async def delete_result(self, node_id: str, result_id: str) -> bool:
```

**Transaction boundary:** DB INSERT + directory creation are ordered:
1. `os.makedirs(result_dir, exist_ok=True)` 
2. Write PCD files to disk (threadpool).
3. On disk success: `INSERT INTO application_results ...` in a `BEGIN IMMEDIATE` transaction.
4. On any failure: `shutil.rmtree(result_dir, ignore_errors=True)` then raise.

**`delete_results_by_node` ordering:**
1. `DELETE FROM application_results WHERE node_id = ?` (DB first).
2. `shutil.rmtree(data/results/{node_id}/)` — log error but do not re-raise if disk fails.

### DB Migration

**Strategy:** Lightweight inline migration in `ResultsStorageService.__init__` (no Alembic). On startup, run `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`. Versioned via a `schema_version` table row. This keeps the system self-contained.

### Node Integration Pattern

```python
# In node's on_input() after computation:
empty_pcd = o3d.geometry.PointCloud()
empty_pcd.points = o3d.utility.Vector3dVector(empty_xyz)
empty_pcd.colors = o3d.utility.Vector3dVector(empty_rgb_normalized)  # node applies color

result_id = await self._results_service.save_result(
    node_id=self.id,
    pcds=[("empty", empty_pcd), ("loaded", loaded_pcd), ("merged", merged_pcd)],
    metadata={
        "volume_m3": result.volume_m3,
        "icp_fitness": result.icp_fitness,
        "icp_valid": result.icp_valid,
    },
    status="warning" if not result.icp_valid else "success",
)
logger.info("Saved result %s for node %s", result_id, self.id)
```

- `ResultsStorageService` injected via orchestrator at node construction time.
- Nodes are responsible for RGB coloring **before** passing to the service.

### API Routes: `app/api/v1/results/`

New router mounted at `/api/v1/results`. Thin handlers delegating to `ResultsStorageService`. All exceptions caught at router level as `HTTPException(404)` or `HTTPException(500)`.

**PCD file access policy**: No download/proxy endpoint is provided. PCD files are served exclusively via the static `/data/` mount. The detail endpoint returns `pcd_files: [{ label, path }]` where `path` is relative to `/data/` (e.g. `results/<node_id>/<result_id>/<label>.pcd`). Frontend forms the URL as `/data/${path}`. This is policy — do not introduce a proxy endpoint.

---

## Frontend Components

### Directory: `web/src/app/features/results/`

```
features/results/
  results-overview/       # /results route
  node-results-list/      # /results/:nodeId route
  result-detail/          # /results/:nodeId/:resultId route
  shared/
    metadata-table/       # dumb component: renders Dict<any> generically
    pcd-viewer/           # wraps Three.js, loads PCD by URL
```

### Service: `core/services/api/results-api.service.ts`

Centralizes all HTTP calls. Returns typed Signals or Observables (RxJS for HTTP streams per project rules).

### State Management

- Each smart component holds a `signal<Result[] | null>` for list data.
- `effect()` triggers API fetch on route param changes.
- PCD tab selection stored in component Signal only (no URL param in MVP).

### PCD Parser: `core/services/pcd-parser.service.ts`

Custom parser (no external deps):
- Supports **ASCII** and **binary** PCD 0.7.
- Reads header fields: `FIELDS`, `SIZE`, `TYPE`, `COUNT`, `WIDTH`, `HEIGHT`, `DATA`.
- For `DATA binary`: `ArrayBuffer` → typed arrays via `DataView`.
- Extracts `x y z r g b` → `Float32Array` for positions, `Float32Array` for colors (normalized 0–1 from uint8).

### Three.js Integration

**Use a new `PcdViewerComponent`** (standalone) rather than extending the live workspace component to avoid coupling live-streaming logic with static result viewing.

- Accepts `@Input() pcdUrl: string`.
- On URL change: fetches binary, parses via `PcdParserService`, mutates `BufferGeometry` attribute arrays in-place (per existing 60FPS pattern).
- On error: shows inline error message, does not crash.

### Routing

```typescript
// Lazy-loaded feature routes
{
  path: 'results',
  children: [
    { path: '', component: ResultsOverviewComponent },
    { path: ':nodeId', component: NodeResultsListComponent },
    { path: ':nodeId/:resultId', component: ResultDetailComponent },
  ]
}
```

---

## Lifecycle & Cleanup

| Event | Action |
|---|---|
| Node created | No action needed (results created lazily) |
| Node deleted | Orchestrator calls `delete_results_by_node(node_id)` |
| App startup | `CREATE TABLE IF NOT EXISTS` migration runs |
| App startup | Log total disk usage of `data/results/` at INFO level |
| Manual delete (admin) | `DELETE /api/v1/results/{node_id}/{result_id}` |

---

## Risk Mitigations

| Risk | Mitigation |
|---|---|
| Disk space exhaustion | Log usage at startup. Hard cap: reject save if `data/results/` > 10GB (configurable constant). |
| Partial write on crash | Directory-first, DB-last ordering. Orphan sweep on startup: scan `data/results/` dirs with no DB record → delete. |
| Concurrent saves, same node | `threading.Lock` per `node_id` in service. UUID dirs prevent filename collisions. |
| Large PCD (>50MB) | Backend: enforce 50MB limit in `save_result`, raise ValueError. Frontend: warn if parsed point count > 100k. |
| Metadata drift | No enforcement needed (free-form JSON by design). Frontend renders generically. |
| Binary PCD endianness | Open3D always writes little-endian. Parser assumes LE; document this constraint. |
| PCD parse failure in frontend | `PcdViewerComponent` catches error, displays `"Unable to render point cloud"` message, metadata panel still shows. |

---

## Open Stakeholder Questions

> These must be resolved before dev execution, but are **not blockers** for starting backend work.

1. **Retention hard cap**: Should MVP default to last N=100 results per node (auto-evict oldest), or unlimited with only the disk quota guard? Recommend: **unlimited + disk quota log warning** in MVP, retention policy UI in next iteration.

2. **Access control**: Are result endpoints internal-only (no auth) like existing endpoints, or do they need authentication? Recommend: match existing API auth posture (currently open).

3. **Node scope**: Results overview lists nodes that **have results**. Should it also list application nodes with zero results? Recommend: **yes** — query active DAG state for application nodes, merge with DB result counts (0 for new nodes).

4. **Realistic PCD sizes**: VolumeCalculation at typical grid resolution — estimate actual PCD sizes to validate the 50MB cap. Backend dev to measure during implementation.

5. **Export deferral confirmation**: API is designed to support future export (PCD download endpoint already exists). Confirm UI export button is out of scope for MVP.
