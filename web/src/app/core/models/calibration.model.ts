import {Pose} from '@core/models/pose.model';

// Re-export Pose for convenience
export type {Pose};

/**
 * Delta between two poses (pose_after - pose_before).
 * Position deltas in mm, angle deltas in degrees.
 */
export interface PoseDelta {
  dx: number;    // mm (pose_after.x - pose_before.x)
  dy: number;    // mm
  dz: number;    // mm
  droll: number;   // degrees
  dpitch: number;  // degrees
  dyaw: number;    // degrees
}

/**
 * Pending calibration result for a single source sensor.
 * Produced by the ICP algorithm; awaiting user accept/reject.
 */
export interface PendingCalibrationResult {
  fitness: number;
  rmse: number;                          // meters (ICP output)
  quality: 'excellent' | 'good' | 'poor';
  quality_good: boolean;
  source_sensor_id?: string;
  processing_chain: string[];
  pose_before: Pose;                     // x/y/z in mm, angles in degrees
  pose_after: Pose;                      // x/y/z in mm, angles in degrees
  transformation_matrix: number[][];    // 4×4; translation col in meters
}

/**
 * Full status response from GET /calibration/:nodeId/status
 */
export interface CalibrationNodeStatusResponse {
  node_id: string;
  node_name: string;
  enabled: boolean;
  calibration_state: 'idle' | 'pending';
  quality_good: boolean | null;
  reference_sensor_id: string | null;
  source_sensor_ids: string[];
  buffered_frames: Record<string, number>;
  last_calibration_time: string | null;
  pending_results: Record<string, PendingCalibrationResult>;
}

export interface CalibrationResult {
  fitness: number;
  rmse: number;
  quality: 'excellent' | 'good' | 'poor';
  stages_used: string[];
  pose_before: Pose;
  pose_after: Pose;
  auto_saved?: boolean;
  // NEW: Provenance tracking fields
  source_sensor_id?: string;  // Canonical leaf sensor ID (lidar_id)
  processing_chain?: string[]; // Ordered DAG path from sensor to calibration node
}


export interface CalibrationTriggerRequest {
  reference_sensor_id?: string;
  source_sensor_ids?: string[];
  sample_frames?: number;
}

export interface CalibrationTriggerResponse {
  success: boolean;
  run_id: string;  // NEW: UUID correlating multi-sensor calibration runs
  results: Record<string, CalibrationResult>;
  pending_approval: boolean;
}

export interface CalibrationAcceptRequest {
  sensor_ids?: string[];
}

export interface CalibrationAcceptResponse {
  success: boolean;
  run_id?: string;  // NEW: run_id of accepted calibration batch
  accepted: string[];
  remaining_pending?: string[];  // NEW: Sensors still pending after accept
}

export interface CalibrationRejectResponse {
  success: boolean;
  rejected?: string[];  // NEW: Leaf sensor IDs whose pending results were discarded
}

export interface CalibrationHistoryRecord {
  id: string;
  sensor_id: string;
  reference_sensor_id: string;
  timestamp: string;
  fitness: number;
  rmse: number;
  quality: 'excellent' | 'good' | 'poor';
  stages_used: string[];
  pose_before: Pose;
  pose_after: Pose;
  transformation_matrix: number[][];
  accepted: boolean;
  notes: string;
  // Provenance tracking fields
  source_sensor_id?: string;  // Canonical leaf sensor ID (null for legacy records)
  processing_chain?: string[]; // DAG traversal path (empty for legacy records)
  run_id?: string;  // Groups all sensors from same trigger (null for legacy records)
  // Extended fields added in calibration-page-redesign
  accepted_at?: string;           // ISO-8601 timestamp when accepted
  accepted_by?: string | null;    // Reserved for future auth
  node_id?: string;               // Which calibration DAG node ran this
  rollback_source_id?: string;    // If this is a rollback, original record_id
  registration_method?: { method: string; stages: string[] } | null;
}

export interface CalibrationHistoryResponse {
  sensor_id: string;
  history: CalibrationHistoryRecord[];
}

export interface CalibrationRollbackRequest {
  record_id: string;   // PK, replaces the old timestamp-based lookup
}

export interface CalibrationRollbackResponse {
  success: boolean;
  sensor_id: string;
  restored_to: string;
}

export interface CalibrationStatistics {
  sensor_id: string;
  total_attempts: number;
  accepted_count: number;
  avg_fitness: number;
  avg_rmse: number;
  best_fitness: number;
  best_rmse: number;
}

export interface CalibrationNodeStatus {
  id: string;
  name: string;
  type: 'calibration';
  enabled: boolean;
  reference_sensor: string | null;
  source_sensors: string[];
  buffered_frames: Record<string, number> | string[];  // NEW: Dict format for frame counts, backward compat with array
  last_calibration_time: string | null;
  has_pending: boolean;
  pending_results: Record<string, {
    fitness: number;
    rmse: number;
    quality: string;
    source_sensor_id?: string;  // NEW
    processing_chain?: string[];  // NEW
  }>;
}
