# Backend Implementation Tasks — ICP Flow Alignment

**Feature:** `icp-flow-alignment`  
**Owner:** @be-dev

**References:**
- Requirements: `requirements.md`
- Architecture: `technical.md`
- API Contract: `api-spec.md`

**Architecture Approach:**
This feature extends the existing `CalibrationNode` (at `app/modules/calibration/calibration_node.py`) to track `source_sensor_id` and `processing_chain` provenance metadata, and adds FGR support to the existing global registration infrastructure. **No new alignment module is created.** All Open3D registration logic is reused from `app/modules/calibration/registration/`.

**Dependencies:**
- `BufferedFrame` dataclass must be defined before `on_input()` refactor
- Database migration must complete before ORM changes
- Provenance tracking must land before transformation patch workflow updates

---

## Phase 1 — Provenance Tracking Infrastructure

**Goal:** Replace the current `_latest_frames: Dict[str, np.ndarray]` with a structured ring-buffer that preserves `source_sensor_id` and `processing_chain` metadata from incoming payloads.

### Tasks

- [x] **Define `BufferedFrame` dataclass** in `app/modules/calibration/calibration_node.py`
  - Fields: `points: np.ndarray`, `timestamp: float`, `source_sensor_id: str`, `processing_chain: List[str]`, `node_id: str`
  - Import `from collections import deque` and `from dataclasses import dataclass, field`

- [x] **Replace `_latest_frames` with `_frame_buffer`**
  - Change type from `Dict[str, np.ndarray]` to `Dict[str, deque]` (key = `source_sensor_id`, value = `deque[BufferedFrame]`)
  - Add `_max_frames: int` config parameter (default 30)
  - Initialize in `__init__()`: `self._frame_buffer: Dict[str, deque] = {}`

- [x] **Refactor `CalibrationNode.on_input()`** to extract and store provenance
  - Extract `source_sensor_id = payload.get("lidar_id")` (canonical leaf sensor ID)
  - Extract `node_id = payload.get("node_id") or source_sensor_id` (last processing node)
  - Extract `timestamp = payload.get("timestamp", 0.0)`
  - Extract `processing_chain = list(payload.get("processing_chain") or [node_id or source_sensor_id])`
  - Create `BufferedFrame` instance with all metadata
  - Append to `self._frame_buffer[source_sensor_id]` (auto-evicts oldest if full)
  - Update reference/source sensor role assignment logic to use `source_sensor_id` keys

- [x] **Implement `_aggregate_frames()` helper method**
  - Signature: `_aggregate_frames(self, source_sensor_id: str, sample_frames: int) -> Optional[Tuple[np.ndarray, str, List[str]]]`
  - Retrieve `self._frame_buffer.get(source_sensor_id)`
  - Select last N frames from deque: `frames = list(buf)[-sample_frames:]`
  - Concatenate points: `aggregated = np.concatenate([f.points for f in frames], axis=0)`
  - Extract latest processing chain: `latest_chain = frames[-1].processing_chain`
  - Return `(aggregated, source_sensor_id, latest_chain)` or `None` if buffer empty

- [x] **Update `get_status()` method**
  - Change `"buffered_frames": list(self._latest_frames.keys())` to `list(self._frame_buffer.keys())`
  - Report per-sensor buffer sizes: `{sensor_id: len(buf) for sensor_id, buf in self._frame_buffer.items()}`

### Files Modified
- `app/modules/calibration/calibration_node.py`

### Reused Components
- Existing `on_input()` structure and passthrough logic
- Existing reference/source sensor role assignment pattern

---

## Phase 2 — Database Schema Extension

**Goal:** Add `source_sensor_id`, `processing_chain`, and `run_id` columns to `CalibrationHistoryModel` to support provenance tracking and multi-sensor run correlation.

### Tasks

- [x] **Extend `CalibrationHistoryModel`** in `app/db/models.py`
  - Add column: `source_sensor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)`
  - Add column: `processing_chain_json: Mapped[str] = mapped_column(String, default="[]")`
  - Add column: `run_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)`
  - Update `to_dict()` to include:
    - `"source_sensor_id": self.source_sensor_id`
    - `"processing_chain": json.loads(self.processing_chain_json or "[]")`
    - `"run_id": self.run_id`

