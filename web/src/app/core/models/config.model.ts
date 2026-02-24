import { LidarConfig } from './lidar.model';
import { FusionConfig } from './fusion.model';

export interface ConfigExport {
  version: string;
  lidars: LidarConfig[];
  fusions: FusionConfig[];
}

export interface ConfigValidationResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: {
    lidars: number;
    fusions: number;
  };
}

export interface ConfigImportResponse {
  success: boolean;
  mode: string;
  imported: {
    lidars: number;
    fusions: number;
  };
  lidar_ids: string[];
  fusion_ids: string[];
}
