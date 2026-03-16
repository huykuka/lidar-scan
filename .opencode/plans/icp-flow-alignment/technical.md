# Technical Specification — ICP Flow Alignment

**Feature:** `icp-flow-alignment`
**Author:** @architecture
**Date:** 2026-03-16
**Status:** Approved for Implementation

---

## 1. Objective

Extend the **existing** `CalibrationNode` (at `app/modules/calibration/calibration_node.py`) so that every ICP alignment operation fully preserves `source_sensor_id` and `processing_chain` from each incoming payload — at buffer-time, registration-time, history-time, and at the apply-time when a transformation is written back to the originating sensor.

No new alignment module is created. The calibration module is the exclusive home of ICP logic. The changes are strictly additive: new fields on existing data-classes, new internal trackers on `CalibrationNode`, and extended DB columns plus ORM helpers.

---

## 2. Root-Cause Analysis of the Gap

### 2.1 Payload arriving at `CalibrationNode.on_input`

The current `on_input` body:

```python
# calibration_node.py  (existing — lines 122-138)
source_id = payload.get("lidar_id") or payload.get("node_id")
points    = payload.get("points")
if source_id and points is not None:
    self._latest_frames[source_id] = points   # ← points only; no metadata
```

Problems:
1. `self._latest_frames` stores `np.ndarray` directly — all provenance is discarded.
2. When a sensor is connected through intermediate processing nodes (crop → downsample → calibration), `node_id` is the **last processing node's ID**, not the originating sensor. The true sensor ID travels in `payload["lidar_id"]` (set by `pcd_worker_process`/`real_worker`), but it is used as a fallback, not the canonical key.
3. `processing_chain` — the ordered list of DAG node IDs the payload has traversed — is **not tracked anywhere** in the current codebase.

### 2.2 `CalibrationRecord` and DB model

`CalibrationRecord` (at `app/modules/calibration/history.py`) stores `sensor_id` but has no `source_sensor_id` (the leaf sensor), no `processing_chain`, and no `run_id` to correlate multi-sensor runs.

`CalibrationHistoryModel` (at `app/db/models.py`) mirrors the same gap in the SQLite schema.

### 2.3 How `_apply_calibration` targets the wrong node on complex DAGs

```python
# calibration_node.py  (existing — lines 318-326)
repo.update_node_config(sensor_id, { ...pose... })
```

Here `sensor_id` is the key from `self._latest_frames`, which may be a **processing node** ID rather than the leaf `LidarSensor` node. The transformation must be written to the `LidarSensor` node so it is picked up by the `handle_data → transform_points` path in `sensor.py` on the next `reload_config`.

---

## 3. Canonical Payload Contract

All nodes that forward data through the DAG MUST include the following keys in their payload dict. Source (`LidarSensor`/PCD-worker) nodes already emit `lidar_id`. Processing nodes that receive and re-forward payloads must pass these through unchanged.

| Key | Type | Owner | Description |
|---|---|---|---|
| `lidar_id` | `str` | Source node | Canonical leaf sensor ID (set once at the hardware/PCD worker). Never mutated by intermediate nodes. |
| `node_id` | `str` | Each forwarding node | The ID of the node that last called `manager.forward_data()`. This changes at every hop. |
| `points` | `np.ndarray` | Any | (N, 3+) float32 point array. |
| `timestamp` | `float` | Source node | Unix epoch. |
| `processing_chain` | `List[str]` | Accumulated | Ordered list of node IDs the payload has traversed. Each node **appends its own `self.id`** before forwarding. Initialised to `[lidar_id]` by the source node. |

### 3.1 How `processing_chain` gets built

The `LidarSensor.handle_data` method is the origin point. Before calling `manager.forward_data`, it initialises the chain:

```python
# app/modules/lidar/sensor.py — modification to handle_data
payload["processing_chain"] = payload.get("processing_chain") or [self.id]
await self.manager.forward_data(self.id, payload)
```

