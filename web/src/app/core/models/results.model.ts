export interface NodeResultSummary {
  node_id: string;
  node_name: string;
  node_type: string;
  result_count: number;
  latest_timestamp: number | null;
}

export interface ResultSummary {
  result_id: string;
  node_id: string;
  timestamp: number;
  status: 'success' | 'warning' | 'error';
  metadata_summary: Record<string, unknown>;
  pcd_count: number;
}

export interface PcdFileEntry {
  label: string;
  url: string;
}

export interface ResultDetail {
  result_id: string;
  node_id: string;
  timestamp: number;
  status: 'success' | 'warning' | 'error';
  metadata: Record<string, unknown>;
  pcd_files: PcdFileEntry[];
}

export interface DeleteResultResponse {
  deleted: boolean;
  result_id: string;
}

export interface PcdParseResult {
  positions: Float32Array;
  colors: Float32Array;
  pointCount: number;
}

export class PcdParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PcdParseError';
  }
}
