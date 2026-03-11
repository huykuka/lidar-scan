import {inject, Injectable, signal} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
import {environment} from '../../../../environments/environment';
import {LidarProfile, LidarProfilesResponse} from '../../models/lidar-profile.model';

@Injectable({
  providedIn: 'root',
})
export class LidarProfilesApiService {
  profiles = signal<LidarProfile[]>([]);
  isLoading = signal<boolean>(false);
  private http = inject(HttpClient);
  private profilesLoaded = false;

  constructor() {
    // Load profiles from backend API on initialization
    this.loadProfiles();
  }

  /**
   * Get specific LiDAR profile by model ID
   */
  getProfileByModelId(modelId: string): LidarProfile | null {
    return this.profiles().find((profile) => profile.model_id === modelId) || null;
  }

  async loadProfiles(forceRefresh = false): Promise<void> {
    // Return early if profiles already loaded and not forcing refresh
    if (this.profilesLoaded && !forceRefresh) {
      return;
    }

    this.isLoading.set(true);
    try {
      // Real API call to get updated profiles from backend
      const data = await firstValueFrom(
        this.http.get<LidarProfilesResponse>(`${environment.apiUrl}/lidar/profiles`),
      );

      // Convert relative thumbnail URLs to absolute backend URLs
      const processedProfiles = data.profiles.map((profile) => ({
        ...profile,
        thumbnail_url: profile.thumbnail_url?.startsWith('/')
          ? `${environment.apiUrl.replace('/api/v1', '')}${profile.thumbnail_url}`
          : profile.thumbnail_url,
      }));

      this.profiles.set(processedProfiles);
      this.profilesLoaded = true;

      // Remove mock implementation - now using real backend data
      // await new Promise(resolve => setTimeout(resolve, 100)); // Simulate API delay
      // this.profiles.set(MOCK_LIDAR_PROFILES);
    } catch (error) {
      console.error('Failed to load LiDAR profiles:', error);
      // Fallback to mock data if backend is unavailable
      this.profiles.set(this.getMockLidarProfiles());
      this.profilesLoaded = false;
    } finally {
      this.isLoading.set(false);
    }
  }

  /**
   * Helper function to generate backend asset URLs using current environment
   */
  private getBackendAssetUrl(assetPath: string): string {
    const url = `${environment.apiUrl}/assets/lidar/${assetPath}`;
    return url;
  }

  /**
   * Generate mock profiles with proper backend URLs at runtime
   */
  private getMockLidarProfiles(): LidarProfile[] {
    return [
      {
        model_id: 'multiscan',
        display_name: 'SICK multiScan',
        launch_file: 'launch/sick_multiscan.launch',
        default_hostname: '192.168.0.1',
        port_arg: 'udp_port',
        default_port: 2115,
        has_udp_receiver: true,
        has_imu_udp_port: true,
        scan_layers: 16,
        thumbnail_url: this.getBackendAssetUrl('multiscan.png'),
        icon_name: 'device_hub',
        icon_color: '#0066CC',
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
        scan_layers: 1,
        thumbnail_url: this.getBackendAssetUrl('tim5xx.png'),
        icon_name: 'sensors',
        icon_color: '#FF6B35',
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
        scan_layers: 1,
        thumbnail_url: this.getBackendAssetUrl('tim7xx.png'),
        icon_name: 'sensors',
        icon_color: '#FF6B35',
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
        scan_layers: 1,
        thumbnail_url: this.getBackendAssetUrl('tim4xx.png'),
        icon_name: 'sensors',
        icon_color: '#FF6B35',
      },
      {
        model_id: 'tim_2xx',
        display_name: 'SICK TiM2xx',
        launch_file: 'launch/sick_tim_2xx.launch',
        default_hostname: '192.168.0.1',
        port_arg: 'port',
        default_port: 2112,
        has_udp_receiver: false,
        has_imu_udp_port: false,
        scan_layers: 1,
        thumbnail_url: this.getBackendAssetUrl('tim2xx.png'),
        icon_name: 'sensors',
        icon_color: '#FF6B35',
      },
      {
        model_id: 'lms_1xx',
        display_name: 'SICK LMS1xx',
        launch_file: 'launch/sick_lms_1xx.launch',
        default_hostname: '192.168.0.1',
        port_arg: '',
        default_port: 2112,
        has_udp_receiver: false,
        has_imu_udp_port: false,
        scan_layers: 1,
        thumbnail_url: this.getBackendAssetUrl('lms1xx.png'),
        icon_name: 'radar',
        icon_color: '#9C27B0',
      },
      {
        model_id: 'lms_5xx',
        display_name: 'SICK LMS5xx',
        launch_file: 'launch/sick_lms_5xx.launch',
        default_hostname: '192.168.0.1',
        port_arg: 'port',
        default_port: 2112,
        has_udp_receiver: false,
        has_imu_udp_port: false,
        scan_layers: 1,
        thumbnail_url: this.getBackendAssetUrl('lms5xx.png'),
        icon_name: 'radar',
        icon_color: '#9C27B0',
      },
      {
        model_id: 'lms_4xxx',
        display_name: 'SICK LMS4xxx',
        launch_file: 'launch/sick_lms_4xxx.launch',
        default_hostname: '192.168.0.1',
        port_arg: 'port',
        default_port: 2112,
        has_udp_receiver: false,
        has_imu_udp_port: false,
        scan_layers: 1,
        thumbnail_url: this.getBackendAssetUrl('lms4xxx.png'),
        icon_name: 'radar',
        icon_color: '#9C27B0',
      },
      {
        model_id: 'mrs_1xxx',
        display_name: 'SICK MRS1xxx',
        launch_file: 'launch/sick_mrs_1xxx.launch',
        default_hostname: '192.168.0.1',
        port_arg: 'port',
        default_port: 2112,
        has_udp_receiver: false,
        has_imu_udp_port: false,
        scan_layers: 4,
        thumbnail_url: this.getBackendAssetUrl('mrs1xxx.png'),
        icon_name: 'device_hub',
        icon_color: '#4CAF50',
      },
      {
        model_id: 'mrs_6xxx',
        display_name: 'SICK MRS6xxx',
        launch_file: 'launch/sick_mrs_6xxx.launch',
        default_hostname: '192.168.0.1',
        port_arg: 'port',
        default_port: 2112,
        has_udp_receiver: false,
        has_imu_udp_port: false,
        scan_layers: 24,
        thumbnail_url: this.getBackendAssetUrl('mrs6xxx.png'),
        icon_name: 'device_hub',
        icon_color: '#4CAF50',
      },
    ];
  }
}
