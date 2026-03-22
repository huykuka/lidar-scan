import {TestBed} from '@angular/core/testing';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {provideHttpClient} from '@angular/common/http';
import {CalibrationApiService} from './calibration-api.service';
import {environment} from '../../../../environments/environment';
import {
  CalibrationAcceptResponse,
  CalibrationHistoryRecord,
  CalibrationHistoryResponse,
  CalibrationNodeStatusResponse,
  CalibrationTriggerResponse,
} from '../../models/calibration.model';

const BASE_HISTORY_RECORD: CalibrationHistoryRecord = {
  id: 'h1',
  sensor_id: 'sensor-1',
  reference_sensor_id: 'ref',
  timestamp: '2026-01-01T10:00:00Z',
  fitness: 0.9,
  rmse: 0.02,
  quality: 'good',
  stages_used: [],
  pose_before: {x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0},
  pose_after:  {x: 1, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0},
  transformation_matrix: [],
  accepted: true,
  notes: '',
};

describe('CalibrationApiService', () => {
  let service: CalibrationApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        CalibrationApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(CalibrationApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  // --- triggerCalibration ---

  it('should POST to trigger endpoint with run_id in response', async () => {
    const mockResponse: CalibrationTriggerResponse = {
      success: true,
      run_id: 'run-abc123',
      results: {
        'sensor-1': {
          fitness: 0.95,
          rmse: 0.01,
          quality: 'excellent',
          stages_used: ['icp'],
          pose_before: {x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0},
          pose_after:  {x: 1, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0},
          source_sensor_id: 'lidar-A',
          processing_chain: ['lidar-A', 'calib-1'],
        },
      },
      pending_approval: true,
    };

    const resultPromise = service.triggerCalibration('calib-node-1', {sample_frames: 5});

    const req = httpMock.expectOne(`${environment.apiUrl}/calibration/calib-node-1/trigger`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({sample_frames: 5});
    req.flush(mockResponse);

    const result = await resultPromise;
    expect(result.run_id).toBe('run-abc123');
    expect(result.results['sensor-1'].source_sensor_id).toBe('lidar-A');
    expect(result.results['sensor-1'].processing_chain).toEqual(['lidar-A', 'calib-1']);
  });

  it('should trigger calibration with default empty request body', async () => {
    const mockResponse: CalibrationTriggerResponse = {
      success: true, run_id: 'run-x', results: {}, pending_approval: false,
    };

    const resultPromise = service.triggerCalibration('calib-node-1');
    const req = httpMock.expectOne(`${environment.apiUrl}/calibration/calib-node-1/trigger`);
    expect(req.request.body).toEqual({});
    req.flush(mockResponse);

    await resultPromise;
  });

  // --- acceptCalibration ---

  it('should POST to accept endpoint and return run_id + accepted list', async () => {
    const mockResponse: CalibrationAcceptResponse = {
      success: true,
      run_id: 'run-abc123',
      accepted: ['sensor-1', 'sensor-2'],
      remaining_pending: [],
    };

    const resultPromise = service.acceptCalibration('calib-node-1', {sensor_ids: ['sensor-1']});

    const req = httpMock.expectOne(`${environment.apiUrl}/calibration/calib-node-1/accept`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({sensor_ids: ['sensor-1']});
    req.flush(mockResponse);

    const result = await resultPromise;
    expect(result.run_id).toBe('run-abc123');
    expect(result.accepted).toEqual(['sensor-1', 'sensor-2']);
    expect(result.remaining_pending).toEqual([]);
  });

  // --- getHistory ---

  it('should GET history without optional query params', async () => {
    const mockResponse: CalibrationHistoryResponse = {
      sensor_id: 'sensor-1',
      history: [BASE_HISTORY_RECORD],
    };

    const resultPromise = service.getHistory('sensor-1', 10);

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/history/sensor-1?limit=10`,
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockResponse);

    const result = await resultPromise;
    expect(result.history.length).toBe(1);
  });

  it('should include source_sensor_id query param when provided', async () => {
    const mockResponse: CalibrationHistoryResponse = {sensor_id: 'sensor-1', history: []};

    const resultPromise = service.getHistory('sensor-1', 10, 'lidar-A');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/history/sensor-1?limit=10&source_sensor_id=lidar-A`,
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockResponse);

    await resultPromise;
  });

  it('should include run_id query param when provided', async () => {
    const mockResponse: CalibrationHistoryResponse = {sensor_id: 'sensor-1', history: []};

    const resultPromise = service.getHistory('sensor-1', 10, undefined, 'run-abc123');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/history/sensor-1?limit=10&run_id=run-abc123`,
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockResponse);

    await resultPromise;
  });

  it('should include both source_sensor_id and run_id query params when both provided', async () => {
    const mockResponse: CalibrationHistoryResponse = {sensor_id: 'sensor-1', history: []};

    const resultPromise = service.getHistory('sensor-1', 20, 'lidar-B', 'run-xyz789');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/history/sensor-1?limit=20&source_sensor_id=lidar-B&run_id=run-xyz789`,
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockResponse);

    await resultPromise;
  });

  it('should URL-encode special characters in source_sensor_id and run_id', async () => {
    const mockResponse: CalibrationHistoryResponse = {sensor_id: 'sensor-1', history: []};

    const resultPromise = service.getHistory('sensor-1', 10, 'sensor A/B', 'run A&B');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/history/sensor-1?limit=10&source_sensor_id=sensor%20A%2FB&run_id=run%20A%26B`,
    );
    req.flush(mockResponse);

    await resultPromise;
  });

  it('should handle legacy history records with no provenance fields', async () => {
    const legacyRecord: CalibrationHistoryRecord = {
      ...BASE_HISTORY_RECORD,
      source_sensor_id: undefined,
      processing_chain: undefined,
      run_id: undefined,
    };
    const mockResponse: CalibrationHistoryResponse = {
      sensor_id: 'sensor-1',
      history: [legacyRecord],
    };

    const resultPromise = service.getHistory('sensor-1');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/history/sensor-1?limit=10`,
    );
    req.flush(mockResponse);

    const result = await resultPromise;
    expect(result.history[0].source_sensor_id).toBe(undefined);
    expect(result.history[0].run_id).toBe(undefined);
  });

  // --- HTTP 409 Conflict handling ---

  it('should reject promise with HTTP error on 409 Conflict during trigger', async () => {
    const resultPromise = service.triggerCalibration('calib-node-1');

    const req = httpMock.expectOne(`${environment.apiUrl}/calibration/calib-node-1/trigger`);
    req.flush(
      {detail: 'Calibration already running'},
      {status: 409, statusText: 'Conflict'},
    );

    await expect(resultPromise).rejects.toThrow();
  });

  it('should reject promise with HTTP error on 409 Conflict during accept', async () => {
    const resultPromise = service.acceptCalibration('calib-node-1');

    const req = httpMock.expectOne(`${environment.apiUrl}/calibration/calib-node-1/accept`);
    req.flush(
      {detail: 'Calibration already running'},
      {status: 409, statusText: 'Conflict'},
    );

    await expect(resultPromise).rejects.toThrow();
  });

  // --- getStatistics ---

  it('should GET statistics for a sensor', async () => {
    const mockStats = {
      sensor_id: 'sensor-1',
      total_attempts: 5,
      accepted_count: 3,
      avg_fitness: 0.88,
      avg_rmse: 0.015,
      best_fitness: 0.95,
      best_rmse: 0.008,
    };

    const resultPromise = service.getStatistics('sensor-1');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/statistics/sensor-1`,
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockStats);

    const result = await resultPromise;
    expect(result.sensor_id).toBe('sensor-1');
    expect(result.total_attempts).toBe(5);
  });

  // --- getNodeStatus (live HTTP, no mock) ---

  it('should GET node status from live endpoint', async () => {
    const mockStatus: CalibrationNodeStatusResponse = {
      node_id: 'calib-node-1',
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

    const resultPromise = service.getNodeStatus('calib-node-1');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/calib-node-1/status`,
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockStatus);

    const result = await resultPromise;
    expect(result.node_id).toBe('calib-node-1');
    expect(result.calibration_state).toBe('idle');
    expect(result.pending_results).toEqual({});
  });

  it('should GET node status with pending results', async () => {
    const mockPendingStatus: CalibrationNodeStatusResponse = {
      node_id: 'calib-node-1',
      node_name: 'ICP Calibration',
      enabled: true,
      calibration_state: 'pending',
      quality_good: true,
      reference_sensor_id: 'ref-sensor',
      source_sensor_ids: ['src-sensor'],
      buffered_frames: {'ref-sensor': 28, 'src-sensor': 25},
      last_calibration_time: '2026-03-22T14:30:00.000Z',
      pending_results: {
        'src-sensor': {
          fitness: 0.921,
          rmse: 0.00312,
          quality: 'excellent',
          quality_good: true,
          source_sensor_id: 'src-sensor',
          processing_chain: ['src-sensor', 'calib-node-1'],
          pose_before: {x: 1500.0, y: -200.0, z: 0.0, roll: 0.0, pitch: 0.0, yaw: 45.0},
          pose_after: {x: 1502.3, y: -198.7, z: 1.1, roll: 0.12, pitch: -0.08, yaw: 45.31},
          transformation_matrix: [
            [0.9999, -0.0054, 0.0021, 0.0023],
            [0.0054, 0.9999, 0.0008, 0.0013],
            [-0.0021, -0.0008, 1.0, 0.0000],
            [0.0, 0.0, 0.0, 1.0],
          ],
        },
      },
    };

    const resultPromise = service.getNodeStatus('calib-node-1');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/calib-node-1/status`,
    );
    req.flush(mockPendingStatus);

    const result = await resultPromise;
    expect(result.calibration_state).toBe('pending');
    expect(result.quality_good).toBe(true);
    expect(Object.keys(result.pending_results).length).toBe(1);
    const pendingResult = result.pending_results['src-sensor'];
    expect(pendingResult.fitness).toBeCloseTo(0.921);
    expect(pendingResult.rmse).toBeCloseTo(0.00312);
    expect(pendingResult.pose_after.x).toBe(1502.3);
  });

  it('should reject promise on 404 for unknown calibration node', async () => {
    const resultPromise = service.getNodeStatus('unknown-node');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/unknown-node/status`,
    );
    req.flush({detail: 'Node not found'}, {status: 404, statusText: 'Not Found'});

    await expect(resultPromise).rejects.toThrow();
  });

  it('should reject promise on 400 for non-calibration node', async () => {
    const resultPromise = service.getNodeStatus('lidar-sensor-node');

    const req = httpMock.expectOne(
      `${environment.apiUrl}/calibration/lidar-sensor-node/status`,
    );
    req.flush(
      {detail: 'Node is not a calibration node'},
      {status: 400, statusText: 'Bad Request'},
    );

    await expect(resultPromise).rejects.toThrow();
  });
});