- [x] **Write database migration** in `app/db/migrate.py`
  - Add to `ensure_schema()` function:
    ```python
    ALTER_COLUMNS = [
        "ALTER TABLE calibration_history ADD COLUMN source_sensor_id TEXT;",
        "ALTER TABLE calibration_history ADD COLUMN processing_chain_json TEXT NOT NULL DEFAULT '[]';",
        "ALTER TABLE calibration_history ADD COLUMN run_id TEXT;",
    ]
    ```
  - Use try-except to handle columns that already exist (SQLite-safe)

- [x] **Extend `CalibrationRecord` dataclass** in `app/modules/calibration/history.py`
  - Add field: `source_sensor_id: str = ""`
  - Add field: `processing_chain: List[str] = field(default_factory=list)`
  - Add field: `run_id: str = ""`
  - Ensure `to_dict()` includes new fields
  - Ensure `from_dict()` handles new fields with defaults for backward compatibility

- [x] **Update `create_calibration_record()` factory function** in `history.py`
  - Add parameters: `source_sensor_id: str = ""`, `processing_chain: Optional[List[str]] = None`, `run_id: str = ""`
  - Pass to `CalibrationRecord` constructor

- [x] **Extend `calibration_orm.create_calibration_record()`** in `app/repositories/calibration_orm.py`
  - Add parameters: `source_sensor_id: Optional[str] = None`, `processing_chain: Optional[List[str]] = None`, `run_id: Optional[str] = None`
  - Set `source_sensor_id=source_sensor_id or sensor_id` (fallback for backward compat)
  - Set `processing_chain_json=json.dumps(processing_chain or [])`
  - Set `run_id=run_id`

- [x] **Add query helper: `get_calibration_history_by_source()`**
  - Signature: `get_calibration_history_by_source(db: Session, source_sensor_id: str, limit: Optional[int] = None) -> List[CalibrationHistoryModel]`
  - Query: `db.query(CalibrationHistoryModel).filter(CalibrationHistoryModel.source_sensor_id == source_sensor_id).order_by(desc(timestamp)).limit(limit)`

- [x] **Add query helper: `get_calibration_history_by_run()`**
  - Signature: `get_calibration_history_by_run(db: Session, run_id: str) -> List[CalibrationHistoryModel]`
  - Query: `db.query(CalibrationHistoryModel).filter(CalibrationHistoryModel.run_id == run_id).order_by(timestamp)`

### Files Modified
- `app/db/models.py`
- `app/db/migrate.py`
- `app/modules/calibration/history.py`
- `app/repositories/calibration_orm.py`

### Backward Compatibility Notes
- All new columns are nullable or have defaults → existing rows unaffected
- `from_dict()` uses `**data` → old records without new fields work fine
- ORM signature extensions use optional kwargs → existing call sites unchanged

---

## Phase 3 — Transformation Patch Workflow

**Goal:** Clarify and fix the transformation application workflow so that ICP results are always written to the **leaf sensor config** (`source_sensor_id`), not an intermediate processing node.

### Tasks

