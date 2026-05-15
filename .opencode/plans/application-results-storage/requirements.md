# Application Node Results Storage - Requirements

## Feature Overview

The **Application Node Results Storage** feature enables persistent storage and viewing of execution results for all application-level DAG nodes (vehicle_profiler, volume_calculation, and future application nodes). Each node can define its own result schema—storing arbitrary point cloud files with pre-colored data and flexible metadata—while the system handles storage, retrieval, lifecycle management, and visualization.

**Key Characteristics:**
- **Node-Agnostic Storage**: No global result schema. Each node type defines what point clouds and metadata to save.
- **Backend-Defined Output**: Nodes produce complete result payloads with pre-colored RGB point clouds and arbitrary metadata.
- **SQLite Persistence**: Metadata and file paths stored in DB; PCD files written to structured disk storage.
- **Lifecycle Coupling**: Results tied to node instances—deleted when parent node is removed from DAG.
- **Frontend Rendering**: Displays results dynamically based on backend-defined schemas without hardcoded field lists.

## Business Context

Application nodes perform high-value, computationally expensive analysis (vehicle profiling, volume estimation) that operators need to review, validate, and trace back over time. Unlike real-time streaming data (which is ephemeral), application results represent **decision-worthy outputs** that must be:

- **Inspectable**: View processed point clouds with domain-specific coloring (e.g., height-coded volume grids, profile slices).
- **Traceable**: Historical record of when and how results were generated (timestamps, input sources, configuration snapshots).
- **Auditable**: Metadata captures diagnostic information (ICP fitness scores, detection confidence, processing warnings).

**Use Cases:**
- **Vehicle Profiling Review**: Inspect profile slices from past vehicles to validate dimension measurements or debug detection failures.
- **Volume Calculation History**: Browse previous load/empty comparisons to track material handling patterns or identify calibration drift.
- **Diagnostic Investigation**: Trace errors or anomalies back to specific execution runs using stored metadata (e.g., low ICP fitness, insufficient point count).
- **Configuration Tuning**: Compare results before/after parameter changes by reviewing historical outputs.

---

## User Stories

### US1: View Application Node Results History

**As a** point cloud processing engineer,  
**I want to** see a list of all application nodes with result counts,  
**So that** I can quickly identify which nodes have historical data available for review.

**Acceptance Criteria:**
- Navigate to a dedicated `/results` page showing all application nodes currently in the DAG
- Each node entry displays:
  - Node name and type (e.g., "Vehicle Profiler", "Volume Calculation")
  - Total result count
  - Timestamp of most recent result
  - Visual indicator if no results exist yet
- Page includes a manual refresh button to fetch latest result counts
- Clicking a node entry navigates to its detailed result listing page

---

### US2: Browse Historical Results for a Specific Node

**As an** operator,  
**I want to** view all historical execution results for a specific application node,  
**So that** I can review past runs and select one for detailed inspection.

**Acceptance Criteria:**
- Navigate to `/results/{node_id}` to see result list for that node
- Result list displays each run as a row/card with:
  - Unique result ID
  - Timestamp (human-readable and sortable)
  - Key metadata fields (node-specific, e.g., "vehicle detected", "volume_m3")
  - Status indicator (success, warning, error based on metadata flags)
- Results are sorted by timestamp (newest first by default)
- Manual refresh button fetches updated result list from backend
- Clicking a result entry navigates to detail view for that specific run

---

### US3: Inspect Detailed Result with Point Clouds and Metadata

**As a** quality assurance engineer,  
**I want to** view all point cloud files and metadata for a specific result,  
**So that** I can validate the output and diagnose any issues.

**Acceptance Criteria:**
- Navigate to `/results/{node_id}/{result_id}` to see detail view
- Detail view displays:
  - **Point Cloud Viewer**: Renders PCD files in Three.js workspace with backend-defined colors
  - **Metadata Panel**: Shows all metadata fields as key-value pairs (table or JSON tree)
  - **Tabbed PCD Selection**: If multiple PCD files exist (e.g., empty, loaded, merged), tabs/dropdown switches between them
  - **Breadcrumb Navigation**: Links back to node result list and main results page
- Point clouds render at 60 FPS using existing Three.js `BufferGeometry` patterns
- Metadata is displayed generically (no hardcoded field names)—handles varying structures across node types
- If result has no PCD files, displays placeholder: "No point cloud data available"
- If result_id is invalid or deleted, shows 404 error with link back to node list

