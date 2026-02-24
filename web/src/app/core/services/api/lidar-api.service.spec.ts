import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';

import { LidarApiService } from './lidar-api.service';
import { LidarStoreService } from '../stores/lidar-store.service';

describe('LidarApiService', () => {
  let service: LidarApiService;
  let httpMock: HttpTestingController;
  let store: LidarStoreService;

  beforeEach(() => {
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
    const p = service.getLidars();

    const req = httpMock.expectOne((r) => r.method === 'GET' && r.url.endsWith('/lidars'));
    req.flush({
      lidars: [{ id: 'a', name: 'A', launch_args: '', mode: 'real' }],
      available_pipelines: ['none'],
    });

    const res = await p;
    expect(res.lidars.length).toBe(1);
    expect(store.lidars().length).toBe(1);
    expect(store.availablePipelines()).toEqual(['none']);
  });

  it('setEnabled() calls enabled endpoint', async () => {
    const p = service.setEnabled('sensor-1', false);
    const req = httpMock.expectOne((r) => r.method === 'POST' && r.url.includes('/lidars/') && r.url.includes('/enabled'));
    expect(req.request.url).toContain('/lidars/');
    expect(req.request.urlWithParams).toContain('enabled=false');
    req.flush({ status: 'success' });
    await p;
  });
});
