import {computed, inject, Injectable} from '@angular/core';
import {map, Observable, tap} from 'rxjs';
import {SignalsSimpleStoreService} from '../signals-simple-store.service';
import {ActiveRecording, BlobUploadState, Recording} from '../../models/recording.model';
import {ToastService} from '../toast.service';
import {RecordingApiService} from '../api/recording-api.service';

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
  private recordingApi = inject(RecordingApiService);
  private toast = inject(ToastService);

  constructor() {
    super();
    this.setState(initialState);
  }

  // Actions

  /**
   * Load all recordings, optionally filtered by node_id
   */
  loadRecordings(nodeId?: string): Promise<void> {
    this.setState({isLoading: true, error: null});
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
    return this.recordingApi.startRecording({node_id: nodeId, name}).pipe(
      tap(() => {
        // Reload recordings to get updated active list
        this.loadRecordings();
      }),
      map((response) => response.recording_id),
    );
  }

  /** Patch a recording's blob-upload state in place (pushed over the WebSocket). */
  applyBlobUpload(recordingId: string, blobUpload: BlobUploadState | null): void {
    const prev = this.recordings().find((r) => r.id === recordingId);
    const prevStatus = prev?.metadata?.blob_upload?.status;
    if (prev && blobUpload && (prevStatus === 'queued' || prevStatus === 'uploading')) {
      if (blobUpload.status === 'uploaded') {
        this.toast.success(`Uploaded ${prev.name} to ${blobUpload.bucket}`);
      } else if (blobUpload.status === 'failed') {
        this.toast.danger(`Upload of ${prev.name} failed: ${blobUpload.error ?? 'unknown error'}`, 6000);
      }
    }
    this.setState({
      recordings: this.recordings().map((r) =>
        r.id === recordingId ? {...r, metadata: {...r.metadata, blob_upload: blobUpload ?? undefined}} : r,
      ),
    });
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
    this.setState({selectedRecording: recording});
  }

  /**
   * Clear error message
   */
  clearError(): void {
    this.setState({error: null});
  }
}
