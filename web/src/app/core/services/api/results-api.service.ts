import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {Observable, of} from 'rxjs';
import {environment} from '@env/environment';
import {
  DeleteResultResponse,
  NodeResultSummary,
  ResultDetail,
  ResultSummary,
} from '@core/models';

// ---------------------------------------------------------------------------
// Mock data — used when backend is not yet available
// ---------------------------------------------------------------------------
export const MOCK_NODE_INDEX: NodeResultSummary[] = [
  {
    node_id: 'volume_calc_abc123',
    node_name: 'Volume Calculation',
    node_type: 'volume_calculation',
    result_count: 14,
    latest_timestamp: 1715000000.123,
  },
  {
    node_id: 'vehicle_profiler_def456',
    node_name: 'Vehicle Profiler',
    node_type: 'vehicle_profiler',
    result_count: 3,
    latest_timestamp: 1714990000.0,
  },
  {
    node_id: 'surface_inspector_ghi789',
    node_name: 'Surface Inspector',
    node_type: 'surface_inspection',
    result_count: 0,
    latest_timestamp: null,
  },
];

export const MOCK_RESULTS_BY_NODE: Record<string, ResultSummary[]> = {
  volume_calc_abc123: [
    {
      result_id: '550e8400-e29b-41d4-a716-446655440000',
      node_id: 'volume_calc_abc123',
      timestamp: 1715000000.123,
      status: 'success',
      metadata_summary: {volume_m3: 12.4, icp_valid: true},
      pcd_count: 3,
    },
    {
      result_id: '550e8400-e29b-41d4-a716-446655440001',
      node_id: 'volume_calc_abc123',
      timestamp: 1714995000.0,
      status: 'warning',
      metadata_summary: {volume_m3: 9.1, icp_valid: false},
      pcd_count: 3,
    },
    {
      result_id: '550e8400-e29b-41d4-a716-446655440002',
      node_id: 'volume_calc_abc123',
      timestamp: 1714990000.0,
      status: 'error',
      metadata_summary: {volume_m3: 0, icp_valid: false},
      pcd_count: 0,
    },
  ],
  vehicle_profiler_def456: [
    {
      result_id: '660e8400-e29b-41d4-a716-446655440000',
      node_id: 'vehicle_profiler_def456',
      timestamp: 1714990000.0,
      status: 'success',
      metadata_summary: {vehicle_length_m: 5.2, confidence: 0.95},
      pcd_count: 2,
    },
  ],
};

export const MOCK_RESULT_DETAIL: Record<string, ResultDetail> = {
  '550e8400-e29b-41d4-a716-446655440000': {
    result_id: '550e8400-e29b-41d4-a716-446655440000',
    node_id: 'volume_calc_abc123',
    timestamp: 1715000000.123,
    status: 'success',
    metadata: {
      volume_m3: 12.4,
      volume_l: 12400.0,
      icp_fitness: 0.91,
      icp_valid: true,
      cell_count: 2048,
      grid_res: 0.05,
      calculation_number: 7,
    },
    pcd_files: [
      {
        label: 'empty',
        url: '/api/v1/results/volume_calc_abc123/550e8400-e29b-41d4-a716-446655440000/pcd/empty',
      },
      {
        label: 'loaded',
        url: '/api/v1/results/volume_calc_abc123/550e8400-e29b-41d4-a716-446655440000/pcd/loaded',
      },
      {
        label: 'merged',
        url: '/api/v1/results/volume_calc_abc123/550e8400-e29b-41d4-a716-446655440000/pcd/merged',
      },
    ],
  },
};

// ---------------------------------------------------------------------------

@Injectable({
  providedIn: 'root',
})
export class ResultsApiService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/results`;

  /** Returns all application nodes that have ≥1 result, merged with active DAG nodes. */
  getNodeIndex(): Observable<NodeResultSummary[]> {
    return this.http.get<NodeResultSummary[]>(this.baseUrl);
  }

  /** Lists all results for a node, newest first. */
  getResultsByNode(
    nodeId: string,
    limit = 100,
    offset = 0,
  ): Observable<ResultSummary[]> {
    return this.http.get<ResultSummary[]>(`${this.baseUrl}/${nodeId}`, {
      params: {limit: limit.toString(), offset: offset.toString()},
    });
  }

  /** Full result detail including all metadata and PCD file entries. */
  getResultDetail(nodeId: string, resultId: string): Observable<ResultDetail> {
    return this.http.get<ResultDetail>(`${this.baseUrl}/${nodeId}/${resultId}`);
  }

  /**
   * Returns the URL for a PCD file download.
   * Used directly in component for `<src>` binding or fetch calls.
   */
  getPcdUrl(nodeId: string, resultId: string, label: string): string {
    return `${this.baseUrl}/${nodeId}/${resultId}/pcd/${label}`;
  }

  /** Deletes a single result. Admin/debug use. */
  deleteResult(nodeId: string, resultId: string): Observable<DeleteResultResponse> {
    return this.http.delete<DeleteResultResponse>(`${this.baseUrl}/${nodeId}/${resultId}`);
  }
}
