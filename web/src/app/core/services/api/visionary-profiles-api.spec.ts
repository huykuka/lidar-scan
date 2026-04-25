import {TestBed} from '@angular/core/testing';
import {VisionaryProfilesApiService} from './visionary-profiles-api.service';
import {NodeStoreService} from '../stores/node-store.service';
import {NodeDefinition} from '../../models/node.model';

const MOCK_VISIONARY_DEFINITION: NodeDefinition = {
  type: 'visionary_sensor',
  display_name: 'Visionary 3D Camera',
  category: 'sensor',
  icon: 'videocam',
  websocket_enabled: true,
  properties: [
    {
      name: 'camera_model',
      label: 'Camera Model',
      type: 'select',
      default: 'visionary_t_mini_cx',
      required: true,
      options: [
        {
          label: 'Visionary-T Mini CX (V3S105)',
          value: 'visionary_t_mini_cx',
          is_stereo: false,
          acquisition_method: 'sdk',
          default_hostname: '192.168.1.10',
          cola_protocol: 'Cola2',
          default_control_port: 2122,
          default_streaming_port: 2114,
          thumbnail_url: '/api/v1/assets/visionary/visionary_t_mini_cx.png',
          icon_name: 'videocam',
          icon_color: '#0066CC',
          disabled: false,
        },
        {
          label: 'Visionary-S CX (V3S102)',
          value: 'visionary_s_cx',
          is_stereo: true,
          acquisition_method: 'sdk',
          default_hostname: '192.168.1.10',
          cola_protocol: 'Cola2',
          default_control_port: 2122,
          default_streaming_port: 2114,
          thumbnail_url: '/api/v1/assets/visionary/visionary_s_cx.png',
          icon_name: 'videocam',
          icon_color: '#00994D',
          disabled: false,
        },
        {
          label: 'Disabled Camera',
          value: 'disabled_camera',
          is_stereo: false,
          acquisition_method: 'sdk',
          default_hostname: '192.168.1.10',
          cola_protocol: 'Cola2',
          default_control_port: 2122,
          default_streaming_port: 2114,
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

describe('VisionaryProfilesApiService', () => {
  let service: VisionaryProfilesApiService;
  let nodeStore: NodeStoreService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    nodeStore = TestBed.inject(NodeStoreService);
    service = TestBed.inject(VisionaryProfilesApiService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should return empty profiles when no node definitions are loaded', () => {
    expect(service.profiles()).toEqual([]);
  });

  it('should derive profiles from visionary_sensor node definition', () => {
    nodeStore.set('nodeDefinitions', [MOCK_VISIONARY_DEFINITION]);

    const profiles = service.profiles();
    expect(profiles.length).toBe(2); // disabled camera is filtered out
  });

  it('should exclude disabled profiles', () => {
    nodeStore.set('nodeDefinitions', [MOCK_VISIONARY_DEFINITION]);

    const profiles = service.profiles();
    const disabledProfile = profiles.find((p) => p.model_id === 'disabled_camera');
    expect(disabledProfile).toBeUndefined();
  });

  it('should map option fields to VisionaryProfile interface correctly', () => {
    nodeStore.set('nodeDefinitions', [MOCK_VISIONARY_DEFINITION]);

    const profiles = service.profiles();
    const tMini = profiles.find((p) => p.model_id === 'visionary_t_mini_cx');

    expect(tMini).toBeDefined();
    expect(tMini!.display_name).toBe('Visionary-T Mini CX (V3S105)');
    expect(tMini!.is_stereo).toBe(false);
    expect(tMini!.acquisition_method).toBe('sdk');
    expect(tMini!.default_hostname).toBe('192.168.1.10');
    expect(tMini!.cola_protocol).toBe('Cola2');
    expect(tMini!.default_control_port).toBe(2122);
    expect(tMini!.default_streaming_port).toBe(2114);
    expect(tMini!.icon_name).toBe('videocam');
    expect(tMini!.icon_color).toBe('#0066CC');
  });

  it('should resolve relative thumbnail URLs to absolute backend URLs', () => {
    nodeStore.set('nodeDefinitions', [MOCK_VISIONARY_DEFINITION]);

    const profiles = service.profiles();
    const tMini = profiles.find((p) => p.model_id === 'visionary_t_mini_cx');

    expect(tMini!.thumbnail_url).toContain('/api/v1/assets/visionary/visionary_t_mini_cx.png');
    expect(tMini!.thumbnail_url?.startsWith('/api')).toBe(false);
  });

  describe('getProfileByModelId', () => {
    it('should return matching profile', () => {
      nodeStore.set('nodeDefinitions', [MOCK_VISIONARY_DEFINITION]);

      const profile = service.getProfileByModelId('visionary_s_cx');
      expect(profile).toBeDefined();
      expect(profile!.model_id).toBe('visionary_s_cx');
      expect(profile!.display_name).toBe('Visionary-S CX (V3S102)');
      expect(profile!.is_stereo).toBe(true);
    });

    it('should return null for unknown model ID', () => {
      nodeStore.set('nodeDefinitions', [MOCK_VISIONARY_DEFINITION]);

      const profile = service.getProfileByModelId('unknown_model');
      expect(profile).toBeNull();
    });

    it('should return null for disabled model ID', () => {
      nodeStore.set('nodeDefinitions', [MOCK_VISIONARY_DEFINITION]);

      const profile = service.getProfileByModelId('disabled_camera');
      expect(profile).toBeNull();
    });
  });
});
