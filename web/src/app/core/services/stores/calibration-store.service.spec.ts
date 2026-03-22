// @ts-nocheck
import {TestBed} from '@angular/core/testing';
import {CalibrationStoreService} from './calibration-store.service';
import {CalibrationApiService} from '../api/calibration-api.service';
import {
  CalibrationHistoryResponse,
  CalibrationNodeStatusResponse,
} from '../../models/calibration.model';

// ── Mock data ────────────────────────────────────────────────────────────────

const MOCK_STATUS_IDLE: CalibrationNodeStatusResponse = {
  node_id: 'node-1',
  node_name: 'ICP Calibration',
  enabled: true,
  calibration_state: 'idle',
  quality_good: null,
  reference_sensor_id: 'ref-sensor',
  source_sensor_ids: ['src-sensor'],
  buffered_frames: {'ref-sensor': 10, 'src-sensor': 8},
  last_calibration_time: null,
  pending_results: {},
};

const MOCK_STATUS_PENDING: CalibrationNodeStatusResponse = {
  ...MOCK_STATUS_IDLE,
  calibration_state: 'pending',
  quality_good: true,
  last_calibration_time: '2026-03-22T14:30:00.000Z',
  pending_results: {
    'src-sensor': {
      fitness: 0.921,
      rmse: 0.00312,
      quality: 'excellent',
      quality_good: true,
      source_sensor_id: 'src-sensor',
      processing_chain: ['src-sensor', 'node-1'],
      pose_before: {x: 1500, y: -200, z: 0, roll: 0, pitch: 0, yaw: 45},
      pose_after: {x: 1502.3, y: -198.7, z: 1.1, roll: 0.12, pitch: -0.08, yaw: 45.31},
      transformation_matrix: [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
    },
  },
};

const MOCK_TRIGGER_RESPONSE = {
  success: true,
  run_id: 'run-abc123',
  results: {},
  pending_approval: true,
};

const MOCK_ACCEPT_RESPONSE = {
  success: true,
  run_id: 'run-abc123',
  accepted: ['src-sensor'],
  remaining_pending: [],
};

const MOCK_REJECT_RESPONSE = {
  success: true,
  rejected: ['src-sensor'],
};

const MOCK_ROLLBACK_RESPONSE = {
  success: true,
  sensor_id: 'src-sensor',
  restored_to: '2026-01-01T00:00:00Z',
};

const MOCK_HISTORY_RESPONSE: CalibrationHistoryResponse = {
  sensor_id: 'node-1',
  history: [
    {
      id: 'hist-1',
      sensor_id: 'src-sensor',
      reference_sensor_id: 'ref-sensor',
      timestamp: '2026-03-20T10:00:00Z',
      fitness: 0.9,
      rmse: 0.004,
      quality: 'good',
      stages_used: ['icp'],
      pose_before: {x: 1500, y: -200, z: 0, roll: 0, pitch: 0, yaw: 45},
      pose_after: {x: 1502, y: -199, z: 0.5, roll: 0.1, pitch: -0.05, yaw: 45.2},
      transformation_matrix: [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
      accepted: true,
      notes: '',
    },
  ],
};

// ── Test suite ───────────────────────────────────────────────────────────────

describe('CalibrationStoreService', () => {
  let store: CalibrationStoreService;
  let apiSpy: {
    getNodeStatus: ReturnType<typeof vi.fn>;
    triggerCalibration: ReturnType<typeof vi.fn>;
    acceptCalibration: ReturnType<typeof vi.fn>;
    rejectCalibration: ReturnType<typeof vi.fn>;
    rollback: ReturnType<typeof vi.fn>;
    getHistory: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    apiSpy = {
      getNodeStatus: vi.fn(),
      triggerCalibration: vi.fn(),
      acceptCalibration: vi.fn(),
      rejectCalibration: vi.fn(),
      rollback: vi.fn(),
      getHistory: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        CalibrationStoreService,
        {provide: CalibrationApiService, useValue: apiSpy},
      ],
    });

    store = TestBed.inject(CalibrationStoreService);
  });

  afterEach(() => {
    // Ensure polling is always stopped after each test to avoid timer leaks
    store.stopPolling();
    vi.useRealTimers();
  });

  // ── Initial state ─────────────────────────────────────────────────────────

  it('should initialize with empty state', () => {
    expect(store.nodeStatuses()).toEqual({});
    expect(store.pollingNodeId()).toBeNull();
    expect(store.historyByNode()).toEqual({});
    expect(store.isTriggering()).toBe(false);
    expect(store.isAccepting()).toBe(false);
    expect(store.isRejecting()).toBe(false);
    expect(store.isRollingBack()).toBe(false);
    expect(store.error()).toBeNull();
  });

  // ── getNodeStatus computed factory ───────────────────────────────────────

  it('getNodeStatus() should return null for unknown node', () => {
    expect(store.getNodeStatus()('unknown-id')).toBeNull();
  });

  it('getHistoryForNode() should return empty array for unknown node', () => {
    expect(store.getHistoryForNode()('unknown-id')).toEqual([]);
  });

  // ── Polling ───────────────────────────────────────────────────────────────

  it('startPolling should set pollingNodeId and trigger immediate fetch', async () => {
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    store.startPolling('node-1');

    expect(store.pollingNodeId()).toBe('node-1');
    expect(apiSpy.getNodeStatus).toHaveBeenCalledWith('node-1');

    // Clean up interval
    store.stopPolling();
  });

  it('startPolling should update nodeStatuses after first fetch', async () => {
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    store.startPolling('node-1');

    // Wait for the async fetch to resolve
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(store.nodeStatuses()['node-1']).toEqual(MOCK_STATUS_IDLE);
    expect(store.getNodeStatus()('node-1')).toEqual(MOCK_STATUS_IDLE);

    store.stopPolling();
  });

  it('startPolling should poll every 2 seconds', async () => {
    vi.useFakeTimers();
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    store.startPolling('node-1');
    // Flush the initial async fetch (promises resolve, but timers don't advance)
    await vi.advanceTimersByTimeAsync(0);

    expect(apiSpy.getNodeStatus).toHaveBeenCalledTimes(1);

    // Advance 2 seconds — triggers the interval callback and flushes its promise
    await vi.advanceTimersByTimeAsync(2000);
    expect(apiSpy.getNodeStatus).toHaveBeenCalledTimes(2);

    // Advance another 2 seconds
    await vi.advanceTimersByTimeAsync(2000);
    expect(apiSpy.getNodeStatus).toHaveBeenCalledTimes(3);

    store.stopPolling();
  });

  it('startPolling should stop previous poll before starting new one', async () => {
    vi.useFakeTimers();
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    store.startPolling('node-1');
    await vi.advanceTimersByTimeAsync(0);
    store.startPolling('node-2');
    await vi.advanceTimersByTimeAsync(0);

    expect(store.pollingNodeId()).toBe('node-2');

    store.stopPolling();
  });

  it('stopPolling should clear pollingNodeId and stop timer', async () => {
    vi.useFakeTimers();
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    store.startPolling('node-1');
    await vi.advanceTimersByTimeAsync(0);
    store.stopPolling();

    expect(store.pollingNodeId()).toBeNull();

    // No more calls after stopping
    const callCount = apiSpy.getNodeStatus.mock.calls.length;
    await vi.advanceTimersByTimeAsync(4000);
    expect(apiSpy.getNodeStatus.mock.calls.length).toBe(callCount);
  });

  it('polling should silently ignore fetch failures (stale data preservation)', async () => {
    apiSpy.getNodeStatus.mockRejectedValue(new Error('Network error'));

    store.startPolling('node-1');

    // Wait for the failed fetch to settle
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    // No error in store — silently ignored
    expect(store.error()).toBeNull();
    // nodeStatuses remains unchanged
    expect(store.nodeStatuses()['node-1']).toBeUndefined();

    store.stopPolling();
  });

  it('polling should preserve stale data when fetch fails after success', async () => {
    vi.useFakeTimers();

    // First call succeeds
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);
    store.startPolling('node-1');
    await vi.advanceTimersByTimeAsync(0);
    expect(store.nodeStatuses()['node-1']).toEqual(MOCK_STATUS_IDLE);

    // Subsequent call fails
    apiSpy.getNodeStatus.mockRejectedValue(new Error('Timeout'));
    await vi.advanceTimersByTimeAsync(2000);

    // Stale data is preserved, no error surfaced
    expect(store.nodeStatuses()['node-1']).toEqual(MOCK_STATUS_IDLE);
    expect(store.error()).toBeNull();

    store.stopPolling();
  });

  // ── Cold reload scenario ──────────────────────────────────────────────────

  it('should fetch node status correctly when startPolling is called after construction (simulated cold reload)', async () => {
    // Simulate the component calling startPolling on init (e.g. after route resolves)
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_PENDING);

    // No data yet
    expect(store.getNodeStatus()('node-1')).toBeNull();

    // startPolling called as part of component init after a cold reload
    store.startPolling('node-1');
    // Wait for immediate fetch to resolve
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    // Data is now available
    const status = store.getNodeStatus()('node-1');
    expect(status).not.toBeNull();
    expect(status?.calibration_state).toBe('pending');
    expect(status?.node_name).toBe('ICP Calibration');

    store.stopPolling();
  });

  it('should accept multiple node IDs in sequence (multi-node scenario)', async () => {
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    // Poll two nodes sequentially — second overwrites pollingNodeId
    store.startPolling('node-A');
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    store.startPolling('node-B');
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(store.pollingNodeId()).toBe('node-B');
    expect(apiSpy.getNodeStatus).toHaveBeenCalledWith('node-A');
    expect(apiSpy.getNodeStatus).toHaveBeenCalledWith('node-B');

    store.stopPolling();
  });

  // ── triggerCalibration ────────────────────────────────────────────────────

  it('triggerCalibration should set isTriggering true during call and false after', async () => {
    let capturedIsTriggering: boolean | null = null;

    apiSpy.triggerCalibration.mockImplementation(async () => {
      capturedIsTriggering = store.isTriggering();
      return MOCK_TRIGGER_RESPONSE;
    });

    await store.triggerCalibration('node-1', {});

    expect(capturedIsTriggering).toBe(true);
    expect(store.isTriggering()).toBe(false);
    expect(store.error()).toBeNull();
  });

  it('triggerCalibration should set error on failure', async () => {
    apiSpy.triggerCalibration.mockRejectedValue(new Error('ICP failed'));

    await store.triggerCalibration('node-1', {});

    expect(store.isTriggering()).toBe(false);
    expect(store.error()).toBe('ICP failed');
  });

  it('triggerCalibration should immediately fetch status after successful trigger', async () => {
    apiSpy.triggerCalibration.mockResolvedValue(MOCK_TRIGGER_RESPONSE);
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_PENDING);

    await store.triggerCalibration('node-1', {});

    expect(apiSpy.getNodeStatus).toHaveBeenCalledWith('node-1');
    expect(store.nodeStatuses()['node-1']).toEqual(MOCK_STATUS_PENDING);
  });

  it('triggerCalibration should NOT fetch status when the trigger call fails', async () => {
    apiSpy.triggerCalibration.mockRejectedValue(new Error('ICP failed'));

    await store.triggerCalibration('node-1', {});

    expect(apiSpy.getNodeStatus).not.toHaveBeenCalled();
    expect(store.error()).toBe('ICP failed');
  });

  // ── acceptCalibration ─────────────────────────────────────────────────────

  it('acceptCalibration should call api and refresh status on success', async () => {
    apiSpy.acceptCalibration.mockResolvedValue(MOCK_ACCEPT_RESPONSE);
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    await store.acceptCalibration('node-1', {sensor_ids: undefined});

    expect(apiSpy.acceptCalibration).toHaveBeenCalledWith('node-1', {sensor_ids: undefined});
    expect(store.isAccepting()).toBe(false);
  });

  it('acceptCalibration should set error on failure', async () => {
    apiSpy.acceptCalibration.mockRejectedValue(new Error('No pending'));

    await store.acceptCalibration('node-1');

    expect(store.error()).toBe('No pending');
    expect(store.isAccepting()).toBe(false);
  });

  // ── rejectCalibration ─────────────────────────────────────────────────────

  it('rejectCalibration should call api and set isRejecting false after', async () => {
    apiSpy.rejectCalibration.mockResolvedValue(MOCK_REJECT_RESPONSE);
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    await store.rejectCalibration('node-1');

    expect(apiSpy.rejectCalibration).toHaveBeenCalledWith('node-1');
    expect(store.isRejecting()).toBe(false);
    expect(store.error()).toBeNull();
  });

  it('rejectCalibration should set error on failure', async () => {
    apiSpy.rejectCalibration.mockRejectedValue(new Error('Node not found'));

    await store.rejectCalibration('node-1');

    expect(store.error()).toBe('Node not found');
    expect(store.isRejecting()).toBe(false);
  });

  // ── rollbackHistory ───────────────────────────────────────────────────────

  it('rollbackHistory should call rollback with record_id', async () => {
    apiSpy.rollback.mockResolvedValue(MOCK_ROLLBACK_RESPONSE);

    await store.rollbackHistory('src-sensor', 'record-uuid-001');

    expect(apiSpy.rollback).toHaveBeenCalledWith('src-sensor', {record_id: 'record-uuid-001'});
    expect(store.isRollingBack()).toBe(false);
    expect(store.error()).toBeNull();
  });

  it('rollbackHistory should set error on failure', async () => {
    apiSpy.rollback.mockRejectedValue(new Error('Record not accepted'));

    await store.rollbackHistory('src-sensor', 'bad-record');

    expect(store.error()).toBe('Record not accepted');
    expect(store.isRollingBack()).toBe(false);
  });

  // ── loadHistory ───────────────────────────────────────────────────────────

  it('loadHistory should populate historyByNode on success', async () => {
    apiSpy.getHistory.mockResolvedValue(MOCK_HISTORY_RESPONSE);

    await store.loadHistory('node-1', 50);

    expect(store.historyByNode()['node-1']).toEqual(MOCK_HISTORY_RESPONSE.history);
    expect(store.getHistoryForNode()('node-1').length).toBe(1);
    expect(store.isLoadingHistory()).toBe(false);
  });

  it('loadHistory should pass runId query param when provided', async () => {
    apiSpy.getHistory.mockResolvedValue(MOCK_HISTORY_RESPONSE);

    await store.loadHistory('node-1', 50, 'run-abc123');

    expect(apiSpy.getHistory).toHaveBeenCalledWith('node-1', 50, undefined, 'run-abc123');
  });

  it('loadHistory should set error on failure', async () => {
    apiSpy.getHistory.mockRejectedValue(new Error('DB error'));

    await store.loadHistory('node-1');

    expect(store.error()).toBe('DB error');
    expect(store.isLoadingHistory()).toBe(false);
  });

  // ── ngOnDestroy ───────────────────────────────────────────────────────────

  it('ngOnDestroy should stop polling', async () => {
    vi.useFakeTimers();
    apiSpy.getNodeStatus.mockResolvedValue(MOCK_STATUS_IDLE);

    store.startPolling('node-1');
    await vi.advanceTimersByTimeAsync(0);

    store.ngOnDestroy();

    expect(store.pollingNodeId()).toBeNull();
    const callCount = apiSpy.getNodeStatus.mock.calls.length;
    await vi.advanceTimersByTimeAsync(4000);
    expect(apiSpy.getNodeStatus.mock.calls.length).toBe(callCount);
  });
});
