import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';

export interface HostCpuInfo {
  percent_total: number;
  percent_per_core: number[];
  count_logical: number | null;
  count_physical: number | null;
  freq_mhz: { current: number | null; min: number | null; max: number | null };
  load_avg_1_5_15: number[];
}

export interface HostMemoryInfo {
  ram: { total_mb: number | null; available_mb: number | null; used_mb: number | null; percent: number };
  swap: { total_mb: number | null; used_mb: number | null; percent: number | null } | null;
}

export interface HostDiskPartition {
  device: string;
  mountpoint: string;
  fstype: string;
  total_gb: number | null;
  used_gb: number | null;
  free_gb: number | null;
  percent: number | null;
}

export interface HostDiskInfo {
  partitions: HostDiskPartition[];
  io: { read_mb: number | null; write_mb: number | null; read_count: number | null; write_count: number | null } | null;
}

export interface HostNetworkInterface {
  name: string;
  ipv4: string | null;
  ipv6: string | null;
  is_up: boolean | null;
  speed_mbps: number | null;
  sent_mb: number | null;
  recv_mb: number | null;
  packets_sent: number | null;
  packets_recv: number | null;
  errin: number | null;
  errout: number | null;
}

export interface HostProcessInfo {
  pid: number;
  cpu_percent: number | null;
  rss_mb: number | null;
  vms_mb: number | null;
  num_threads: number | null;
  num_fds: number | null;
  create_time: number | null;
  uptime_s: number;
}

export interface HostInfo {
  hostname: string | null;
  platform: string | null;
  python: string | null;
  boot_time: number;
  uptime_s: number;
}

export interface HostSnapshot {
  host: HostInfo;
  cpu: HostCpuInfo;
  memory: HostMemoryInfo;
  disk: HostDiskInfo;
  network: { interfaces: HostNetworkInterface[] };
  process: HostProcessInfo;
  collected_at: number;
}

@Injectable({ providedIn: 'root' })
export class HostApiService {
  private http = inject(HttpClient);
  private base = `${environment.apiUrl}/host`;

  async getSnapshot(): Promise<HostSnapshot> {
    return firstValueFrom(this.http.get<HostSnapshot>(this.base));
  }

  async getCpu(): Promise<HostCpuInfo> {
    return firstValueFrom(this.http.get<HostCpuInfo>(`${this.base}/cpu`));
  }
}
