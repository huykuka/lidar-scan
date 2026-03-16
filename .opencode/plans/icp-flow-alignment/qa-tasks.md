# QA Tasks — ICP Flow Alignment

**Feature:** `icp-flow-alignment`
**Owner:** @qa

**References:**
- Requirements: `requirements.md`
- Architecture: `technical.md`
- API Contract: `api-spec.md`
- Backend Tasks: `backend-tasks.md`
- Frontend Tasks: `frontend-tasks.md`

---

## TDD Preparation

- [x] Confirm failing backend tests exist for `processing_chain` propagation through DAG before Group A implementation starts.
- [x] Confirm failing backend tests exist for `BufferedFrame` storage and `_aggregate_frames` before Group B/C implementation starts.
- [x] Confirm failing backend tests exist for `_apply_calibration` targeting the correct leaf sensor before Group C implementation starts.
- [x] Confirm failing backend tests exist for new DB columns and ORM helpers before Group D implementation starts.

---

## Unit Test Execution

### Payload Protocol (Group A)

- [x] Verify `LidarSensor.handle_data` initialises `processing_chain = [self.id]` when key is absent from payload.
- [x] Verify `LidarSensor.handle_data` does not overwrite a `processing_chain` already present in the payload.
- [x] Verify `lidar_id` is set by `pcd_worker_process` before the payload reaches `handle_data`.
- [x] Verify intermediate nodes (crop, downsample) do not strip `lidar_id` or `processing_chain` from forwarded payloads.

### Data Structures (Group B)

- [x] Verify `BufferedFrame` dataclass stores `source_sensor_id`, `processing_chain`, `node_id`, `timestamp`, and `points`.
- [x] Verify `CalibrationRecord` accepts and stores `source_sensor_id`, `processing_chain`, and `run_id`.
- [x] Verify `create_calibration_record` passes new fields through correctly; defaults are empty string / empty list / empty string.

### CalibrationNode Logic (Group C)

- [x] Verify `on_input` extracts `source_sensor_id` from `lidar_id` (not `node_id`) when both are present.
- [x] Verify `on_input` falls back to `node_id` when `lidar_id` is absent.
- [x] Verify `_frame_buffer[source_sensor_id]` is a `deque` with `maxlen = max_buffered_frames` (default 30).
- [x] Verify `_frame_buffer` accumulates multiple frames per sensor before overflowing oldest.
- [x] Verify `_aggregate_frames` concatenates the most recent `sample_frames` entries correctly.
- [x] Verify `_aggregate_frames` returns the `processing_chain` of the **most recent** frame.
- [x] Verify `_aggregate_frames` returns `None` when the sensor has no buffered data.
- [x] Verify `trigger_calibration` generates a `run_id` of exactly 12 hex characters.
- [x] Verify `_apply_calibration` calls `update_node_config` with `source_sensor_id`, not an intermediate node ID.
- [x] Verify `get_status["buffered_frames"]` returns a `Dict[str, int]` (count per sensor) not a list.

### Database & ORM (Group D)

- [x] Verify `ensure_schema()` adds `source_sensor_id`, `processing_chain_json`, and `run_id` columns without error on a fresh DB.
- [x] Verify `ensure_schema()` is idempotent — running twice on an existing DB with the columns does not raise.
- [x] Verify existing rows in `calibration_history` remain intact after migration (no data corruption).
- [x] Verify `create_calibration_record` serialises `processing_chain` as JSON string in `processing_chain_json`.
- [x] Verify `to_dict()` deserialises `processing_chain_json` back to a Python list.
- [x] Verify `get_calibration_history_by_source` filters correctly on `source_sensor_id`.
- [x] Verify `get_calibration_history_by_run` returns all records sharing a `run_id`.

---

## Integration Test Execution

### Traceability — Direct Sensor Wiring

- [x] Sensor A and Sensor B connected directly to `CalibrationNode` (no intermediate nodes):
  - Trigger calibration → verify `processing_chain` for A is `["sensor-A-id", "calib-node-id"]`.
  - Verify `source_sensor_id` in response equals `lidar_id` of Sensor A.
  - Accept → verify `NodeRepository` was updated for Sensor A's node ID.
  - Query history → verify record has `source_sensor_id`, `processing_chain`, and `run_id` populated.

### Traceability — Sensor Behind Intermediate Nodes

- [x] Sensor A → CropNode → DownsampleNode → CalibrationNode:
  - Trigger calibration → verify `processing_chain` is `["sensor-A-id", "crop-id", "ds-id", "calib-id"]`.
  - Verify `source_sensor_id` in response equals `lidar_id` of Sensor A (not crop or downsample node ID).
  - Accept → verify `NodeRepository` was updated for Sensor A (the leaf), not the crop or downsample node.

### run_id Correlation

- [x] Trigger calibration with two source sensors → verify both results in the response share the same `run_id`.
- [x] Query `GET /api/v1/calibration/history/{id}?run_id={run_id}` → verify both sensor records are returned.

### History Filtering

- [x] `GET /api/v1/calibration/history/{id}?source_sensor_id={leaf_id}` → returns only records matching the leaf sensor.
- [x] Mixing `source_sensor_id` and `run_id` query params works without error (most specific filter applies).

### Concurrent Trigger Guard

- [x] Second `POST trigger` while first is running returns `409 Conflict`.

### Accept / Reject Lifecycle

- [x] Accept a subset of pending sensors → `remaining_pending` in response lists the un-accepted sensors.
- [x] Reject clears `_pending_calibration` without writing to DB or updating node config.

---

## Backward Compatibility

- [x] Query history records created before this feature (legacy rows): confirm `source_sensor_id=null`, `processing_chain=[]`, `run_id=null` in response body.
- [x] Existing accept/reject endpoints work without a `run_id` field in the request body.

---

## E2E / Workflow Validation

- [x] Operator places CalibrationNode, connects two sensors directly → triggers, reviews, accepts. Verify new pose applied to correct sensor in live DAG.
- [x] Operator connects Sensor A through a crop node → triggers → `processing_chain` shown in UI includes crop node ID.
- [x] Operator triggers → observes low-fitness result → rejects → no pose change persisted.
- [x] Operator queries calibration history filtered by `source_sensor_id` → correct records returned.

---

## Linter Verification

- [x] Run backend lint/type checks (mypy/ruff) — no new errors introduced by the feature changes.
- [x] Run frontend lint/type checks — frontend handles optional `source_sensor_id`, `processing_chain`, and `run_id` fields gracefully.

---

## Developer Coordination

- [x] Verify backend Group A–F completion with `@be-dev` against `backend-tasks.md`.
- [x] Verify frontend completion with `@fe-dev` against `frontend-tasks.md`.
- [x] Confirm `api-spec.md` is the source of truth for any contract questions — escalate drift to `@architecture`.

---

## Pre-PR Verification

- [x] Run full backend unit test suite — all Group A–F unit tests pass.
- [x] Run full backend integration suite — all traceability and history tests pass.
- [x] Run backward-compatibility smoke test against a DB with pre-existing calibration_history rows.
- [x] Run E2E workflow smoke test for direct and indirect sensor wiring cases.
