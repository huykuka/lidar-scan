import {ComponentFixture, TestBed} from '@angular/core/testing';
import {ReactiveFormsModule} from '@angular/forms';
import {signal} from '@angular/core';
import {vi} from 'vitest';
import {SensorNodeEditorComponent} from './sensor-node-editor.component';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodeEditorFacadeService} from '@features/settings/services/node-editor-facade.service';
import {LidarProfilesApiService} from '@core/services/api/lidar-profiles-api.service';
import {NodeConfig, NodeDefinition} from '@core/models/node.model';
import {StatusWebSocketService} from '@core/services/status-websocket.service';
import {Pose, ZERO_POSE} from '@core/models';

const mockDefinition: NodeDefinition = {
  type: 'sensor',
  display_name: 'Test Sensor',
  category: 'sensor',
  description: 'Test sensor node',
  icon: 'sensors',
  websocket_enabled: true,
  properties: [
    { name: 'hostname', label: 'Hostname', type: 'string', default: '' },
    { name: 'mode', label: 'Mode', type: 'select', default: 'real', options: [{ label: 'Real', value: 'real' }] },
  ],
  inputs: [],
  outputs: [],
};

const mockNode: NodeConfig = {
  id: 'sensor-001',
  name: 'Front LiDAR',
  type: 'sensor',
  category: 'sensor',
  enabled: true,
  config: { hostname: '192.168.1.10', mode: 'real' },
  pose: ZERO_POSE,
  x: 100,
  y: 100,
};

describe('SensorNodeEditorComponent', () => {
  let component: SensorNodeEditorComponent;
  let fixture: ComponentFixture<SensorNodeEditorComponent>;
  let mockFacade: any;
  let mockNodeStore: any;

  beforeEach(async () => {
    const saveNodeSpy = vi.fn().mockResolvedValue(true);
    mockFacade = { saveNode: saveNodeSpy };

    mockNodeStore = {
      selectedNode: signal(mockNode),
      nodeDefinitions: signal([mockDefinition]),
      setState: vi.fn(),
    };

    const mockLidarProfilesApi = {
      loadProfiles: vi.fn(),
      getProfileByModelId: vi.fn().mockReturnValue(null),
    };

    const mockStatusWs = {
      status: signal(null),
    };

    await TestBed.configureTestingModule({
      imports: [SensorNodeEditorComponent, ReactiveFormsModule],

      providers: [
        { provide: NodeStoreService, useValue: mockNodeStore },
        { provide: LidarProfilesApiService, useValue: mockLidarProfilesApi },
        { provide: StatusWebSocketService, useValue: mockStatusWs },
      ],
    })
    .overrideComponent(SensorNodeEditorComponent, {
      set: { providers: [{ provide: NodeEditorFacadeService, useValue: mockFacade }] }
    })
    .compileComponents();

    fixture = TestBed.createComponent(SensorNodeEditorComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('PoseFormComponent integration', () => {
    it('should render app-pose-form inside the editor template', () => {
      const poseFormEl = fixture.nativeElement.querySelector('app-pose-form');
      expect(poseFormEl).toBeTruthy();
    });
  });

  describe('onPoseChange()', () => {
    it('should update poseValue signal when onPoseChange is called', () => {
      const newPose: Pose = { x: 100, y: 200, z: 300, roll: 10, pitch: 20, yaw: 30 };
      component.onPoseChange(newPose);
      expect(component['poseValue']()).toEqual(newPose);
    });
  });

  describe('onSave() with pose', () => {
    it('should include pose field in the payload passed to facade.saveNode()', async () => {
      const customPose: Pose = { x: 10, y: 20, z: 30, roll: 5, pitch: 10, yaw: 15 };
      component.onPoseChange(customPose);

      await component.onSave();

      expect(mockFacade.saveNode).toHaveBeenCalled();
      const payload = mockFacade.saveNode.mock.calls[mockFacade.saveNode.mock.calls.length - 1][0];
      expect(payload.pose).toEqual(customPose);
    });

    it('should pass ZERO_POSE in payload when pose has not been changed', async () => {
      await component.onSave();

      const payload = mockFacade.saveNode.mock.calls[mockFacade.saveNode.mock.calls.length - 1][0];
      expect(payload.pose).toEqual(ZERO_POSE);
    });
  });

  describe('Save button disabled state', () => {
    it('should be disabled when isPoseValid is false', () => {
      component['isPoseValid'].set(false);
      fixture.detectChanges();
      expect(component['isSaveDisabled']()).toBe(true);
    });

    it('should be enabled when all forms are valid', () => {
      component['isPoseValid'].set(true);
      fixture.detectChanges();
      expect(component['isSaveDisabled']()).toBe(false);
    });
  });

  describe('Reset Pose propagation', () => {
    it('should reset poseValue to ZERO_POSE when onPoseChange emits ZERO_POSE', () => {
      component.onPoseChange({ x: 100, y: 200, z: 300, roll: 10, pitch: 20, yaw: 30 });
      component.onPoseChange(ZERO_POSE);
      expect(component['poseValue']()).toEqual(ZERO_POSE);
    });
  });
});
