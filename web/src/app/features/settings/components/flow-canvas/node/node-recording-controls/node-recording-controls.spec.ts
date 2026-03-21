import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { vi } from 'vitest';
import { NodeRecordingControls } from './node-recording-controls';
import { CanvasNode } from '../flow-canvas-node.component';
import { RecordingStoreService } from '@core/services/stores';
import { RecordingApiService } from '@core/services/api';
import { ZERO_POSE, Pose } from '@core/models/pose.model';
import { signal } from '@angular/core';

function createMockNodeWithPose(pose?: Pose): CanvasNode {
  return {
    id: 'sensor-001',
    type: 'sensor',
    data: {
      id: 'sensor-001',
      name: 'Test Sensor',
      type: 'sensor',
      category: 'sensor',
      enabled: true,
      config: {
        mode: 'real',
        pipeline_name: 'test_pipeline',
      },
      pose: pose ?? { x: 10, y: 20, z: 30, roll: 5, pitch: 10, yaw: 15 },
      x: 100,
      y: 100,
    },
    position: { x: 100, y: 100 },
  };
}

describe('NodeRecordingControls — pose metadata', () => {
  let component: NodeRecordingControls;
  let fixture: ComponentFixture<NodeRecordingControls>;
  let mockRecordingApi: any;
  let mockRecordingStore: any;

  beforeEach(async () => {
    mockRecordingApi = {
      startRecording: vi.fn().mockReturnValue({ toPromise: () => Promise.resolve({ recording_id: 'rec-001', file_path: '/tmp/rec.bag', started_at: '' }) }),
      stopRecording: vi.fn().mockReturnValue({ toPromise: () => Promise.resolve() }),
    };

    mockRecordingStore = {
      isRecording: signal(() => false),
      getActiveRecordingByNodeId: signal(() => null),
      loadRecordings: vi.fn().mockResolvedValue(undefined),
    };

    await TestBed.configureTestingModule({
      imports: [NodeRecordingControls],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
      providers: [
        { provide: RecordingApiService, useValue: mockRecordingApi },
        { provide: RecordingStoreService, useValue: mockRecordingStore },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(NodeRecordingControls);
    component = fixture.componentInstance;
    const testPose: Pose = { x: 10, y: 20, z: 30, roll: 5, pitch: 10, yaw: 15 };
    fixture.componentRef.setInput('node', createMockNodeWithPose(testPose));
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('metadata.pose — reads from data.pose (top-level), not config.pose', () => {
    it('should set metadata.pose from node.data.pose when starting recording', async () => {
      const expectedPose: Pose = { x: 10, y: 20, z: 30, roll: 5, pitch: 10, yaw: 15 };

      await component['toggleRecording']();

      expect(mockRecordingApi.startRecording).toHaveBeenCalled();
      const startPayload = mockRecordingApi.startRecording.mock.calls[mockRecordingApi.startRecording.mock.calls.length - 1][0];
      expect(startPayload.metadata?.pose).toEqual(expectedPose);
    });

    it('should set metadata.pose to undefined when node.data.pose is undefined', async () => {
      const nodeNoPose: CanvasNode = {
        id: 'sensor-002',
        type: 'sensor',
        data: {
          id: 'sensor-002',
          name: 'No Pose',
          type: 'sensor',
          category: 'sensor',
          enabled: true,
          config: { mode: 'real' },
          x: 100,
          y: 100,
        },
        position: { x: 100, y: 100 },
      };
      fixture.componentRef.setInput('node', nodeNoPose);
      fixture.detectChanges();

      await component['toggleRecording']();

      const startPayload = mockRecordingApi.startRecording.mock.calls[mockRecordingApi.startRecording.mock.calls.length - 1][0];
      // The fix reads data.pose directly; when undefined no pose key should be set from the old broken path
      expect(startPayload.metadata?.pose).toBeUndefined();
    });

    it('should NOT use config.pose — the old broken path', async () => {
      // Create a node with config.pose (old format) but NO data.pose
      const nodeWithConfigPose: CanvasNode = {
        id: 'sensor-003',
        type: 'sensor',
        data: {
          id: 'sensor-003',
          name: 'Config Pose Node',
          type: 'sensor',
          category: 'sensor',
          enabled: true,
          config: {
            mode: 'real',
            pose: { x: 999, y: 999, z: 999, roll: 99, pitch: 99, yaw: 99 }, // old broken format
          },
          x: 100,
          y: 100,
          // note: NO top-level pose field
        },
        position: { x: 100, y: 100 },
      };

      fixture.componentRef.setInput('node', nodeWithConfigPose);
      fixture.detectChanges();

      await component['toggleRecording']();

      const startPayload = mockRecordingApi.startRecording.mock.calls[mockRecordingApi.startRecording.mock.calls.length - 1][0];
      // The new code reads data.pose (undefined in this case), NOT config.pose
      // So metadata.pose should be undefined, not the stale config.pose values
      expect(startPayload.metadata?.pose).toBeUndefined();
    });
  });
});
