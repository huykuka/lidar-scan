import {CalibrationNodeStatusResponse} from '@core/models/calibration.model';

/**
 * Mock data for frontend development while backend Task 5.1 (new /status endpoint) is pending.
 * Remove these mocks from CalibrationApiService.getNodeStatus() once Backend Task 5.1 is [x].
 */

export const MOCK_CALIBRATION_STATUS_IDLE: CalibrationNodeStatusResponse = {
  node_id: 'mock-cal-node-001',
  node_name: 'ICP Calibration',
  enabled: true,
  calibration_state: 'idle',
  quality_good: null,
  reference_sensor_id: 'mock-sensor-ref',
  source_sensor_ids: ['mock-sensor-src'],
  buffered_frames: {'mock-sensor-ref': 28, 'mock-sensor-src': 25},
  last_calibration_time: null,
  pending_results: {},
};

export const MOCK_CALIBRATION_STATUS_PENDING: CalibrationNodeStatusResponse = {
  node_id: 'mock-cal-node-001',
  node_name: 'ICP Calibration',
  enabled: true,
  calibration_state: 'pending',
  quality_good: true,
  reference_sensor_id: 'mock-sensor-ref',
  source_sensor_ids: ['mock-sensor-src'],
  buffered_frames: {'mock-sensor-ref': 28, 'mock-sensor-src': 25},
  last_calibration_time: '2026-03-22T14:30:00.000Z',
  pending_results: {
    'mock-sensor-src': {
      fitness: 0.921,
      rmse: 0.00312,
      quality: 'excellent',
      quality_good: true,
      source_sensor_id: 'mock-sensor-src',
      processing_chain: ['mock-sensor-src', 'mock-cal-node-001'],
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
