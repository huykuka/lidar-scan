import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { vi } from 'vitest';
import { SensorNodeCardComponent } from './sensor-node-card.component';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import { ZERO_POSE, Pose } from '@core/models/pose.model';
import { LidarProfilesApiService } from '@core/services/api/lidar-profiles-api.service';

function createMockNode(poseOverride?: Partial<Pose>, configOverride: Record<string, any> = {}): CanvasNode {
  return {
    id: 'sensor-001',
    type: 'sensor',
    data: {
      id: 'sensor-001',
      name: 'Front LiDAR',
      type: 'sensor',
      category: 'sensor',
      enabled: true,
      config: {
        hostname: '192.168.1.10',
        mode: 'real',
        lidar_type: 'multiscan',
        ...configOverride,
      },
      pose: poseOverride ? { ...ZERO_POSE, ...poseOverride } : ZERO_POSE,
      x: 100,
      y: 100,
    },
    position: { x: 100, y: 100 },
  };
}

describe('SensorNodeCardComponent', () => {
  let component: SensorNodeCardComponent;
  let fixture: ComponentFixture<SensorNodeCardComponent>;

  beforeEach(async () => {
    const lidarProfilesSpy = {
      loadProfiles: vi.fn(),
      getProfileByModelId: vi.fn().mockReturnValue(null),
    };

    await TestBed.configureTestingModule({
      imports: [SensorNodeCardComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
      providers: [{ provide: LidarProfilesApiService, useValue: lidarProfilesSpy }],
    }).compileComponents();

    fixture = TestBed.createComponent(SensorNodeCardComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('node', createMockNode());
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('pose() computed', () => {
    it('should read x, y, z from node.data.pose (not config)', () => {
      fixture.componentRef.setInput('node', createMockNode({ x: 150.5, y: -25.5, z: 800.0 }));
      fixture.detectChanges();

      const poseValues = component['pose']();
      expect(poseValues[0]).toBe('150.50');
      expect(poseValues[1]).toBe('-25.50');
      expect(poseValues[2]).toBe('800.00');
    });

    it('should NOT read x from config when pose is available', () => {
      // node with x=999 in config but x=1 in pose
      const node = createMockNode({ x: 1 }, { x: 999 });
      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      const poseValues = component['pose']();
      expect(poseValues[0]).toBe('1.00');
    });

    it('should fallback to ZERO_POSE when node.data.pose is undefined', () => {
      const node: CanvasNode = {
        id: 'sensor-no-pose',
        type: 'sensor',
        data: {
          id: 'sensor-no-pose',
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

      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      const poseValues = component['pose']();
      expect(poseValues[0]).toBe('0.00');
      expect(poseValues[1]).toBe('0.00');
      expect(poseValues[2]).toBe('0.00');
    });
  });

  describe('rotation() computed', () => {
    it('should read roll, pitch, yaw from node.data.pose (not config)', () => {
      fixture.componentRef.setInput('node', createMockNode({ roll: 10.5, pitch: -5.0, yaw: 45.0 }));
      fixture.detectChanges();

      const rotValues = component['rotation']();
      expect(rotValues[0]).toBe('10.5');
      expect(rotValues[1]).toBe('-5.0');
      expect(rotValues[2]).toBe('45.0');
    });

    it('should NOT read roll from config', () => {
      const node = createMockNode({ roll: 5 }, { roll: 999 });
      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      const rotValues = component['rotation']();
      expect(rotValues[0]).toBe('5.0');
    });

    it('should fallback to 0 rotation when pose is undefined', () => {
      const node: CanvasNode = {
        id: 'sensor-no-pose',
        type: 'sensor',
        data: {
          id: 'sensor-no-pose',
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
      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      const rotValues = component['rotation']();
      expect(rotValues[0]).toBe('0.0');
      expect(rotValues[1]).toBe('0.0');
      expect(rotValues[2]).toBe('0.0');
    });
  });
});
