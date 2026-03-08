export interface LidarProfile {
  model_id: string;
  display_name: string;
  launch_file: string;
  default_hostname: string;
  port_arg: string;        // "port" | "udp_port" | ""
  default_port: number;
  has_udp_receiver: boolean;
  has_imu_udp_port: boolean;
  scan_layers: number;
}

export interface LidarProfilesResponse {
  profiles: LidarProfile[];
}

export interface LidarConfigValidationRequest {
  lidar_type: string;
  hostname: string;
  udp_receiver_ip?: string;
  port?: number;
  imu_udp_port?: number;
}

export interface LidarConfigValidationResponse {
  valid: boolean;
  lidar_type: string;
  resolved_launch_file: string | null;
  errors: string[];
  warnings: string[];
}