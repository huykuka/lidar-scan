import { NodeStatus } from './node.model';

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
 */
export interface IfNodeStatus extends NodeStatus {
  expression: string;
  state: boolean | null;  // Unified routing state (True = route to 'true' port, False = route to 'false' port)
  last_error: string | null;
}

/**
 * Configuration for IF condition nodes
 */
export interface IfConditionConfig {
  expression: string;
  throttle_ms: number;
}
