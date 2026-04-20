# Playback Node — API Specification

**Base URL**: `/api/v1`  
**Auth**: Same as existing system

---

## ⚡ API Reuse — Core Principle

The Playback Node uses the **existing** `GET /api/v1/recordings` endpoints exclusively for recording discovery and metadata. **No new REST endpoints are added for listing, selecting, or retrieving recording metadata.**

---

## 1. Recording Discovery — Existing Endpoints (Reused)

### 1a. List Available Recordings

```
GET /api/v1/recordings
```

Implemented in `app/api/v1/recordings/handler.py`. Used by the Playback config panel to populate the recording dropdown.

**Query param** (optional): `node_id` — not used by playback; omit to list all.

**Response `200 OK`** (existing `ListRecordingsResponse`):
```json
{
  "recordings": [
    {
      "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "name": "outdoor-test-run-01",
      "node_id": "sensor-abc123",
      "sensor_id": null,
      "file_path": "recordings/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.zip",
      "file_size_bytes": 10485760,
      "frame_count": 300,
      "duration_seconds": 30.0,
      "recording_timestamp": "2026-04-19T12:34:56Z",
      "metadata": { "node_id": "sensor-abc123" },
      "thumbnail_path": null,
      "created_at": "2026-04-19T12:35:30Z"
    }
  ],
  "active_recordings": []
}
```

**Playback panel consumes**: `recordings[]` only. `active_recordings[]` is excluded from the dropdown (recordings must be completed to be playable).

**Fields used by playback**:
| Field | Used for |
|-------|----------|
| `id` | Stored as `recording_id` in node config |
| `name` | Display label in dropdown |
| `frame_count` | Info display; zero-frame guard |
| `duration_seconds` | Info display in panel |
| `recording_timestamp` | Info display in panel |
| `node_id` | Provenance info display |

### 1b. Get Single Recording

```
GET /api/v1/recordings/{recording_id}
```

Used by the config panel on recording select change (metadata detail display), and by the `PlaybackNode` factory builder to resolve `file_path`.

**Response `200 OK`** (`RecordingResponse` — existing):
```json
{
  "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "name": "outdoor-test-run-01",
  "node_id": "sensor-abc123",
  "sensor_id": null,
  "file_path": "recordings/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.zip",
  "file_size_bytes": 10485760,
  "frame_count": 300,
  "duration_seconds": 30.0,
  "recording_timestamp": "2026-04-19T12:34:56Z",
  "metadata": {},
  "thumbnail_path": null,
  "created_at": "2026-04-19T12:35:30Z"
}
```

**Response `404`** (existing):
```json
{ "detail": "Recording a1b2c3d4... not found" }
```

---

## 2. Node Config Schema (stored in `NodeRecord.config`)

Node type: `"playback"`. The key field is `recording_id` (DB UUID), **not** a filename.

```json
{
  "recording_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "playback_speed": 1.0,
  "loopable": false,
  "throttle_ms": 0
}
```

| Field | Type | Allowed values | Default | Required | Validation |
|-------|------|----------------|---------|----------|------------|
| `recording_id` | string | UUID from `GET /api/v1/recordings` | — | **yes** | Must exist in DB; 404 → `ERROR` state |
| `playback_speed` | number (enum) | `0.1`, `0.25`, `0.5`, `1.0` | `1.0` | no | Any other value → `400 Bad Request`. **Never > 1.0** — backend rejects |
| `loopable` | boolean | `true` / `false` | `false` | no | None |
| `throttle_ms` | number | `0..N` | `0` | no | `< 0` → treated as `0` |

---

## 2a. Config Wiring: Frontend → Backend

```
Config Panel (Angular)
  playbackSpeed syn-select  →  playback_speed: float   (enum: 1.0 | 0.5 | 0.25 | 0.1)
  loopable      syn-switch  →  loopable:       boolean (default false)
        ↓ Signal output()
DAG save API  POST/PATCH /api/v1/nodes/{id}  { config: { recording_id, playback_speed, loopable, throttle_ms } }
        ↓
NodeFactory builder  validates playback_speed ∈ VALID_SPEEDS; rejects ≥ 1.0 is auto-satisfied by enum
        ↓
PlaybackNode(_playback_speed=..., _loopable=...)  runtime behaviour
```

**Field name mapping** (frontend camelCase → backend snake_case via JSON serialization):

| Frontend (TS) | Payload JSON key | Backend (Python) |
|---------------|-----------------|------------------|
| `playbackSpeed` | `playback_speed` | `playback_speed` |
| `loopable` | `loopable` | `loopable` |

---

## 3. Node Status (via existing `/api/v1/nodes/status`)

```json
{
  "node_id": "uuid",
  "name": "Playback",
  "type": "playback",
  "category": "sensor",
  "enabled": true,
  "operational_state": "RUNNING",
  "application_state": {
    "label": "playback_status",
    "value": "playing (frame 42/300)",
    "color": "green"
  },
  "topic": "playback_a1b2c3d4",
  "error_message": null
}
```

`operational_state` values: `STOPPED` (idle), `RUNNING` (playing), `ERROR`.

---

## 4. WebSocket Stream

Topic: `playback_{node_id[:8]}`  
Binary frame format: standard **LIDR** protocol.  
No new WebSocket endpoints — reuses existing `/ws/{topic}`.

---

## 5. Frontend Mock Data

While backend is in development, FE mocks the **existing** endpoint responses:

**GET /api/v1/recordings**
```json
{
  "recordings": [
    {
      "id": "demo0001demo0001demo0001demo0001",
      "name": "demo_outdoor_scan",
      "node_id": "sensor-001",
      "sensor_id": null,
      "file_path": "recordings/demo0001.zip",
      "file_size_bytes": 5242880,
      "frame_count": 150,
      "duration_seconds": 15.0,
      "recording_timestamp": "2026-04-01T10:00:00Z",
      "metadata": {},
      "thumbnail_path": null,
      "created_at": "2026-04-01T10:01:00Z"
    }
  ],
  "active_recordings": []
}
```

**GET /api/v1/recordings/demo0001demo0001demo0001demo0001**
```json
{
  "id": "demo0001demo0001demo0001demo0001",
  "name": "demo_outdoor_scan",
  "node_id": "sensor-001",
  "sensor_id": null,
  "file_path": "recordings/demo0001.zip",
  "file_size_bytes": 5242880,
  "frame_count": 150,
  "duration_seconds": 15.0,
  "recording_timestamp": "2026-04-01T10:00:00Z",
  "metadata": {},
  "thumbnail_path": null,
  "created_at": "2026-04-01T10:01:00Z"
}
```

---

## 6. Future Extensions (Not In Scope)

> **Document only — do NOT implement.**

| Need | Future change |
|------|--------------|
| Per-frame timestamps for precise speed scaling | Add `timestamps: list[float]` to `RecordingResponse` DTO in existing `dto.py` |
| Average FPS field | Add `average_fps: float` derived field to `RecordingResponse` |
| Playback-specific filtering (e.g. only playback-compatible recordings) | Add query param to existing `GET /api/v1/recordings` |

All future extensions MUST extend the existing `RecordingResponse` DTO or add query params to the existing endpoint — never add a parallel `/playback/recordings` endpoint.
