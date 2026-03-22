# Backend Tasks: Calibration Page Redesign

**Feature:** `calibration-page-redesign`
**References:** `technical.md`, `api-spec.md`
**Developer:** `@be-dev`

> **Ordering rule:** Complete tasks in numbered order. Each group depends on the previous.
> **Checkbox rule:** Mark `[x]` when a task is verified working, not just coded.

---

## Group 1: Database Migration

### Task 1.1 — Add new columns to `calibration_history` in `migrate.py`
- [x] **File:** `app/db/migrate.py`
- [x] In `ensure_schema()`, inside the `with engine.begin() as conn:` block, after the existing `run_id` column check, add 5 new `ALTER TABLE` statements (each guarded by an `if "col_name" not in cal_cols:` check):
  - `node_id TEXT` — nullable, no default
  - `accepted_at TEXT` — nullable, no default
  - `accepted_by TEXT` — nullable, no default
  - `rollback_source_id TEXT` — nullable, no default
  - `registration_method_json TEXT DEFAULT 'null'`
- [x] All 5 checks must be idempotent (run `ensure_schema()` twice without errors)
- [x] **Test:** Run `python -c "from app.db.migrate import ensure_schema; from app.db.session import get_engine; ensure_schema(get_engine())"` — no errors. Run again — still no errors.

### Task 1.2 — Add new `Mapped` columns to `CalibrationHistoryModel`
- [x] **File:** `app/db/models.py` → class `CalibrationHistoryModel`
- [x] Add 5 new `Mapped` column declarations after the existing `run_id` column:
  ```python
  node_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  accepted_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  accepted_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  rollback_source_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
  registration_method_json: Mapped[str] = mapped_column(String, default="null")
  ```
- [x] Update `to_dict()` method to include:
  ```python
  "node_id": self.node_id,
  "accepted_at": self.accepted_at,
  "accepted_by": self.accepted_by,
  "rollback_source_id": self.rollback_source_id,
  "registration_method": json.loads(self.registration_method_json or "null"),
  ```
- [x] **Test:** `CalibrationHistoryModel().to_dict()` includes all 5 new keys without error.

---

## Group 2: ORM Functions

### Task 2.1 — Update `create_calibration_record()` signature
- [x] **File:** `app/repositories/calibration_orm.py`
- [x] Add 5 new optional parameters to `create_calibration_record()`:
  - `node_id: Optional[str] = None`
  - `accepted_at: Optional[str] = None`
  - `accepted_by: Optional[str] = None`
  - `rollback_source_id: Optional[str] = None`
  - `registration_method: Optional[Dict[str, Any]] = None`
- [x] Pass them to the `CalibrationHistoryModel(...)` constructor:
  - `node_id=node_id`
  - `accepted_at=accepted_at`
  - `accepted_by=accepted_by`
  - `rollback_source_id=rollback_source_id`
  - `registration_method_json=json.dumps(registration_method) if registration_method else "null"`
- [x] All existing callers of `create_calibration_record()` still work (new params have defaults)
- [x] **Test:** Call without new params — existing tests pass. Call with new params — new fields are persisted.

### Task 2.2 — Fix and activate `update_calibration_acceptance()`
- [x] **File:** `app/repositories/calibration_orm.py`
- [x] This function exists but is never called. Add `accepted_at: Optional[str] = None` parameter.
- [x] When `accepted=True` is passed and `accepted_at` is not `None`, set `record.accepted_at = accepted_at`
- [x] The function signature becomes:
  ```python
  def update_calibration_acceptance(
      db: Session,
      record_id: str,
      accepted: bool,
      notes: Optional[str] = None,
      accepted_at: Optional[str] = None,
  ) -> Optional[CalibrationHistoryModel]:
  ```
- [x] **Test:** Create a record, call `update_calibration_acceptance(db, record_id, True, accepted_at="2026-01-01T00:00:00Z")`, assert `accepted_at` is persisted.

### Task 2.3 — Add `get_calibration_history_by_node()` function
- [x] **File:** `app/repositories/calibration_orm.py`
- [x] Add new function:
  ```python
  def get_calibration_history_by_node(
      db: Session,
      node_id: str,
      limit: Optional[int] = None,
      run_id: Optional[str] = None
  ) -> List[CalibrationHistoryModel]:
  ```
