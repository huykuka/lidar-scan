/**
 * WebSocket message emitted by the Output Node on the system_status topic.
 */
export interface OutputNodeMetadataMessage {
  type: 'output_node_metadata';
  node_id: string;
  timestamp: number;
  metadata: Record<string, any>;
}

/**
 * Webhook configuration for an Output Node.
 */
export interface WebhookConfig {
  webhook_enabled: boolean;
  webhook_url: string;
  webhook_auth_type: 'none' | 'bearer' | 'basic' | 'api_key';
  webhook_auth_token?: string | null;
  webhook_auth_username?: string | null;
  webhook_auth_password?: string | null;
  webhook_auth_key_name?: string | null;
  webhook_auth_key_value?: string | null;
  webhook_custom_headers?: Record<string, string> | null;
}

/**
 * Default webhook configuration used as initial form state.
 */
export const DEFAULT_WEBHOOK_CONFIG: WebhookConfig = {
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
