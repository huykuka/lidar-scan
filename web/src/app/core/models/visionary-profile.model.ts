export interface VisionaryProfile {
  model_id: string;
  display_name: string;
  is_stereo: boolean;
  acquisition_method: string;   // "sdk" | "harvester"
  default_hostname: string;
  cola_protocol: string;
  default_control_port: number;
  default_streaming_port: number;
  thumbnail_url?: string;
  icon_name?: string;
  icon_color?: string;
}