- [x] Filter by `CalibrationHistoryModel.node_id == node_id`
- [x] Optionally chain `.filter(CalibrationHistoryModel.run_id == run_id)` when `run_id` is not None
- [x] Order by `timestamp` descending
- [x] Apply `limit` if not None
- [x] **Test:** Insert 3 records with `node_id="test-node"`, call function, assert all 3 returned sorted desc.

### Task 2.4 — Add `run_id` filter to `get_calibration_history()`
- [x] **File:** `app/repositories/calibration_orm.py`
- [x] Add `run_id: Optional[str] = None` parameter to `get_calibration_history()`
- [x] When `run_id` is not `None`, add `.filter(CalibrationHistoryModel.run_id == run_id)` to the query
- [x] **Test:** Insert 2 records with different `run_id` values, assert filter returns only the matching one.

---

## Group 3: CalibrationNode Changes

### Task 3.1 — Add `get_calibration_status()` method
- [x] **File:** `app/modules/calibration/calibration_node.py`
- [x] Add new public method `get_calibration_status(self) -> Dict[str, Any]` to `CalibrationNode` class
- [x] Method must NOT modify any state (pure read)
- [x] Determine `calibration_state`:
  - `"pending"` if `self._pending_calibration is not None`
  - `"idle"` otherwise
- [x] Compute `quality_good`:
  - `None` if no pending calibration
  - `True` if all pending records have `fitness >= self.min_fitness_to_save`
  - `False` otherwise
- [x] Build `pending_results` dict: for each `(sensor_id, record)` in `self._pending_calibration.items()`:
  ```python
  {
      "fitness": record.fitness,
      "rmse": record.rmse,
      "quality": record.quality,
      "quality_good": record.fitness >= self.min_fitness_to_save,
      "source_sensor_id": record.source_sensor_id,
      "processing_chain": list(record.processing_chain or []),
      "pose_before": record.pose_before.to_flat_dict(),
      "pose_after": record.pose_after.to_flat_dict(),
      "transformation_matrix": record.transformation_matrix,
  }
  ```
- [x] Return the full dict as specified in `technical.md` § 2.3
- [x] **Test:** Create a `CalibrationNode` instance, set `_pending_calibration` with mock records, call `get_calibration_status()`, assert all fields present and values correct.

### Task 3.2 — Fix `sample_frames` default inconsistency
- [x] **File:** `app/api/v1/calibration/dto.py`
- [x] Change `TriggerCalibrationRequest.sample_frames: int = 1` to `sample_frames: int = 5`
- [x] Verify `calibration_node.py` `trigger_calibration()` also uses `5` as fallback: `sample_frames = params.get("sample_frames", 5)` (already correct — confirm only)
- [x] **Test:** Trigger with no `sample_frames` param → default is 5.

### Task 3.3 — Pass `node_id` and `accepted_at` when saving calibration records
- [x] **File:** `app/modules/calibration/history.py` → `CalibrationHistory.save_record()`
- [x] Add `node_id: Optional[str] = None` parameter to `CalibrationHistory.save_record()`
- [x] Pass `node_id=node_id` to `calibration_orm.create_calibration_record()`
- [x] **File:** `app/modules/calibration/calibration_node.py` → `_apply_calibration()`
- [x] After `CalibrationHistory.save_record(record, db_session=db)`, call:
  ```python
  calibration_orm.update_calibration_acceptance(
      db=db,
      record_id=record_id,  # need to capture from save_record return value
      accepted=True,
      accepted_at=datetime.now(timezone.utc).isoformat()
  )
  ```
  - **Note:** `save_record()` must return the `record_id` string (update it to `return record_id`)
- [x] Pass `node_id=self.id` when calling `CalibrationHistory.save_record(record, node_id=self.id, ...)`
- [x] **Test:** Accept a calibration, check DB row has `node_id` set and `accepted_at` is an ISO-8601 string.

---

## Group 4: History Rollback Fix

### Task 4.1 — Update `RollbackRequest` DTO to use `record_id`
- [x] **File:** `app/api/v1/calibration/dto.py`
- [x] Change `RollbackRequest`:
  ```python
  class RollbackRequest(BaseModel):
      record_id: str   # was: timestamp: str
  ```
- [x] **Test:** POST `{"record_id": "abc123"}` — Pydantic validation passes. POST `{"timestamp": "..."}` — validation error.