---

### US4: Automatic Result Cleanup on Node Deletion

**As a** system administrator,  
**I want** results to be automatically deleted when their parent node is removed,  
**So that** I don't accumulate orphaned data or need manual cleanup.

**Acceptance Criteria:**
- When a node is deleted via DAG editor, all associated results are deleted from:
  - Database (metadata records)
  - Disk storage (PCD files in `data/results/{node_id}/`)
- Deletion is atomic—DB transaction rollback on file deletion failure
- Logs deletion actions at INFO level: `"Deleted X results for node {node_id}"`
- If user navigates to `/results/{deleted_node_id}`, shows error: "Node not found or deleted"
- No manual cleanup UI needed in MVP

---

### US5: Backend-Defined Result Schema Flexibility

**As a** backend developer implementing a new application node,  
**I want** to define exactly which point clouds and metadata fields to store per result,  
**So that** I can tailor outputs to my node's domain without changing the results storage API.

**Acceptance Criteria:**
- Application nodes generate result payloads with:
  - **Point Cloud Files**: List of numpy arrays with pre-colored RGB data (backend applies domain-specific color schemes before storage)
  - **Metadata Dictionary**: Arbitrary JSON-serializable fields (no validation schema enforcement)
  - **Common Fields**: `timestamp`, `node_id`, `result_id` (auto-generated by storage service)
- Backend provides a `ResultsStorageService` with method: `save_result(node_id: str, pcds: List[Tuple[str, np.ndarray]], metadata: Dict[str, Any]) -> str`
- Service writes PCD files to disk, stores metadata + file paths in DB, returns `result_id`
- Nodes call storage service at the end of processing (e.g., after volume calculation completes)
- Storage service handles file naming conventions, directory structure, and DB transactions
- Example usage pattern documented in technical spec

---

## Acceptance Criteria

### Functional Requirements

#### F1: Database Schema

- [ ] SQLite table `application_results` with columns:
  - `result_id` (TEXT PRIMARY KEY, UUID)
  - `node_id` (TEXT NOT NULL, indexed)
  - `timestamp` (REAL NOT NULL, Unix timestamp)
  - `metadata` (TEXT NOT NULL, JSON serialized)
  - `pcd_files` (TEXT NOT NULL, JSON list of file paths relative to `data/results/`)
  - `status` (TEXT, enum: 'success', 'warning', 'error')
- [ ] Foreign key constraint on `node_id` (references nodes table if exists) with CASCADE DELETE
- [ ] Index on `(node_id, timestamp)` for efficient result listing queries
- [ ] Migration script to create table on first startup (Alembic or equivalent)

#### F2: File Storage Structure

- [ ] Results stored in `data/results/{node_id}/{result_id}/` directory structure
- [ ] PCD files named with descriptive labels: `{label}.pcd` (e.g., `empty.pcd`, `loaded.pcd`, `profile.pcd`)
- [ ] Each PCD file contains RGB color data in standard PCD format
- [ ] Backend creates directories atomically (fail-safe if concurrent writes occur)
- [ ] File paths in DB are relative to `data/results/` root for portability

#### F3: Backend Storage API

- [x] `ResultsStorageService` class in `app/services/results_storage.py` with methods:
  - `save_result(node_id, pcds: List[Tuple[label, points_rgb]], metadata) -> result_id`
  - `get_results_by_node(node_id) -> List[ResultSummary]` (metadata + file paths)
  - `get_result_detail(result_id) -> ResultDetail` (full metadata + PCD file paths)
  - `delete_results_by_node(node_id) -> int` (returns count deleted)
  - `delete_result(result_id) -> bool`
- [x] Service handles:
  - DB transactions (rollback on error)
  - File write failures (atomic cleanup)
  - Concurrent access safety (locks if needed)
  - UUID generation for `result_id`
- [x] Logging at INFO level for save/delete operations

#### F4: Backend REST API Endpoints

- [x] `GET /api/v1/results` → List all application nodes with result counts
- [x] `GET /api/v1/results/{node_id}` → List results for specific node
- [x] `GET /api/v1/results/{node_id}/{result_id}` → Detailed result with metadata
- [x] `GET /api/v1/results/{node_id}/{result_id}/pcd/{label}` → Download specific PCD file
- [x] `DELETE /api/v1/results/{node_id}/{result_id}` → Delete single result (admin/debug)
- [x] Error responses: 404 / 500

#### F5: Node Integration (Example: VolumeCalculationNode)

