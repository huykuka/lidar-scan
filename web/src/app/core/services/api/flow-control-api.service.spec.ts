// @ts-nocheck
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { FlowControlApiService } from './flow-control-api.service';
import { environment } from '@env/environment';
import { ExternalStateResponse } from '@core/models/flow-control.model';

describe('FlowControlApiService', () => {
  let service: FlowControlApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        FlowControlApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(FlowControlApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('setExternalState', () => {
    it('should POST to set endpoint with correct payload', async () => {
      const nodeId = 'node-123';
      const value = true;
      const mockResponse: ExternalStateResponse = {
        success: true,
        node_id: nodeId,
        external_state: value,
      };

      // Disable mock for this test
      service['USE_MOCK'] = false;

      const resultPromise = service.setExternalState(nodeId, value);

      const req = httpMock.expectOne(`${environment.apiUrl}/nodes/${nodeId}/flow-control/set`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ value });
      req.flush(mockResponse);

      const result = await resultPromise;
      expect(result.success).toBe(true);
      expect(result.node_id).toBe(nodeId);
      expect(result.external_state).toBe(value);
    });

    it('should handle false value', async () => {
      const nodeId = 'node-456';
      const value = false;
      const mockResponse: ExternalStateResponse = {
        success: true,
        node_id: nodeId,
        external_state: value,
      };

      service['USE_MOCK'] = false;

      const resultPromise = service.setExternalState(nodeId, value);

      const req = httpMock.expectOne(`${environment.apiUrl}/nodes/${nodeId}/flow-control/set`);
      expect(req.request.body).toEqual({ value: false });
      req.flush(mockResponse);

      const result = await resultPromise;
      expect(result.external_state).toBe(false);
    });

    it('should handle API errors gracefully', async () => {
      const nodeId = 'invalid-node';
      const value = true;

      service['USE_MOCK'] = false;

      const resultPromise = service.setExternalState(nodeId, value);

      const req = httpMock.expectOne(`${environment.apiUrl}/nodes/${nodeId}/flow-control/set`);
      req.flush(
        { detail: 'Node not found' },
        { status: 404, statusText: 'Not Found' }
      );

      await expectAsync(resultPromise).toBeRejected();
    });
  });

  describe('resetExternalState', () => {
    it('should POST to reset endpoint', async () => {
      const nodeId = 'node-789';
      const mockResponse: ExternalStateResponse = {
        success: true,
        node_id: nodeId,
        external_state: null,
      };

      service['USE_MOCK'] = false;

      const resultPromise = service.resetExternalState(nodeId);

      const req = httpMock.expectOne(`${environment.apiUrl}/nodes/${nodeId}/flow-control/reset`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({});
      req.flush(mockResponse);

      const result = await resultPromise;
      expect(result.success).toBe(true);
      expect(result.node_id).toBe(nodeId);
      expect(result.external_state).toBeNull();
    });

    it('should handle API errors gracefully', async () => {
      const nodeId = 'invalid-node';

      service['USE_MOCK'] = false;

      const resultPromise = service.resetExternalState(nodeId);

      const req = httpMock.expectOne(`${environment.apiUrl}/nodes/${nodeId}/flow-control/reset`);
      req.flush(
        { detail: 'Node not found' },
        { status: 404, statusText: 'Not Found' }
      );

      await expectAsync(resultPromise).toBeRejected();
    });
  });

  describe('Mock Mode', () => {
    it('should return mock data when USE_MOCK is true', async () => {
      service['USE_MOCK'] = true;

      const result = await service.setExternalState('node-123', true);

      expect(result.success).toBe(true);
      expect(result.node_id).toBe('node-123');
      expect(result.external_state).toBe(true);

      // Verify no HTTP request was made
      httpMock.expectNone(`${environment.apiUrl}/nodes/node-123/flow-control/set`);
    });

    it('should simulate delay in mock mode', async () => {
      service['USE_MOCK'] = true;
      const startTime = Date.now();

      await service.setExternalState('node-123', true);

      const elapsed = Date.now() - startTime;
      // Should have at least some delay (mock uses 200ms)
      expect(elapsed).toBeGreaterThanOrEqual(150); // Allow some tolerance
    });

    it('should simulate error for invalid node ID in mock mode', async () => {
      service['USE_MOCK'] = true;

      await expectAsync(
        service.setExternalState('invalid', true)
      ).toBeRejectedWithError('Mock: Node not found');
    });

    it('should reset to null in mock mode', async () => {
      service['USE_MOCK'] = true;

      const result = await service.resetExternalState('node-123');

      expect(result.success).toBe(true);
      expect(result.external_state).toBeNull();
    });
  });
});
