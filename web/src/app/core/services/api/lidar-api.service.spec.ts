import {TestBed} from '@angular/core/testing';
import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';

import {LidarApiService} from './lidar-api.service';
import {LidarStoreService} from '../stores/lidar-store.service';

describe('LidarApiService', () => {
  let service: LidarApiService;
  let httpMock: HttpTestingController;
  let store: LidarStoreService;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(LidarApiService);
    httpMock = TestBed.inject(HttpTestingController);
    store = TestBed.inject(LidarStoreService);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('getLidars() updates store', async () => {
    // getLidars() uses sequential awaits: first /nodes, then /nodes/pipelines.
    // Start the call but do NOT await — we need to flush requests as they arrive.
    const p = service.getLidars();

    // Microtask tick: let the first `await firstValueFrom(http.get('/nodes'))` register its request
    await Promise.resolve();

    // Only /nodes is pending at this point (sequential await)
    const reqNodes = httpMock.expectOne(
      (r) => r.method === 'GET' && r.url.endsWith('/nodes') && !r.url.endsWith('/nodes/pipelines'),
    );
    reqNodes.flush([
      {
        id: 'a',
        name: 'A',
        type: 'sensor',
        category: 'Input',
        enabled: true,
        config: {hostname: '', mode: 'real'},
      },
    ]);

    // Allow the second await to fire
    await Promise.resolve();

    const reqPipelines = httpMock.expectOne(
      (r) => r.method === 'GET' && r.url.endsWith('/nodes/pipelines'),
    );
    reqPipelines.flush({pipelines: ['none']});

    const res = await p;
    expect(res.lidars.length).toBe(1);
    expect(store.lidars().length).toBe(1);
    expect(store.availablePipelines()).toEqual(['none']);
  });

  it('setEnabled() calls enabled endpoint', async () => {
    const p = service.setEnabled('sensor-1', false);
    const req = httpMock.expectOne(
      (r) => r.method === 'PUT' && r.url.includes('/nodes/') && r.url.includes('/enabled'),
    );
    expect(req.request.url).toContain('/nodes/');
    expect(req.request.body).toEqual({enabled: false});
    req.flush({status: 'success'});
    await p;
  });
});
