# Playback Node — Technical Design

**References**: `requirements.md`, `backend.md`, `frontend.md`, `protocols.md`

---

## 1. Architecture Overview

The Playback Node is a **DAG source node** under `app/modules/playback/`. It reuses the **existing** `GET /api/v1/recordings` REST contract exclusively for recording discovery and metadata retrieval. No new listing or info endpoints are added.

```
DB (recordings table)
     │  ← populated by existing recorder workflow
     ▼
GET /api/v1/recordings          ← EXISTING endpoint (no change)
GET /api/v1/recordings/{id}     ← EXISTING endpoint (no change)
     │
     ▼  (Frontend config panel selects a recording_id)
PlaybackNode (asyncio task loop)
     │  RecordingReader(file_path from DB record)
     │  manager.forward_data(node_id, payload)
     ▼
NodeManager / WebSocket broadcast (LIDR binary)
     │
     ▼
Downstream DAG nodes
```

---

## 2. API Reuse Strategy

### Existing endpoints consumed (read-only, no modification)

| Endpoint | Used for |
|----------|----------|
| `GET /api/v1/recordings` | Populate recording selector dropdown in config panel |
| `GET /api/v1/recordings/{recording_id}` | Retrieve `file_path` at node start; display metadata after selection |

### RecordingResponse fields used by Playback

From the existing `RecordingResponse` DTO (`app/api/v1/recordings/dto.py`):

| Field | Playback usage |
|-------|---------------|
| `id` | Stored in node config as `recording_id` |
| `name` | Display label in dropdown |
| `file_path` | Passed to `RecordingReader` at `start()` |
| `frame_count` | Status display `frame N/M`; zero-frame guard |
| `duration_seconds` | Shown in config panel metadata summary |
| `node_id` | Shown as provenance info in config panel |
| `recording_timestamp` | Shown in config panel |
| `metadata` | Supplementary info display |

All required fields are **already present** in `RecordingResponse`. No DTO changes needed.

### ⚠️ Edge case: missing fields (future scope, NOT implemented now)

If playback ever needs per-frame timestamps for precise speed scaling (beyond `duration_seconds / frame_count` average), a new field `timestamps: list[float]` in `RecordingResponse` would be required. This is **deferred** — current implementation uses average-interval timing. Any future addition must go through a `RecordingResponse` DTO change in `app/api/v1/recordings/dto.py`, **not** a new endpoint.

---

## 3. Module Directory Layout

```
app/modules/playback/
    __init__.py
    node.py       ← PlaybackNode(ModuleNode)
    registry.py   ← NodeDefinition + @NodeFactory.register("playback")
```

---

## 4. Backend: `PlaybackNode`

### 4.1 Constructor Signature

```python
class PlaybackNode(ModuleNode):
    def __init__(
        self,
        manager: Any,
        node_id: str,
        name: str,
        recording_id: str,           # DB UUID — resolved to file_path at start()
        playback_speed: float = 1.0, # renamed from `speed`; clamped to (0, 1.0]
        loopable: bool = False,       # renamed from `loop`
        throttle_ms: float = 0,
    ): ...
```

**Note**: config stores `recording_id` (DB UUID), not a raw file path. The factory builder resolves `file_path` via `GET /api/v1/recordings/{id}` (or directly via `RecordingRepository`) at instantiation.

### 4.2 Internal State

| Attribute | Type | Purpose |
|-----------|------|---------|
| `_reader` | `RecordingReader \| None` | Opened at `start()`, closed at `stop()` |
| `_task` | `asyncio.Task \| None` | Background playback loop |
| `_status` | `str` | `"idle"` / `"playing"` / `"error"` |
| `_current_frame` | `int` | Frame counter for status reporting |
| `_total_frames` | `int` | Set from `RecordingReader.frame_count` at start |
| `_playback_speed` | `float` | Validated at construction: must be in `{0.1, 0.25, 0.5, 1.0}`, clamped to `≤1.0` |
| `_loopable` | `bool` | Whether to restart from frame 0 after the last frame |

### 4.3 Config Validation

`playback_speed` is validated at construction and in the factory builder:

```python
VALID_SPEEDS = {0.1, 0.25, 0.5, 1.0}

def _validate_speed(value: float) -> float:
    if value not in VALID_SPEEDS:
        raise ValueError(f"Invalid playback_speed {value!r}. Must be one of {sorted(VALID_SPEEDS)}")
    return value  # always ≤ 1.0 by definition of the allowed set
```

- Values not in the allowed set → `ValueError` → node instantiation fails → `400 Bad Request` from DAG API.
- Frontend `syn-select` constrains input to the four valid options, making invalid values unreachable under normal use.
- `loopable` requires no additional validation (boolean).

### 4.4 Playback Loop (`_run_loop`)

```
open RecordingReader(file_path) via asyncio.to_thread
while not cancelled:
    get_frame(i)  ← asyncio.to_thread (ZIP read + PCD unpack)
    build payload: {points, timestamp, node_id, metadata}
    manager.forward_data(node_id, payload)

    compute delay:
        avg_interval = duration_seconds / max(frame_count - 1, 1)
        sleep_s = max(0, avg_interval / playback_speed)  (+ throttle_ms/1000)
    await asyncio.sleep(sleep_s)

    advance i (wrap if loopable=True, else stop after last frame)
transition to "idle" on clean finish, "error" on exception
```

ZIP reads run on `asyncio.to_thread()` — never blocking the event loop.

### 4.5 Lifecycle Methods

