import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { LidarProfile, LidarProfilesResponse } from '../../models/lidar-profile.model';

// Mock data matching api-spec.md §1 response
const MOCK_LIDAR_PROFILES: LidarProfile[] = [
  {
    model_id: 'multiscan',
    display_name: 'SICK multiScan',
    launch_file: 'launch/sick_multiscan.launch',
    default_hostname: '192.168.0.1',
    port_arg: 'udp_port',
    default_port: 2115,
    has_udp_receiver: true,
    has_imu_udp_port: true,
    scan_layers: 16
  },
  {
    model_id: 'tim_5xx',
    display_name: 'SICK TiM5xx',
    launch_file: 'launch/sick_tim_5xx.launch',
    default_hostname: '192.168.0.1',
    port_arg: 'port',
    default_port: 2112,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 1
  },
  {
    model_id: 'tim_7xx',
    display_name: 'SICK TiM7xx',
    launch_file: 'launch/sick_tim_7xx.launch',
    default_hostname: '192.168.0.1',
    port_arg: 'port',
    default_port: 2112,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 1
  },
  {
    model_id: 'tim_4xx',
    display_name: 'SICK TiM4xx',
    launch_file: 'launch/sick_tim_4xx.launch',
    default_hostname: '192.168.0.1',
    port_arg: 'port',
    default_port: 2112,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 1
  },
  {
    model_id: 'tim_2xx',
    display_name: 'SICK TiM2xx',
    launch_file: 'launch/sick_tim_240.launch',
    default_hostname: '192.168.0.1',
    port_arg: 'port',
    default_port: 2112,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 1
  },
  {
    model_id: 'lms_1xx',
    display_name: 'SICK LMS1xx',
    launch_file: 'launch/sick_lms_1xx.launch',
    default_hostname: '192.168.0.1',
    port_arg: '',
    default_port: 0,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 1
  },
  {
    model_id: 'lms_5xx',
    display_name: 'SICK LMS5xx',
    launch_file: 'launch/sick_lms_5xx.launch',
    default_hostname: '192.168.0.1',
    port_arg: '',
    default_port: 0,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 1
  },
  {
    model_id: 'lms_4xxx',
    display_name: 'SICK LMS4000',
    launch_file: 'launch/sick_lms_4xxx.launch',
    default_hostname: '192.168.0.1',
    port_arg: '',
    default_port: 0,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 1
  },
  {
    model_id: 'mrs_1xxx',
    display_name: 'SICK MRS1000',
    launch_file: 'launch/sick_mrs_1xxx.launch',
    default_hostname: '192.168.0.1',
    port_arg: '',
    default_port: 0,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 4
  },
  {
    model_id: 'mrs_6xxx',
    display_name: 'SICK MRS6124',
    launch_file: 'launch/sick_mrs_6xxx.launch',
    default_hostname: '192.168.0.1',
    port_arg: '',
    default_port: 0,
    has_udp_receiver: false,
    has_imu_udp_port: false,
    scan_layers: 24
  }
];

@Injectable({
  providedIn: 'root',
})
export class LidarProfilesApiService {
  private http = inject(HttpClient);
  
  profiles = signal<LidarProfile[]>([]);
  isLoading = signal<boolean>(false);

  constructor() {
    // Initialize with mock data for development
    this.profiles.set(MOCK_LIDAR_PROFILES);
  }

  async loadProfiles(): Promise<void> {
    this.isLoading.set(true);
    try {
      // TODO: Replace with real API call once backend TASK-B5/B6 are deployed
      // const data = await firstValueFrom(
      //   this.http.get<LidarProfilesResponse>(`${environment.apiUrl}/lidar/profiles`)
      // );
      // this.profiles.set(data.profiles);
      
      // Mock implementation for development
      await new Promise(resolve => setTimeout(resolve, 100)); // Simulate API delay
      this.profiles.set(MOCK_LIDAR_PROFILES);
    } catch (error) {
      console.error('Failed to load LiDAR profiles:', error);
      this.profiles.set([]);
    } finally {
      this.isLoading.set(false);
    }
  }
}