### Task 4.2 — Fix `rollback_calibration()` service function
- [x] **File:** `app/api/v1/calibration/service.py`
- [x] Change `rollback_calibration()` to use `calibration_orm.get_calibration_by_id(db, request.record_id)` (NOT `get_calibration_by_timestamp`)
- [x] Remove the `node_manager.nodes.get(sensor_id)` existence check — the sensor may not be in-memory (rolled-back sensors may have been stopped). Only the DB record and `NodeRepository` are needed.
- [x] After applying the pose via `repo.update_node_pose()`, create a new "rollback" history record using `calibration_orm.create_calibration_record()`:
  ```python
  rollback_record_id = uuid.uuid4().hex
  calibration_orm.create_calibration_record(
      db=db,
      record_id=rollback_record_id,
      sensor_id=sensor_id,
      reference_sensor_id=record.reference_sensor_id or "",
      fitness=record.fitness,
      rmse=record.rmse,
      quality=record.quality,
      stages_used=json.loads(record.stages_used_json),
      pose_before=current_pose_dict,   # read current pose before rollback
      pose_after=json.loads(record.pose_after_json),
      transformation_matrix=json.loads(record.transformation_matrix_json),
      accepted=True,
      accepted_at=datetime.now(timezone.utc).isoformat(),
      node_id=record.node_id,
      rollback_source_id=request.record_id,
      source_sensor_id=record.source_sensor_id,
      run_id=None,
  )
  ```
- [x] Update response to include `new_record_id`:
  ```python
  return {
      "success": True,
      "sensor_id": sensor_id,
      "restored_to": record.timestamp,
      "new_record_id": rollback_record_id,
  }
  ```
- [x] Trigger `await node_manager.reload_config()` (already present — confirm it remains)
- [x] **Test:** POST rollback with valid `record_id` → sensor pose updated, new history record created with `rollback_source_id`, DAG reloads.

### Task 4.3 — Update `RollbackResponse` schema
- [x] **File:** `app/api/v1/schemas/calibration.py`
- [x] Update `RollbackResponse`:
  ```python
  class RollbackResponse(BaseModel):
      success: bool
      sensor_id: str
      restored_to: str
      new_record_id: str
  ```
- [x] **Test:** Response serializes all 4 fields.

---

## Group 5: API Endpoint Changes

### Task 5.1 — Add new `GET /calibration/{node_id}/status` endpoint
- [x] **File:** `app/api/v1/schemas/calibration.py`
- [x] Add new Pydantic models:
  ```python
  class PendingCalibrationResult(BaseModel):
      fitness: float
      rmse: float
      quality: str
      quality_good: bool
      source_sensor_id: Optional[str] = None
      processing_chain: List[str] = []
      pose_before: Dict[str, float]
      pose_after: Dict[str, float]
      transformation_matrix: List[List[float]]

  class CalibrationNodeStatusResponse(BaseModel):
      node_id: str
      node_name: str
      enabled: bool
      calibration_state: str
      quality_good: Optional[bool]
      reference_sensor_id: Optional[str]
      source_sensor_ids: List[str]
      buffered_frames: Dict[str, int]
      last_calibration_time: Optional[str]
      pending_results: Dict[str, PendingCalibrationResult]
  ```
- [x] **File:** `app/api/v1/calibration/service.py`
- [x] Add `get_calibration_status()` function (imports `CalibrationNode`, calls `node.get_calibration_status()`)
- [x] **File:** `app/api/v1/calibration/handler.py`
- [x] Register endpoint:
  ```python
  @router.get(
      "/calibration/{node_id}/status",
      response_model=CalibrationNodeStatusResponse,
      responses={404: {"description": "Node not found"}},
      summary="Get Calibration Node Status",
  )
  async def calibration_status_endpoint(node_id: str):
      return await get_calibration_status(node_id)
  ```
  **IMPORTANT:** This route MUST be registered BEFORE the `rollback` and `history` routes, or FastAPI may match `{node_id}` = "history" or "rollback". Verify route ordering in the router.
- [x] **Test:** `GET /api/v1/calibration/test-node-id/status` with a live node → 200 with valid JSON. With non-existent node → 404.

