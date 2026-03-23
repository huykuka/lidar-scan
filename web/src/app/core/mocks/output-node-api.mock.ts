import {WebhookConfig} from '@core/models/output-node.model';
import {NodeConfig} from '@core/models/node.model';

/**
 * Mock data for frontend development while @be-dev implements the Output Node endpoints.
 * See api-spec.md §4 for the authoritative mock data.
 *
 * Usage in tests:
 *   providers: [{ provide: OutputNodeApiService, useValue: MOCK_OUTPUT_NODE_API_SERVICE }]
 */

export const MOCK_WEBHOOK_CONFIG_DISABLED: WebhookConfig = {
  webhook_enabled: false,
  webhook_url: '',
  webhook_auth_type: 'none',
  webhook_auth_token: null,
  webhook_auth_username: null,
  webhook_auth_password: null,
  webhook_auth_key_name: 'X-API-Key',
  webhook_auth_key_value: null,
  webhook_custom_headers: {},
};

export const MOCK_WEBHOOK_CONFIG_BEARER: WebhookConfig = {
  webhook_enabled: true,
  webhook_url: 'https://api.example.com/webhook',
  webhook_auth_type: 'bearer',
  webhook_auth_token: 'my-secret-token',
  webhook_auth_username: null,
  webhook_auth_password: null,
  webhook_auth_key_name: null,
  webhook_auth_key_value: null,
  webhook_custom_headers: {'X-Source': 'lidar-standalone'},
};

export const MOCK_OUTPUT_NODE: NodeConfig = {
  id: 'mock-output-node-001',
  name: 'My Output',
  type: 'output_node',
  category: 'flow_control',
  enabled: true,
  visible: false,
  config: {
    webhook_enabled: true,
    webhook_url: 'https://api.example.com/webhook',
    webhook_auth_type: 'bearer',
    webhook_auth_token: 'my-secret-token',
    webhook_custom_headers: {},
  },
  x: 300.0,
  y: 150.0,
};

/**
 * Mock WS messages emitted once per second during development.
 * Mirrors the api-spec.md §4 stream, using a dynamic node_id placeholder.
 */
export const MOCK_METADATA_MESSAGES = (nodeId: string) => [
  {
    type: 'output_node_metadata' as const,
    node_id: nodeId,
    timestamp: 1700000001.0,
    metadata: {point_count: 45000, intensity_avg: 0.72, sensor_name: 'lidar_front'},
  },
  {
    type: 'output_node_metadata' as const,
    node_id: nodeId,
    timestamp: 1700000002.0,
    metadata: {point_count: 46200, intensity_avg: 0.68, sensor_name: 'lidar_front'},
  },
];

/**
 * Mock implementation of OutputNodeApiService for use in tests.
 */
export const createMockOutputNodeApiService = (overrides?: {
  getNode?: (nodeId: string) => Promise<NodeConfig>;
  getWebhookConfig?: (nodeId: string) => Promise<WebhookConfig>;
  updateWebhookConfig?: (
    nodeId: string,
    config: WebhookConfig,
  ) => Promise<{status: string; node_id: string}>;
}) => ({
  getNode: overrides?.getNode ?? vi.fn().mockResolvedValue(MOCK_OUTPUT_NODE),
  getWebhookConfig:
    overrides?.getWebhookConfig ?? vi.fn().mockResolvedValue(MOCK_WEBHOOK_CONFIG_DISABLED),
  updateWebhookConfig:
    overrides?.updateWebhookConfig ??
    vi.fn().mockResolvedValue({status: 'ok', node_id: 'mock-node-id'}),
});
