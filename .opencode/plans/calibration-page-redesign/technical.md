# Technical Design: Calibration Page Redesign

**Feature:** `calibration-page-redesign`
**Author:** Architecture
**Status:** Approved for Development

---

## 1. Architecture Overview

The calibration page redesign separates **workflow actions** (trigger, accept, reject, rollback) from **passive status display** in the DAG flow canvas. The goal is a clean separation of concerns:

| Layer | Before | After |
|---|---|---|
| DAG node card (`node-calibration-controls`) | Trigger + Accept + Reject buttons | Status badge + "Go to Calibration →" link only |
| `CalibrationComponent` (`/calibration`) | Read-only node list via WebSocket | Node list + Trigger action, 2s HTTP polling |
| `CalibrationViewerComponent` (`/calibration/:id`) | Broken (always null) | Fixed; shows current status + full workflow via polling |
| `CalibrationHistoryComponent` (`/calibration/:id/history`) | History only | History accordion per sensor, Δ-delta table, rollback per entry |

### Interaction Pattern Split

```
WebSocket (system_status topic)
  └── StatusWebSocketService.status()
        └── Used by: CalibrationComponent (list), node-calibration-controls (status badge only)
        └── Payload: NodeStatusUpdate { operational_state, application_state{label:"calibrating", value:bool} }

HTTP Polling (2 second interval)
  └── CalibrationStoreService.startPolling(nodeId)
        └── Calls: GET /api/v1/calibration/{node_id}/status
        └── Used by: CalibrationComponent (per selected node), CalibrationViewerComponent
        └── Payload: CalibrationNodeStatusResponse (see section 5)
```

---

## 2. Backend Changes

### 2.1 Database Migration (`app/db/migrate.py` + `app/db/models.py`)

Add 5 new nullable columns to `calibration_history`. Keep all existing columns intact.

**Columns to ADD:**

| Column | Type | SQL Default | Purpose |
|---|---|---|---|
| `node_id` | `TEXT` | `NULL` | FK to `nodes.id` — which calibration node ran this |
| `accepted_at` | `TEXT` | `NULL` | ISO-8601 timestamp when user clicked Accept |
| `accepted_by` | `TEXT` | `NULL` | Reserved for future auth (always `NULL` now) |
| `rollback_source_id` | `TEXT` | `NULL` | FK to `calibration_history.id` of the entry that was rolled-back to |
| `registration_method_json` | `TEXT` | `'null'` | JSON: `{"method": "icp", "stages": ["global","icp"]}` |

**Migration pattern** (follows existing `ensure_schema` in `app/db/migrate.py`):

```python
# In ensure_schema(), add inside the `with engine.begin() as conn:` block:
cal_cols = _table_cols(conn, "calibration_history")
if "node_id" not in cal_cols:
    conn.execute(text("ALTER TABLE calibration_history ADD COLUMN node_id TEXT"))
if "accepted_at" not in cal_cols:
    conn.execute(text("ALTER TABLE calibration_history ADD COLUMN accepted_at TEXT"))
if "accepted_by" not in cal_cols:
    conn.execute(text("ALTER TABLE calibration_history ADD COLUMN accepted_by TEXT"))
if "rollback_source_id" not in cal_cols:
    conn.execute(text("ALTER TABLE calibration_history ADD COLUMN rollback_source_id TEXT"))
if "registration_method_json" not in cal_cols:
    conn.execute(text("ALTER TABLE calibration_history ADD COLUMN registration_method_json TEXT DEFAULT 'null'"))
```

**ORM Model update** (`app/db/models.py`, `CalibrationHistoryModel`):

Add 5 new `Mapped` columns:
```python
node_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
accepted_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
accepted_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
rollback_source_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
registration_method_json: Mapped[str] = mapped_column(String, default="null")
```

Update `to_dict()` to include these fields:
```python
"node_id": self.node_id,
"accepted_at": self.accepted_at,
"accepted_by": self.accepted_by,
"rollback_source_id": self.rollback_source_id,
"registration_method": json.loads(self.registration_method_json or "null"),
```

### 2.2 ORM Functions (`app/repositories/calibration_orm.py`)

**Modify `create_calibration_record()`**: Add 5 new optional parameters (`node_id`, `accepted_at`, `accepted_by`, `rollback_source_id`, `registration_method`) and pass them to the model. Keep all existing parameters unchanged — backward compatible.

**Modify `update_calibration_acceptance()`** (currently orphaned, now gets called): Add `accepted_at` parameter. When `accepted=True`, set `record.accepted_at = datetime.now(timezone.utc).isoformat()`. This function is now the single path for persisting acceptance.

