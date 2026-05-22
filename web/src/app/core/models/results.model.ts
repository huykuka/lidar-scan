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
  /**
   * Relative path to the PCD file as returned by the backend Results API.
   * Always in the form `results/<node_id>/<result_id>/<label>.pcd`.
   *
   * The frontend MUST form the full fetch URL as `/data/${path}`.
   * NEVER use the download API (`/api/.../download`) or any proxy endpoint
   * for point cloud viewing — PCD files are served directly as static assets
   * by the backend's `/data` mount.
   *
   * @example 'results/volume_calc_abc123/550e8400.../empty.pcd'
   */
  path: string;
  /**
   * Optional display color for the point cloud, as a CSS/hex color string
   * (e.g. `'#ff0000'`, `'rgb(255,0,0)'`).
   *
   * **Rendering contract:**
   * - When present, `PcdViewerComponent` uses this as `THREE.PointsMaterial.color`
   *   and sets `vertexColors = false`, ignoring any per-point RGB data in the PCD file.
   * - When absent, the viewer falls back to `vertexColors = true` and reads RGB
   *   from the PCD binary stream.
   *
   * This field is set by the backend node that produces the file. Different PCD
   * outputs from the same result (e.g. `empty` vs `loaded`) may use different colors
   * to allow visual discrimination in the viewer.
   */
  color?: string;
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
