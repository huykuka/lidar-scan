import {TestBed} from '@angular/core/testing';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {provideHttpClient} from '@angular/common/http';
import {ResultsApiService} from './results-api.service';
import {environment} from '../../../../environments/environment';
import {DeleteResultResponse, NodeResultSummary, ResultDetail, ResultSummary} from '../../models/results.model';
import {firstValueFrom} from 'rxjs';

const MOCK_NODE: NodeResultSummary = {
  node_id: 'vol_node_001',
  node_name: 'Volume Calc',
  node_type: 'volume_calculation',
  result_count: 5,
  latest_timestamp: 1715000000.0,
};

const MOCK_SUMMARY: ResultSummary = {
  result_id: 'res-001',
  node_id: 'vol_node_001',
  timestamp: 1715000000.0,
  status: 'success',
  metadata_summary: {volume_m3: 12.4},
  pcd_count: 3,
};

const MOCK_DETAIL: ResultDetail = {
  result_id: 'res-001',
  node_id: 'vol_node_001',
  timestamp: 1715000000.0,
  status: 'success',
  metadata: {volume_m3: 12.4, icp_valid: true},
  pcd_files: [{label: 'empty', url: '/data/results/vol_node_001/res-001/empty.pcd'}],
};

describe('ResultsApiService', () => {
  let service: ResultsApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [ResultsApiService, provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ResultsApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('should GET node index from /results', async () => {
    const promise = firstValueFrom(service.getNodeIndex());
    const req = httpMock.expectOne(`${environment.apiUrl}/results`);
    expect(req.request.method).toBe('GET');
    req.flush([MOCK_NODE]);
    const nodes = await promise;
    expect(nodes.length).toBe(1);
    expect(nodes[0].node_id).toBe('vol_node_001');
  });

  it('should GET results by nodeId with limit and offset params', async () => {
    const promise = firstValueFrom(service.getResultsByNode('vol_node_001', 10, 0));
    const req = httpMock.expectOne(
      `${environment.apiUrl}/results/vol_node_001?limit=10&offset=0`,
    );
    expect(req.request.method).toBe('GET');
    req.flush([MOCK_SUMMARY]);
    const results = await promise;
    expect(results.length).toBe(1);
    expect(results[0].result_id).toBe('res-001');
  });

  it('should GET result detail', async () => {
    const promise = firstValueFrom(service.getResultDetail('vol_node_001', 'res-001'));
    const req = httpMock.expectOne(`${environment.apiUrl}/results/vol_node_001/res-001`);
    expect(req.request.method).toBe('GET');
    req.flush(MOCK_DETAIL);
    const detail = await promise;
    expect(detail.result_id).toBe('res-001');
    expect(detail.pcd_files.length).toBe(1);
  });

  it('should return static PCD URL without HTTP request', () => {
    const url = service.getPcdUrl('vol_node_001', 'res-001', 'empty');
    expect(url).toBe('/data/results/vol_node_001/res-001/empty.pcd');
  });

  it('should DELETE a result', async () => {
    const mockResp: DeleteResultResponse = {deleted: true, result_id: 'res-001'};
    const promise = firstValueFrom(service.deleteResult('vol_node_001', 'res-001'));
    const req = httpMock.expectOne(`${environment.apiUrl}/results/vol_node_001/res-001`);
    expect(req.request.method).toBe('DELETE');
    req.flush(mockResp);
    const resp = await promise;
    expect(resp.deleted).toBe(true);
  });

  it('should propagate 404 on getResultDetail', async () => {
    const promise = firstValueFrom(service.getResultDetail('vol_node_001', 'nonexistent'));
    const req = httpMock.expectOne(`${environment.apiUrl}/results/vol_node_001/nonexistent`);
    req.flush({detail: 'Result not found'}, {status: 404, statusText: 'Not Found'});
    await expect(promise).rejects.toThrow();
  });
});