**Add `get_calibration_history_by_node()`**:
```python
def get_calibration_history_by_node(
    db: Session,
    node_id: str,
    limit: Optional[int] = None,
    run_id: Optional[str] = None
) -> List[CalibrationHistoryModel]:
```
Queries `WHERE node_id = :node_id`, optionally filtered by `run_id`, ordered `DESC` by `timestamp`.

**Add `get_calibration_history_by_run()`**: Already exists — verify it returns full `to_dict()` data.

**Modify `get_calibration_history()`**: Add optional `run_id: Optional[str] = None` parameter. When provided, chain `.filter(CalibrationHistoryModel.run_id == run_id)`.

### 2.3 `CalibrationNode` Changes (`app/modules/calibration/calibration_node.py`)

**Problem 1 — Calibration status is opaque in the current `emit_status()`**: The existing `emit_status()` uses `OperationalState.RUNNING` for all active states and squashes the calibration workflow state into `application_state.value` (bool). This is sufficient for the WebSocket status badge, but the calibration page needs richer detail.

**New `get_calibration_status()` method** (NOT `emit_status()` — that stays unchanged):
```python
def get_calibration_status(self) -> Dict[str, Any]:
    """
    Return full calibration workflow state for the polling endpoint.
    Unlike emit_status() which is for WebSocket broadcast, this returns
    the complete state needed by the calibration page.
    """
    calibration_state = "idle"
    if self._pending_calibration is not None:
        calibration_state = "pending"
    
    pending_results = {}
    if self._pending_calibration:
        for sensor_id, record in self._pending_calibration.items():
            pending_results[sensor_id] = {
                "fitness": record.fitness,
                "rmse": record.rmse,
                "quality": record.quality,
                "quality_good": record.fitness >= self.min_fitness_to_save,
                "source_sensor_id": record.source_sensor_id,
                "processing_chain": record.processing_chain or [],
                "pose_before": record.pose_before.to_flat_dict(),
                "pose_after": record.pose_after.to_flat_dict(),
                "transformation_matrix": record.transformation_matrix,
            }
    
    return {
        "node_id": self.id,
        "node_name": self.name,
        "enabled": self._enabled,
        "calibration_state": calibration_state,   # "idle" | "pending"
        "quality_good": all(
            r.fitness >= self.min_fitness_to_save
            for r in (self._pending_calibration or {}).values()
        ) if self._pending_calibration else None,
        "reference_sensor_id": self._reference_sensor_id,
        "source_sensor_ids": list(self._source_sensor_ids),
        "buffered_frames": {k: len(v) for k, v in self._frame_buffer.items()},
        "last_calibration_time": self._last_calibration_time,
        "pending_results": pending_results,
    }
```

**Fix `sample_frames` default inconsistency**: In `dto.py`, `TriggerCalibrationRequest.sample_frames` defaults to `1`. In `calibration_node.py` `trigger_calibration()`, the `params.get("sample_frames", 5)` default is `5`. These must be unified. **Change both to `5`**:
- `app/api/v1/calibration/dto.py`: `sample_frames: int = 5`
- `app/modules/calibration/calibration_node.py`: `sample_frames = params.get("sample_frames", 5)` (already 5, confirm unchanged)

**Fix `accept_calibration()` to stamp `accepted_at`** on the history record: After calling `CalibrationHistory.save_record()`, call `calibration_orm.update_calibration_acceptance()` with `accepted=True` and `accepted_at=now`. Since the record is freshly created, use `record_id` returned from `create_calibration_record()`.

**Pass `node_id` when saving records**: In `CalibrationHistory.save_record()`, add `node_id` parameter and pass it to `calibration_orm.create_calibration_record()`.

### 2.4 Fix `CalibrationHistory.rollback_to()` (`app/modules/calibration/history.py`)

**Current bug**: `rollback_to()` updates the pose in the database but does NOT trigger a DAG reload, so the sensor keeps using its old in-memory transformation.

**Fix**: The static method cannot call `manager.reload_config()` directly (it has no reference to the manager). The fix is to **remove** `rollback_to()` from `CalibrationHistory` and instead perform rollback entirely in `app/api/v1/calibration/service.py` → `rollback_calibration()`, which already has access to `node_manager`.

The existing `rollback_calibration()` in `service.py` **already calls** `await node_manager.reload_config()` (line 225). It just needs to be updated to accept a `record_id` (PK) instead of `timestamp` for reliable lookup.

