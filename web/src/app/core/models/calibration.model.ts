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

export interface Pose {
  x: number;
  y: number;
  z: number;
  roll: number;
  pitch: number;
  yaw: number;
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
  // NEW: Provenance tracking fields
  source_sensor_id?: string;  // Canonical leaf sensor ID (null for legacy records)
  processing_chain?: string[]; // DAG traversal path (empty for legacy records)
  run_id?: string;  // Groups all sensors from same trigger (null for legacy records)
}

export interface CalibrationHistoryResponse {
  sensor_id: string;
  history: CalibrationHistoryRecord[];
}

export interface CalibrationRollbackRequest {
  timestamp: string;
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
