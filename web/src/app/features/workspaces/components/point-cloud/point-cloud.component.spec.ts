// @vitest-environment jsdom
/**
 * PointCloudComponent unit tests.
 *
 * PointCloudSceneComponent runs inside NgtCanvas and relies on injectStore(),
 * so deep integration tests require a full canvas context.  These unit tests
 * cover the public contract of PointCloudComponent (signal inputs / defaults)
 * and the pure helper methods on PointCloudSceneComponent that do NOT need a
 * running renderer (getEffectiveMaxPoints, updatePointsForTopic via topicMap).
 */

import { TestBed } from '@angular/core/testing';
import { NO_ERRORS_SCHEMA, signal } from '@angular/core';
import { PointCloudComponent, PointCloudSceneComponent } from './point-cloud.component';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { PointCloudDataService } from '@core/services/point-cloud-data.service';
import { WorkspaceStoreService } from '@core/services/stores/workspace-store.service';
import { SplitLayoutStoreService } from '@core/services/split-layout-store.service';
import { ShapeLayerService } from '@core/services/shape-layer.service';
import { ShapesWsService } from '@core/services/shapes-ws.service';
import { EMPTY } from 'rxjs';

// ── Mock ResizeObserver (not available in jsdom) ──────────────────────────────
class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
(globalThis as any).ResizeObserver = MockResizeObserver;

// ── Service stubs ─────────────────────────────────────────────────────────────

const mockDataService = {
  frames: signal(new Map()),
  isConnected: signal(false),
};

const mockWorkspaceStore = {
  selectedTopics: signal<Array<{ topic: string; color: string; enabled: boolean }>>([]),
};

const mockSplitLayout = {
  resetCameraRequest: signal<{ paneId: string } | null>(null),
};

const mockShapeLayerService = {
  init: vi.fn(),
  applyFrame: vi.fn(),
  disposeAll: vi.fn(),
};

const mockShapesWsService = {
  frames$: EMPTY,
};

// ── Minimal NgtCanvas / injectStore stub ──────────────────────────────────────
// PointCloudSceneComponent calls injectStore() at construction.
// We stub the token so TestBed can construct it without a real WebGL context.
const mockStore = {
  gl: signal(null),
  size: signal({ width: 0, height: 0 }),
  snapshot: {
    scene: { background: null, add: vi.fn(), remove: vi.fn() },
    gl: null,
    size: { width: 400, height: 400 },
    controls: undefined,
    invalidate: vi.fn(),
  },
  update: vi.fn(),
};

vi.mock('angular-three', async (importOriginal) => {
  const actual = await importOriginal<typeof import('angular-three')>();
  return {
    ...actual,
    injectStore: () => mockStore,
    addAfterEffect: () => vi.fn(),
  };
});

// =============================================================================

describe('PointCloudComponent — signal inputs', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PointCloudComponent],
      providers: [
        { provide: PointCloudDataService, useValue: mockDataService },
        { provide: WorkspaceStoreService, useValue: mockWorkspaceStore },
        { provide: SplitLayoutStoreService, useValue: mockSplitLayout },
        { provide: ShapeLayerService, useValue: mockShapeLayerService },
        { provide: ShapesWsService, useValue: mockShapesWsService },
      ],
      schemas: [NO_ERRORS_SCHEMA],
    }).compileComponents();
  });

  it('viewType defaults to "perspective"', () => {
    const fixture = TestBed.createComponent(PointCloudComponent);
    expect(fixture.componentInstance.viewType()).toBe('perspective');
  });

  it('viewId defaults to empty string', () => {
    const fixture = TestBed.createComponent(PointCloudComponent);
    expect(fixture.componentInstance.viewId()).toBe('');
  });

  it('adaptiveLod defaults to false', () => {
    const fixture = TestBed.createComponent(PointCloudComponent);
    expect(fixture.componentInstance.adaptiveLod()).toBe(false);
  });

  it('pointSize defaults to 0.1', () => {
    const fixture = TestBed.createComponent(PointCloudComponent);
    expect(fixture.componentInstance.pointSize()).toBe(0.1);
  });

  it('showGrid defaults to true', () => {
    const fixture = TestBed.createComponent(PointCloudComponent);
    expect(fixture.componentInstance.showGrid()).toBe(true);
  });

  it('showAxes defaults to true', () => {
    const fixture = TestBed.createComponent(PointCloudComponent);
    expect(fixture.componentInstance.showAxes()).toBe(true);
  });

  it('backgroundColor defaults to "#000000"', () => {
    const fixture = TestBed.createComponent(PointCloudComponent);
    expect(fixture.componentInstance.backgroundColor()).toBe('#000000');
  });
});

// =============================================================================

