# Playback Node — Frontend Tasks

**References**: `requirements.md`, `technical.md`, `api-spec.md`  
**Mock data**: Use `api-spec.md §5` (mock the existing `GET /api/v1/recordings` response) while backend is in development.

> **Recording discovery uses `GET /api/v1/recordings` (existing endpoint). Do NOT create a playback-specific recordings service.**

---

## Models

- [ ] Reuse existing `RecordingResponse` / `ListRecordingsResponse` models if already defined in `core/models/`. If not yet created:
  - Create `web/src/app/core/models/recording.model.ts`
  - `RecordingResponse` matching `api-spec.md §1b`
  - `ListRecordingsResponse { recordings: RecordingResponse[], active_recordings: any[] }`
- [ ] Define `PlaybackConfig` interface in `playback-config-panel/`:
  ```ts
  export interface PlaybackConfig {
    recording_id: string;
    playback_speed: 1.0 | 0.5 | 0.25 | 0.1;  // never > 1.0
    loopable: boolean;
    throttle_ms: number;
  }
  ```
- [ ] Define `PLAYBACK_SPEED_OPTIONS` constant:
  ```ts
  export const PLAYBACK_SPEED_OPTIONS = [
    { label: '1.0×', value: 1.0 },
    { label: '0.5×', value: 0.5 },
    { label: '0.25×', value: 0.25 },
    { label: '0.1×', value: 0.1 },
  ] as const;
  ```

## API Service

- [ ] Check if `web/src/app/core/services/api/recordings-api.service.ts` exists
  - If **yes**: add methods if missing (see below)
  - If **no**: scaffold via Angular CLI and implement
- [ ] `getRecordings(): Observable<ListRecordingsResponse>` → `GET /api/v1/recordings`
- [ ] `getRecording(id: string): Observable<RecordingResponse>` → `GET /api/v1/recordings/{id}`
- [ ] Add mock interceptor / environment switch for `api-spec.md §5` mock data

## Config Panel Component

- [ ] Scaffold `web/src/app/features/workspaces/components/playback-config-panel/` via Angular CLI (standalone)
- [ ] **Smart**: on panel open, call `recordingsApiService.getRecordings()` → filter to `recordings[]` only (exclude `active_recordings`) → store as `Signal<RecordingResponse[]>`
- [ ] **Smart**: on recording select change, call `recordingsApiService.getRecording(id)` → display `frame_count`, `duration_seconds`, `recording_timestamp`
- [ ] Render recording selector: `syn-select` with `{value: r.id, label: r.name}` options; show "No recordings available" when list is empty
- [ ] Render speed selector: `syn-select` bound to `playbackSpeed` signal; options from `PLAYBACK_SPEED_OPTIONS`; default `1.0`; no free-text input — only the four valid enum values are selectable
- [ ] Render loop toggle: `syn-switch` (or `syn-checkbox`) bound to `loopable` signal; label "Loop playback"; default unchecked (`false`)
- [ ] Emit `PlaybackConfig` object `{recording_id, playback_speed, loopable, throttle_ms}` via Signal `output()` — camelCase `playbackSpeed` serialized to snake_case `playback_speed` in the HTTP payload (use a serialization helper or Angular `HttpClient` transformer)
- [ ] Guard: if `playbackSpeed` signal value is somehow not in `PLAYBACK_SPEED_OPTIONS` (e.g. from stale config), reset it to `1.0` and show a console warning
- [ ] Show recording metadata inline: `frame_count`, `duration_seconds`, `recording_timestamp` after selection

## Node Card / Status Badge

- [ ] Extend node card in flow canvas to show playback-specific badge when `type === 'playback'`
  - `▶ PLAYING (frame N/M)` — green — `operational_state === 'RUNNING'`
  - `■ IDLE` — grey — `operational_state === 'STOPPED'`
  - `✕ ERROR` — red — `operational_state === 'ERROR'`
- [ ] Use Synergy icon `play_circle` for palette entry

## Node Palette

- [ ] Verify "Playback" appears in `sensor` category of node palette — driven by `/api/v1/nodes/schema`, no FE change needed

## WebSocket Subscription

- [ ] No new WS code — existing `LidrStreamService` handles `playback_*` topics

---

## Dependencies / Order

1. Models + API service first (can mock from day 1 using `api-spec.md §5`)
2. Config panel (depends on service)
3. Node badge (depends on existing status polling)
