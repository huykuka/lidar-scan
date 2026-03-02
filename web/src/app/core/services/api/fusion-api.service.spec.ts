import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';

import { FusionApiService } from './fusion-api.service';
import { FusionStoreService } from '../stores/fusion-store.service';

describe('FusionApiService', () => {
  let service: FusionApiService;
  let httpMock: HttpTestingController;
  let store: FusionStoreService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(FusionApiService);
    httpMock = TestBed.inject(HttpTestingController);
    store = TestBed.inject(FusionStoreService);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('getFusions() updates store', async () => {
    const p = service.getFusions();

    const reqNodes = httpMock.expectOne((r) => r.method === 'GET' && r.url.endsWith('/nodes'));
    reqNodes.flush([
      {
        id: 'f1',
        name: 'F1',
        type: 'fusion',
        category: 'Processing',
        config: { topic: 'fused_points', sensor_ids: [] },
      },
    ]);

    const res = await p;
    expect(res.fusions.length).toBe(1);
    expect(store.fusions().length).toBe(1);
  });

  it('setEnabled() calls enabled endpoint', async () => {
    const p = service.setEnabled('fusion-1', true);
    const req = httpMock.expectOne(
      (r) => r.method === 'PUT' && r.url.includes('/nodes/') && r.url.includes('/enabled'),
    );
    expect(req.request.body).toEqual({ enabled: true });
    req.flush({ status: 'success' });
    await p;
  });
});