- [x] `VolumeCalculationNode` calls storage service after successful calculation
- [x] VehicleProfilerNode similarly saves profile slice and metadata
- [x] Storage service usage documented in node implementation guide

#### F9: Lifecycle Integration - Node Deletion

- [x] When node is deleted via DAG editor, all associated results are deleted (DB + disk)
- [x] Deletion is logged at INFO level
- [x] Startup orphan sweep removes disk dirs with no DB record

#### F6: Frontend Results Overview Page

- [x] Route: `/results` displays list of all application nodes with results
- [x] Component: `ResultsOverviewComponent` (standalone, Angular 20)
- [x] Uses `ResultsApiService` to fetch node list on page load
- [x] Manual refresh button calls API again and updates Signal state
- [x] Each node card shows:
  - Node name, type icon (Synergy/Material Icon)
  - Result count badge
  - Last updated timestamp (relative time, e.g., "2 hours ago")
- [x] Click card navigates to `/results/{node_id}`
- [x] Empty state: "No application nodes with results available"

#### F7: Frontend Node Result List Page

- [x] Route: `/results/:nodeId` displays result history for node
- [x] Component: `NodeResultsListComponent` with Signal-based state
- [x] Fetches results via `GET /api/v1/results/{nodeId}` on load
- [x] Displays results as sortable table or card list:
  - Columns: Timestamp, Key Metadata (dynamic), Status
  - Sort by timestamp (newest first default)
- [x] Manual refresh button re-fetches from API
- [x] Click result row navigates to `/results/{nodeId}/{resultId}`
- [x] Breadcrumb: "Results > {Node Name}"
- [x] Empty state: "No results recorded for this node yet"

#### F8: Frontend Result Detail Page

- [x] Route: `/results/:nodeId/:resultId` shows full result
- [x] Component: `ResultDetailComponent` with Three.js integration
- [x] Fetches result metadata via `GET /api/v1/results/{nodeId}/{resultId}`
- [x] Displays:
  - **Metadata Panel**: Renders all metadata fields as key-value table (generic, no hardcoded fields)
  - **PCD Tabs**: If multiple PCD files, tabs/dropdown to switch active file
  - **3D Viewer**: Renders selected PCD using existing Three.js workspace component
- [x] Loads PCD files via `GET /api/v1/results/{nodeId}/{resultId}/pcd/{label}`
- [x] Parses PCD format and extracts XYZ + RGB for Three.js rendering
- [x] Reuses existing `BufferGeometry` mutation patterns (60 FPS, no geometry recreation)
- [x] Breadcrumb: "Results > {Node Name} > {Result Timestamp}"
- [x] Back button or breadcrumb navigation to node result list

#### F9: Lifecycle Integration - Node Deletion

- [ ] When node is deleted via DAG editor (`DELETE /api/v1/nodes/{node_id}`):
  - Calls `results_service.delete_results_by_node(node_id)`
  - Deletes DB records with CASCADE
  - Deletes `data/results/{node_id}/` directory and all contents
- [ ] Deletion is logged: `"Deleted {count} results for node {node_id}"`
- [ ] If directory deletion fails, logs error but completes DB deletion (prevents orphaned DB records)
- [ ] UI shows error if navigating to deleted node's results: "Node not found or has been deleted"

#### F10: Error Handling & Edge Cases

- [ ] **Missing PCD file on disk**: Returns 404 with error message, logs warning
- [ ] **Corrupted metadata JSON**: Displays raw JSON string with warning banner
- [ ] **Invalid result_id**: Returns 404 Not Found
- [ ] **Concurrent node deletion during result save**: Transaction rollback, node save fails gracefully
- [ ] **Disk full during PCD write**: Returns 500 with error, cleans up partial files, logs error
- [ ] **Large PCD files (>50MB)**: Backend streams file response (chunked transfer)
- [ ] **Malformed PCD format**: Frontend displays error message instead of crashing 3D viewer

---

### Non-Functional Requirements

#### NF1: Performance

- [ ] Result listing query (100 results) completes in <100ms
- [ ] PCD file download starts streaming within 200ms for files <10MB
- [ ] Three.js rendering maintains 60 FPS for point clouds up to 100k points
- [ ] Metadata JSON parsing handles up to 1000 fields without UI lag
- [ ] Database indexing ensures O(log n) lookup on `(node_id, timestamp)`

#### NF2: Storage Efficiency

