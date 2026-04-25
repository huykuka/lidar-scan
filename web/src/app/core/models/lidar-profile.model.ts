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
  // Backend-controlled thumbnail/icon
  thumbnail_url?: string;   // URL to thumbnail image (e.g., "/api/v1/assets/lidar/tim7xx.png")
  icon_name?: string;       // Synergy icon name (e.g., "sensors", "radar", "device_hub") 
  icon_color?: string;      // Hex color for icon (e.g., "#0066CC", "#FF6B35")
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