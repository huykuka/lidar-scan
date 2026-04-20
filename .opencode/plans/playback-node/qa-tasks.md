# Playback Node — QA Tasks

**References**: `requirements.md`, `technical.md`, `api-spec.md`

> Recording listing/metadata tests use the **existing** `GET /api/v1/recordings` endpoint only. No tests for a `/playback/recordings` endpoint (it does not exist).

---

## TDD Preparation (run BEFORE development starts)

- [ ] Write failing unit tests for `PlaybackNode` constructor (fields stored: `recording_id`, `playback_speed`, `loopable`, `throttle_ms`)
- [ ] Write failing unit tests for `_run_loop()` timing: mock `RecordingReader`, assert `asyncio.sleep` called with `avg_interval / playback_speed`
- [ ] Write failing unit tests for `loopable=False` stop condition (task ends after last frame)
- [ ] Write failing unit tests for `loopable=True` wrap condition (frame index resets to 0)
- [ ] Write failing unit tests for `emit_status()` state transitions (idle → playing → idle/error)
- [ ] Write failing unit test: invalid `playback_speed` (e.g. `2.0`, `0.0`, `"fast"`) → `ValueError` raised at construction
- [ ] Write failing integration test: `RecordingRepository.get_by_id()` result is consumed correctly by `PlaybackNode.start()`

---

## Unit Tests (Backend)

- [ ] `tests/modules/playback/test_playback_node.py`
  - [ ] Instantiation with all four valid `playback_speed` presets × `loopable` True/False
  - [ ] **Invalid `playback_speed`**: values `2.0`, `1.5`, `0.0`, `0.3`, `"fast"` → `ValueError` at construction (never > 1.0 enforced)
  - [ ] **Boundary**: `playback_speed=1.0` (max allowed) instantiates correctly
  - [ ] `on_input()` is a no-op (source node contract)
  - [ ] `_run_loop()` calls `manager.forward_data()` for each frame
  - [ ] Frame timing: `sleep(avg_interval / playback_speed)` verified for each speed preset (0.1, 0.25, 0.5, 1.0)
  - [ ] `loopable=False`: task ends after last frame, `_status` → `"idle"`
  - [ ] `loopable=True`: frame counter wraps to 0
  - [ ] Payload metadata contains `playback_speed` and `loopable` fields with correct values
  - [ ] Missing `recording_id` in DB: `start()` sets `_status = "error"`
  - [ ] `file_path` from DB does not exist on disk: `start()` sets `_status = "error"`
  - [ ] Zero-frame recording: `_status = "error"`, no frames emitted
  - [ ] Frame parse error: logged, skips frame, playback continues
  - [ ] `stop()` cancels running task cleanly

---

## Integration Tests

- [ ] `PlaybackNode` registered in `node_schema_registry` (extend `test_all_module_registries_loaded`)
- [ ] `@NodeFactory.register("playback")` builder creates correct `PlaybackNode` with `recording_id` → `file_path` resolved from DB
- [ ] **Config passing end-to-end**: send `{ playback_speed: 0.5, loopable: true }` via node create/update API → verify `PlaybackNode._playback_speed == 0.5` and `_loopable == True` at runtime
- [ ] **Invalid speed rejected at API level**: POST config `{ playback_speed: 2.0 }` → verify `400 Bad Request` response body with descriptive error
- [ ] **Invalid speed rejected at API level**: POST config `{ playback_speed: 0.75 }` (valid float, not in enum) → `400`
- [ ] `RecordingRepository.get_by_id()` returns a dict with `file_path` field; `RecordingReader(file_path)` opens successfully
- [ ] End-to-end: playback node emits `forward_data` payloads reaching a mock downstream node (minimal DAG)
- [ ] `GET /api/v1/recordings` (existing endpoint) returns a `recordings[]` list that the playback config panel can consume — verify `id`, `name`, `frame_count`, `duration_seconds` all present
- [ ] Node status polling (`/api/v1/nodes/status`) reports correct `operational_state` during playback

---

## E2E / Manual Verification

- [ ] Create a recording via the existing recorder; confirm it appears in the Playback node config dropdown
- [ ] Select recording in config panel; confirm `frame_count`, `duration_seconds`, `recording_timestamp` display correctly
- [ ] Verify `playbackSpeed` dropdown shows exactly four options: `1.0×`, `0.5×`, `0.25×`, `0.1×` — no free-text input possible
- [ ] Verify `loopable` toggle is unchecked by default; can be toggled on/off
- [ ] Confirm config `{ playback_speed, loopable }` is present in the HTTP payload when saving the node (inspect network tab)
- [ ] Configure a Playback node, start DAG, verify LIDR frames on WebSocket topic `playback_*`
- [ ] Verify speed presets: time 10 frames at `0.5×` — should take ~2× original average interval (±15%)
- [ ] Verify speed presets: time 10 frames at `0.25×` — should take ~4× original average interval (±15%)
- [ ] Verify `loopable=true`: playback restarts from frame 0 after last frame
- [ ] Verify `loopable=false`: node transitions to `idle` after last frame
- [ ] **Config switching at rest**: change `playback_speed` from `1.0` → `0.1` via config panel while node is stopped; restart → new speed applied
- [ ] Verify error state: delete recording file from disk while node is stopped; restart → node shows ERROR

---

## Performance

- [ ] 100k-point recording at 10 FPS, loop=True for 5 minutes: no memory leak (heap snapshot before/after)
- [ ] `asyncio.to_thread` keeps event loop unblocked: FastAPI latency <20ms p99 during playback

---

## Linter & Type Checks

- [ ] `cd app && ruff check app/modules/playback/`
- [ ] `mypy app/modules/playback/`
- [ ] `cd web && ng lint` — no new lint errors
- [ ] `cd web && npx tsc --noEmit` — no type errors

---

## Pre-PR Checklist

- [ ] All unit + integration tests pass (`pytest tests/modules/playback/`)
- [ ] `test_all_module_registries_loaded` passes (playback registry discovered)
- [ ] No tests reference `/api/v1/playback/recordings` — only `GET /api/v1/recordings`
- [ ] No tests or code reference old field names `speed` / `loop` — only `playback_speed` / `loopable`
- [ ] Invalid `playback_speed` test confirms `400` returned (not a silent default)
- [ ] Frontend config panel renders correctly; `playbackSpeed` dropdown and `loopable` toggle visible and functional
- [ ] Serialization verified: `playbackSpeed` (TS) → `playback_speed` (JSON) → `playback_speed` (Python)
- [ ] `requirements.md` acceptance criteria checked off manually by QA
- [ ] QA report written in `qa-report.md`