**Change rollback to use `record_id` (PK) instead of `timestamp`**:
- `RollbackRequest.timestamp: str` → `RollbackRequest.record_id: str`
- `rollback_calibration()` in `service.py`: use `calibration_orm.get_calibration_by_id(db, request.record_id)` instead of `get_calibration_by_timestamp()`
- Set `rollback_source_id` on a new `CalibrationHistoryModel` (or update the rolled-back record): create a new "rollback" history record with `rollback_source_id = request.record_id`, `accepted=True`, `accepted_at=now`, `pose_before=current_pose`, `pose_after=record.pose_after`

### 2.5 New and Modified API Endpoints (`app/api/v1/calibration/handler.py` + `service.py`)

#### NEW: `GET /api/v1/calibration/{node_id}/status`

**Purpose**: Polling endpoint (2s interval) returning full calibration workflow state.

**Handler** (`handler.py`):
```python
@router.get(
    "/calibration/{node_id}/status",
    response_model=CalibrationNodeStatusResponse,
    responses={404: {"description": "Node not found"}},
    summary="Get Calibration Node Status",
    description="Poll calibration node status (2s interval). Returns calibration_state, pending results, quality.",
)
async def calibration_status_endpoint(node_id: str):
    return await get_calibration_status(node_id)
```

**Service function** (`service.py`):
```python
async def get_calibration_status(node_id: str) -> Dict[str, Any]:
    node = node_manager.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    if not isinstance(node, CalibrationNode):
        raise HTTPException(status_code=400, detail=f"Node {node_id} is not a calibration node")
    return node.get_calibration_status()
```

#### MODIFIED: `POST /api/v1/calibration/{node_id}/reject`

**Current problem**: Returns `{"status": "success"}` (`StatusResponse`). `CalibrationRejectResponse` in the frontend model expects `{"success": bool, "rejected": string[]}`.

**Fix in `service.py`**:
```python
async def reject_calibration(node_id: str):
    node = node_manager.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, ...)
    if not isinstance(node, CalibrationNode):
        raise HTTPException(status_code=400, ...)
    rejected_ids = list((node._pending_calibration or {}).keys())
    await node.reject_calibration()
    return {"success": True, "rejected": rejected_ids}
```

**Fix `response_model`** in `handler.py`: Change from `StatusResponse` to a new `RejectResponse` Pydantic model.

**New schema** in `app/api/v1/schemas/calibration.py`:
```python
class RejectResponse(BaseModel):
    success: bool
    rejected: List[str]  # leaf sensor IDs whose pending results were discarded
```

#### MODIFIED: `GET /api/v1/calibration/history/{sensor_id}`

Add `run_id: Optional[str] = None` query parameter. When provided, pass to `get_calibration_history()` in `service.py`, which passes it to `calibration_orm.get_calibration_history()`.

#### MODIFIED: `POST /api/v1/calibration/rollback/{sensor_id}`

Change from timestamp-based to ID-based lookup (see section 2.4 above). Update `RollbackRequest` DTO.

#### NEW SCHEMA: `CalibrationNodeStatusResponse`

Add to `app/api/v1/schemas/calibration.py`:
```python
class PendingCalibrationResult(BaseModel):
    fitness: float
    rmse: float
    quality: str
    quality_good: bool
    source_sensor_id: Optional[str] = None
    processing_chain: List[str] = []
    pose_before: Dict[str, float]   # {x,y,z,roll,pitch,yaw} in mm/degrees
    pose_after: Dict[str, float]    # {x,y,z,roll,pitch,yaw} in mm/degrees
    transformation_matrix: List[List[float]]  # 4x4

class CalibrationNodeStatusResponse(BaseModel):
    node_id: str
    node_name: str
    enabled: bool
    calibration_state: str          # "idle" | "pending"
    quality_good: Optional[bool]    # None if no pending; True if all results above threshold
    reference_sensor_id: Optional[str]
    source_sensor_ids: List[str]
    buffered_frames: Dict[str, int] # {sensor_id: frame_count}
    last_calibration_time: Optional[str]
    pending_results: Dict[str, PendingCalibrationResult]
```

### 2.6 New Schema for Full History Record

