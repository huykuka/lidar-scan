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

- [ ] Confirm failing backend tests exist for `processing_chain` propagation through DAG before Group A implementation starts.
- [ ] Confirm failing backend tests exist for `BufferedFrame` storage and `_aggregate_frames` before Group B/C implementation starts.
- [ ] Confirm failing backend tests exist for `_apply_calibration` targeting the correct leaf sensor before Group C implementation starts.
- [ ] Confirm failing backend tests exist for new DB columns and ORM helpers before Group D implementation starts.

---

## Unit Test Execution

### Payload Protocol (Group A)

- [ ] Verify `LidarSensor.handle_data` initialises `processing_chain = [self.id]` when key is absent from payload.
- [ ] Verify `LidarSensor.handle_data` does not overwrite a `processing_chain` already present in the payload.
- [ ] Verify `lidar_id` is set by `pcd_worker_process` before the payload reaches `handle_data`.
- [ ] Verify intermediate nodes (crop, downsample) do not strip `lidar_id` or `processing_chain` from forwarded payloads.

### Data Structures (Group B)

- [ ] Verify `BufferedFrame` dataclass stores `source_sensor_id`, `processing_chain`, `node_id`, `timestamp`, and `points`.
- [ ] Verify `CalibrationRecord` accepts and stores `source_sensor_id`, `processing_chain`, and `run_id`.
- [ ] Verify `create_calibration_record` passes new fields through correctly; defaults are empty string / empty list / empty string.

### CalibrationNode Logic (Group C)

- [ ] Verify `on_input` extracts `source_sensor_id` from `lidar_id` (not `node_id`) when both are present.
- [ ] Verify `on_input` falls back to `node_id` when `lidar_id` is absent.
- [ ] Verify `_frame_buffer[source_sensor_id]` is a `deque` with `maxlen = max_buffered_frames` (default 30).
- [ ] Verify `_frame_buffer` accumulates multiple frames per sensor before overflowing oldest.
- [ ] Verify `_aggregate_frames` concatenates the most recent `sample_frames` entries correctly.
- [ ] Verify `_aggregate_frames` returns the `processing_chain` of the **most recent** frame.
- [ ] Verify `_aggregate_frames` returns `None` when the sensor has no buffered data.
- [ ] Verify `trigger_calibration` generates a `run_id` of exactly 12 hex characters.
- [ ] Verify `_apply_calibration` calls `update_node_config` with `source_sensor_id`, not an intermediate node ID.
- [ ] Verify `get_status["buffered_frames"]` returns a `Dict[str, int]` (count per sensor) not a list.

### Database & ORM (Group D)

- [ ] Verify `ensure_schema()` adds `source_sensor_id`, `processing_chain_json`, and `run_id` columns without error on a fresh DB.
- [ ] Verify `ensure_schema()` is idempotent — running twice on an existing DB with the columns does not raise.
- [ ] Verify existing rows in `calibration_history` remain intact after migration (no data corruption).
- [ ] Verify `create_calibration_record` serialises `processing_chain` as JSON string in `processing_chain_json`.
- [ ] Verify `to_dict()` deserialises `processing_chain_json` back to a Python list.
- [ ] Verify `get_calibration_history_by_source` filters correctly on `source_sensor_id`.
- [ ] Verify `get_calibration_history_by_run` returns all records sharing a `run_id`.

---

## Integration Test Execution

### Traceability — Direct Sensor Wiring

- [ ] Sensor A and Sensor B connected directly to `CalibrationNode` (no intermediate nodes):
  - Trigger calibration → verify `processing_chain` for A is `["sensor-A-id", "calib-node-id"]`.
  - Verify `source_sensor_id` in response equals `lidar_id` of Sensor A.
  - Accept → verify `NodeRepository` was updated for Sensor A's node ID.
  - Query history → verify record has `source_sensor_id`, `processing_chain`, and `run_id` populated.

### Traceability — Sensor Behind Intermediate Nodes

- [ ] Sensor A → CropNode → DownsampleNode → CalibrationNode:
  - Trigger calibration → verify `processing_chain` is `["sensor-A-id", "crop-id", "ds-id", "calib-id"]`.
  - Verify `source_sensor_id` in response equals `lidar_id` of Sensor A (not crop or downsample node ID).
  - Accept → verify `NodeRepository` was updated for Sensor A (the leaf), not the crop or downsample node.

### run_id Correlation

- [ ] Trigger calibration with two source sensors → verify both results in the response share the same `run_id`.
- [ ] Query `GET /api/v1/calibration/history/{id}?run_id={run_id}` → verify both sensor records are returned.

### History Filtering

- [ ] `GET /api/v1/calibration/history/{id}?source_sensor_id={leaf_id}` → returns only records matching the leaf sensor.
- [ ] Mixing `source_sensor_id` and `run_id` query params works without error (most specific filter applies).

### Concurrent Trigger Guard

- [ ] Second `POST trigger` while first is running returns `409 Conflict`.

### Accept / Reject Lifecycle

- [ ] Accept a subset of pending sensors → `remaining_pending` in response lists the un-accepted sensors.
- [ ] Reject clears `_pending_calibration` without writing to DB or updating node config.

---

## Backward Compatibility

- [ ] Query history records created before this feature (legacy rows): confirm `source_sensor_id=null`, `processing_chain=[]`, `run_id=null` in response body.
- [ ] Existing accept/reject endpoints work without a `run_id` field in the request body.

---

## E2E / Workflow Validation

- [ ] Operator places CalibrationNode, connects two sensors directly → triggers, reviews, accepts. Verify new pose applied to correct sensor in live DAG.
- [ ] Operator connects Sensor A through a crop node → triggers → `processing_chain` shown in UI includes crop node ID.
- [ ] Operator triggers → observes low-fitness result → rejects → no pose change persisted.
- [ ] Operator queries calibration history filtered by `source_sensor_id` → correct records returned.

---

## Linter Verification

- [ ] Run backend lint/type checks (mypy/ruff) — no new errors introduced by the feature changes.
- [ ] Run frontend lint/type checks — frontend handles optional `source_sensor_id`, `processing_chain`, and `run_id` fields gracefully.

---

## Developer Coordination

- [ ] Verify backend Group A–F completion with `@be-dev` against `backend-tasks.md`.
- [ ] Verify frontend completion with `@fe-dev` against `frontend-tasks.md`.
- [ ] Confirm `api-spec.md` is the source of truth for any contract questions — escalate drift to `@architecture`.

---

## Pre-PR Verification

- [ ] Run full backend unit test suite — all Group A–F unit tests pass.
- [ ] Run full backend integration suite — all traceability and history tests pass.
- [ ] Run backward-compatibility smoke test against a DB with pre-existing calibration_history rows.
- [ ] Run E2E workflow smoke test for direct and indirect sensor wiring cases.