- [x] **Update `CalibrationNode.trigger_calibration()`** to use `source_sensor_id` consistently
  - Generate `run_id = uuid.uuid4().hex[:12]` at the start of the method
  - For each source sensor:
    - Call `aggregated, source_sensor_id, latest_chain = self._aggregate_frames(source_id, sample_frames)`
    - Fetch current pose from database using `source_sensor_id` (the leaf LidarSensor node):
      ```python
      repo = NodeRepository()
      sensor_node_data = repo.get_by_id(source_sensor_id)  # NOT node_id
      current_pose = {
          "x": config.get("x", 0.0),
          "y": config.get("y", 0.0),
          "z": config.get("z", 0.0),
          "roll": config.get("roll", 0.0),
          "pitch": config.get("pitch", 0.0),
          "yaw": config.get("yaw", 0.0)
      }
      ```
    - Build initial transformation matrix: `T_current = create_transformation_matrix(**current_pose)`
    - Run ICP: `reg_result = await self.icp_engine.register(source=aggregated, target=ref_points, initial_transform=T_current)`
    - Compose transformations: `T_new = reg_result.transformation @ T_current`
    - Extract new pose: `new_pose = extract_pose_from_matrix(T_new)`
    - Create calibration record with provenance:
      ```python
      record = create_calibration_record(
          sensor_id=source_sensor_id,
          source_sensor_id=source_sensor_id,
          processing_chain=latest_chain,
          run_id=run_id,
          reference_sensor_id=ref_id,
          fitness=reg_result.fitness,
          rmse=reg_result.rmse,
          quality=reg_result.quality,
          stages_used=reg_result.stages_used,
          pose_before=current_pose,
          pose_after=new_pose,
          transformation_matrix=T_new.tolist(),
          accepted=False
      )
      ```
    - Store in `self._pending_calibration[source_sensor_id] = record`
    - Include in response: `source_sensor_id`, `processing_chain`
  - Return `{"success": True, "run_id": run_id, "results": results, "pending_approval": not self.auto_save}`

- [x] **Refactor `CalibrationNode._apply_calibration()`** to always target the leaf sensor
  - Extract target ID from record: `target_id = record.source_sensor_id or sensor_id`
  - Use `target_id` for `NodeRepository.update_node_config()` call
  - Add inline comment explaining why:
    ```python
    # CRITICAL: Always update the leaf LidarSensor node (source_sensor_id),
    # NOT an intermediate processing node. This ensures the transformation
    # is picked up by LidarSensor.handle_data() after reload_config().
    repo.update_node_config(target_id, {
        "x": record.pose_after["x"],
        "y": record.pose_after["y"],
        "z": record.pose_after["z"],
        "roll": record.pose_after["roll"],
        "pitch": record.pose_after["pitch"],
        "yaw": record.pose_after["yaw"]
    })
    ```
  - Verify `CalibrationHistory.save_record()` is called with full record including new fields
  - Verify `self.manager.reload_config()` is called to trigger DAG hot-reload

- [x] **Verify `NodeRepository.update_node_config()` workflow**
  - Confirm it uses `json.dumps(config)` to serialize the full config dict
  - Confirm it commits the SQLAlchemy session
  - Confirm the node's `config_json` column is updated in the database

- [x] **Test transformation patch end-to-end**
  - Create test DAG: `LidarSensor A → CropNode → DownsampleNode → CalibrationNode`
  - Trigger calibration for sensor A
  - Verify `source_sensor_id` in record is `A` (not `DownsampleNode`)
  - Accept calibration
  - Verify `nodes.config_json` for node `A` has updated `x, y, z, roll, pitch, yaw`
  - Verify `manager.reload_config()` rebuilds DAG with new sensor transform
  - Verify `LidarSensor.handle_data()` applies new transformation matrix to points

### Files Modified
- `app/modules/calibration/calibration_node.py`

### Reused Components
- `app/modules/lidar/core/transformations.create_transformation_matrix()` — builds 4x4 matrix from pose dict
- `app/modules/calibration/calibration_node.extract_pose_from_matrix()` — decomposes 4x4 matrix to 6-DOF pose
- `app/repositories/node_orm.NodeRepository.update_node_config()` — persists pose to database
- `app/modules/calibration/registration/icp_engine.ICPEngine.register()` — runs ICP registration
- `NodeManager.reload_config()` — triggers DAG hot-reload

---

## Phase 4 — FGR Support in Global Registration

**Goal:** Extend the existing `GlobalRegistration` class to support Fast Global Registration (FGR) as an alternative to RANSAC, controlled by a `use_fast_global_registration` boolean flag.

### Tasks

- [x] **Add `use_fast_global_registration` parameter** to `GlobalRegistration.__init__()`
  - File: `app/modules/calibration/registration/global_registration.py`
  - Add to config: `self.use_fgr = config.get("use_fast_global_registration", False)`