Every intermediate `ModuleNode.on_input` that forwards the payload appends its own ID before delegating:

```python
# Pattern for all intermediate nodes (operation, fusion, etc.)
chain = list(payload.get("processing_chain") or [])
chain.append(self.id)
payload["processing_chain"] = chain
await self.manager.forward_data(self.id, payload)
```

The `CalibrationNode.on_input` reads but **does not append** — it is a sink for frame buffering, not a transparent pass-through (though it does call `forward_data` for passthrough mode).

---

## 4. Changes to `CalibrationNode`

### 4.1 `_latest_frames` — enhanced frame buffer

Replace the current `Dict[str, np.ndarray]` with a structured buffer that preserves provenance:

```python
# Before (existing)
self._latest_frames: Dict[str, np.ndarray] = {}

# After
from collections import deque
from dataclasses import dataclass, field

@dataclass
class BufferedFrame:
    points: np.ndarray
    timestamp: float
    source_sensor_id: str       # lidar_id — the leaf sensor
    processing_chain: List[str] # full chain from leaf → this node
    node_id: str                # the node that last forwarded this payload

# Ring-buffer per logical key (lidar_id)
self._frame_buffer: Dict[str, deque] = {}   # lidar_id -> deque[BufferedFrame]
self._max_frames: int = config.get("max_buffered_frames", 30)
```

### 4.2 `on_input` — extract and store provenance

```python
async def on_input(self, payload: Dict[str, Any]):
    if not self._enabled:
        return

    # Canonical sensor ID is always lidar_id (set at the hardware source).
    # node_id is the last processing node — use it for DAG routing only.
    source_sensor_id = payload.get("lidar_id")
    node_id          = payload.get("node_id") or source_sensor_id
    points           = payload.get("points")
    timestamp        = payload.get("timestamp", 0.0)
    processing_chain = list(payload.get("processing_chain") or [node_id or source_sensor_id])

    if source_sensor_id and points is not None and len(points) > 0:
        if source_sensor_id not in self._frame_buffer:
            self._frame_buffer[source_sensor_id] = deque(maxlen=self._max_frames)

        frame = BufferedFrame(
            points=points.copy(),
            timestamp=timestamp,
            source_sensor_id=source_sensor_id,
            processing_chain=processing_chain,
            node_id=node_id,
        )
        self._frame_buffer[source_sensor_id].append(frame)

        # Role assignment (reference = first seen)
        if self._reference_sensor_id is None:
            self._reference_sensor_id = source_sensor_id
        elif (source_sensor_id not in self._source_sensor_ids
              and source_sensor_id != self._reference_sensor_id):
            self._source_sensor_ids.append(source_sensor_id)

    # Passthrough
    await self.manager.forward_data(self.id, payload)
```

### 4.3 `trigger_calibration` — aggregate frames by `source_sensor_id`

The method currently iterates over `self._source_sensor_ids` and looks up `self._latest_frames[source_id]`. After the refactor, it must:

1. Use `self._frame_buffer[source_sensor_id]` to aggregate `sample_frames` frames.
2. Pass `source_sensor_id` and the latest `processing_chain` into `create_calibration_record`.
3. Use `source_sensor_id` (the leaf sensor) for the `NodeRepository` lookup and subsequent `_apply_calibration` call — not the intermediate node ID.

**Aggregation helper** (new private method on `CalibrationNode`):

```python
def _aggregate_frames(
    self,
    source_sensor_id: str,
    sample_frames: int
) -> Optional[Tuple[np.ndarray, str, List[str]]]:
    """
    Aggregate up to sample_frames recent frames for source_sensor_id.

    Returns:
        Tuple of (aggregated_points, source_sensor_id, latest_processing_chain)
        or None if no frames available.
    """
    buf = self._frame_buffer.get(source_sensor_id)
    if not buf:
        return None

    frames = list(buf)[-sample_frames:]   # most recent N frames
    aggregated = np.concatenate([f.points for f in frames], axis=0)
    latest_chain = frames[-1].processing_chain
    return aggregated, source_sensor_id, latest_chain
```

