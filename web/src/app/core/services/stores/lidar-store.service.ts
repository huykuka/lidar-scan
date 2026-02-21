import { Injectable } from '@angular/core';
import { SignalsSimpleStoreService } from '../signals-simple-store.service';
import { LidarConfig } from '../../models/lidar.model';

export interface LidarState {
  lidars: LidarConfig[];
  availablePipelines: string[];
  isLoading: boolean;
  selectedLidar: Partial<LidarConfig>;
  editMode: boolean;
}

const initialState: LidarState = {
  lidars: [],
  availablePipelines: [],
  isLoading: false,
  selectedLidar: {},
  editMode: false,
};

@Injectable({
  providedIn: 'root',
})
export class LidarStoreService extends SignalsSimpleStoreService<LidarState> {
  constructor() {
    super();
    this.setState(initialState);
  }

  lidars = this.select('lidars');
  availablePipelines = this.select('availablePipelines');
  isLoading = this.select('isLoading');
  selectedLidar = this.select('selectedLidar');
  editMode = this.select('editMode');
}
