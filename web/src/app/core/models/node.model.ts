import {Pose} from './pose.model';

export interface NodeConfig {
  id: string;
  name: string;
  type: string;
  category: string; // Dynamic from backend (sensor, fusion, operation, calibration, etc.)
  enabled: boolean;
  visible?: boolean; // defaults to true if omitted (legacy compat)
  config: Record<string, any>;
  pose?: Pose;
  x: number;
  y: number;
}

export interface Edge {
  id?: string;
  source_node: string;
  source_port: string;
  target_node: string;
  target_port: string;
}

export interface PropertySchema {
  name: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'vec3' | 'list' | 'pose';
  default?: any;
  options?: { label: string; value: any }[];
  required?: boolean;
  help_text?: string;
  min?: number;
  max?: number;
  step?: number;
  hidden?: boolean;
  depends_on?: Record<string, any[]>;
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
  category: string; // Dynamic from backend (sensor, fusion, operation, calibration, etc.)
  description?: string;
  icon: string;
  /** When false, the node does not stream data via WebSocket. Hides visibility & recording controls in the canvas UI. */
  websocket_enabled: boolean;
  properties: PropertySchema[];
  inputs: PortSchema[];
  outputs: PortSchema[];
}
