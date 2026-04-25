import {TestBed} from '@angular/core/testing';
import {LidarProfilesApiService} from './lidar-profiles-api.service';
import {NodeStoreService} from '../stores/node-store.service';
import {NodeDefinition} from '../../models/node.model';

const MOCK_SENSOR_DEFINITION: NodeDefinition = {
  type: 'sensor',
  display_name: 'LiDAR Sensor',
  category: 'sensor',
  icon: 'sensors',
  websocket_enabled: true,
  properties: [
    {
      name: 'lidar_type',
      label: 'LiDAR Model',
      type: 'select',
      default: 'multiscan',
      required: true,
      options: [
        {
          label: 'SICK multiScan100',
          value: 'multiscan',
          launch_file: 'launch/sick_multiscan.launch',
          default_hostname: '192.168.100.124',
          port_arg: 'udp_port',
          default_port: 2115,
          has_udp_receiver: true,
          has_imu_udp_port: true,
          scan_layers: 16,
          thumbnail_url: '/api/v1/assets/lidar/multiscan.png',
          icon_name: 'device_hub',
          icon_color: '#0066CC',
          disabled: false,
        },
        {
          label: 'SICK TiM5xx Family',
          value: 'tim_5xx',
          launch_file: 'launch/sick_tim_5xx.launch',
          default_hostname: '192.168.1.11',
          port_arg: 'port',
          default_port: 2112,
          has_udp_receiver: false,
          has_imu_udp_port: false,
          scan_layers: 1,
          thumbnail_url: '/api/v1/assets/lidar/tim5xx.png',
          icon_name: 'sensors',
          icon_color: '#FF6B35',
          disabled: false,
        },
        {
          label: 'Disabled Model',
          value: 'disabled_model',
          launch_file: 'launch/disabled.launch',
          default_hostname: '192.168.0.1',
          port_arg: '',
          default_port: 0,
          has_udp_receiver: false,
          has_imu_udp_port: false,
          scan_layers: 1,
          thumbnail_url: null,
          icon_name: null,
          icon_color: null,
          disabled: true,
        },
      ],
    },
  ],
  inputs: [],
  outputs: [],
};

describe('LidarProfilesApiService', () => {
  let service: LidarProfilesApiService;
  let nodeStore: NodeStoreService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    nodeStore = TestBed.inject(NodeStoreService);
    service = TestBed.inject(LidarProfilesApiService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should return empty profiles when no node definitions are loaded', () => {
    expect(service.profiles()).toEqual([]);
  });

  it('should derive profiles from sensor node definition', () => {
    nodeStore.set('nodeDefinitions', [MOCK_SENSOR_DEFINITION]);

    const profiles = service.profiles();
    expect(profiles.length).toBe(2); // disabled model is filtered out
  });

  it('should exclude disabled profiles', () => {
    nodeStore.set('nodeDefinitions', [MOCK_SENSOR_DEFINITION]);

    const profiles = service.profiles();
    const disabledProfile = profiles.find((p) => p.model_id === 'disabled_model');
    expect(disabledProfile).toBeUndefined();
  });

  it('should map option fields to LidarProfile interface correctly', () => {
    nodeStore.set('nodeDefinitions', [MOCK_SENSOR_DEFINITION]);

    const profiles = service.profiles();
    const multiscan = profiles.find((p) => p.model_id === 'multiscan');

    expect(multiscan).toBeDefined();
    expect(multiscan!.display_name).toBe('SICK multiScan100');
    expect(multiscan!.launch_file).toBe('launch/sick_multiscan.launch');
    expect(multiscan!.default_hostname).toBe('192.168.100.124');
    expect(multiscan!.port_arg).toBe('udp_port');
    expect(multiscan!.default_port).toBe(2115);
    expect(multiscan!.has_udp_receiver).toBe(true);
    expect(multiscan!.has_imu_udp_port).toBe(true);
    expect(multiscan!.scan_layers).toBe(16);
    expect(multiscan!.icon_name).toBe('device_hub');
    expect(multiscan!.icon_color).toBe('#0066CC');
  });

  it('should resolve relative thumbnail URLs to absolute backend URLs', () => {
    nodeStore.set('nodeDefinitions', [MOCK_SENSOR_DEFINITION]);

    const profiles = service.profiles();
    const multiscan = profiles.find((p) => p.model_id === 'multiscan');

    expect(multiscan!.thumbnail_url).toContain('/api/v1/assets/lidar/multiscan.png');
    expect(multiscan!.thumbnail_url?.startsWith('/api')).toBe(false);
  });

  describe('getProfileByModelId', () => {
    it('should return matching profile', () => {
      nodeStore.set('nodeDefinitions', [MOCK_SENSOR_DEFINITION]);

      const profile = service.getProfileByModelId('tim_5xx');
      expect(profile).toBeDefined();
      expect(profile!.model_id).toBe('tim_5xx');
      expect(profile!.display_name).toBe('SICK TiM5xx Family');
    });

    it('should return null for unknown model ID', () => {
      nodeStore.set('nodeDefinitions', [MOCK_SENSOR_DEFINITION]);

      const profile = service.getProfileByModelId('unknown_model');
      expect(profile).toBeNull();
    });

    it('should return null for disabled model ID', () => {
      nodeStore.set('nodeDefinitions', [MOCK_SENSOR_DEFINITION]);

      const profile = service.getProfileByModelId('disabled_model');
      expect(profile).toBeNull();
    });
  });
});
