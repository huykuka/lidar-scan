import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';

import { SystemStatusService } from './system-status.service';
import { ToastService } from './toast.service';

describe('SystemStatusService', () => {
  let service: SystemStatusService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ToastService,
          useValue: {
            primary: () => {},
            success: () => {},
            neutral: () => {},
            warning: () => {},
            danger: () => {},
          },
        },
      ],
    });
    service = TestBed.inject(SystemStatusService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('refreshNow() hits /status and sets online state', () => {
    service.refreshNow();
    const req = httpMock.expectOne((r) => r.method === 'GET' && r.url.endsWith('/status'));
    req.flush({ is_running: true, active_sensors: ['a'], version: '1.0.0' });
    expect(service.backendOnline()).toBe(true);
    expect(service.backendVersion()).toBe('1.0.0');
    expect(service.activeSensors()).toEqual(['a']);
  });

  it('refreshNow() sets offline on error', () => {
    service.refreshNow();
    const req = httpMock.expectOne((r) => r.method === 'GET' && r.url.endsWith('/status'));
    req.error(new ProgressEvent('error'));
    expect(service.backendOnline()).toBe(false);
    expect(service.backendVersion()).toBe(null);
    expect(service.activeSensors()).toEqual([]);
  });
});
