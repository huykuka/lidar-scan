import { NodeConfig, Edge } from './node.model';

export interface DagConfigResponse {
  config_version: number;
  nodes: NodeConfig[];
  edges: Edge[];
}

export interface DagConfigSaveRequest {
  base_version: number;
  nodes: NodeConfig[];
  edges: Edge[];
}

export interface DagConfigSaveResponse {
  config_version: number;
  node_id_map: Record<string, string>;
}

export interface DagConflictError {
  status: 409;
  error: {
    detail: string;
  };
}