- [x] **Implement FGR branch** in `GlobalRegistration.register()`
  - After downsampling and FPFH computation, add conditional:
    ```python
    if self.use_fgr:
        # Fast Global Registration
        result = o3d.pipelines.registration.registration_fgr_based_on_feature_matching(
            source_down,
            target_down,
            source_fpfh,
            target_fpfh,
            o3d.pipelines.registration.FastGlobalRegistrationOption(
                maximum_correspondence_distance=self.voxel_size * 0.5
            )
        )
        method = "fgr"
    else:
        # RANSAC (existing code)
        result = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
            source_down,
            target_down,
            source_fpfh,
            target_fpfh,
            mutual_filter=True,
            max_correspondence_distance=self.ransac_threshold,
            estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
            ransac_n=3,
            checkers=[...],
            criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(...)
        )
        method = "ransac"
    ```

- [x] **Extend `GlobalResult` dataclass** to include method used
  - Add field: `method: str` (values: `"ransac"` or `"fgr"`)
  - Return in `GlobalRegistration.register()`: `GlobalResult(..., method=method)`

- [x] **Update `ICPEngine` to pass through FGR flag**
  - File: `app/modules/calibration/registration/icp_engine.py`
  - Add to config: `use_fast_global_registration: bool`
  - Pass to `GlobalRegistration(config)` constructor

- [x] **Unit tests for RANSAC vs FGR selection**
  - Test case: `use_fast_global_registration=False` → calls `registration_ransac_based_on_feature_matching`
  - Test case: `use_fast_global_registration=True` → calls `registration_fgr_based_on_feature_matching`
  - Test case: Verify `GlobalResult.method` field is correctly set

### Files Modified
- `app/modules/calibration/registration/global_registration.py`
- `app/modules/calibration/registration/icp_engine.py`

### Reused Components
- Existing FPFH computation logic
- Existing downsampling and normal estimation logic
- Existing `GlobalResult` dataclass structure

---

## Phase 5 — API Layer Updates

**Goal:** Extend API request/response schemas to include `run_id`, `source_sensor_id`, and `processing_chain` metadata. All changes are **additive** (backward compatible).

### Tasks

- [x] **Extend `CalibrationSensorResult` schema** in `app/api/v1/schemas/calibration.py`
  - Add fields:
    - `source_sensor_id: Optional[str] = None` — leaf sensor ID
    - `processing_chain: List[str] = []` — DAG path from leaf sensor to calibration node
  - Keep all existing fields unchanged

- [x] **Extend `CalibrationTriggerResponse` schema**
  - Add field: `run_id: str` — UUID correlating multi-sensor runs
  - Keep `results: Dict[str, CalibrationResult]` unchanged (gains new fields transitively)

- [x] **Extend `CalibrationHistoryRecord` schema**
  - Add fields:
    - `source_sensor_id: Optional[str] = None`
    - `processing_chain: List[str] = []`
    - `run_id: Optional[str] = None`

- [x] **Update `trigger_calibration()` in `app/api/v1/calibration/service.py`**
  - Pass `sample_frames` from request to `CalibrationNode.trigger_calibration()` (default: raise from 1 to 5)
  - Extract `run_id` from node response
  - Include `source_sensor_id` and `processing_chain` in each `CalibrationSensorResult`
  - Return `run_id` in `CalibrationTriggerResponse`

- [x] **Add optional `source_sensor_id` query param** to `get_calibration_history()` endpoint
  - Update route: `GET /api/v1/calibration/history/{sensor_id}?source_sensor_id={leaf_sensor_id}`
  - If `source_sensor_id` param provided, call `calibration_orm.get_calibration_history_by_source(db, source_sensor_id, limit)`
  - Otherwise, call existing `get_calibration_history(db, sensor_id, limit)`

- [ ] **Update Swagger/OpenAPI documentation**
  - Document that `source_sensor_id` is the **leaf LidarSensor node ID** (`lidar_id`), not an intermediate processing node
  - Document `processing_chain` as ordered list of DAG node IDs from leaf sensor to calibration node
  - Document `run_id` as UUID correlating multi-sensor calibration runs