### Task 5.2 — Fix `reject_calibration()` response schema
- [x] **File:** `app/api/v1/schemas/calibration.py`
- [x] Add:
  ```python
  class RejectResponse(BaseModel):
      success: bool
      rejected: List[str]
  ```
- [x] **File:** `app/api/v1/calibration/service.py` → `reject_calibration()`
- [x] Before calling `node.reject_calibration()`, capture: `rejected_ids = list((node._pending_calibration or {}).keys())`
- [x] Return: `{"success": True, "rejected": rejected_ids}`
- [x] **File:** `app/api/v1/calibration/handler.py`
- [x] Change `response_model=StatusResponse` to `response_model=RejectResponse` on the reject endpoint
- [x] Remove `StatusResponse` import from handler if no longer used
- [x] **Test:** POST reject when 2 sensors pending → `{"success": true, "rejected": ["sensor-a", "sensor-b"]}`. POST reject when nothing pending → `{"success": true, "rejected": []}`.

### Task 5.3 — Add `run_id` query param to history endpoint
- [x] **File:** `app/api/v1/calibration/handler.py`
- [x] Update `calibration_history_endpoint()` signature to add `run_id: Optional[str] = None`
- [x] Pass `run_id` to `get_calibration_history()` in `service.py`
- [x] **File:** `app/api/v1/calibration/service.py` → `get_calibration_history()`
- [x] Add `run_id: Optional[str] = None` parameter
- [x] When neither `source_sensor_id` nor `run_id` → use legacy `get_calibration_history(db, sensor_id, limit)`
- [x] When `run_id` provided → use `calibration_orm.get_calibration_history(db, sensor_id, limit, run_id=run_id)`
- [x] When `source_sensor_id` provided → existing `get_calibration_history_by_source()` path (unchanged)
- [x] **Test:** Insert 5 records with 2 different `run_id` values. `GET /history/sensor?run_id=abc` → returns only 2.

### Task 5.4 — Update `CalibrationRecord` schema to include new fields
- [x] **File:** `app/api/v1/schemas/calibration.py`
- [x] Extend `CalibrationRecord` Pydantic model with all new fields as per `api-spec.md` § 5
- [x] Add: `accepted_at`, `accepted_by`, `node_id`, `rollback_source_id`, `registration_method`, `pose_before`, `pose_after`, `transformation_matrix`, `stages_used`, `notes`
- [x] All new fields must be `Optional` with `None` default for backward compatibility with legacy records
- [x] **Test:** `CalibrationRecord(**old_record_dict_without_new_fields)` — validation succeeds with defaults.

---

## Group 6: Integration Tests

### Task 6.1 — Write integration test for the full calibration workflow
- [x] **File:** `tests/api/test_calibration_workflow.py` (new file)
- [x] Test sequence:
  1. Trigger calibration → `POST /trigger` → assert `pending_approval=true`
  2. Poll status → `GET /status` → assert `calibration_state="pending"`, `pending_results` non-empty
  3. Accept → `POST /accept` → assert `success=true`, `accepted` list non-empty
  4. Poll status → `GET /status` → assert `calibration_state="idle"`
  5. Fetch history → `GET /history/{node_id}` → assert 1 record with `accepted=true`, `accepted_at` set
  6. Rollback → `POST /rollback/{sensor_id}` with `record_id` → assert `success=true`, `new_record_id` returned
  7. Fetch history → assert 2 records (original + rollback), second has `rollback_source_id` set

### Task 6.2 — Write unit test for `get_calibration_status()`
- [x] **File:** `tests/modules/test_calibration_node_status.py` (11 tests covering all 3 states)
- [x] Test: No pending calibration → `calibration_state="idle"`, `quality_good=None`, `pending_results={}`
- [x] Test: Pending calibration with good fitness → `calibration_state="pending"`, `quality_good=True`
- [x] Test: Pending calibration with poor fitness → `calibration_state="pending"`, `quality_good=False`

### Task 6.3 — Write unit test for rollback with `record_id`
- [x] **File:** `tests/api/test_calibration_rollback.py` (new file)
- [x] Test: Valid `record_id` → 200, `new_record_id` in response
- [x] Test: Non-existent `record_id` → 404
- [x] Test: Non-accepted `record_id` → 400
- [x] Test: Old `{"timestamp": "..."}` body → 422 Unprocessable Entity (Pydantic validation)
