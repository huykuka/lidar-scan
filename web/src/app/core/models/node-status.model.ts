/**
 * Node Status Standardization — TypeScript schema
 * Mirrors the Python NodeStatusUpdate / SystemStatusBroadcast Pydantic models.
 * 
 * @see api-spec.md § 1.2
 */

export type OperationalState = 'INITIALIZE' | 'RUNNING' | 'STOPPED' | 'ERROR';

export interface ApplicationState {
  /** Human-readable state identifier, e.g. "connection_status", "calibrating" */
  label: string;
  /** JSON-serializable value: string | boolean | number */
  value: string | boolean | number;
  /** Optional UI color hint: "green" | "blue" | "orange" | "red" | "gray" */
  color?: 'green' | 'blue' | 'orange' | 'red' | 'gray';
}

export interface NodeStatusUpdate {
  node_id: string;
  operational_state: OperationalState;
  application_state?: ApplicationState;
  /** Only present when operational_state === ERROR */
  error_message?: string;
  /** Unix epoch seconds (float) */
  timestamp: number;
}

export interface NodesStatusResponse {
  nodes: NodeStatusUpdate[];
}
