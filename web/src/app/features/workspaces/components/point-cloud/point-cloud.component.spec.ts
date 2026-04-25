// @vitest-environment jsdom
/**
 * FE-04: PointCloudComponent — Dual-Camera & Adaptive LOD
 *
 * Strategy: spy on the private `initThree` and `animate` prototype methods
 * BEFORE createComponent so ngAfterViewInit never creates a WebGLRenderer.
 * The spy for initThree also injects minimal in-memory stubs for cameras,
 * controls, renderer, and scene so that effects/methods don't crash.
 */

import { TestBed } from '@angular/core/testing';
import { NO_ERRORS_SCHEMA, signal } from '@angular/core';
import { PointCloudComponent } from './point-cloud.component';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { PointCloudDataService } from '@core/services/point-cloud-data.service';
import { WorkspaceStoreService } from '@core/services/stores/workspace-store.service';
import { ViewOrientation } from '@core/services/split-layout-store.service';

// ── Mock ResizeObserver (not available in jsdom) ──────────────────────────────
class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
(globalThis as any).ResizeObserver = MockResizeObserver;

// ── Minimal stub for PointCloudDataService ────────────────────────────────────

const mockFrames = signal(new Map());

const mockDataService = {
  frames: mockFrames,
  isConnected: signal(false),
};

// ── Minimal stub for WorkspaceStoreService ────────────────────────────────────

const mockWorkspaceStore = {
  selectedTopics: signal<Array<{ topic: string; color: string; enabled: boolean }>>([]),
};

// ── Helpers ───────────────────────────────────────────────────────────────────

let initThreeSpy: ReturnType<typeof vi.spyOn>;
let animateSpy: ReturnType<typeof vi.spyOn>;

/** Minimal in-memory camera stub */
function makeCameraStub() {
  return {
    position: { set: vi.fn(), distanceTo: vi.fn(() => 1), copy: vi.fn() },
    lookAt: vi.fn(),
    aspect: 1,
    fov: 50,
    left: 0, right: 0, top: 0, bottom: 0,
    updateProjectionMatrix: vi.fn(),
  };
}

function createSut() {
  const proto = (PointCloudComponent as any).prototype;

  initThreeSpy = vi.spyOn(proto, 'initThree').mockImplementation(function (this: any) {
    this.perspCamera = makeCameraStub();
    this.orthoCamera = makeCameraStub();
    this.controls = {
      enableRotate: true,
      enableDamping: true,
      object: null,
      target: { set: vi.fn(), copy: vi.fn() },
      update: vi.fn(),
    };
    this.renderer = { dispose: vi.fn(), domElement: document.createElement('canvas') };
    this.scene = { background: null, add: vi.fn(), remove: vi.fn() };
    this.gridLabels = [];
    this.axesLabels = [];
  });
  animateSpy = vi.spyOn(proto, 'animate').mockImplementation(() => {});

  const fixture = TestBed.createComponent(PointCloudComponent);
  fixture.detectChanges();
  return fixture;
}

// =============================================================================