### 4.4 `_apply_calibration` — write to the correct leaf sensor

After ICP converges, the transformation must be applied to the **leaf sensor** node, not a processing node. The method should be updated to always target `record.source_sensor_id` rather than the generic `sensor_id` argument:

```python
async def _apply_calibration(self, sensor_id: str, record: "CalibrationRecord", db_session=None):
    # Use source_sensor_id for the DB update — that is the LidarSensor node.
    target_id = getattr(record, "source_sensor_id", sensor_id)
    repo.update_node_config(target_id, { ...pose_after... })
    CalibrationHistory.save_record(record, db_session=db)
    self.manager.reload_config()
```

---

## 5. Changes to `CalibrationRecord` and `CalibrationHistory`

### 5.1 `CalibrationRecord` dataclass additions

File: `app/modules/calibration/history.py`

Add two new fields:

```python
@dataclass
class CalibrationRecord:
    # ... existing fields ...
    source_sensor_id: str = ""         # NEW — leaf LidarSensor node ID
    processing_chain: List[str] = field(default_factory=list)  # NEW — DAG path
    run_id: str = ""                   # NEW — correlates multi-sensor runs
```

`create_calibration_record` factory function gains the same three parameters.

### 5.2 `CalibrationHistory.save_record` — forward new fields to ORM

```python
calibration_orm.create_calibration_record(
    db=db_session,
    ...existing args...,
    source_sensor_id=record.source_sensor_id,
    processing_chain=record.processing_chain,
    run_id=record.run_id,
)
```

---

## 6. Database Schema Extension

File: `app/db/models.py` — `CalibrationHistoryModel`

Add three new nullable columns (backward-compatible; existing rows get empty/null defaults):

```python
class CalibrationHistoryModel(Base):
    __tablename__ = "calibration_history"
    # ... existing columns ...
    source_sensor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    processing_chain_json: Mapped[str] = mapped_column(String, default="[]")
    run_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
```

`to_dict()` must include:

```python
"source_sensor_id": self.source_sensor_id,
"processing_chain": json.loads(self.processing_chain_json or "[]"),
"run_id": self.run_id,
```

### 6.1 Migration

File: `app/db/migrate.py` — `ensure_schema()` uses `ADD COLUMN IF NOT EXISTS` (SQLite-safe):

```python
ADD_COLUMNS = [
    "ALTER TABLE calibration_history ADD COLUMN source_sensor_id TEXT;",
    "ALTER TABLE calibration_history ADD COLUMN processing_chain_json TEXT NOT NULL DEFAULT '[]';",
    "ALTER TABLE calibration_history ADD COLUMN run_id TEXT;",
]
```

---

## 7. ORM Repository Changes

File: `app/repositories/calibration_orm.py`

### 7.1 `create_calibration_record` signature extension

```python
def create_calibration_record(
    db: Session,
    ...,
    source_sensor_id: Optional[str] = None,
    processing_chain: Optional[List[str]] = None,
    run_id: Optional[str] = None,
) -> CalibrationHistoryModel:
    record = CalibrationHistoryModel(
        ...,
        source_sensor_id=source_sensor_id or sensor_id,
        processing_chain_json=json.dumps(processing_chain or []),
        run_id=run_id,
    )
```

### 7.2 New query helpers

```python
def get_calibration_history_by_source(
    db: Session,
    source_sensor_id: str,
    limit: Optional[int] = None,
) -> List[CalibrationHistoryModel]:
    """Query by canonical leaf sensor ID."""

def get_calibration_history_by_run(
    db: Session,
    run_id: str,
) -> List[CalibrationHistoryModel]:
    """Return all sensor records for a given run."""
```

