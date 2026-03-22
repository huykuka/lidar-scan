// @ts-nocheck
import {ComponentFixture, TestBed} from '@angular/core/testing';
import {provideRouter, Router} from '@angular/router';
import {signal, ApplicationRef} from '@angular/core';
import {CalibrationComponent} from './calibration.component';
import {CalibrationStoreService} from '../../core/services/stores/calibration-store.service';
import {NodeStoreService} from '../../core/services/stores/node-store.service';
import {ToastService} from '../../core/services/toast.service';
import {NavigationService} from '../../core/services';
import {NodeConfig} from '../../core/models/node.model';

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeCalibrationNode(id: string, name: string): NodeConfig {
  return {
    id,
    name,
    type: 'icp_calibration',
    category: 'calibration',
    enabled: true,
    config: {},
    x: 0,
    y: 0,
  };
}

/** Flush all pending Angular effects/microtasks */
async function flushEffects(fixture: ComponentFixture<unknown>): Promise<void> {
  fixture.detectChanges();
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
  fixture.detectChanges();
}

// ── Test suite ───────────────────────────────────────────────────────────────

describe('CalibrationComponent', () => {
  let component: CalibrationComponent;
  let fixture: ComponentFixture<CalibrationComponent>;

  let calibrationStoreSpy: {
    startPolling: ReturnType<typeof vi.fn>;
    stopPolling: ReturnType<typeof vi.fn>;
    triggerCalibration: ReturnType<typeof vi.fn>;
    nodeStatuses: ReturnType<typeof signal>;
    error: ReturnType<typeof signal>;
    isTriggering: ReturnType<typeof signal>;
  };

  // Writable signals for the spies
  let nodeSignal: ReturnType<typeof signal<NodeConfig[]>>;
  let nodeStatusesSignal: ReturnType<typeof signal<Record<string, any>>>;
  let errorSignal: ReturnType<typeof signal<string | null>>;
  let isTriggeringSignal: ReturnType<typeof signal<boolean>>;

  beforeEach(async () => {
    nodeSignal = signal<NodeConfig[]>([]);
    nodeStatusesSignal = signal<Record<string, any>>({});
    errorSignal = signal<string | null>(null);
    isTriggeringSignal = signal<boolean>(false);

    calibrationStoreSpy = {
      startPolling: vi.fn(),
      stopPolling: vi.fn(),
      triggerCalibration: vi.fn().mockResolvedValue(undefined),
      nodeStatuses: nodeStatusesSignal,
      error: errorSignal,
      isTriggering: isTriggeringSignal,
    };

    const nodeStoreValue = {
      nodeStatusMap: signal(new Map()),
    };
    Object.defineProperty(nodeStoreValue, 'calibrationNodes', {
      get: () => nodeSignal,
    });

    const toastSpyValue = {
      danger: vi.fn(),
      success: vi.fn(),
    };

    const navigationSpyValue = {
      setPageConfig: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [CalibrationComponent],
      providers: [
        provideRouter([]),
        {provide: CalibrationStoreService, useValue: calibrationStoreSpy},
        {provide: NodeStoreService, useValue: nodeStoreValue},
        {provide: ToastService, useValue: toastSpyValue},
        {provide: NavigationService, useValue: navigationSpyValue},
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(CalibrationComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  // ── Reactive polling on node list changes (the core fix) ─────────────────

  it('should NOT start polling when calibrationNodeConfigs is empty (cold reload with no nodes yet)', () => {
    // nodeSignal starts empty — no polling should happen
    expect(calibrationStoreSpy.startPolling).not.toHaveBeenCalled();
  });

  it('should start polling reactively when calibrationNodeConfigs emits nodes', async () => {
    // Simulate nodes loading after the component is already alive (cold reload scenario)
    nodeSignal.set([makeCalibrationNode('node-1', 'ICP Cal A')]);
    await flushEffects(fixture);

    expect(calibrationStoreSpy.startPolling).toHaveBeenCalledWith('node-1');
  });

  it('should start polling for all nodes when multiple calibration nodes are present', async () => {
    nodeSignal.set([
      makeCalibrationNode('node-1', 'ICP Cal A'),
      makeCalibrationNode('node-2', 'ICP Cal B'),
    ]);
    await flushEffects(fixture);

    expect(calibrationStoreSpy.startPolling).toHaveBeenCalledWith('node-1');
    expect(calibrationStoreSpy.startPolling).toHaveBeenCalledWith('node-2');
  });

  it('should restart polling when node list changes (simulate node added at runtime)', async () => {
    nodeSignal.set([makeCalibrationNode('node-1', 'ICP Cal A')]);
    await flushEffects(fixture);

    const callCountAfterFirst = calibrationStoreSpy.startPolling.mock.calls.length;
    expect(callCountAfterFirst).toBe(1);

    // Now a second node is added
    nodeSignal.set([
      makeCalibrationNode('node-1', 'ICP Cal A'),
      makeCalibrationNode('node-2', 'ICP Cal B'),
    ]);
    await flushEffects(fixture);

    expect(calibrationStoreSpy.startPolling.mock.calls.length).toBeGreaterThan(callCountAfterFirst);
    expect(calibrationStoreSpy.startPolling).toHaveBeenCalledWith('node-2');
  });

  // ── ngOnDestroy ───────────────────────────────────────────────────────────

  it('should stop polling on destroy', () => {
    component.ngOnDestroy();
    expect(calibrationStoreSpy.stopPolling).toHaveBeenCalled();
  });

  // ── Error toast ───────────────────────────────────────────────────────────

  it('should show danger toast when store error signal changes', async () => {
    const toastService = TestBed.inject(ToastService);
    errorSignal.set('Something went wrong');
    await flushEffects(fixture);

    expect(toastService.danger).toHaveBeenCalledWith('Something went wrong');
  });

  // ── triggerCalibration ────────────────────────────────────────────────────

  it('should delegate triggerCalibration to store', async () => {
    await component.triggerCalibration('node-1');
    expect(calibrationStoreSpy.triggerCalibration).toHaveBeenCalledWith('node-1', {});
  });

  // ── Navigation ────────────────────────────────────────────────────────────

  it('viewDetails should navigate to /calibration/:id', () => {
    const router = TestBed.inject(Router);
    const spy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    component.viewDetails('node-1');

    expect(spy).toHaveBeenCalledWith(['/calibration', 'node-1']);
  });

  it('viewHistory should navigate to /calibration/:id/history', () => {
    const router = TestBed.inject(Router);
    const spy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    component.viewHistory('node-1');

    expect(spy).toHaveBeenCalledWith(['/calibration', 'node-1', 'history']);
  });

  it('goToSettings should navigate to /settings', () => {
    const router = TestBed.inject(Router);
    const spy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    component.goToSettings();

    expect(spy).toHaveBeenCalledWith(['/settings']);
  });

  // ── formatTime ────────────────────────────────────────────────────────────

  it('formatTime should return em dash for null/undefined', () => {
    expect(component.formatTime(null)).toBe('—');
    expect(component.formatTime(undefined)).toBe('—');
  });

  it('formatTime should return "Just now" for very recent timestamps', () => {
    const now = new Date().toISOString();
    expect(component.formatTime(now)).toBe('Just now');
  });

  it('formatTime should return minutes ago for recent timestamps', () => {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(component.formatTime(fiveMinutesAgo)).toBe('5m ago');
  });

  it('formatTime should return hours ago for older timestamps', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    expect(component.formatTime(twoHoursAgo)).toBe('2h ago');
  });

  it('formatTime should return days ago for very old timestamps', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
    expect(component.formatTime(threeDaysAgo)).toBe('3d ago');
  });

  // ── getNodePolledStatus ───────────────────────────────────────────────────

  it('getNodePolledStatus should return null for unknown node', () => {
    expect(component.getNodePolledStatus()('unknown')).toBeNull();
  });

  it('getNodePolledStatus should return status for known node', async () => {
    const mockStatus = {node_id: 'node-1', calibration_state: 'idle'};
    nodeStatusesSignal.set({'node-1': mockStatus});
    await flushEffects(fixture);

    expect(component.getNodePolledStatus()('node-1')).toEqual(mockStatus);
  });
});
