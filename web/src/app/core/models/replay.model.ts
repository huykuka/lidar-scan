export type ReplayStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface ValueStats {
  count: number;
  min: number;
  max: number;
  mean: number;
  last: number;
  /** Spread of the value across frames. Missing on runs recorded before it was tracked. */
  std?: number;
}

export interface ReplayNodeSummary {
  name: string;
  type: string;
  emitted: number;
  points_mean: number | null;
  values: Record<string, ValueStats>;
}

export interface CapturedCloudSummary {
  name: string;
  frames: number[];
  max_points: number;
  truncated: boolean;
}

export interface ReplaySummary {
  nodes?: Record<string, ReplayNodeSummary>;
  /** Nodes whose point clouds were stored for visual diff. */
  clouds?: Record<string, CapturedCloudSummary>;
  saved_results?: Record<string, number>;
  saved_results_total?: number;
  errors_total?: number;
}

// ── Ground truth ────────────────────────────────────────────────────────────

export type ScoreStatus = 'pass' | 'fail' | 'info' | 'missing';

export interface TargetScore {
  target_id: string;
  label: string;
  node_id: string;
  metric_key: string;
  expected: number;
  tolerance: number | null;
  value: number | null;
  std: number | null;
  error: number | null;
  abs_error: number | null;
  pct_error: number | null;
  status: ScoreStatus;
}

export interface RunScores {
  /** null when the recording has no ground truth (or the run is not completed). */
  overall: ScoreStatus | null;
  targets: TargetScore[];
}

export interface GroundTruthTarget {
  id: string;
  recording_id: string;
  node_id: string;
  metric_key: string;
  label: string;
  expected: number;
  tolerance: number | null;
  created_at: string;
}

export interface CreateTargetRequest {
  recording_id: string;
  node_id: string;
  metric_key: string;
  expected: number;
  tolerance?: number | null;
  label?: string;
}

export interface ReplayRun {
  id: string;
  label: string;
  recording_id: string;
  playback_node_id: string;
  status: ReplayStatus;
  frames_total: number;
  frames_processed: number;
  config_hash: string;
  overrides: Record<string, Record<string, unknown>>;
  summary: ReplaySummary;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  sweep_id: string | null;
  /** Nodes whose point clouds were kept; null for runs created before this was recorded. */
  capture_nodes: string[] | null;
  scores?: RunScores | null;
  /** Sweep runs only: the value of the swept parameter this run used. */
  x_value?: unknown;
  /** Sweep runs only: true for the run that uses the pipeline's current value. */
  is_baseline?: boolean | null;
}

// ── Parameter sweeps ────────────────────────────────────────────────────────

export interface SweepProgress {
  total: number;
  completed: number;
  failed: number;
  active: number;
}

export interface Sweep {
  id: string;
  label: string;
  recording_id: string;
  playback_node_id: string;
  node_id: string;
  parameter: string;
  values: unknown[];
  created_at: string;
  progress: SweepProgress | null;
}

export interface SweepDetail {
  sweep: Sweep;
  runs: ReplayRun[];
  targets: GroundTruthTarget[];
  best_run_id: string | null;
}

export interface ListSweepsResponse {
  sweeps: Sweep[];
  total: number;
}

export interface CreateSweepRequest {
  recording_id: string;
  playback_node_id: string;
  node_id: string;
  parameter: string;
  values: unknown[];
  label?: string;
  capture_nodes?: string[];
  include_current?: boolean;
}

// ── Apply to the live pipeline ──────────────────────────────────────────────

export interface ApplyChange {
  node_id: string;
  node_name: string;
  node_exists: boolean;
  key: string;
  current: unknown;
  new: unknown;
  changed: boolean;
}

export interface PipelineDrift {
  node_id: string;
  node_name: string;
  /** null when the whole node is gone from the live pipeline. */
  key: string | null;
  run_value: unknown;
  live_value: unknown;
}

export interface ApplyPreview {
  run_id: string;
  label: string;
  changes: ApplyChange[];
  has_changes: boolean;
  missing_nodes: string[];
  pipeline_changed_since_run: PipelineDrift[];
}

export interface ApplyResult {
  applied: {node_id: string; node_name: string; key: string; old: unknown; new: unknown}[];
  config_version: number;
  reload_mode: string;
  reloaded_node_ids: string[];
}

export interface ListReplayRunsResponse {
  runs: ReplayRun[];
  total: number;
}

export interface CreateReplayRequest {
  recording_id: string;
  playback_node_id: string;
  label?: string;
  overrides?: Record<string, Record<string, unknown>>;
  /** Omit for the default (final nodes + their parents); [] captures nothing. */
  capture_nodes?: string[];
}

export interface ValueComparison {
  compared: number;
  differing: number;
  only_a: number;
  only_b: number;
  mean_a?: number;
  mean_b?: number;
  mean_delta?: number;
  mean_pct?: number | null;
  max_abs_delta?: number;
}

export interface NodeComparison {
  name: string;
  type: string;
  in_a: boolean;
  in_b: boolean;
  emitted_a: number;
  emitted_b: number;
  frames_only_a: number;
  frames_only_b: number;
  frames_compared: number;
  points_mean_delta: number | null;
  points_differing_frames: number;
  values: Record<string, ValueComparison>;
}

export interface FieldDiff {
  a: unknown;
  b: unknown;
  delta?: number;
  pct?: number | null;
}

export interface SavedResultPair {
  index: number;
  frame_a: number | null;
  frame_b: number | null;
  status_a: string | null;
  status_b: string | null;
  fields: Record<string, FieldDiff>;
}

export interface SavedResultsComparison {
  count_a: number;
  count_b: number;
  differing: number;
  pairs: SavedResultPair[];
}

export interface ComparisonSeries {
  node_id: string;
  node_name: string;
  key: string;
  points: {frame: number; a: number; b: number}[];
}

export interface ReplayRunInfo {
  id: string;
  label: string;
  recording_id: string;
  config_hash: string;
  overrides: Record<string, Record<string, unknown>>;
}

/** A node whose point clouds were captured in both compared runs. */
export interface CloudNode {
  node_id: string;
  name: string;
  /** Frames available in both runs, ascending. */
  frames: number[];
  truncated: boolean;
}

export interface ReplayComparison {
  run_a: string;
  run_b: string;
  run_a_info: ReplayRunInfo;
  run_b_info: ReplayRunInfo;
  same_recording: boolean;
  summary: {
    nodes_compared: number;
    nodes_only_a: string[];
    nodes_only_b: string[];
    differing_value_keys: number;
    saved_results_a: number;
    saved_results_b: number;
    saved_results_differing: number;
    errors_a: number;
    errors_b: number;
    identical: boolean;
  };
  nodes: Record<string, NodeComparison>;
  saved_results: Record<string, SavedResultsComparison>;
  series: ComparisonSeries[];
  cloud_nodes: CloudNode[];
  scores_a?: RunScores;
  scores_b?: RunScores;
  errors: {a: unknown[]; b: unknown[]};
}