---

## 8. API Layer Changes

### 8.1 `TriggerCalibrationRequest` DTO

File: `app/api/v1/calibration/dto.py`

No breaking change. Add optional `sample_frames` (already exists), confirm `source_sensor_ids` accepts **leaf sensor IDs**. Document in Swagger that these are `lidar_id` values, not intermediate node IDs.

### 8.2 `CalibrationTriggerResponse` schema

File: `app/api/v1/schemas/calibration.py`

```python
class CalibrationSensorResult(BaseModel):
    fitness: Optional[float] = None
    rmse: Optional[float] = None
    quality: Optional[str] = None
    stages_used: List[str] = []
    pose_before: Optional[Dict[str, float]] = None
    pose_after: Optional[Dict[str, float]] = None
    # NEW fields
    source_sensor_id: Optional[str] = None
    processing_chain: List[str] = []
    auto_saved: bool = False

class CalibrationTriggerResponse(BaseModel):
    success: bool
    run_id: str                    # NEW — UUID for this calibration run
    results: Dict[str, CalibrationSensorResult]
    pending_approval: bool
```

### 8.3 `CalibrationHistoryRecord` schema extension

```python
class CalibrationRecord(BaseModel):
    id: str
    sensor_id: str
    source_sensor_id: Optional[str] = None     # NEW
    processing_chain: List[str] = []           # NEW
    run_id: Optional[str] = None               # NEW
    timestamp: str
    accepted: bool
    fitness: Optional[float] = None
    rmse: Optional[float] = None
```

### 8.4 Service layer

File: `app/api/v1/calibration/service.py`

`trigger_calibration`:
- Pass `sample_frames` from request to node (default 1 → raise to 5 for better ICP accuracy).
- Include `source_sensor_id` and `processing_chain` in the returned results dict.
- Return `run_id` to the caller.

`get_calibration_history`:
- Add optional `?source_sensor_id=` query param so the frontend can filter by true leaf sensor.

---

## 9. `CalibrationNode.trigger_calibration` — Full Revised Flow

```
trigger_calibration(params)
│
├─ 1. Resolve reference sensor from params or self._reference_sensor_id
│     (key = lidar_id / source_sensor_id)
│
├─ 2. Resolve source sensors list from params or self._source_sensor_ids
│     (all keys in self._frame_buffer except reference)
│
├─ 3. generate run_id = uuid4().hex[:12]
│
├─ 4. For each source_sensor_id:
│     │
│     ├─ 4a. _aggregate_frames(source_sensor_id, sample_frames)
│     │       → aggregated_points, source_sensor_id, latest_processing_chain
│     │
│     ├─ 4b. Fetch current pose from NodeRepository using source_sensor_id
│     │       (the leaf sensor's config — x, y, z, roll, pitch, yaw)
│     │
│     ├─ 4c. Build T_current from current pose
│     │
│     ├─ 4d. await icp_engine.register(source=aggregated, target=ref_points,
│     │                                  initial_transform=T_current)
│     │       (runs in asyncio.to_thread — no event loop blocking)
│     │
│     ├─ 4e. Compose T_new = T_icp @ T_current, extract new_pose
│     │
│     ├─ 4f. create_calibration_record(
│     │           sensor_id=source_sensor_id,
│     │           source_sensor_id=source_sensor_id,
│     │           processing_chain=latest_processing_chain,
│     │           run_id=run_id,
│     │           ...fitness, rmse, quality, T_new...
│     │       )
│     │
│     └─ 4g. If auto_save & fitness >= threshold: _apply_calibration immediately
│
├─ 5. Store self._pending_calibration = {source_sensor_id: record, ...}
│
└─ 6. Return {success, run_id, results, pending_approval}
```

---

## 10. Data Flow Diagram (DAG Path + ICP Apply)

