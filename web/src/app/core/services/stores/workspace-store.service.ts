import { Injectable, effect } from '@angular/core';
import { SignalsSimpleStoreService } from '../signals-simple-store.service';

export interface TopicConfig {
  topic: string;
  color: string;
  enabled: boolean;
}

export interface WorkspaceState {
  topics: string[];
  currentTopic: string; // Deprecated - kept for backwards compatibility
  selectedTopics: TopicConfig[]; // New: Multiple topics with colors
  isConnected: boolean;
  pointCount: number;
  pointSize: number;
  pointColor: string; // Deprecated - kept for backwards compatibility
  fps: number;
  lidarTime: string;
  showHud: boolean;
  showGrid: boolean;
  showAxes: boolean;
  showCockpit: boolean;
}

// Predefined colors for multiple point clouds
export const DEFAULT_TOPIC_COLORS = [
  '#00ff00', // Lime green
  '#ff0000', // Red
  '#0080ff', // Blue
  '#ffff00', // Yellow
  '#ff00ff', // Magenta
  '#00ffff', // Cyan
  '#ff8000', // Orange
  '#8000ff', // Purple
];

const initialState: WorkspaceState = {
  topics: [],
  currentTopic: '',
  selectedTopics: [],
  isConnected: false,
  pointCount: 0,
  pointSize: 0.1,
  pointColor: '#00ff00',
  fps: 0,
  lidarTime: '--:--:--',
  showHud: true,
  showGrid: true,
  showAxes: true,
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
      selectedTopics: persistedState.selectedTopics || [], // Persist topic selections
    });

    // 2. Setup persistence effect
    effect(() => {
      const state = this.state();
      const settingsToSave = {
        pointSize: state.pointSize,
        pointColor: state.pointColor,
        showHud: state.showHud,
        showGrid: state.showGrid,
        showAxes: state.showAxes,
        showCockpit: state.showCockpit,
        currentTopic: state.currentTopic,
        selectedTopics: state.selectedTopics,
      };
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(settingsToSave));
    });
  }

  // Helper selectors
  currentTopic = this.select('currentTopic');
  topics = this.select('topics');
  selectedTopics = this.select('selectedTopics');
  isConnected = this.select('isConnected');
  pointCount = this.select('pointCount');
  pointSize = this.select('pointSize');
  pointColor = this.select('pointColor');
  fps = this.select('fps');
  lidarTime = this.select('lidarTime');
  showHud = this.select('showHud');
  showGrid = this.select('showGrid');
  showAxes = this.select('showAxes');
  showCockpit = this.select('showCockpit');

  // Helper methods for managing selected topics
  addTopic(topic: string) {
    const current = this.getValue('selectedTopics');
    if (current.find((t) => t.topic === topic)) return; // Already added

    const colorIndex = current.length % DEFAULT_TOPIC_COLORS.length;
    const newTopic: TopicConfig = {
      topic,
      color: DEFAULT_TOPIC_COLORS[colorIndex],
      enabled: true,
    };
    this.set('selectedTopics', [...current, newTopic]);
  }

  removeTopic(topic: string) {
    const current = this.getValue('selectedTopics');
    this.set(
      'selectedTopics',
      current.filter((t) => t.topic !== topic),
    );
  }

  toggleTopicEnabled(topic: string) {
    const current = this.getValue('selectedTopics');
    this.set(
      'selectedTopics',
      current.map((t) => (t.topic === topic ? { ...t, enabled: !t.enabled } : t)),
    );
  }

  updateTopicColor(topic: string, color: string) {
    const current = this.getValue('selectedTopics');
    this.set(
      'selectedTopics',
      current.map((t) => (t.topic === topic ? { ...t, color } : t)),
    );
  }
}

