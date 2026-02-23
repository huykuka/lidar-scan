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
    return (topic: string) => {
      return activeRecordings.some(r => r.topic === topic);
    };
  });

  /**
   * Get active recording for a specific topic
   */
  getActiveRecordingByTopic = computed(() => {
    const activeRecordings = this.activeRecordings();
    return (topic: string): ActiveRecording | undefined => {
      return activeRecordings.find(r => r.topic === topic);
    };
  });

  // Actions

  /**
   * Load all recordings, optionally filtered by topic
   */
  loadRecordings(topic?: string): Promise<void> {
    this.setState({ isLoading: true, error: null });
    return new Promise((resolve, reject) => {
      this.recordingApi.listRecordings(topic).subscribe({
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
   * Start recording a topic
   */
  startRecording(topic: string, name?: string): Observable<string> {
    return this.recordingApi.startRecording({ topic, name }).pipe(
      tap(() => {
        // Reload recordings to get updated active list
        this.loadRecordings();
      }),
      map(response => response.recording_id)
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
      })
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
          recordings: recordings.filter(r => r.id !== recordingId),
        });
      }),
      map(() => void 0)
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
