/**
 * Playback Node configuration models.
 * Used by the PlaybackConfigPanelComponent and the DAG save API.
 * api-spec.md §2 — Node Config Schema
 */

/**
 * Playback speed options — never > 1.0 (backend enforces this at the enum level).
 */
export type PlaybackSpeed = 1.0 | 0.5 | 0.25 | 0.1;

/**
 * Config object emitted by PlaybackConfigPanelComponent and stored in NodeRecord.config.
 * camelCase on the frontend; serialised to snake_case in the HTTP payload.
 */
export interface PlaybackConfig {
  /** DB UUID of the recording to play back */
  recording_id: string;
  /** Replay speed relative to real-time — restricted to the four allowed enum values */
  playback_speed: PlaybackSpeed;
  /** Whether to restart from frame 0 after the last frame */
  loopable: boolean;
  /** Optional inter-frame delay added on top of natural timing (milliseconds) */
  throttle_ms: number;
}

/**
 * Display options for the playback-speed `syn-select`.
 * Only these four values are valid — no free-text entry.
 */
export const PLAYBACK_SPEED_OPTIONS = [
  { label: '1.0×', value: 1.0 as PlaybackSpeed },
  { label: '0.5×', value: 0.5 as PlaybackSpeed },
  { label: '0.25×', value: 0.25 as PlaybackSpeed },
  { label: '0.1×', value: 0.1 as PlaybackSpeed },
] as const;

/** The set of valid speed values — used for validation guards. */
export const VALID_PLAYBACK_SPEEDS = new Set<number>(PLAYBACK_SPEED_OPTIONS.map((o) => o.value));
