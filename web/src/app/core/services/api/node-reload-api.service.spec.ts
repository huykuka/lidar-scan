import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { NodeReloadApiService } from './node-reload-api.service';
import { NodeReloadResponse, ReloadStatusResponse } from '@core/models/status.model';

describe('NodeReloadApiService', () => {
  let service: NodeReloadApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        NodeReloadApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(NodeReloadApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  describe('reloadNode()', () => {
    it('should POST to /nodes/{nodeId}/reload and return NodeReloadResponse', async () => {
      const mockResponse: NodeReloadResponse = {
        node_id: 'a1b2c3d4',
        status: 'reloaded',
        duration_ms: 73,
        ws_topic: 'multiscan_left_a1b2c3d4',
      };

      const promise = service.reloadNode('a1b2c3d4');
      const req = httpMock.expectOne((r) =>
        r.method === 'POST' && r.url.endsWith('/nodes/a1b2c3d4/reload'),
      );
      req.flush(mockResponse);

      const result = await promise;
      expect(result.node_id).toBe('a1b2c3d4');
      expect(result.status).toBe('reloaded');
      expect(result.duration_ms).toBe(73);
      expect(result.ws_topic).toBe('multiscan_left_a1b2c3d4');
    });

    it('should propagate HTTP errors from reloadNode()', async () => {
      const promise = service.reloadNode('bad-node');
      const req = httpMock.expectOne((r) => r.url.endsWith('/nodes/bad-node/reload'));
      req.flush({ detail: 'Node not found' }, { status: 404, statusText: 'Not Found' });

      await expect(promise).rejects.toBeDefined();
    });
  });

  describe('getReloadStatus()', () => {
    it('should GET /nodes/reload/status and return ReloadStatusResponse', async () => {
      const mockStatus: ReloadStatusResponse = {
        locked: false,
        reload_in_progress: false,
        active_reload_node_id: null,
        estimated_completion_ms: null,
      };

      const promise = service.getReloadStatus();
      const req = httpMock.expectOne((r) =>
        r.method === 'GET' && r.url.endsWith('/nodes/reload/status'),
      );
      req.flush(mockStatus);

      const result = await promise;
      expect(result.locked).toBe(false);
      expect(result.reload_in_progress).toBe(false);
      expect(result.active_reload_node_id).toBeNull();
      expect(result.estimated_completion_ms).toBeNull();
    });

    it('should return locked=true with active_reload_node_id during selective reload', async () => {
      const mockStatus: ReloadStatusResponse = {
        locked: true,
        reload_in_progress: true,
        active_reload_node_id: 'a1b2c3d4',
        estimated_completion_ms: 150,
      };

      const promise = service.getReloadStatus();
      const req = httpMock.expectOne((r) => r.url.endsWith('/nodes/reload/status'));
      req.flush(mockStatus);

      const result = await promise;
      expect(result.locked).toBe(true);
      expect(result.active_reload_node_id).toBe('a1b2c3d4');
      expect(result.estimated_completion_ms).toBe(150);
    });
  });
});