describe('PointCloudComponent — FE-04 Extensions', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PointCloudComponent],
      providers: [
        { provide: PointCloudDataService, useValue: mockDataService },
        { provide: WorkspaceStoreService, useValue: mockWorkspaceStore },
      ],
      schemas: [NO_ERRORS_SCHEMA],
    }).compileComponents();
  });

  afterEach(() => {
    initThreeSpy?.mockRestore();
    animateSpy?.mockRestore();
    vi.restoreAllMocks();
  });

  // ── Signal inputs ──────────────────────────────────────────────────────────

  describe('Signal inputs (new in FE-04)', () => {
    it('should have viewType input defaulting to "perspective"', () => {
      const fixture = createSut();
      expect(fixture.componentInstance.viewType()).toBe('perspective');
    });

    it('should have viewId input defaulting to empty string', () => {
      const fixture = createSut();
      expect(fixture.componentInstance.viewId()).toBe('');
    });

    it('should have adaptiveLod input defaulting to false', () => {
      const fixture = createSut();
      expect(fixture.componentInstance.adaptiveLod()).toBe(false);
    });
  });

  // ── Existing inputs preserved ──────────────────────────────────────────────

  describe('Existing inputs (backward-compatible)', () => {
    it('should still have pointSize input defaulting to 0.1', () => {
      const fixture = createSut();
      expect(fixture.componentInstance.pointSize()).toBe(0.1);
    });

    it('should still have showGrid input defaulting to true', () => {
      const fixture = createSut();
      expect(fixture.componentInstance.showGrid()).toBe(true);
    });

    it('should still have showAxes input defaulting to true', () => {
      const fixture = createSut();
      expect(fixture.componentInstance.showAxes()).toBe(true);
    });

    it('should still have backgroundColor input defaulting to "#000000"', () => {
      const fixture = createSut();
      expect(fixture.componentInstance.backgroundColor()).toBe('#000000');
    });
  });

  // ── Adaptive LOD constants ─────────────────────────────────────────────────

  describe('Adaptive LOD', () => {
    it('should expose MAX_POINTS_LOD constant of 125 000', () => {
      const cmp = createSut().componentInstance as any;
      expect(cmp.MAX_POINTS_LOD).toBe(125_000);
    });

    it('should expose MAX_POINTS constant of 250 000', () => {
      const cmp = createSut().componentInstance as any;
      expect(cmp.MAX_POINTS).toBe(250_000);
    });

    it('getEffectiveMaxPoints() returns LOD limit when passed true', () => {
      const cmp = createSut().componentInstance as any;
      expect(cmp.getEffectiveMaxPoints(true)).toBe(125_000);
    });

    it('getEffectiveMaxPoints() returns full limit when passed false', () => {
      const cmp = createSut().componentInstance as any;
      expect(cmp.getEffectiveMaxPoints(false)).toBe(250_000);
    });
  });

  // ── updatePointsForTopic with LOD ──────────────────────────────────────────

  describe('updatePointsForTopic with adaptive LOD', () => {
    it('should clamp draw range to MAX_POINTS_LOD when getEffectiveMaxPoints returns 125 000', () => {
      const cmp = createSut().componentInstance as any;

      const fakeGeometry = {
        attributes: {
          position: { array: new Float32Array(250_000 * 3), needsUpdate: false },
        },
        setDrawRange: vi.fn(),
        // ngOnDestroy calls geometry.dispose() — must exist on stub
        dispose: vi.fn(),
      };
      const fakeMaterial = { color: { set: vi.fn() }, dispose: vi.fn(), size: 0.1 };
      cmp.pointClouds.set('topic1', { pointsObj: {}, geometry: fakeGeometry, material: fakeMaterial, lastCount: 0 });

      vi.spyOn(cmp, 'getEffectiveMaxPoints').mockReturnValue(125_000);

      cmp.updatePointsForTopic('topic1', new Float32Array(150_000 * 3), 150_000);

      expect(fakeGeometry.setDrawRange).toHaveBeenCalledWith(0, 125_000);
    });

    it('should use full point count when getEffectiveMaxPoints returns 250 000', () => {
      const cmp = createSut().componentInstance as any;

      const fakeGeometry = {
        attributes: {
          position: { array: new Float32Array(250_000 * 3), needsUpdate: false },
        },
        setDrawRange: vi.fn(),
        // ngOnDestroy calls geometry.dispose() — must exist on stub
        dispose: vi.fn(),
      };
      const fakeMaterial = { color: { set: vi.fn() }, dispose: vi.fn(), size: 0.1 };
      cmp.pointClouds.set('topic2', { pointsObj: {}, geometry: fakeGeometry, material: fakeMaterial, lastCount: 0 });

      vi.spyOn(cmp, 'getEffectiveMaxPoints').mockReturnValue(250_000);

      cmp.updatePointsForTopic('topic2', new Float32Array(200_000 * 3), 200_000);

      expect(fakeGeometry.setDrawRange).toHaveBeenCalledWith(0, 200_000);
    });
  });

  // ── activeCamera getter ────────────────────────────────────────────────────

  describe('activeCamera getter', () => {
    it('should return perspCamera when viewType is "perspective"', () => {
      const cmp = createSut().componentInstance as any;
      const perspCam = { type: 'PerspectiveCamera' };
      const orthoCam = { type: 'OrthographicCamera' };
      cmp.perspCamera = perspCam;
      cmp.orthoCamera = orthoCam;
      vi.spyOn(cmp, 'viewType').mockReturnValue('perspective');
      expect(cmp.activeCamera).toBe(perspCam);
    });

    it('should return orthoCamera when viewType is "top"', () => {
      const cmp = createSut().componentInstance as any;
      const perspCam = { type: 'PerspectiveCamera' };
      const orthoCam = { type: 'OrthographicCamera' };
      cmp.perspCamera = perspCam;
      cmp.orthoCamera = orthoCam;
      vi.spyOn(cmp, 'viewType').mockReturnValue('top');
      expect(cmp.activeCamera).toBe(orthoCam);
    });

    it('should return orthoCamera when viewType is "front"', () => {
      const cmp = createSut().componentInstance as any;
      const perspCam = { type: 'PerspectiveCamera' };
      const orthoCam = { type: 'OrthographicCamera' };
      cmp.perspCamera = perspCam;
      cmp.orthoCamera = orthoCam;
      vi.spyOn(cmp, 'viewType').mockReturnValue('front');
      expect(cmp.activeCamera).toBe(orthoCam);
    });

    it('should return orthoCamera when viewType is "side"', () => {
      const cmp = createSut().componentInstance as any;
      const perspCam = { type: 'PerspectiveCamera' };
      const orthoCam = { type: 'OrthographicCamera' };
      cmp.perspCamera = perspCam;
      cmp.orthoCamera = orthoCam;
      vi.spyOn(cmp, 'viewType').mockReturnValue('side');
      expect(cmp.activeCamera).toBe(orthoCam);
    });
  });

  // ── initCamera position presets ────────────────────────────────────────────

  describe('initCamera position presets', () => {
    it('should configure perspCamera at (15,15,15) and enable rotation for "perspective"', () => {
      const cmp = createSut().componentInstance as any;

      cmp.initCamera('perspective' as ViewOrientation);

      expect(cmp.perspCamera.position.set).toHaveBeenCalledWith(15, 15, 15);
      expect(cmp.controls.enableRotate).toBe(true);
    });

    it('should configure orthoCamera at (0,30,0) and disable rotation for "top"', () => {
      const cmp = createSut().componentInstance as any;

      cmp.initCamera('top' as ViewOrientation);

      expect(cmp.orthoCamera.position.set).toHaveBeenCalledWith(0, 30, 0);
      expect(cmp.controls.enableRotate).toBe(false);
    });

    it('should configure orthoCamera at (0,0,30) and disable rotation for "front"', () => {
      const cmp = createSut().componentInstance as any;

      cmp.initCamera('front' as ViewOrientation);

      expect(cmp.orthoCamera.position.set).toHaveBeenCalledWith(0, 0, 30);
      expect(cmp.controls.enableRotate).toBe(false);
    });

    it('should configure orthoCamera at (30,0,0) and disable rotation for "side"', () => {
      const cmp = createSut().componentInstance as any;

      cmp.initCamera('side' as ViewOrientation);

      expect(cmp.orthoCamera.position.set).toHaveBeenCalledWith(30, 0, 0);
      expect(cmp.controls.enableRotate).toBe(false);
    });
  });

  // ── View method delegates ─────────────────────────────────────────────────

  describe('view delegate methods', () => {
    it('resetCamera() resets perspCamera to (15,15,15) and calls controls.update()', () => {
      const cmp = createSut().componentInstance as any;

      cmp.resetCamera();

      expect(cmp.perspCamera.position.set).toHaveBeenCalledWith(15, 15, 15);
      expect(cmp.controls.update).toHaveBeenCalled();
    });
  });

  // ── Bug fix: sizeAttenuation = false ─────────────────────────────────────
  // Regression guard: ensures PointsMaterial is always created with
  // sizeAttenuation: false so point size is screen-pixel-consistent across
  // perspective AND orthographic panels (Bug 1 fix).
  describe('addOrUpdatePointCloud — sizeAttenuation: false', () => {
    it('should create PointsMaterial with sizeAttenuation: false', () => {
      const cmp = createSut().componentInstance as any;

      // Stub the scene (initThree spy already initialises it, but we need add/remove)
      cmp.scene = { add: vi.fn(), remove: vi.fn(), background: null };

      cmp.addOrUpdatePointCloud('test-topic', '#00ff00');

      const cloud = cmp.pointClouds.get('test-topic');
      expect(cloud).toBeDefined();
      // sizeAttenuation must be false so all camera types render at the same pixel size
      expect(cloud.material.sizeAttenuation).toBe(false);

      // Cleanup
      cloud.geometry.dispose?.();
      cloud.material.dispose?.();
    });
  });



  describe('PointCloudDataService wiring', () => {
    it('should inject PointCloudDataService', () => {
      const cmp = createSut().componentInstance as any;
      expect(cmp.dataService).toBeDefined();
    });

    it('should expose the frames signal from the data service', () => {
      const cmp = createSut().componentInstance as any;
      expect(cmp.dataService.frames).toBeDefined();
      expect(cmp.dataService.frames()).toBeInstanceOf(Map);
    });
  });

  // ── FE-12: Error boundary ─────────────────────────────────────────────────
  describe('FE-12: Error boundary', () => {
    it('should expose hasError signal defaulting to false', () => {
      const cmp = createSut().componentInstance as any;
      expect(cmp.hasError).toBeDefined();
      expect(cmp.hasError()).toBe(false);
    });

    it('should expose errorMessage signal defaulting to empty string', () => {
      const cmp = createSut().componentInstance as any;
      expect(cmp.errorMessage).toBeDefined();
      expect(cmp.errorMessage()).toBe('');
    });

    it('should set hasError to true and capture errorMessage when initThree throws', async () => {
      // Restore the spy so the real initThree can be called
      initThreeSpy.mockRestore();

      // Make initThree throw by providing a broken container
      const throwSpy = vi.spyOn(
        (PointCloudComponent as any).prototype,
        'initThree',
      ).mockImplementation(function (this: any) {
        throw new Error('WebGL context creation failed');
      });
      // Also stub animate so it doesn't crash
      const animSpy = vi.spyOn(
        (PointCloudComponent as any).prototype,
        'animate',
      ).mockImplementation(() => {});

      const fixture = TestBed.createComponent(PointCloudComponent);
      fixture.detectChanges(); // triggers ngAfterViewInit

      const cmp = fixture.componentInstance as any;
      expect(cmp.hasError()).toBe(true);
      expect(cmp.errorMessage()).toContain('WebGL context creation failed');

      throwSpy.mockRestore();
      animSpy.mockRestore();
    });

    it('should NOT set hasError when initThree succeeds', () => {
      // The default createSut already mocks initThree successfully
      const cmp = createSut().componentInstance as any;
      expect(cmp.hasError()).toBe(false);
      expect(cmp.errorMessage()).toBe('');
    });
  });
});
