/**
 * Response from external state control endpoints
 */
export interface ExternalStateResponse {
  node_id: string;
  state: boolean;
  timestamp: number;
}

/**
 * Extended node status for IF condition nodes
 * Legacy type - superseded by NodeStatusUpdate.application_state in new status system
 * Kept for backward compatibility with existing IF node card components
 */
export interface IfNodeStatus {
  id: string;
  name: string;
  type: string;
  category: string;
  enabled: boolean;
  visible: boolean;
  running: boolean;
  topic?: string | null;
  last_error: string | null;
  expression: string;
  state: boolean | null;  // Unified routing state (True = route to 'true' port, False = route to 'false' port)
}

/**
 * Configuration for IF condition nodes
 */
export interface IfConditionConfig {
  expression: string;
  throttle_ms: number;
}
