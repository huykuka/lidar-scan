import { Injectable, inject, computed } from '@angular/core';
import { tap, map, Observable } from 'rxjs';
import { SignalsSimpleStoreService } from '../signals-simple-store.service';
import { Recording, ActiveRecording } from '../../models/recording.model';
import { RecordingApiService } from '../api/recording-api.service';

export interface RecordingState {
  recordings: Recording[];
  activeRecordings: ActiveRecording[];
  selectedRecording: Recording | null;
  isLoading: boolean;
  error: string | null;
}

const initialState: RecordingState = {
  recordings: [],
  activeRecordings: [],
  selectedRecording: null,
  isLoading: false,
  error: null,
};

@Injectable({
  providedIn: 'root',
})
export class RecordingStoreService extends SignalsSimpleStoreService<RecordingState> {
  private recordingApi = inject(RecordingApiService);

  constructor() {
    super();
    this.setState(initialState);
  }

  // Selectors
  recordings = this.select('recordings');
  activeRecordings = this.select('activeRecordings');
  selectedRecording = this.select('selectedRecording');
  isLoading = this.select('isLoading');
  error = this.select('error');

  /**
   * Check if a topic is currently recording
   */
  isRecording = computed(() => {
    const activeRecordings = this.activeRecordings();
    return (nodeId: string) => {
      return activeRecordings.some((r) => {
        return r.node_id === nodeId;
      });
    };
  });

  /**
   * Get active recording for a specific node
   */
  getActiveRecordingByNodeId = computed(() => {
    const activeRecordings = this.activeRecordings();
    return (nodeId: string): ActiveRecording | undefined => {
      return activeRecordings.find((r) => {
        return r.node_id === nodeId;
      });
    };
  });

  // Actions

  /**
   * Load all recordings, optionally filtered by node_id
   */
  loadRecordings(nodeId?: string): Promise<void> {
    this.setState({ isLoading: true, error: null });
    return new Promise((resolve, reject) => {
      this.recordingApi.listRecordings(nodeId).subscribe({
        next: (data) => {
          this.setState({
            recordings: data.recordings,
            activeRecordings: data.active_recordings,
            isLoading: false,
          });
          resolve();
        },
        error: (err) => {
          this.setState({
            error: err.message || 'Failed to load recordings',
            isLoading: false,
          });
          reject(err);
        },
      });
    });
  }

  /**
   * Start recording a node graph
   */
  startRecording(nodeId: string, name?: string): Observable<string> {
    return this.recordingApi.startRecording({ node_id: nodeId, name }).pipe(
      tap(() => {
        // Reload recordings to get updated active list
        this.loadRecordings();
      }),
      map((response) => response.recording_id),
    );
  }

  /**
   * Stop an active recording
   */
  stopRecording(recordingId: string): Observable<Recording> {
    return this.recordingApi.stopRecording(recordingId).pipe(
      tap(() => {
        // Reload recordings
        this.loadRecordings();
      }),
    );
  }

  /**
   * Delete a recording
   */
  deleteRecording(recordingId: string): Observable<void> {
    return this.recordingApi.deleteRecording(recordingId).pipe(
      tap(() => {
        // Remove from state
        const recordings = this.recordings();
        this.setState({
          recordings: recordings.filter((r) => r.id !== recordingId),
        });
      }),
      map(() => void 0),
    );
  }

  /**
   * Select a recording for detailed view
   */
  selectRecording(recording: Recording | null): void {
    this.setState({ selectedRecording: recording });
  }

  /**
   * Clear error message
   */
  clearError(): void {
    this.setState({ error: null });
  }
}
