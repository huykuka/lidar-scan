export interface FusionConfig {
  id?: string;
  name: string;
  topic: string;
  sensor_ids: string[];
  pipeline_name?: string;
  enabled?: boolean;
}
