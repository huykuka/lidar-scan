# Playback Node — Backend Tasks

**References**: `requirements.md`, `technical.md`, `api-spec.md`

> **Recording discovery uses `GET /api/v1/recordings` (existing). No new listing or info endpoints.**

---

## Module: `app/modules/playback/`

- [x] Create `app/modules/playback/__init__.py`
- [x] Create `app/modules/playback/node.py` — `PlaybackNode(ModuleNode)`
  - [x] Constructor: accept `recording_id`, `playback_speed`, `loopable`, `throttle_ms`; store all fields
  - [x] **Validate `playback_speed`** in constructor: must be in `{0.1, 0.25, 0.5, 1.0}`; raise `ValueError` for any other value (enforces never-faster-than-1.0× constraint); log warning and raise
  - [x] `start()`: call `RecordingRepository(db).get_by_id(recording_id)` to resolve `file_path`; validate file exists on disk; create `asyncio.Task` for `_run_loop()`; set `_status = "error"` if file missing or zero frames
  - [x] `_run_loop()`: open `RecordingReader(file_path)` via `asyncio.to_thread`; iterate frames with `asyncio.to_thread(reader.get_frame, i)`; compute `sleep_s = avg_interval / playback_speed + throttle_ms/1000`; call `manager.forward_data(node_id, payload)` per frame; handle `loopable`/stop transition; update `_status` and `_current_frame` throughout
  - [x] `stop()`: cancel `_task`, await, close `_reader`, `_status = "idle"`
  - [x] `on_input()`: no-op (source node)
  - [x] `emit_status()`: map `_status` → `OperationalState` + `ApplicationState` with frame counter `"playing (frame N/M)"`
  - [x] Error handling: missing file → `ERROR`; zero frames → `ERROR`; frame parse failure → log + skip; I/O error → `ERROR`; invalid `playback_speed` at build time → `400`
- [x] Create `app/modules/playback/registry.py`
  - [x] Register `NodeDefinition` (type=`"playback"`, category=`"sensor"`, `websocket_enabled=True`, properties per `api-spec.md §2`): `recording_id`, `playback_speed` (select enum), `loopable` (boolean), `throttle_ms`
  - [x] `@NodeFactory.register("playback")` builder: inject DB session; call `RecordingRepository(db).get_by_id(config["recording_id"])` to get `file_path`; validate `config.get("playback_speed", 1.0)` is in `VALID_SPEEDS` — raise `ValueError` → `400`; instantiate `PlaybackNode`
- [x] Wire `app/modules/playback/registry.py` into `discover_modules()` (follow existing pattern in `app/modules/__init__.py`)

---

## Integration with Existing Recordings API

- [x] Verify `RecordingRepository.get_by_id()` returns a dict with `file_path`, `frame_count`, `duration_seconds` — confirm these are populated for all recordings in the DB (no migration needed if already present)
- [x] Confirm `RecordingReader(file_path)` accepts the absolute or relative `file_path` value stored in `RecordingResponse.file_path` — test with a real DB record
- [x] Verify `GET /api/v1/recordings` returns only completed recordings (not active) for playback selection — confirm `active_recordings` is a separate list and `recordings[]` is safe to display

> ⚠️ **No changes to `app/api/v1/recordings/`**. If a bug or gap is found in the existing API that blocks playback (e.g., `file_path` missing), fix it in the existing service — do not add a parallel endpoint.

---

## Shared / Config

- [x] Add `app.modules.playback.registry` import to module discovery (regression: run `test_all_module_registries_loaded`)

---

## Dependencies / Order

1. Verify `RecordingRepository` and `file_path` field are correct before starting `PlaybackNode` implementation
2. `PlaybackNode` module — can be developed in parallel with frontend (FE mocks `GET /api/v1/recordings`)
3. No new API files to create — existing recordings router is already registered
