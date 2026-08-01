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

  it('calibrateFromImu() calls calibrate endpoint', async () => {
    const mockResponse = {
      success: true,
      node_id: 'sensor-1',
      pose: { x: 0, y: 0, z: 0, roll: 1.5, pitch: -0.8, yaw: 0 },
      imu: null,
    };
    const p = service.calibrateFromImu('sensor-1');
    const req = httpMock.expectOne(
      (r) => r.method === 'POST' && r.url.includes('/lidar/sensor-1/calibrate-from-imu'),
    );
    req.flush(mockResponse);
    const res = await p;
    expect(res.success).toBe(true);
    expect(res.pose.roll).toBe(1.5);
  });

  it('getImuStatus() calls imu-status endpoint', async () => {
    const mockResponse = {
      node_id: 'sensor-1',
      imu_auto_level: false,
      has_imu_data: true,
      imu: { timestamp: 123, orientation: { x: 0, y: 0, z: 0, w: 1 }, angular_velocity: { x: 0, y: 0, z: 0 }, linear_acceleration: { x: 0, y: 0, z: -9.81 } },
    };
    const p = service.getImuStatus('sensor-1');
    const req = httpMock.expectOne(
      (r) => r.method === 'GET' && r.url.includes('/lidar/sensor-1/imu-status'),
    );
    req.flush(mockResponse);
    const res = await p;
    expect(res.has_imu_data).toBe(true);
    expect(res.imu_auto_level).toBe(false);
  });
});
