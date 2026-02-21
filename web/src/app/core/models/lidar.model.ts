export interface LidarPose {
  x: number;
  y: number;
  z: number;
  roll: number;
  pitch: number;
  yaw: number;
}

export interface LidarConfig {
  id: string;
  launch_args: string;
  pipeline_name?: string;
  mode: 'real' | 'sim';
  pcd_path?: string;
  pose: LidarPose;
}

export interface LidarListResponse {
  lidars: LidarConfig[];
  available_pipelines: string[];
}
