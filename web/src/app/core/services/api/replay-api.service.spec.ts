import {TestBed} from '@angular/core/testing';
import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {firstValueFrom} from 'rxjs';
import {environment} from '@env/environment';
import {ReplayApiService} from './replay-api.service';

describe('ReplayApiService', () => {
  let service: ReplayApiService;
  let http: HttpTestingController;
  const base = `${environment.apiUrl}/replays`;

  beforeEach(() => {
    TestBed.configureTestingModule({providers: [provideHttpClient(), provideHttpClientTesting()]});
    service = TestBed.inject(ReplayApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('POSTs a start request', async () => {
    const body = {recording_id: 'r1', playback_node_id: 'pb', overrides: {ds: {k: 2}}};
    const p = firstValueFrom(service.startReplay(body));
    const req = http.expectOne(base);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(body);
    req.flush({id: 'run1'});
    expect((await p).id).toBe('run1');
  });

  it('filters list by recording id', async () => {
    const p = firstValueFrom(service.listReplays('r1'));
    const req = http.expectOne((r) => r.url === base && r.params.get('recording_id') === 'r1');
    req.flush({runs: [], total: 0});
    expect((await p).total).toBe(0);
  });

  it('compares two runs with a and b params', async () => {
    const p = firstValueFrom(service.compare('a1', 'b1'));
    const req = http.expectOne(
      (r) => r.url === `${base}/compare` && r.params.get('a') === 'a1' && r.params.get('b') === 'b1',
    );
    req.flush({summary: {identical: true}});
    expect((await p).summary.identical).toBe(true);
  });

  it('cancels and deletes runs', () => {
    service.cancelReplay('x').subscribe();
    expect(http.expectOne(`${base}/x/cancel`).request.method).toBe('POST');
    service.deleteReplay('x').subscribe();
    expect(http.expectOne(`${base}/x`).request.method).toBe('DELETE');
  });
});
