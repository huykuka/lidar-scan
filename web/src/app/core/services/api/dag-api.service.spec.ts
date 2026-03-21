import { TestBed } from '@angular/core/testing';

import { DagApiService } from './dag-api.service';

describe('DagApiService', () => {
  let service: DagApiService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(DagApiService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