```
[LidarSensor A]  →  [CropNode]  →  [DownsampleNode]  →  [CalibrationNode]
   lidar_id=A        appends         appends                on_input():
   node_id=A         node_id         node_id                  source_sensor_id = lidar_id = A
   processing_chain  =[A,crop]       =[A,crop,ds]             processing_chain = [A,crop,ds]
                                                              → stored in _frame_buffer[A]

[LidarSensor B]  →  [CalibrationNode]
   lidar_id=B                         on_input():
                                        source_sensor_id = B
                                        processing_chain = [B]
                                        → stored in _frame_buffer[B]

trigger_calibration():
  ref = B,  source = A
  aggregated_A = concat(_frame_buffer[A])
  run ICP(source=aggregated_A, target=aggregated_B)
  T_new → pose_after
  CalibrationRecord(sensor_id=A, source_sensor_id=A, processing_chain=[A,crop,ds])

accept_calibration():
  _apply_calibration(sensor_id=A, record)
  → NodeRepository.update_node_config(node_id=A, {x,y,z,roll,pitch,yaw})
                                         ^--- always the leaf LidarSensor
  → manager.reload_config()
     [LidarSensor A] now reads new pose → transform_points uses updated T
```

---

## 11. Concurrency Contract

- All Open3D ICP calls are already wrapped in `await asyncio.to_thread(...)` inside `ICPEngine.register`. No change needed.
- `_frame_buffer` is mutated only from the asyncio event loop (all `on_input` calls are awaited tasks). No additional locking is required.
- `_pending_calibration` is read/written from the event loop only. API handler calls are coroutines dispatched by FastAPI.

---

## 12. Backward Compatibility

| Concern | Impact | Mitigation |
|---|---|---|
| Existing `_latest_frames` dict | Replaced by `_frame_buffer` | No external callers; internal refactor only |
| `CalibrationRecord` fields | New optional fields added | `from_dict` uses `**data` — pass defaults for old DB rows |
| DB schema | New nullable columns | `ensure_schema` migration with `ADD COLUMN IF NOT EXISTS` |
| `calibration_orm.create_calibration_record` signature | New optional kwargs | All existing call sites work unchanged |
| REST response shape | `run_id` is new; `source_sensor_id`/`processing_chain` are additive | Frontend can ignore new fields; not breaking |

---

## 13. Files to Modify (No New Modules)

| File | Change type |
|---|---|
| `app/modules/calibration/calibration_node.py` | Refactor `_latest_frames` → `_frame_buffer`; extend `on_input`, `trigger_calibration`, `_aggregate_frames`, `_apply_calibration` |
| `app/modules/calibration/history.py` | Add `source_sensor_id`, `processing_chain`, `run_id` to `CalibrationRecord`; update `create_calibration_record` |
| `app/db/models.py` | Add 3 columns to `CalibrationHistoryModel.to_dict()` |
| `app/db/migrate.py` | `ADD COLUMN IF NOT EXISTS` for 3 new columns |
| `app/repositories/calibration_orm.py` | Extend `create_calibration_record`; add 2 query helpers |
| `app/api/v1/calibration/dto.py` | Extend `TriggerCalibrationRequest` with `sample_frames` default clarification |
| `app/api/v1/schemas/calibration.py` | Add `source_sensor_id`, `processing_chain`, `run_id` to response schemas |
| `app/api/v1/calibration/service.py` | Pass provenance through to response; add `source_sensor_id` query param on history |
| `app/modules/lidar/sensor.py` | Initialise `processing_chain` in `handle_data` |

---

## 14. What Is Explicitly NOT Changed

- `ICPEngine` — no changes; registration algorithm is correct.
- `GlobalRegistration` — no changes.
- `QualityEvaluator` — no changes.
- `CalibrationNode` node registry / factory (`registry.py`) — no changes.
- The calibration API route paths — no changes.
- WebSocket topic lifecycle — not touched.
- No new DAG node type. No `alignment` module.
