/**
 * Status models for node-reload-improvement feature.
 * Includes ReloadEvent broadcast schema and SystemStatusBroadcast with optional reload_event.
 *
 * @see .opencode/plans/node-reload-improvement/api-spec.md § 4 & 6
 */

import {NodeStatusUpdate} from './node-status.model';

export interface ReloadEvent {
  /** null for full DAG reload events */
  node_id: string | null;
  status: 'reloading' | 'ready' | 'error';
  /** Present only when status === 'error' */
  error_message: string | null;
  reload_mode: 'selective' | 'full';
  /** Unix timestamp (float, seconds) */
  timestamp: number;
}

/** System-level status pushed on every full-status broadcast (~1 s cadence + on change). */
export interface SystemStatusInfo {
  is_running: boolean;
  active_sensors: string[];
  version: string;
}

export interface SystemStatusBroadcast {
  nodes: NodeStatusUpdate[];
  /** Present only during/after a reload */
  reload_event?: ReloadEvent;
  /** Present on every full-status broadcast; absent on reload-event-only messages. */
  system?: SystemStatusInfo;
}

export interface NodeReloadResponse {
  node_id: string;
  status: 'reloaded';
  /** Actual reload duration in milliseconds */
  duration_ms: number;
  /** The WebSocket topic that was preserved; null if node has no WS topic */
  ws_topic: string | null;
}

export interface ReloadStatusResponse {
  locked: boolean;
  reload_in_progress: boolean;
  /** Node currently being reloaded; null if full reload or not locked */
  active_reload_node_id: string | null;
  /** null when not locked */
  estimated_completion_ms: number | null;
}
