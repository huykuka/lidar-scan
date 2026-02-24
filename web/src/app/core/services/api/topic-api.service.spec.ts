import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';

import { TopicApiService } from './topic-api.service';

describe('TopicApiService', () => {
  let service: TopicApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(TopicApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('getTopics() returns topics', async () => {
    const p = service.getTopics();
    const req = httpMock.expectOne((r) => r.method === 'GET' && r.url.endsWith('/topics'));
    req.flush({ topics: ['a_raw_points', 'b_raw_points'] });
    await expect(p).resolves.toEqual(['a_raw_points', 'b_raw_points']);
  });
});
