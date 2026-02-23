export interface LidarPose {
  x: number;
  y: number;
  z: number;
  roll: number;
  pitch: number;
  yaw: number;
}

export interface LidarConfig {
  id?: string;
  name: string;
  topic_prefix?: string;
  raw_topic?: string;
  processed_topic?: string | null;
  enabled?: boolean;
  launch_args: string;
  pipeline_name?: string;
  mode: 'real' | 'sim';
  pcd_path?: string;
  pose: LidarPose;
  imu_udp_port?: number;
}

export interface LidarListResponse {
  lidars: LidarConfig[];
  available_pipelines: string[];
}
