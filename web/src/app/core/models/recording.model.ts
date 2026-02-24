/**
 * TypeScript models for recording features
 */

export interface Recording {
  id: string;
  name: string;
  topic: string;
  sensor_id?: string;
  file_path: string;
  file_size_bytes: number;
  frame_count: number;
  duration_seconds: number;
  recording_timestamp: string;
  metadata: RecordingMetadata;
  thumbnail_path?: string;
  created_at: string;
}

export interface RecordingMetadata {
  sensor_id?: string;
  sensor_name?: string;
  topic: string;
  name: string;
  mode?: string;
  pipeline_name?: string;
  pose?: {
    x: number;
    y: number;
    z: number;
    roll: number;
    pitch: number;
    yaw: number;
  };
  average_fps?: number;
  recording_timestamp: string;
}

export interface ActiveRecording {
  recording_id: string;
  topic: string;
  frame_count: number;
  duration_seconds: number;
  started_at: string;
}

export interface StartRecordingRequest {
  topic: string;
  name?: string;
  metadata?: Record<string, any>;
}

export interface StartRecordingResponse {
  recording_id: string;
  file_path: string;
  started_at: string;
}

export interface ListRecordingsResponse {
  recordings: Recording[];
  active_recordings: ActiveRecording[];
}

export interface RecordingViewerInfo {
  id: string;
  name: string;
  topic: string;
  frame_count: number;
  duration_seconds: number;
  metadata: RecordingMetadata;
  recording_timestamp: string;
}
