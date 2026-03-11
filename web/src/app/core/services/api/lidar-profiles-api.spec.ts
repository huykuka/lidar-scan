import {TestBed} from '@angular/core/testing';
import {HttpClientTestingModule, HttpTestingController} from '@angular/common/http/testing';
import {LidarProfilesApiService} from './lidar-profiles-api.service';

describe('LidarProfilesApiService', () => {
  let service: LidarProfilesApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
    });
    service = TestBed.inject(LidarProfilesApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should initialize with mock profiles data', () => {
    const profiles = service.profiles();
    expect(profiles).toBeDefined();
    expect(profiles.length).toBeGreaterThan(0);
    expect(profiles[0]).toEqual(expect.objectContaining({
      model_id: 'multiscan',
      display_name: 'SICK multiScan',
      launch_file: 'launch/sick_multiscan.launch'
    }));
  });

  it('should set isLoading to false initially', () => {
    expect(service.isLoading()).toBe(false);
  });

  describe('loadProfiles', () => {
    it('should simulate loading state correctly', async () => {
      const loadingStates: boolean[] = [];

      // Track loading state changes
      const loadPromise = service.loadProfiles();

      expect(service.isLoading()).toBe(true);

      await loadPromise;

      expect(service.isLoading()).toBe(false);
    });

    it('should populate profiles signal with mock data', async () => {
      await service.loadProfiles();

      const profiles = service.profiles();
      expect(profiles).toBeDefined();
      expect(profiles.length).toBe(10); // Number of mock profiles

      // Verify structure of first profile
      const firstProfile = profiles[0];
      expect(firstProfile).toEqual(expect.objectContaining({
        model_id: 'multiscan',
        display_name: 'SICK multiScan',
        launch_file: 'launch/sick_multiscan.launch',
        default_hostname: '192.168.0.1',
        port_arg: 'udp_port',
        default_port: 2115,
        has_udp_receiver: true,
        has_imu_udp_port: true,
        scan_layers: 16
      }));
    });

    it('should handle mock API delay', async () => {
      const startTime = Date.now();
      await service.loadProfiles();
      const endTime = Date.now();

      // Should take at least 100ms due to mock delay
      expect(endTime - startTime).toBeGreaterThanOrEqual(100);
    });

    // Note: When real API is implemented, these tests should be updated
    // to test actual HTTP calls to GET /api/v1/lidar/profiles
  });
});