describe('PointCloudSceneComponent — pure helpers', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PointCloudSceneComponent],
      providers: [
        { provide: PointCloudDataService, useValue: mockDataService },
        { provide: WorkspaceStoreService, useValue: mockWorkspaceStore },
        { provide: SplitLayoutStoreService, useValue: mockSplitLayout },
        { provide: ShapeLayerService, useValue: mockShapeLayerService },
        { provide: ShapesWsService, useValue: mockShapesWsService },
      ],
      schemas: [NO_ERRORS_SCHEMA],
    }).compileComponents();
  });

  // ── Adaptive LOD constants ────────────────────────────────────────────────

  describe('Adaptive LOD constants', () => {
    it('MAX_POINTS_LOD is 125 000', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      expect((fixture.componentInstance as any).MAX_POINTS_LOD).toBe(125_000);
    });

    it('MAX_POINTS is 250 000', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      expect((fixture.componentInstance as any).MAX_POINTS).toBe(250_000);
    });

    it('getEffectiveMaxPoints(true) returns LOD limit', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      expect(fixture.componentInstance.getEffectiveMaxPoints(true)).toBe(125_000);
    });

    it('getEffectiveMaxPoints(false) returns full limit', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      expect(fixture.componentInstance.getEffectiveMaxPoints(false)).toBe(250_000);
    });
  });

  // ── updatePointsForTopic via topicMap signal ──────────────────────────────

  describe('updatePointsForTopic', () => {
    it('updates positions and range signals for an existing topic', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      const cmp = fixture.componentInstance as any;

      // Seed topicMap with a topic entry as diffAndSyncTopics would
      const positionsSig = signal(new Float32Array(0));
      const colorSig = signal('#ff0000');
      const rangeSig = signal(0);
      cmp.topicMap.set(
        new Map([['test-topic', { topic: 'test-topic', positions: positionsSig, color: colorSig, range: rangeSig }]])
      );

      const input = new Float32Array(9); // 3 points × 3 coords
      input.set([1, 2, 3, 4, 5, 6, 7, 8, 9]);

      cmp.updatePointsForTopic('test-topic', input, 3);

      expect(rangeSig()).toBe(3);
      expect(positionsSig().length).toBe(9);
      expect(positionsSig()[0]).toBe(1);
    });

    it('clamps to MAX_POINTS_LOD when adaptiveLod is true', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      const cmp = fixture.componentInstance as any;

      const positionsSig = signal(new Float32Array(0));
      const rangeSig = signal(0);
      cmp.topicMap.set(
        new Map([['t', { topic: 't', positions: positionsSig, color: signal('#fff'), range: rangeSig }]])
      );
      // Force adaptiveLod to report true
      vi.spyOn(cmp, 'adaptiveLod').mockReturnValue(true);

      const bigInput = new Float32Array(150_000 * 3);
      cmp.updatePointsForTopic('t', bigInput, 150_000);

      expect(rangeSig()).toBe(125_000);
      expect(positionsSig().length).toBe(125_000 * 3);
    });

    it('is a no-op for unknown topics', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      const cmp = fixture.componentInstance as any;

      // Should not throw
      expect(() => cmp.updatePointsForTopic('unknown', new Float32Array(3), 1)).not.toThrow();
    });
  });

  // ── syncFrameBuffers deduplication ────────────────────────────────────────

  describe('syncFrameBuffers deduplication', () => {
    it('skips unchanged frame references, calls updatePointsForTopic only for new frames', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      const cmp = fixture.componentInstance as any;

      // Seed two topics
      for (const topic of ['topicA', 'topicB']) {
        cmp.topicMap().set(topic, {
          topic,
          positions: signal(new Float32Array(0)),
          color: signal('#fff'),
          range: signal(0),
        });
      }

      const updateSpy = vi.spyOn(cmp, 'updatePointsForTopic').mockImplementation(() => {});

      const frameA1 = { points: new Float32Array(3), count: 1 };
      const frameB1 = { points: new Float32Array(6), count: 2 };
      const frameA2 = { points: new Float32Array(9), count: 3 };

      cmp['syncFrameBuffers'](new Map([['topicA', frameA1], ['topicB', frameB1]]));
      cmp['syncFrameBuffers'](new Map([['topicA', frameA2], ['topicB', frameB1]]));

      // topicA called twice (new frames), topicB called once (frame unchanged)
      expect(updateSpy).toHaveBeenCalledTimes(3);
      expect(updateSpy).toHaveBeenNthCalledWith(1, 'topicA', frameA1.points, frameA1.count);
      expect(updateSpy).toHaveBeenNthCalledWith(2, 'topicB', frameB1.points, frameB1.count);
      expect(updateSpy).toHaveBeenNthCalledWith(3, 'topicA', frameA2.points, frameA2.count);
    });
  });

  // ── PointCloudDataService wiring ─────────────────────────────────────────

  describe('PointCloudDataService wiring', () => {
    it('injects PointCloudDataService', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      expect((fixture.componentInstance as any).dataService).toBeDefined();
    });

    it('exposes the frames signal from the data service', () => {
      const fixture = TestBed.createComponent(PointCloudSceneComponent);
      const svc = (fixture.componentInstance as any).dataService;
      expect(svc.frames).toBeDefined();
      expect(svc.frames()).toBeInstanceOf(Map);
    });
  });
});
