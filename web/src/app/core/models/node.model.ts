export interface NodeConfig {
  id: string;
  name: string;
  type: string;
  category: 'sensor' | 'fusion' | 'operation';
  enabled: boolean;
  config: Record<string, any>;
}

export interface Edge {
  id?: string;
  source_node: string;
  source_port: string;
  target_node: string;
  target_port: string;
}

export interface NodeStatus {
  id: string;
  name: string;
  type: string;
  category: string;
  enabled: boolean;
  running: boolean;
  last_error: string | null;
  // Specific fields for different categories
  connection_status?: 'connected' | 'disconnected' | 'starting' | 'error';
  frame_age_seconds?: number;
  broadcast_age_seconds?: number;
  // Dynamic metrics
  metrics?: Record<string, any>;
}

// Aliases for compatibility
export type LidarNodeStatus = NodeStatus;
export type FusionNodeStatus = NodeStatus;

export interface NodesStatusResponse {
  nodes: NodeStatus[];
}

export interface PropertySchema {
  name: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'vec3' | 'list';
  default?: any;
  options?: { label: string; value: any }[];
  required?: boolean;
  help_text?: string;
  min?: number;
  max?: number;
  step?: number;
}

export interface PortSchema {
  id: string;
  label: string;
  data_type: string;
  multiple: boolean;
}

export interface NodeDefinition {
  type: string;
  display_name: string;
  category: 'sensor' | 'fusion' | 'operation';
  description?: string;
  icon: string;
  properties: PropertySchema[];
  inputs: PortSchema[];
  outputs: PortSchema[];
}
