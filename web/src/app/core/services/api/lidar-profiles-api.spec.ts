import { TestBed } from '@angular/core/testing';

import { LidarProfilesApi } from './lidar-profiles-api';

describe('LidarProfilesApi', () => {
  let service: LidarProfilesApi;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(LidarProfilesApi);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
