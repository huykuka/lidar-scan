import {TestBed, fakeAsync, tick} from '@angular/core/testing';
import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';

import {SystemStatusService} from './system-status.service';
import {ToastService} from './toast.service';
import {ReloadEvent, SystemStatusInfo} from '@core/models/status.model';

const toastMock = {
  primary: () => {},
  success: vi.fn(),
  neutral: () => {},
  warning: vi.fn(),
  danger: () => {},
};

describe('SystemStatusService', () => {
  let service: SystemStatusService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    toastMock.success.mockClear();
    toastMock.warning.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {provide: ToastService, useValue: toastMock},
      ],
    });
    service = TestBed.inject(SystemStatusService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('refreshNow() hits /status and sets online state', () => {
    service.refreshNow();
    const req = httpMock.expectOne((r) => r.method === 'GET' && r.url.endsWith('/status'));
    req.flush({is_running: true, active_sensors: ['a'], version: '1.0.0'});
    expect(service.backendOnline()).toBe(true);
    expect(service.backendVersion()).toBe('1.0.0');
    expect(service.activeSensors()).toEqual(['a']);
  });

  it('refreshNow() sets offline on error', () => {
    service.refreshNow();
    const req = httpMock.expectOne((r) => r.method === 'GET' && r.url.endsWith('/status'));
    req.error(new ProgressEvent('error'));
    expect(service.backendOnline()).toBe(false);
    expect(service.backendVersion()).toBe(null);
    expect(service.activeSensors()).toEqual([]);
  });

  // ---------------------------------------------------------------------------
  // Reload signal handling (Phase 3)
  // ---------------------------------------------------------------------------
  describe('Reload event signal handling', () => {
    it('should expose empty reloadingNodeIds set initially', () => {
      expect(service.reloadingNodeIds().size).toBe(0);
    });

    it('should expose null lastReloadEvent initially', () => {
      expect(service.lastReloadEvent()).toBeNull();
    });

    it('should add node_id to reloadingNodeIds on reloading event', () => {
      const event: ReloadEvent = {
        node_id: 'node-abc',
        status: 'reloading',
        error_message: null,
        reload_mode: 'selective',
        timestamp: Date.now() / 1000,
      };
      service.applyReloadEvent(event);
      expect(service.reloadingNodeIds().has('node-abc')).toBe(true);
      expect(service.lastReloadEvent()).toEqual(event);
    });

    it('should remove node_id from reloadingNodeIds on ready event', () => {
      const reloadingEvent: ReloadEvent = {
        node_id: 'node-abc',
        status: 'reloading',
        error_message: null,
        reload_mode: 'selective',
        timestamp: Date.now() / 1000,
      };
      service.applyReloadEvent(reloadingEvent);
      expect(service.reloadingNodeIds().has('node-abc')).toBe(true);

      const readyEvent: ReloadEvent = {
        node_id: 'node-abc',
        status: 'ready',
        error_message: null,
        reload_mode: 'selective',
        timestamp: Date.now() / 1000,
      };
      service.applyReloadEvent(readyEvent);
      expect(service.reloadingNodeIds().has('node-abc')).toBe(false);
    });

    it('should remove node_id from reloadingNodeIds on error event', () => {
      const reloadingEvent: ReloadEvent = {
        node_id: 'node-xyz',
        status: 'reloading',
        error_message: null,
        reload_mode: 'selective',
        timestamp: Date.now() / 1000,
      };
      service.applyReloadEvent(reloadingEvent);

      const errorEvent: ReloadEvent = {
        node_id: 'node-xyz',
        status: 'error',
        error_message: 'Reload failed',
        reload_mode: 'selective',
        timestamp: Date.now() / 1000,
      };
      service.applyReloadEvent(errorEvent);
      expect(service.reloadingNodeIds().has('node-xyz')).toBe(false);
    });

    it('should clear all reloadingNodeIds on full reload event (node_id null)', () => {
      // Add two nodes as reloading first
      service.applyReloadEvent({
        node_id: 'n1', status: 'reloading', error_message: null,
        reload_mode: 'selective', timestamp: Date.now() / 1000,
      });
      service.applyReloadEvent({
        node_id: 'n2', status: 'reloading', error_message: null,
        reload_mode: 'selective', timestamp: Date.now() / 1000,
      });
      expect(service.reloadingNodeIds().size).toBe(2);

      // Full reload clears all
      service.applyReloadEvent({
        node_id: null, status: 'ready', error_message: null,
        reload_mode: 'full', timestamp: Date.now() / 1000,
      });
      expect(service.reloadingNodeIds().size).toBe(0);
    });

    it('should clear reloadingNodeIds via clearReloadingState()', () => {
      service.applyReloadEvent({
        node_id: 'n1', status: 'reloading', error_message: null,
        reload_mode: 'selective', timestamp: Date.now() / 1000,
      });
      service.clearReloadingState();
      expect(service.reloadingNodeIds().size).toBe(0);
    });
  });

  // ---------------------------------------------------------------------------
  // applySystemStatus — WS-push path
  // ---------------------------------------------------------------------------
  describe('applySystemStatus()', () => {
    const info: SystemStatusInfo = {is_running: true, active_sensors: ['lidar-1'], version: '2.0.0'};

    it('sets online signals', () => {
      service.applySystemStatus(info);
      expect(service.backendOnline()).toBe(true);
      expect(service.backendVersion()).toBe('2.0.0');
      expect(service.activeSensors()).toEqual(['lidar-1']);
      expect(service.isRunning()).toBe(true);
    });

    it('toasts online on offline→online transition', () => {
      // Force offline first
      service.setOffline();
      toastMock.success.mockClear();
      service.applySystemStatus(info);
      expect(toastMock.success).toHaveBeenCalledTimes(1);
    });

    it('does NOT toast when already online', () => {
      service.applySystemStatus(info);
      toastMock.success.mockClear();
      service.applySystemStatus(info);
      expect(toastMock.success).not.toHaveBeenCalled();
    });
  });

  // ---------------------------------------------------------------------------
  // setOffline — WS disconnect path
  // ---------------------------------------------------------------------------
  describe('setOffline()', () => {
    it('sets offline signals', () => {
      service.applySystemStatus({is_running: true, active_sensors: ['x'], version: '1'});
      service.setOffline();
      expect(service.backendOnline()).toBe(false);
      expect(service.backendVersion()).toBeNull();
      expect(service.activeSensors()).toEqual([]);
    });

    it('toasts offline on online→offline transition', () => {
      service.applySystemStatus({is_running: true, active_sensors: [], version: '1'});
      toastMock.warning.mockClear();
      service.setOffline();
      expect(toastMock.warning).toHaveBeenCalledTimes(1);
    });

    it('respects 30 s throttle — no double toast', () => {
      service.applySystemStatus({is_running: true, active_sensors: [], version: '1'});
      service.setOffline();
      // Flip back online, then offline again quickly
      service.applySystemStatus({is_running: true, active_sensors: [], version: '1'});
      toastMock.warning.mockClear();
      service.setOffline();
      expect(toastMock.warning).not.toHaveBeenCalled();
    });
  });

  // ---------------------------------------------------------------------------
  // start() — no polling, only one initial GET
  // ---------------------------------------------------------------------------
});