- [ ] PCD files use binary format (not ASCII) to minimize disk usage
- [ ] Metadata JSON is minified (no pretty-printing in DB)
- [ ] No duplicate storage—point clouds saved once per result, referenced by path
- [ ] Disk usage monitoring logged at startup (total size of `data/results/`)

#### NF3: Data Integrity

- [ ] DB transactions ensure atomic writes (metadata + file paths committed together)
- [ ] File deletion on node removal is logged and verified (check directory empty)
- [ ] Foreign key constraints prevent orphaned results if nodes table exists
- [ ] UUID collision probability: <1e-15 (standard UUID4)

#### NF4: Logging & Observability

- [ ] INFO level: Result save/delete operations with node_id, result_id, file count
- [ ] WARNING level: Missing PCD files, disk I/O errors, corrupted metadata
- [ ] ERROR level: DB transaction failures, unexpected exceptions
- [ ] Debug level: Detailed file paths, metadata structure, query execution times

#### NF5: Testing Requirements

- [ ] **Backend Unit Tests**:
  - `ResultsStorageService` save/retrieve/delete operations
  - Concurrent access safety (parallel saves to same node)
  - Rollback on file write failure
  - PCD file path resolution
- [ ] **Backend Integration Tests**:
  - Full result lifecycle: save → list → retrieve detail → delete
  - Node deletion cascades to results
  - API endpoints return correct status codes and payloads
- [ ] **Frontend Unit Tests**:
  - `ResultsApiService` HTTP calls
  - Component state management (Signals)
  - Metadata table rendering with dynamic fields
  - PCD tab switching logic
- [ ] **E2E Tests**:
  - Navigate results overview → node list → detail page
  - Render point cloud in 3D viewer from result
  - Delete node and verify results are cleaned up

---

## Out of Scope

The following are **explicitly excluded** from this MVP feature:

- ❌ **Real-Time Result Notifications**: No WebSocket broadcasting when new results are saved. Results fetched on page load/refresh only.
- ❌ **Export Functionality**: No download buttons for individual results or batch ZIP export. Users can only view results in the UI.
- ❌ **Result Comparison**: No side-by-side diff, overlay mode, or metadata comparison between results.
- ❌ **Configurable Retention Policy UI**: Retention limits (e.g., last N results, time-based expiry) deferred to settings page in future iteration.
- ❌ **Search & Filtering**: No keyword search, metadata filtering, or date range queries in result lists.
- ❌ **Sorting & Pagination**: Results displayed in fixed newest-first order. Pagination deferred until result counts exceed 100.
- ❌ **Result Sharing**: No permalink generation, sharing via email/link, or access control.
- ❌ **Custom Metadata Schemas**: No Pydantic validation or node-specific schema enforcement. All metadata is free-form JSON.
- ❌ **Dynamic Color Mapping**: Backend pre-colors point clouds. No frontend color scheme editor or dynamic intensity mapping.
- ❌ **Result Annotations**: No ability to add comments, tags, or notes to results.
- ❌ **Performance Metrics Dashboard**: No aggregate statistics, trend charts, or performance monitoring for results.
- ❌ **Multi-Node Result Correlation**: No linking or grouping results across multiple nodes (e.g., "all results from the same vehicle event").
- ❌ **Batch Delete**: No UI to delete multiple results at once. Single result deletion is admin/debug only.
- ❌ **Result Restore**: No undo/restore functionality after deletion. Deletes are permanent.

---

## Technical Constraints

### Backend Constraints

- **Database**: SQLite only (no PostgreSQL/MySQL support in MVP). JSON storage in TEXT columns.
- **File Format**: PCD (Point Cloud Data) format only. No PLY, LAS, or custom formats.
- **Storage Location**: Local disk (`data/results/`) only. No cloud storage (S3, Azure Blob).
- **Concurrency**: Single-instance backend (no distributed locking needed). Use Python threading locks if concurrent access is detected.
- **Heavy I/O**: PCD file writes run in threadpool (`asyncio.to_thread`) to avoid blocking FastAPI event loop.

### Frontend Constraints

- **Angular 20 Standalone Components**: No NgModules. All components use Signals for state.
- **Three.js Rendering**: Reuse existing workspace patterns—mutate `BufferGeometry` arrays, no geometry recreation.
- **PCD Parsing**: Custom PCD parser (ASCII and binary formats) implemented in frontend service.
- **No External Libraries**: No PCD.js or other point cloud libraries. Use native Three.js only.
- **Responsive Design**: Desktop-first. Mobile/tablet layout deferred to future iteration.