| Method | Behaviour |
|--------|-----------|
| `start()` | Resolve `file_path` from DB; validate file exists; create `_task` |
| `stop()` | Cancel `_task`, await, close `_reader`, `_status = "idle"` |
| `on_input(payload)` | No-op (source node) |
| `emit_status()` | Maps `_status` → `OperationalState` |

### 4.6 `emit_status` Mapping

| `_status` | `OperationalState` | `application_state.value` |
|-----------|-------------------|--------------------------|
| `idle` | `STOPPED` | `"idle"` |
| `playing` | `RUNNING` | `"playing (frame N/M)"` |
| `error` | `ERROR` | error message string |

### 4.7 Payload Schema

```python
    {
        "points": np.ndarray,     # shape (N,3), float32 — from RecordingReader
        "timestamp": float,       # original recording timestamp
        "node_id": str,
        "metadata": {
            "source": "playback",
            "recording_id": str,
            "frame": int,
            "total_frames": int,
            "playback_speed": float,
            "loopable": bool,
        }
    }
```

---

## 5. Backend: `registry.py`

```python
node_schema_registry.register(NodeDefinition(
    type="playback",
    display_name="Playback",
    category="sensor",
    description="Replay a recording as synthetic sensor data",
    icon="play_circle",
    websocket_enabled=True,
    properties=[
        PropertySchema(
            name="recording_id", label="Recording", type="select",
            required=True, options=[],   # populated dynamically by FE from /api/v1/recordings
        ),
        PropertySchema(name="playback_speed", label="Playback Speed", type="select", default=1.0,
                       options=[
                           {"label": "1.0×", "value": 1.0},
                           {"label": "0.5×", "value": 0.5},
                           {"label": "0.25×", "value": 0.25},
                           {"label": "0.1×", "value": 0.1},
                       ]),
        PropertySchema(name="loopable", label="Loop", type="boolean", default=False),
        PropertySchema(name="throttle_ms", label="Throttle (ms)", type="number",
                       default=0, min=0, step=10),
    ],
    outputs=[PortSchema(id="out", label="Output")],
))
```

The factory builder calls `RecordingRepository(db).get_by_id(config["recording_id"])` to resolve `file_path` before instantiating `PlaybackNode`.

---

## 6. RecordingReader Reuse

`RecordingReader` (`app/services/shared/recording.py`) is used **as-is**. No modifications required. The builder resolves `file_path` from the DB record and passes it directly to `RecordingReader(file_path)`.

Frame reads use `reader.get_frame(i)` individually inside `asyncio.to_thread()` — compatible with the existing synchronous iterator API.

---

## 7. Frontend Architecture

### 7.1 API Service — reuse existing recordings API

`web/src/app/core/services/api/recordings-api.service.ts` (existing or new if not yet created):
- `getRecordings(): Observable<ListRecordingsResponse>` → `GET /api/v1/recordings`
- `getRecording(id: string): Observable<RecordingResponse>` → `GET /api/v1/recordings/{id}`

**Do not create a new `playback-api.service.ts`** for recording discovery. If a `recordings-api.service.ts` does not yet exist in `core/services/api/`, create it there. Playback config panel injects this shared service.

### 7.2 Config Panel Integration

`web/src/app/features/workspaces/components/playback-config-panel/`

- On panel open: calls `recordingsApiService.getRecordings()` → populates `syn-select` with `{value: id, label: name}` pairs from `recordings[]`
- On recording select: calls `recordingsApiService.getRecording(id)` → displays `frame_count`, `duration_seconds`, `recording_timestamp`
- Render speed selector: `syn-select` bound to `playbackSpeed`; only the four enum values `1.0, 0.5, 0.25, 0.1` are offered — no free-text entry
- Render loop toggle: `syn-switch` or `syn-checkbox` bound to `loopable` (default unchecked)
- Emits config object `{recording_id, playback_speed, loopable, throttle_ms}` via Signal `output()`

Only `completed` recordings (non-active) are shown — filter out `active_recordings` from the list response.

### 7.3 Node Status Display

Status comes from existing `/api/v1/nodes/status` polling. Playback-specific badge:
- `▶ PLAYING (frame N/M)` — green — `RUNNING`
- `■ IDLE` — grey — `STOPPED`
- `✕ ERROR` — red — `ERROR`

---

## 8. WebSocket Streaming

`PlaybackNode` is a standard source node. `manager.forward_data()` → LIDR binary broadcast path is unchanged. Topic: `playback_{node_id[:8]}`.

---

## 9. Module Discovery

Add `import app.modules.playback.registry` to module discovery (follow existing pattern in `app/modules/__init__.py`).

---

## 10. Resolved Questions

| # | Question | Decision |
|---|----------|----------|
| 1 | Recording discovery | **Reuse `GET /api/v1/recordings`** — no new endpoint |
| 2 | Metadata display | From `RecordingResponse` fields — no new info endpoint |
| 3 | Config stores filename vs ID | **DB UUID (`recording_id`)** — factory resolves `file_path` from DB |
| 4 | Timing precision | **Average-interval** (`duration_seconds / frame_count`) scaled by speed |
| 5 | End-of-playback | Node stays `idle` in DAG — no auto-remove in V1 |
| 6 | Missing file on start | Transition to `ERROR` state immediately |
| 7 | Active recordings in dropdown | **Excluded** — only `recordings[]` (completed) shown |
| 8 | Future per-frame timestamps | Document as deferred; extend `RecordingResponse` DTO if needed — no new endpoint |
