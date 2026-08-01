import {TestBed} from '@angular/core/testing';
import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';

import {NodesApiService} from './nodes-api.service';

describe('NodesApiService', () => {
  let service: NodesApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(NodesApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('calibrateFromFloor() calls the neutral node endpoint', async () => {
    const mockResponse = {
      success: true,
      node_id: 'sensor-1',
      pose: {x: 0, y: 0, z: 0, roll: 2.1, pitch: -1.3, yaw: 0},
    };
    const p = service.calibrateFromFloor('sensor-1');
    const req = httpMock.expectOne(
      (r) => r.method === 'POST' && r.url.includes('/nodes/sensor-1/calibrate-from-floor'),
    );
    req.flush(mockResponse);
    const res = await p;
    expect(res.success).toBe(true);
    expect(res.pose.pitch).toBe(-1.3);
  });
});