### Performance Constraints

- **Max PCD File Size**: 50MB per file (larger files may cause frontend memory issues).
- **Max Point Count**: 100k points per PCD for 60 FPS rendering.
- **Metadata Field Limit**: Up to 1000 fields per result (beyond this, performance degrades).
- **Result Count**: Performant up to 100 results per node (pagination needed beyond this).

---

## Dependencies & Prerequisites

### Backend Dependencies

- **Existing**:
  - FastAPI, SQLite, Open3D, asyncio
  - `app/services/nodes/` orchestrator for node lifecycle hooks
  - `app/core/logging` for consistent logging
- **New**:
  - `app/services/results_storage.py` (ResultsStorageService)
  - SQLite table migration script
  - API route handlers in `app/api/v1/results/`

### Frontend Dependencies

- **Existing**:
  - Angular 20 (Signals, Standalone Components, Router)
  - Three.js workspace component (`features/workspaces/`)
  - Tailwind CSS + Synergy UI
- **New**:
  - `core/services/api/results-api.service.ts`
  - `features/results/` feature module (overview, list, detail components)
  - PCD parser service (`core/services/pcd-parser.service.ts`)

### Data Dependencies

- Application nodes must call `results_service.save_result()` after processing
- Point clouds must be pre-colored (RGB) by backend before storage
- Metadata must be JSON-serializable (no numpy arrays, datetime objects)

---

## Open Questions for Architecture & Planning

The following questions need resolution during the Architecture phase (documented in `technical.md`):

### Backend Questions

1. **DB Migration Strategy**: Use Alembic or custom SQLite migration script? Should we version schema?
2. **File Naming Collision**: If a node produces two PCDs with the same label in different runs, how to handle? (Proposed: label is unique per result_id directory).
3. **Transaction Isolation**: SQLite default isolation level sufficient, or need explicit `BEGIN IMMEDIATE`?
4. **Disk Space Monitoring**: Should backend enforce storage quotas? Log warnings at X% full?
5. **PCD Format Version**: Standard PCD 0.7 format, or Open3D-specific extensions?
6. **Metadata Size Limit**: Enforce max JSON size (e.g., 1MB) to prevent DB bloat?
7. **Color Storage**: Store RGB as separate fields or packed into single integer in PCD?

### Frontend Questions

8. **PCD Parsing Library**: Implement custom parser or adapt open-source PCD.js? (Constraint: no external deps preferred).
9. **Three.js Integration**: Create new viewer component or extend existing workspace component?
10. **Metadata Rendering**: Use Synergy UI table component, or custom JSON tree viewer?
11. **Tab State Management**: Store active PCD tab in URL query param (e.g., `?pcd=loaded`) or component state only?
12. **Error Boundaries**: How to handle PCD parsing failures gracefully without crashing page?
13. **Loading States**: Skeleton loaders, spinners, or progress bars for PCD downloads?

### API Design Questions

14. **Pagination**: Should `GET /results/{node_id}` support `limit`/`offset` in MVP, or defer?
15. **Result Ordering**: Always newest-first, or allow query param `?sort=timestamp_asc`?
16. **Partial Responses**: Should metadata be summarized in list view (subset of fields) or full payload?
17. **CORS & Auth**: Results API requires authentication, or open like other internal endpoints?

---

## Success Metrics

### Quantitative

- [ ] Backend saves result (3 PCDs + metadata) in <500ms (excluding heavy computation time)
- [ ] Result listing page loads and renders 50 results in <1 second
- [ ] Result detail page renders 100k-point PCD at 60 FPS
- [ ] Node deletion cleans up 100 results (including files) in <5 seconds
- [ ] Zero DB corruption or orphaned files after 100 node create/delete cycles
- [ ] Unit test coverage >80% for backend storage service and frontend components

### Qualitative

- [ ] Operators can inspect any historical result within 3 clicks (overview → node → result)
- [ ] Result detail page clearly displays all metadata fields without developer intervention
- [ ] Point cloud coloring accurately reflects backend's domain logic (e.g., volume grid height)
- [ ] Engineers can implement new application nodes using storage service without modifying results UI
- [ ] No manual cleanup required—node deletion automatically removes all associated data

---

## Risk Assessment & Mitigation

### High-Risk Areas

1. **Disk Space Exhaustion**
   - **Risk**: Unbounded result storage fills disk over time.
   - **Mitigation**: Log disk usage at startup. Document retention policy requirement for future settings page.

