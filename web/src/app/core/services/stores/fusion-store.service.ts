import { Injectable } from '@angular/core';
import { SignalsSimpleStoreService } from '../signals-simple-store.service';
import { FusionConfig } from '../../models/fusion.model';

export interface FusionState {
  fusions: FusionConfig[];
  isLoading: boolean;
  selectedFusion: Partial<FusionConfig>;
  editMode: boolean;
}

const initialState: FusionState = {
  fusions: [],
  isLoading: false,
  selectedFusion: {},
  editMode: false,
};

@Injectable({
  providedIn: 'root',
})
export class FusionStoreService extends SignalsSimpleStoreService<FusionState> {
  constructor() {
    super();
    this.setState(initialState);
  }

  fusions = this.select('fusions');
  isLoading = this.select('isLoading');
  selectedFusion = this.select('selectedFusion');
  editMode = this.select('editMode');
}
