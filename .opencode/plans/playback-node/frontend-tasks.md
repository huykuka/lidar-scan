# Playback Node — Frontend Tasks

**References**: `requirements.md`, `technical.md`, `api-spec.md`  
**Mock data**: Use `api-spec.md §5` (mock the existing `GET /api/v1/recordings` response) while backend is in development.

> **Recording discovery uses `GET /api/v1/recordings` (existing endpoint). Do NOT create a playback-specific recordings service.**

---

## Models

- [x] Reuse existing `RecordingResponse` / `ListRecordingsResponse` models if already defined in `core/models/`. If not yet created:
  - Create `web/src/app/core/models/recording.model.ts`
  - `RecordingResponse` matching `api-spec.md §1b`
  - `ListRecordingsResponse { recordings: RecordingResponse[], active_recordings: any[] }`
- [x] Define `PlaybackConfig` interface in `playback-config-panel/`:
  ```ts
  export interface PlaybackConfig {
    recording_id: string;
    playback_speed: 1.0 | 0.5 | 0.25 | 0.1;  // never > 1.0
    loopable: boolean;
    throttle_ms: number;
  }
  ```
- [x] Define `PLAYBACK_SPEED_OPTIONS` constant:
  ```ts
  export const PLAYBACK_SPEED_OPTIONS = [
    { label: '1.0×', value: 1.0 },
    { label: '0.5×', value: 0.5 },
    { label: '0.25×', value: 0.25 },
    { label: '0.1×', value: 0.1 },
  ] as const;
  ```

## API Service

- [x] Check if `web/src/app/core/services/api/recordings-api.service.ts` exists
  - Found as `recording-api.service.ts` — added `getRecordings()` method
- [x] `getRecordings(): Observable<ListRecordingsResponse>` → `GET /api/v1/recordings`
- [x] `getRecording(id: string): Observable<RecordingResponse>` → `GET /api/v1/recordings/{id}` (already existed)
- [ ] Add mock interceptor / environment switch for `api-spec.md §5` mock data
  > *Note: backend is live at localhost; mock interceptor deferred as backend serves real data*

## Config Panel Component

- [x] Scaffold `web/src/app/plugins/playback/form/playback-node-editor/` via Angular CLI (standalone)
  > *Located under plugins/playback per existing plugin architecture, not features/workspaces*
- [x] **Smart**: on panel open, call `recordingsApiService.getRecordings()` → filter to `recordings[]` only (exclude `active_recordings`) → store as `Signal<RecordingResponse[]>`
- [x] **Smart**: on recording select change, call `recordingsApiService.getRecording(id)` → display `frame_count`, `duration_seconds`, `recording_timestamp`
- [x] Render recording selector: `syn-select` with `{value: r.id, label: r.name}` options; show "No recordings available" when list is empty
- [x] Render speed selector: `syn-select` bound to `playbackSpeed` signal; options from `PLAYBACK_SPEED_OPTIONS`; default `1.0`; no free-text input — only the four valid enum values are selectable
- [x] Render loop toggle: `syn-switch` bound to `loopable` signal; label "Loop playback"; default unchecked (`false`)
- [x] Emit `PlaybackConfig` object `{recording_id, playback_speed, loopable, throttle_ms}` via `facade.saveNode()` — snake_case keys in config payload
- [x] Guard: if `playbackSpeed` signal value is somehow not in `PLAYBACK_SPEED_OPTIONS` (e.g. from stale config), reset it to `1.0` and show a console warning
- [x] Show recording metadata inline: `frame_count`, `duration_seconds`, `recording_timestamp` after selection

## Node Card / Status Badge

- [x] Extend node card in flow canvas to show playback-specific badge when `type === 'playback'`
  - `▶ PLAYING (frame N/M)` — green — `operational_state === 'RUNNING'`
  - `■ IDLE` — grey — `operational_state === 'STOPPED'`
  - `✕ ERROR` — red — `operational_state === 'ERROR'`
  > *Implemented as dedicated `PlaybackNodeCardComponent` registered in `NodePluginRegistry`*
- [x] Use Synergy icon `play_circle` for palette entry
  > *`NodeEditorHeaderComponent` uses `icon="play_circle"` in the PlaybackNodeEditorComponent header*

## Node Palette

- [x] Verify "Playback" appears in `sensor` category of node palette — driven by `/api/v1/nodes/schema`, no FE change needed
  > *Registry correctly maps `type === 'playback'` (sensor category) to PlaybackNodeCardComponent + PlaybackNodeEditorComponent*

## WebSocket Subscription

- [x] No new WS code — existing `LidrStreamService` handles `playback_*` topics

---

## Dependencies / Order

1. Models + API service first (can mock from day 1 using `api-spec.md §5`)
2. Config panel (depends on service)
3. Node badge (depends on existing status polling)
