import { TestBed } from '@angular/core/testing';

import { LidarImages } from './lidar-images';

describe('LidarImages', () => {
  let service: LidarImages;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(LidarImages);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