### Files Modified
- `app/api/v1/schemas/calibration.py`
- `app/api/v1/calibration/service.py`
- `app/api/v1/calibration/dto.py` (if separate request DTOs exist)

### API Contract Changes (All Additive)
- ✅ `POST /api/v1/calibration/{node_id}/trigger` response gains `run_id` field
- ✅ `results[sensor_id]` gains `source_sensor_id` and `processing_chain` fields
- ✅ `GET /api/v1/calibration/history/{sensor_id}` accepts optional `?source_sensor_id=` query param
- ✅ History records gain `source_sensor_id`, `processing_chain`, `run_id` fields
- ❌ No breaking changes to request schemas

---

## Phase 6 — Integration Testing

**Goal:** Verify provenance tracking and transformation patching work correctly through complex DAG topologies.

### Test Scenarios

- [x] **Test 1: Simple direct connection**
  - DAG: `LidarSensor A → CalibrationNode`
  - Verify: `source_sensor_id = A`, `processing_chain = [A]`
  - Verify: Transformation applied to node A config

- [x] **Test 2: Complex processing chain**
  - DAG: `LidarSensor A → CropNode → DownsampleNode → CalibrationNode`
  - Verify: `source_sensor_id = A`, `processing_chain = [A, crop_id, downsample_id]`
  - Verify: Transformation applied to node A config (NOT crop or downsample)

- [x] **Test 3: Multi-sensor calibration**
  - DAG: `LidarSensor A → CalibrationNode`, `LidarSensor B → CalibrationNode`
  - Trigger calibration with reference=A, sources=[B]
  - Verify: `run_id` is the same for both sensors
  - Verify: `source_sensor_id` is correct for each result

- [x] **Test 4: Accept calibration workflow**
  - Trigger calibration
  - Verify result is `pending`
  - Call `POST /api/v1/calibration/{node_id}/accept`
  - Verify: `nodes.config_json` for leaf sensor is updated
  - Verify: `calibration_history` record created with `accepted=True`
  - Verify: `manager.reload_config()` was called

- [x] **Test 5: Reject calibration workflow**
  - Trigger calibration
  - Call `POST /api/v1/calibration/{node_id}/reject`
  - Verify: `nodes.config_json` unchanged
  - Verify: `_pending_calibration` is cleared

- [x] **Test 6: History query by source_sensor_id**
  - Trigger calibration for sensor A through processing chain
  - Call `GET /api/v1/calibration/history/{sensor_id}?source_sensor_id=A`
  - Verify: Only records for leaf sensor A are returned

- [x] **Test 7: Run correlation**
  - Trigger multi-sensor calibration
  - Query `calibration_orm.get_calibration_history_by_run(db, run_id)`
  - Verify: All sensors from that run are returned

### Files to Create
- `tests/modules/test_calibration_provenance.py` — unit tests for provenance tracking
- `tests/api/test_calibration_complex_dag.py` — integration tests for complex DAG paths
- `tests/api/test_calibration_transformation_patch.py` — end-to-end tests for transformation application

---

## Phase 7 — Documentation Updates

**Goal:** Update inline code comments and docstrings to reflect the provenance tracking architecture.

### Tasks

- [ ] **Add module-level docstring** to `calibration_node.py` explaining provenance tracking
  - Document `source_sensor_id` vs `node_id` distinction
  - Document `processing_chain` accumulation pattern
  - Document transformation patch workflow

- [ ] **Update `on_input()` docstring** to document payload contract
  - Required keys: `lidar_id`, `node_id`, `points`, `timestamp`, `processing_chain`
  - Explain that `lidar_id` is canonical leaf sensor ID
  - Explain that `node_id` is last processing node in chain

- [ ] **Update `_apply_calibration()` docstring**
  - Clarify that it always targets `source_sensor_id` (leaf sensor)
  - Document transformation patch workflow step-by-step
  - Reference `NodeRepository.update_node_config()` and `reload_config()`

- [ ] **Add inline comments** in `trigger_calibration()`
  - Explain `run_id` generation for multi-sensor correlation
  - Explain `_aggregate_frames()` usage
  - Explain why `source_sensor_id` is used for DB lookup

