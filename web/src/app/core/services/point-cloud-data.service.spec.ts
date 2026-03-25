// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { signal } from '@angular/core';
import { PointCloudDataService } from './point-cloud-data.service';
import { MultiWebsocketService } from './multi-websocket.service';
import { WorkspaceStoreService } from './stores/workspace-store.service';

describe('PointCloudDataService', () => {
  let service: PointCloudDataService;
  let wsSubject: Subject<any>;
  let mockWsService: any;
  let mockWorkspaceStore: any;

  beforeEach(() => {
    wsSubject = new Subject<any>();

    mockWsService = {
      connect: vi.fn().mockReturnValue(wsSubject.asObservable()),
      disconnect: vi.fn(),
      disconnectAll: vi.fn(),
      isConnected: vi.fn().mockReturnValue(false),
    };

    // Minimal WorkspaceStoreService stub
    mockWorkspaceStore = {
      selectedTopics: signal<Array<{ topic: string; color: string; enabled: boolean }>>([]),
      set: vi.fn(),
      removeTopic: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        PointCloudDataService,
        { provide: MultiWebsocketService, useValue: mockWsService },
        { provide: WorkspaceStoreService, useValue: mockWorkspaceStore },
      ],
    });

    service = TestBed.inject(PointCloudDataService);
  });

  afterEach(() => {
    service.ngOnDestroy();
    TestBed.resetTestingModule();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should expose frames signal starting as an empty Map', () => {
    expect(service.frames()).toBeInstanceOf(Map);
    expect(service.frames().size).toBe(0);
  });

  it('should expose isConnected signal starting as false', () => {
    expect(service.isConnected()).toBe(false);
  });

  describe('WebSocket connection management', () => {
    it('should connect to WS when a topic becomes enabled', () => {
      mockWorkspaceStore.selectedTopics.set([
        { topic: 'lidar_1', color: '#00ff00', enabled: true },
      ]);

      // Trigger effect re-evaluation
      TestBed.flushEffects();

      expect(mockWsService.connect).toHaveBeenCalledWith(
        'lidar_1',
        expect.stringContaining('lidar_1'),
      );
    });

    it('should NOT connect to a disabled topic', () => {
      mockWorkspaceStore.selectedTopics.set([
        { topic: 'lidar_1', color: '#00ff00', enabled: false },
      ]);
      TestBed.flushEffects();
      expect(mockWsService.connect).not.toHaveBeenCalled();
    });

    it('should disconnect from a topic when it is removed', () => {
      // First connect
      mockWorkspaceStore.selectedTopics.set([
        { topic: 'lidar_1', color: '#00ff00', enabled: true },
      ]);
      TestBed.flushEffects();

      // Then remove
      mockWorkspaceStore.selectedTopics.set([]);
      TestBed.flushEffects();

      expect(mockWsService.disconnect).toHaveBeenCalledWith('lidar_1');
    });
  });

  describe('LIDR frame processing', () => {
    function buildLidrBuffer(count: number): ArrayBuffer {
      const buf = new ArrayBuffer(20 + count * 12);
      const view = new DataView(buf);
      view.setUint8(0, 76); view.setUint8(1, 73);
      view.setUint8(2, 68); view.setUint8(3, 82);
      view.setUint32(4, 1, true);
      view.setFloat64(8, Date.now() / 1000, true);
      view.setUint32(16, count, true);
      return buf;
    }

    it('should update frames signal when a valid LIDR binary frame arrives', () => {
      mockWorkspaceStore.selectedTopics.set([
        { topic: 'lidar_1', color: '#00ff00', enabled: true },
      ]);
      TestBed.flushEffects();

      wsSubject.next(buildLidrBuffer(100));

      expect(service.frames().has('lidar_1')).toBe(true);
      expect(service.frames().get('lidar_1')!.count).toBe(100);
    });

    it('should NOT update frames for invalid binary data (bad magic)', () => {
      mockWorkspaceStore.selectedTopics.set([
        { topic: 'lidar_1', color: '#00ff00', enabled: true },
      ]);
      TestBed.flushEffects();

      const badBuf = new ArrayBuffer(20);
      wsSubject.next(badBuf); // magic bytes are all 0 → invalid

      expect(service.frames().has('lidar_1')).toBe(false);
    });

    it('should update frames signal when JSON point cloud arrives', () => {
      mockWorkspaceStore.selectedTopics.set([
        { topic: 'lidar_1', color: '#00ff00', enabled: true },
      ]);
      TestBed.flushEffects();

      const jsonPayload = JSON.stringify({
        points: [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
      });
      wsSubject.next(jsonPayload);

      expect(service.frames().has('lidar_1')).toBe(true);
      expect(service.frames().get('lidar_1')!.count).toBe(3);
    });
  });

  describe('ngOnDestroy', () => {
    it('should call disconnectAll on destroy', () => {
      service.ngOnDestroy();
      expect(mockWsService.disconnectAll).toHaveBeenCalled();
    });
  });
});