Extend `CalibrationRecord` in `app/api/v1/schemas/calibration.py` to include all new fields:
```python
class CalibrationRecord(BaseModel):
    id: str
    sensor_id: str
    reference_sensor_id: str
    timestamp: str
    accepted: bool
    accepted_at: Optional[str] = None
    accepted_by: Optional[str] = None
    fitness: Optional[float] = None
    rmse: Optional[float] = None
    quality: Optional[str] = None
    stages_used: List[str] = []
    pose_before: Optional[Dict[str, float]] = None   # {x,y,z,roll,pitch,yaw} in mm/degrees
    pose_after: Optional[Dict[str, float]] = None
    transformation_matrix: Optional[List[List[float]]] = None
    source_sensor_id: Optional[str] = None
    processing_chain: List[str] = []
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    rollback_source_id: Optional[str] = None
    registration_method: Optional[Dict[str, Any]] = None
    notes: str = ""
```

---

## 3. Frontend Changes

### 3.1 New `CalibrationStoreService` (`web/src/app/core/services/stores/calibration-store.service.ts`)

Follows the exact pattern of `RecordingStoreService` — extends `SignalsSimpleStoreService<CalibrationState>`, `providedIn: 'root'`.

**State shape:**
```typescript
export interface CalibrationState {
  // Per-node polling data (keyed by node_id)
  nodeStatuses: Record<string, CalibrationNodeStatusResponse>;
  // Currently active poll node ID
  pollingNodeId: string | null;
  // History per sensor_id
  historyByNode: Record<string, CalibrationHistoryRecord[]>;
  // Loading flags
  isLoadingStatus: boolean;
  isLoadingHistory: boolean;
  isTriggering: boolean;
  isAccepting: boolean;
  isRejecting: boolean;
  isRollingBack: boolean;
  error: string | null;
}
```

**Polling mechanism**: Uses `setInterval` (NOT RxJS `interval`, per the rules: RxJS is only for HTTP streams and WebSocket). The store holds a `private _pollTimer: ReturnType<typeof setInterval> | null = null`.

```typescript
startPolling(nodeId: string): void {
  this.stopPolling();
  this.setState({ pollingNodeId: nodeId });
  // Immediate fetch, then repeat
  this._fetchStatus(nodeId);
  this._pollTimer = setInterval(() => this._fetchStatus(nodeId), 2000);
}

stopPolling(): void {
  if (this._pollTimer) {
    clearInterval(this._pollTimer);
    this._pollTimer = null;
  }
  this.setState({ pollingNodeId: null });
}

private async _fetchStatus(nodeId: string): Promise<void> {
  try {
    const status = await this.calibrationApi.getNodeStatus(nodeId);
    const current = this.nodeStatuses();
    this.setState({ nodeStatuses: { ...current, [nodeId]: status } });
  } catch {
    // Silently ignore poll failures — stale data is better than crash
  }
}
```

**Action methods** (all `async`, update loading flags, call `CalibrationApiService`, update state on success):
- `triggerCalibration(nodeId, request)` — sets `isTriggering`, calls API
- `acceptCalibration(nodeId, request)` — sets `isAccepting`, calls API, then re-fetches status
- `rejectCalibration(nodeId)` — sets `isRejecting`, calls API, then re-fetches status
- `rollbackHistory(sensorId, recordId)` — sets `isRollingBack`, calls API
- `loadHistory(nodeId, limit?, runId?)` — sets `isLoadingHistory`, stores in `historyByNode`

**Selectors:**
```typescript
nodeStatuses = this.select('nodeStatuses');
isLoadingStatus = this.select('isLoadingStatus');
isTriggering = this.select('isTriggering');
isAccepting = this.select('isAccepting');
isRejecting = this.select('isRejecting');
isRollingBack = this.select('isRollingBack');
error = this.select('error');

// Computed: get status for a specific node
getNodeStatus = computed(() => {
  const statuses = this.nodeStatuses();
  return (nodeId: string): CalibrationNodeStatusResponse | null =>
    statuses[nodeId] ?? null;
});
```

Export from `web/src/app/core/services/stores/index.ts`.

### 3.2 New `CalibrationApiService` Addition (`web/src/app/core/services/api/calibration-api.service.ts`)

Add `getNodeStatus()` method (new polling endpoint):
```typescript
async getNodeStatus(nodeId: string): Promise<CalibrationNodeStatusResponse> {
  return await firstValueFrom(
    this.http.get<CalibrationNodeStatusResponse>(
      `${environment.apiUrl}/calibration/${nodeId}/status`,
    ),
  );
}
```

Update `rollback()` to send `record_id` instead of `timestamp`:
```typescript
// CalibrationRollbackRequest: { record_id: string }  (was timestamp: string)
async rollback(sensorId: string, request: CalibrationRollbackRequest): Promise<CalibrationRollbackResponse>
```

### 3.3 New/Updated Models (`web/src/app/core/models/calibration.model.ts`)