### Files Modified
- `app/modules/calibration/calibration_node.py`
- `app/modules/calibration/history.py`

---

## Summary: Files Modified (No New Modules)

| File | Change Type |
|------|-------------|
| `app/modules/calibration/calibration_node.py` | **Refactor** — `_latest_frames` → `_frame_buffer`, provenance tracking, transformation patch |
| `app/modules/calibration/history.py` | **Extend** — Add `source_sensor_id`, `processing_chain`, `run_id` to `CalibrationRecord` |
| `app/modules/calibration/registration/global_registration.py` | **Extend** — Add FGR support alongside RANSAC |
| `app/modules/calibration/registration/icp_engine.py` | **Extend** — Pass through `use_fast_global_registration` flag |
| `app/db/models.py` | **Extend** — Add 3 columns to `CalibrationHistoryModel` |
| `app/db/migrate.py` | **Extend** — Add migration for new columns |
| `app/repositories/calibration_orm.py` | **Extend** — Add fields to `create_calibration_record()`, add query helpers |
| `app/api/v1/schemas/calibration.py` | **Extend** — Add fields to response schemas |
| `app/api/v1/calibration/service.py` | **Extend** — Pass through provenance metadata |

## Summary: Infrastructure Reused

✅ **Directly Reused (No Changes):**
- `app/modules/calibration/registration/icp_engine.ICPEngine.register()` — ICP execution
- `app/modules/calibration/registration/quality.QualityEvaluator` — quality classification
- `app/modules/calibration/history.CalibrationHistory.save_record()` — persistence
- `app/repositories/node_orm.NodeRepository.update_node_config()` — config patching
- `app/modules/lidar/core/transformations.create_transformation_matrix()` — pose → matrix
- `app/modules/calibration/calibration_node.extract_pose_from_matrix()` — matrix → pose

🔧 **Extended (Minimal Changes):**
- `app/modules/calibration/registration/global_registration.GlobalRegistration` — add FGR mode
- `app/modules/calibration/history.CalibrationRecord` — add provenance fields
- `app/repositories/calibration_orm` — add provenance to ORM

❌ **NOT Created:**
- No `app/modules/alignment/` module
- No `AlignmentNode` class
- No `AlignmentNodeConfig` schema
- No new DAG node type

---

## Transformation Patch Workflow Reference

For developers implementing Phase 3, here is the complete transformation patch workflow:

```python
# 1. Current state: Retrieve sensor pose from database
repo = NodeRepository()
sensor_data = repo.get_by_id(source_sensor_id)  # leaf sensor, not processing node
current_pose = sensor_data["config"]  # {x, y, z, roll, pitch, yaw}

# 2. Build 4x4 transformation matrix from current pose
from app.modules.lidar.core.transformations import create_transformation_matrix
T_current = create_transformation_matrix(**current_pose)

# 3. Run ICP registration (returns 4x4 transformation)
reg_result = await icp_engine.register(
    source=source_cloud,
    target=target_cloud,
    initial_transform=T_current
)

# 4. Compose transformations: T_new = T_icp @ T_current
T_new = reg_result.transformation @ T_current

# 5. Extract 6-DOF pose from composed matrix
from app.modules.calibration.calibration_node import extract_pose_from_matrix
new_pose = extract_pose_from_matrix(T_new)  # {x, y, z, roll, pitch, yaw}

# 6. On user acceptance: Patch sensor config with new pose
repo.update_node_config(source_sensor_id, new_pose)
# This updates the `nodes.config_json` column in the database

# 7. Trigger DAG reload so sensor picks up new transform
node_manager.reload_config()
# This rebuilds the DAG, and LidarSensor.handle_data() will use the new pose
# to rebuild its transformation matrix for all future frames
```

**Critical Notes:**
- Always use `source_sensor_id` (from payload `lidar_id`), NOT `node_id` (intermediate processing node)
- Transformation patch occurs **only after user acceptance** via `/accept` endpoint
- Pending calibrations store `pose_before` and `pose_after` but do NOT modify config until accepted
- `reload_config()` is essential — without it, the new pose won't take effect until manual restart