2. **Large PCD File Performance**
   - **Risk**: 50MB+ files cause frontend memory crashes or slow rendering.
   - **Mitigation**: Enforce max file size in backend. Implement streaming/chunked download if needed.

3. **Schema Evolution**
   - **Risk**: Future nodes produce incompatible metadata structures.
   - **Mitigation**: Free-form JSON design allows flexibility. Document best practices for node developers.

4. **Concurrent Access Race Conditions**
   - **Risk**: Parallel result saves to same node cause file conflicts.
   - **Mitigation**: UUID-based result_id ensures unique directories. DB transactions handle metadata atomicity.

5. **Frontend PCD Parsing Complexity**
   - **Risk**: Custom parser is bug-prone, fails on edge cases (binary PCD, endianness).
   - **Mitigation**: Thorough unit testing. Consider Open3D Python PCD export as reference implementation.

### Medium-Risk Areas

6. **Node Deletion Cascade Failures**
   - **Risk**: DB deletes succeed but file deletion fails (permissions, disk error).
   - **Mitigation**: Log errors. Consider background cleanup job to sweep orphaned files.

7. **Metadata Display Edge Cases**
   - **Risk**: Deeply nested JSON or large arrays crash frontend table renderer.
   - **Mitigation**: Truncate/collapse large values. Display "View Full JSON" modal for complex structures.

---

## Stakeholder Clarifications Needed

The following points require explicit confirmation or input from stakeholders before proceeding to architecture:

### Must Clarify

1. **Retention Policy Timeline**: When will the settings page for retention limits be implemented? Should we hard-code a default (e.g., last 100 results) as a safeguard in MVP?

2. **Result Access Control**: Are results considered sensitive data? Do we need user authentication/authorization checks on result API endpoints?

3. **Node Type Filtering**: Should the results overview page show ALL nodes in DAG, or only application nodes (type="application")? What about flow_control or processing nodes that might produce results in the future?

4. **PCD File Size Realism**: What is the realistic max PCD size we expect from vehicle_profiler and volume_calculation? Do we need to support >50MB files, or is this a safe hard limit?

5. **Offline/Export Priority**: User selected "No export in MVP", but is there pressure to deliver export before full release? Should we design API with export in mind even if UI deferred?

### Nice to Clarify (Lower Priority)

6. **Color Scheme Documentation**: Should backend nodes document their coloring logic somewhere (e.g., "height mapped to blue-red gradient")? Or assume operators understand the domain?

7. **Error Recovery UX**: If a result's PCD file is missing/corrupted, should we hide the 3D viewer and only show metadata, or display a placeholder "corrupted data" mesh?

8. **Performance Baseline**: What is the typical result generation frequency? (e.g., 1 result per minute? per second?) This affects DB indexing and refresh UX decisions.

---

## Next Steps for Architecture & Planning

1. **@architecture**: Design `ResultsStorageService` API and DB schema in `technical.md`
   - Confirm UUID4 for `result_id` vs sequential integers
   - Specify PCD file naming conventions (label uniqueness, sanitization)
   - Define transaction boundaries and rollback behavior
   - Document integration hooks for application nodes

2. **@architecture**: Define REST API contract in `api-spec.md`
   - Specify exact JSON response schemas for each endpoint
   - Clarify pagination strategy (even if deferred)
   - Document error response formats
   - Include example payloads for VehicleProfiler and VolumeCalculation results

3. **@architecture**: Specify frontend component structure in `technical.md`
   - Component hierarchy (overview → list → detail)
   - Signal-based state management patterns
   - PCD parser implementation approach
   - Three.js integration strategy (extend workspace or new component)

4. **@architecture**: Address open questions and clarify risks in `technical.md`

5. **@be-dev** & **@fe-dev**: Review `technical.md` and `api-spec.md` before breaking down into tasks

6. **@qa**: Define test scenarios in `qa-tasks.md`:
   - Result lifecycle testing (save, retrieve, delete)
   - PCD rendering with varying file sizes and formats
   - Edge cases (missing files, corrupted metadata, concurrent access)
   - Node deletion cascade verification

---

**Document Status:** ✅ READY FOR ARCHITECTURE REVIEW  
**Next Phase:** Architecture to produce `technical.md` and `api-spec.md`  
**Blocked On:** Stakeholder clarifications (retention policy timeline, file size limits, access control requirements)
