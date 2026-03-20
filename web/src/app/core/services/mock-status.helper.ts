/**
 * Mock Status Helper for Development
 * 
 * Provides mock NodeStatusUpdate data for frontend development
 * while the backend standardization is in progress.
 * 
 * Enable by setting environment.mockStatus = true
 */

import { signal, effect } from '@angular/core';
import { NodesStatusResponse, OperationalState } from '../models/node-status.model';

export const MOCK_SYSTEM_STATUS: NodesStatusResponse = {
  nodes: [
    {
      node_id: 'lidar_sensor_abc12345',
      operational_state: 'RUNNING',
      application_state: { label: 'connection_status', value: 'connected', color: 'green' },
      timestamp: Date.now() / 1000,
    },
    {
      node_id: 'calibration_node_def67890',
      operational_state: 'RUNNING',
      application_state: { label: 'calibrating', value: false, color: 'gray' },
      timestamp: Date.now() / 1000,
    },
    {
      node_id: 'if_condition_ghi11111',
      operational_state: 'RUNNING',
      application_state: { label: 'condition', value: 'true', color: 'green' },
      timestamp: Date.now() / 1000,
    },
    {
      node_id: 'voxel_downsample_jkl22222',
      operational_state: 'ERROR',
      application_state: { label: 'processing', value: false, color: 'gray' },
      error_message: 'Open3D: invalid point cloud — zero points after voxel filter',
      timestamp: Date.now() / 1000,
    },
    {
      node_id: 'fusion_service_mno33333',
      operational_state: 'RUNNING',
      application_state: { label: 'fusing', value: 2, color: 'blue' },
      timestamp: Date.now() / 1000,
    },
  ],
};

/**
 * Cycles through all four operational states on a 3-second timer
 * for visual testing of all status icons and badges.
 * 
 * @param statusSignal - The signal to update with cycling mock data
 * @returns cleanup function to stop the timer
 */
export function startMockStatusCycling(
  statusSignal: ReturnType<typeof signal<NodesStatusResponse | null>>
): () => void {
  const states: OperationalState[] = ['INITIALIZE', 'RUNNING', 'STOPPED', 'ERROR'];
  let currentStateIndex = 0;

  // Cycle every 3 seconds
  const intervalId = setInterval(() => {
    currentStateIndex = (currentStateIndex + 1) % states.length;
    const currentState = states[currentStateIndex];

    const mockData: NodesStatusResponse = {
      nodes: MOCK_SYSTEM_STATUS.nodes.map(node => ({
        ...node,
        operational_state: currentState,
        // Only include error_message when state is ERROR
        error_message: currentState === 'ERROR' ? (node.error_message ?? 'Mock error state') : undefined,
        timestamp: Date.now() / 1000,
      })),
    };

    statusSignal.set(mockData);
  }, 3000);

  // Return cleanup function
  return () => clearInterval(intervalId);
}