**Add new types:**

```typescript
// Response from GET /api/v1/calibration/{node_id}/status
export interface PendingCalibrationResult {
  fitness: number;
  rmse: number;
  quality: 'excellent' | 'good' | 'poor';
  quality_good: boolean;
  source_sensor_id?: string;
  processing_chain: string[];
  pose_before: Pose;
  pose_after: Pose;
  transformation_matrix: number[][];
}

export interface CalibrationNodeStatusResponse {
  node_id: string;
  node_name: string;
  enabled: boolean;
  calibration_state: 'idle' | 'pending';
  quality_good: boolean | null;
  reference_sensor_id: string | null;
  source_sensor_ids: string[];
  buffered_frames: Record<string, number>;
  last_calibration_time: string | null;
  pending_results: Record<string, PendingCalibrationResult>;
}

// Updated rollback request
export interface CalibrationRollbackRequest {
  record_id: string;   // was: timestamp: string
}

// Delta pose for display
export interface PoseDelta {
  dx: number;   // mm
  dy: number;   // mm
  dz: number;   // mm
  droll: number;   // degrees
  dpitch: number;  // degrees
  dyaw: number;    // degrees
}
```

**Update `CalibrationHistoryRecord`** to include new fields:
```typescript
export interface CalibrationHistoryRecord {
  // ... existing fields ...
  accepted_at?: string;
  accepted_by?: string;
  node_id?: string;
  rollback_source_id?: string;
  registration_method?: { method: string; stages: string[] } | null;
  pose_before: Pose;        // x,y,z in mm; roll,pitch,yaw in degrees
  pose_after: Pose;         // x,y,z in mm; roll,pitch,yaw in degrees
  transformation_matrix: number[][];  // 4x4
}
```

### 3.4 `node-calibration-controls` — Remove Action Buttons

**File:** `web/src/app/features/settings/components/flow-canvas/node/node-calibration-controls/node-calibration-controls.ts`

**Changes:**
1. Remove `triggerCalibration()`, `acceptCalibration()`, `rejectCalibration()` methods entirely
2. Remove `CalibrationApiService` injection
3. Remove `isCalibrating`, `calibrationError` signals
4. Remove `ToastService` injection
5. Add `Router` injection
6. Add `navigateToCalibration()` method: `this.router.navigate(['/calibration', this.node().id])`
7. Keep `hasPendingCalibration` computed signal (status badge display only)

**Template** (`node-calibration-controls.html`) — replace entirely:
```html
<!-- Calibration Status Badge -->
<div class="flex items-center gap-1">
  @if (hasPendingCalibration()) {
    <syn-badge variant="warning" size="small">Pending</syn-badge>
  } @else {
    <syn-badge variant="neutral" size="small">Idle</syn-badge>
  }
  <syn-icon-button
    (click)="navigateToCalibration(); $event.stopPropagation()"
    label="Go to Calibration Page"
    name="open_in_new"
    size="small"
    title="Go to Calibration"
  />
</div>
```

### 3.5 `CalibrationNodeCardComponent` — Status Display Only (No Changes Required)

**File:** `web/src/app/plugins/calibration/node/calibration-node-card.component.ts`

The existing `CalibrationNodeCardComponent` already shows only status (reference sensor, source sensor count, buffered frames, pending count, last calibration time). No action buttons are present. **This component requires no code changes** — it is already conformant with the new design.

