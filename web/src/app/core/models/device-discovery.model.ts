export type ScanStatus = 'running' | 'completed' | 'failed';

export interface DiscoveredDevice {
  ip: string;
  port: number;
  device_name: string | null;
  firmware_version: string | null;
  serial: string | null;
  raw: unknown;
  lidar_type: string | null;
}

export interface ScanJob {
  id: string;
  status: ScanStatus;
  subnets: string[];
  scanned: number;
  total: number;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  devices: DiscoveredDevice[];
}
