import { Injectable, effect } from '@angular/core';
import { SignalsSimpleStoreService } from '../signals-simple-store.service';

export interface WorkspaceState {
  topics: string[];
  currentTopic: string;
  isConnected: boolean;
  pointCount: number;
  pointSize: number;
  pointColor: string;
  fps: number;
  lidarTime: string;
  showHud: boolean;
  showCockpit: boolean;
}

const initialState: WorkspaceState = {
  topics: [],
  currentTopic: '',
  isConnected: false,
  pointCount: 0,
  pointSize: 0.1,
  pointColor: '#00ff00',
  fps: 0,
  lidarTime: '--:--:--',
  showHud: true,
  showCockpit: true,
};

@Injectable({
  providedIn: 'root',
})
export class WorkspaceStoreService extends SignalsSimpleStoreService<WorkspaceState> {
  private readonly STORAGE_KEY = 'lidar_workspace_settings';

  constructor() {
    super();

    // 1. Load initial state
    const saved = localStorage.getItem(this.STORAGE_KEY);
    const persistedState = saved ? JSON.parse(saved) : {};

    this.setState({
      ...initialState,
      ...persistedState,
      isConnected: false, // Don't persist connection status
      topics: [], // Don't persist topics
    });

    // 2. Setup persistence effect
    effect(() => {
      const state = this.state();
      const settingsToSave = {
        pointSize: state.pointSize,
        pointColor: state.pointColor,
        showHud: state.showHud,
        showCockpit: state.showCockpit,
        currentTopic: state.currentTopic,
      };
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(settingsToSave));
    });
  }

  // Helper selectors
  currentTopic = this.select('currentTopic');
  topics = this.select('topics');
  isConnected = this.select('isConnected');
  pointCount = this.select('pointCount');
  pointSize = this.select('pointSize');
  pointColor = this.select('pointColor');
  fps = this.select('fps');
  lidarTime = this.select('lidarTime');
  showHud = this.select('showHud');
  showCockpit = this.select('showCockpit');
}