The card still reads from `CalibrationNodeStatus` via WebSocket. However, `CalibrationNodeStatus` is the old legacy type. After the redesign, the card receives a `NodeStatusUpdate` via the `status` input (standardized format). Confirm the `hasPendingCalibration` computed in the card reads `application_state.label === 'calibrating' && application_state.value === true` rather than the old `has_pending` field (this is already handled in `NodeCalibrationControls.hasPendingCalibration` — verify the card's own computed does the same).

### 3.6 `CalibrationComponent` (List Page) — Major Redesign

**File:** `web/src/app/features/calibration/calibration.component.ts`

**Inject:** `CalibrationStoreService`, `NodeStoreService`, `ToastService`

**Remove:** `hasPendingResults()`, `getPendingResultsList()`, `getBufferedFrameCount()`, `getBufferedFrameEntries()`, `formatTime()`, `getQualityVariant()` — all move to the store or become computed.

**New computed signals:**
```typescript
// Calibration nodes from node store (config, not WebSocket)
calibrationNodeConfigs = computed(() =>
  this.nodeStore.calibrationNodes()
);

// Per-node status from WebSocket (lightweight: operational_state + calibrating bool)
getNodeWsStatus = computed(() => {
  const map = this.nodeStore.nodeStatusMap();
  return (nodeId: string) => map.get(nodeId) ?? null;
});

// Per-node polled status (rich: pending_results, poses)
getNodePolledStatus = computed(() => {
  const statuses = this.calibrationStore.nodeStatuses();
  return (nodeId: string): CalibrationNodeStatusResponse | null => statuses[nodeId] ?? null;
});
```

**On `ngOnInit`** (or `constructor effect`): For each calibration node in `calibrationNodeConfigs()`, start polling its status. Since this is a list page, poll all nodes (most users will have 1-2 calibration nodes).

**Trigger action on list page**: Each node card shows a "Run Calibration" button. On click, call `this.calibrationStore.triggerCalibration(nodeId, {})`. Show toast on success/failure via `effect()` on `calibrationStore.error`.

**Template changes** (`calibration.component.html`):
- Replace WebSocket-sourced `calibrationNodes()` with `calibrationNodeConfigs()`
- Show WebSocket `operational_state` badge (`RUNNING`/`STOPPED`/`ERROR`) from `getNodeWsStatus(nodeId)()`
- Show "calibrating" pill badge when `application_state.label === 'calibrating' && application_state.value === true`
- Replace "Pending Results" section with polled data from `getNodePolledStatus(nodeId)()`
- Add "Run Calibration" button per card (calls `triggerCalibration`)
- Keep "View Details" link → `/calibration/:id`
- Keep "View History" link → `/calibration/:id/history`

### 3.7 `CalibrationViewerComponent` (Detail Page) — Full Rebuild

**File:** `web/src/app/features/calibration/components/calibration-viewer/calibration-viewer.component.ts`

**Root cause of the bug**: `calibrationNode` is a `computed(() => null)` with a TODO comment (line 59-63). It tries to derive status from a non-existent endpoint.

**Fix**: Inject `CalibrationStoreService`. In the constructor `effect`:
```typescript
effect(() => {
  const id = this.route.snapshot.paramMap.get('id');
  if (id) {
    this.nodeId.set(id);
    this.calibrationStore.startPolling(id);      // 2s polling
    this.calibrationStore.loadHistory(id, 50);   // eager load history
  }
}, { allowSignalWrites: true });
```

**Replace `calibrationNode` computed**:
```typescript
calibrationNode = computed<CalibrationNodeStatusResponse | null>(() =>
  this.calibrationStore.getNodeStatus()(this.nodeId())
);
```

**On destroy** (`ngOnDestroy`): `this.calibrationStore.stopPolling()`.

**Add computed signals for transformation deltas** (pure functions, no side effects):
```typescript
// Returns PoseDelta for a pending result
poseDelta = (result: PendingCalibrationResult): PoseDelta => ({
  dx: result.pose_after.x - result.pose_before.x,
  dy: result.pose_after.y - result.pose_before.y,
  dz: result.pose_after.z - result.pose_before.z,
  droll: result.pose_after.roll - result.pose_before.roll,
  dpitch: result.pose_after.pitch - result.pose_before.pitch,
  dyaw: result.pose_after.yaw - result.pose_before.yaw,
});
```

**New `showMatrix` signals**: `showMatrixFor = signal<Record<string, boolean>>({})` — tracks which sensor's 4×4 matrix is expanded. Toggle with `toggleMatrix(sensorId: string)`.

**Workflow actions** (moved from `node-calibration-controls`):
- `triggerCalibration()` → `this.calibrationStore.triggerCalibration(this.nodeId(), {})`
- `acceptCalibration(sensorIds)` → `this.calibrationStore.acceptCalibration(this.nodeId(), { sensor_ids: sensorIds })`
- `rejectCalibration()` → `this.calibrationStore.rejectCalibration(this.nodeId())`

**Template structure** (`calibration-viewer.component.html`):
- Header: Node name, ID, status badge (from polled data), Back button
- Section 1: **Node Status Card** — `calibration_state`, enabled, buffered frames, last calibration time
- Section 2: **Pending Results Card** (shown only when `calibration_state === 'pending'`):
  - Per-sensor subsection:
    - Quality badge + fitness/RMSE values
    - **Δ-pose table**: `Δx`, `Δy`, `Δz` (mm), `Δroll`, `Δpitch`, `Δyaw` (°)
    - **Raw matrix toggle**: `syn-details` (expandable, shows 4×4 grid)
  - Accept / Reject buttons (+ dialogs)
- Section 3: **Calibration History** accordion (loads from `calibrationStore.historyByNode[nodeId]`)
  - Grouped by `source_sensor_id`
  - Per entry: timestamp, quality, fitness, Δ-pose table, Rollback button (if `accepted === true`)

**Rollback per history entry** (not just most recent):
```typescript
async rollbackToEntry(sensorId: string, record: CalibrationHistoryRecord): Promise<void> {
  await this.calibrationStore.rollbackHistory(sensorId, record.id);
  // toast on success
}
```

### 3.8 History Page — Add Rollback Per Entry

**File:** `web/src/app/features/calibration/components/calibration-history-detail/calibration-history-detail.component.ts`

Add `rollback = output<string>()` signal output (emits `record.id`).
Add `isRollingBack = input<boolean>(false)`.

In template, add Rollback button (shown when `record().accepted === true`):
```html
@if (record().accepted) {
  <syn-button (click)="rollback.emit(record().id)" [disabled]="isRollingBack()" variant="outline" size="small">
    <syn-icon name="restore" slot="prefix" />
    Rollback to This
  </syn-button>
}
```

**`CalibrationHistoryComponent`** (`calibration-history.component.ts`): Add `onRollback(recordId: string)` handler. Inject `CalibrationStoreService`. Call `calibrationStore.rollbackHistory(sensorId, recordId)` where `sensorId` comes from the selected record's `source_sensor_id || sensor_id`.

---

## 4. Data Flow Diagrams

### 4.1 WebSocket Status Flow (Passive Monitoring)

```
CalibrationNode.emit_status()
  → StatusAggregator.collect()
    → WebSocket broadcast on /ws/system_status
      → StatusWebSocketService.status() (Signal)
        ├── CalibrationComponent: displays operational_state + calibrating badge per card
        └── NodeCalibrationControls: displays status badge only
```

**Message shape** (unchanged — no modifications to this path):
```json
{
  "nodes": [
    {
      "node_id": "abc123",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "calibrating",
        "value": true,
        "color": "blue"
      },
      "timestamp": 1700000000.0
    }
  ]
}
```

### 4.2 HTTP Polling Flow (Action + Detail)

```
CalibrationStoreService.startPolling(nodeId)
  → setInterval(2000ms)
    → CalibrationApiService.getNodeStatus(nodeId)
      → GET /api/v1/calibration/{node_id}/status
        → CalibrationNode.get_calibration_status()
          → Returns: { calibration_state, pending_results{pose_before, pose_after, matrix}, ... }
  → CalibrationStoreService.nodeStatuses signal updated
    ├── CalibrationViewerComponent.calibrationNode() (derived from store)
    └── CalibrationComponent: per-card polled status
```

### 4.3 Calibration Workflow (Action Path)

```
User clicks "Run Calibration" (CalibrationComponent or CalibrationViewerComponent)
  → CalibrationStoreService.triggerCalibration(nodeId, {})
    → CalibrationApiService.triggerCalibration(nodeId, request)
      → POST /api/v1/calibration/{node_id}/trigger
        → CalibrationNode.trigger_calibration(params)
          → ICP runs on threadpool (asyncio.to_thread)
          → Sets self._pending_calibration
          → Calls notify_status_change(self.id)
            → StatusAggregator → WebSocket broadcasts "calibrating: true"
  → Next poll (≤2s) picks up the new pending_results
  → User sees the Δ-pose table + matrix in viewer

User clicks "Accept" (CalibrationViewerComponent)
  → CalibrationStoreService.acceptCalibration(nodeId, {sensor_ids})
    → POST /api/v1/calibration/{node_id}/accept
      → CalibrationNode.accept_calibration()
        → Updates sensor pose in DB
        → CalibrationHistory.save_record() (with node_id + accepted_at)
        → manager.reload_config()
  → CalibrationStoreService re-fetches status (calibration_state → "idle")
```

---

## 5. API Contracts (Summary)

See `api-spec.md` for full request/response schemas.

| Endpoint | Method | Change |
|---|---|---|
| `/api/v1/calibration/{node_id}/status` | GET | **NEW** — polling endpoint |
| `/api/v1/calibration/{node_id}/trigger` | POST | Fix `sample_frames` default (1→5) |
| `/api/v1/calibration/{node_id}/accept` | POST | No change |
| `/api/v1/calibration/{node_id}/reject` | POST | Fix response schema (add `rejected: string[]`) |
| `/api/v1/calibration/history/{sensor_id}` | GET | Add `run_id` query param |
| `/api/v1/calibration/rollback/{sensor_id}` | POST | Change from `timestamp` to `record_id` |
| `/api/v1/calibration/statistics/{sensor_id}` | GET | No change |

---

## 6. Unit Conversion Boundary Documentation

This is **the single most critical data contract** in the calibration subsystem. All developers must know this.

### Canonical Storage Format

```
DB column pose_before_json / pose_after_json:
  { "x": 1500.0, "y": -200.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 45.0 }
  ^^^ MILLIMETERS for x/y/z                          ^^^ DEGREES for angles
```

### ICP Engine Input Format

```
ICP engine (app/modules/calibration/registration/icp_engine.py):
  - Expects point clouds in METERS
  - Transformation matrix is in METERS
  - RMSE is in METERS
  - Fitness is dimensionless (0-1)

Conversion at boundary (in calibration_node.py, trigger_calibration()):
  - Point clouds from sensors are already in METERS (Open3D native)
  - Pose is read from DB in MILLIMETERS, then:
    T_current = create_transformation_matrix(
        x=current_pose.x / 1000,   # mm → meters
        y=current_pose.y / 1000,
        z=current_pose.z / 1000,
        roll=current_pose.roll,     # degrees, no conversion needed
        pitch=current_pose.pitch,
        yaw=current_pose.yaw,
    )
```

**IMPORTANT**: `create_transformation_matrix` in `app/modules/lidar/core/transformations.py` expects position in **meters**, not mm. The Pose schema stores in **mm**. Division by 1000 must happen at this exact boundary.

### API / Frontend Display Format

```
All API responses expose pose in MILLIMETERS (raw DB values):
  pose_before: { x: 1500.0, y: -200.0, z: 0.0, ... }  ← mm

Frontend display:
  Pose values: show as-is in mm (label the column headers "mm")
  Δ-pose table: computed as pose_after - pose_before, unit is mm for x/y/z and ° for angles
  RMSE (from ICP): in METERS — label as "m"
  Fitness: dimensionless 0–1 (display as %)

4×4 transformation matrix:
  Row 0–2, Col 3 (translation components): in METERS (ICP output, not converted to mm)
  Row 0–2, Col 0–2 (rotation components): dimensionless
  Frontend must label matrix cells: "translation column in meters"
```

### Unit Conversion Table

| Field | Storage | ICP Engine | API Response | Frontend Display |
|---|---|---|---|---|
| `x`, `y`, `z` (pose) | mm | meters (÷1000) | mm | mm |
| `roll`, `pitch`, `yaw` | degrees | degrees (no conversion) | degrees | ° |
| `rmse` | meters (raw ICP) | meters | meters | m |
| `fitness` | 0.0–1.0 | 0.0–1.0 | 0.0–1.0 | % (×100) |
| Transform matrix [0:3, 3] | meters (raw ICP) | meters | meters | m (labeled) |
| Transform matrix [0:3, 0:3] | dimensionless | dimensionless | dimensionless | — |

---

## 7. Key Design Decisions & Rationale

1. **Why HTTP polling (not WebSocket) for the calibration page?**
   - Calibration events are low-frequency (minutes apart), not high-frequency point clouds.
   - The calibration page needs richer data (full poses, matrices) than WebSocket status can carry.
   - 2s polling is adequate for human-facing workflow; avoids WebSocket state management complexity.

2. **Why `record_id` (PK) instead of `timestamp` for rollback?**
   - `timestamp` is a string column (ISO 8601). If two runs complete within the same second, timestamps collide.
   - `id` is a UUID hex, globally unique. Safer for PK-based lookup.
   - Frontend already receives `id` in every history record.

3. **Why move rollback out of `CalibrationHistory.rollback_to()`?**
   - The static utility class has no access to `node_manager`.
   - The service layer (`service.py`) already has `node_manager` and already calls `reload_config()`.
   - Avoids introducing a dependency injection anti-pattern into a pure data utility class.

4. **Why keep `emit_status()` unchanged?**
   - The WebSocket status path serves ALL node types with a unified schema.
   - Changing it would require updates to `StatusAggregator`, all consumers, and tests.
   - The new `get_calibration_status()` method is additive and only called by the new polling endpoint.

5. **Why `CalibrationStoreService` instead of component-local state?**
   - Polling must survive navigation between child routes (`/calibration/:id` and `/calibration/:id/history`).
   - The store as `providedIn: 'root'` means the poll timer is shared and not recreated on navigation.
   - Matches the existing store pattern (`RecordingStoreService`, `NodeStoreService`).
