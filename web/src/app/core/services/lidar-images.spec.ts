import { TestBed } from '@angular/core/testing';

import { LidarImagesService } from './lidar-images';

describe('LidarImages', () => {
  let service: LidarImagesService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(LidarImagesService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
