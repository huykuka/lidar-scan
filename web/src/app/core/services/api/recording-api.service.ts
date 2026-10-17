import {inject, Injectable} from '@angular/core';
import {HttpClient, HttpEvent} from '@angular/common/http';
import {Observable} from 'rxjs';
import {environment} from '../../../../environments/environment';
import {
  ListRecordingsResponse,
  RecordingsPageQuery,
  Recording,
  RecordingViewerInfo,
  StartRecordingRequest,
  StartRecordingResponse,
  TrimRecordingRequest,
} from '../../models/recording.model';

export interface BlobStorageStatus {
  configured: boolean;
  authenticated: boolean;
  /** configured AND credentials valid */
  available: boolean;
  bucket: string | null;
  reason: string | null;
}

@Injectable({
  providedIn: 'root',
})
export class RecordingApiService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/recordings`;

  /**
   * Start recording a topic
   */
  startRecording(request: StartRecordingRequest): Observable<StartRecordingResponse> {
    return this.http.post<StartRecordingResponse>(`${this.baseUrl}/start`, request);
  }

  /**
   * Stop an active recording
   */
  stopRecording(recordingId: string): Observable<Recording> {
    return this.http.post<Recording>(`${this.baseUrl}/${recordingId}/stop`, {});
  }

  /**
   * List all recordings, optionally filtered by topic
   */
  listRecordings(topic?: string): Observable<ListRecordingsResponse> {
    const params = topic ? { topic } : undefined;
    return this.http.get<ListRecordingsResponse>(this.baseUrl, { params });
  }

  /** One page of recordings (newest first) with optional server-side search. */
  listRecordingsPage(query: RecordingsPageQuery): Observable<ListRecordingsResponse> {
    const params: Record<string, string | number> = {limit: query.limit, offset: query.offset};
    if (query.q) params['q'] = query.q;
    return this.http.get<ListRecordingsResponse>(this.baseUrl, {params});
  }

  /**
   * List all completed recordings for the playback config panel.
   * Alias for listRecordings() with no filter — consumers should use
   * the `recordings[]` array only (exclude `active_recordings`).
   */
  getRecordings(): Observable<ListRecordingsResponse> {
    return this.http.get<ListRecordingsResponse>(this.baseUrl);
  }

  /**
   * Get a specific recording by ID
   */
  getRecording(recordingId: string): Observable<Recording> {
    return this.http.get<Recording>(`${this.baseUrl}/${recordingId}`);
  }

  /**
   * Delete a recording
   */
  deleteRecording(recordingId: string): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.baseUrl}/${recordingId}`);
  }

  /**
   * Rename a recording
   */
  renameRecording(recordingId: string, name: string): Observable<Recording> {
    return this.http.patch<Recording>(`${this.baseUrl}/${recordingId}/rename`, { name });
  }

  /**
   * Download a recording file via browser download
   */
  downloadRecording(recordingId: string, filename: string): void {
    const url = `${this.baseUrl}/${recordingId}/download`;

    // Use window location to trigger browser download
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  /**
   * Get recording info for viewer (frame count, metadata)
   */
  getRecordingInfo(recordingId: string): Observable<RecordingViewerInfo> {
    return this.http.get<RecordingViewerInfo>(`${this.baseUrl}/${recordingId}/info`);
  }

  /**
   * Get a specific frame as PCD data
   */
  getFrameAsPcd(recordingId: string, frameIndex: number): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/${recordingId}/frame/${frameIndex}`, {
      responseType: 'blob',
    });
  }

  /**
   * Upload a recording ZIP file and import it into the library.
   * Reports upload progress via HttpClient reportProgress.
   */
  uploadRecording(file: File, name?: string): Observable<Recording> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    if (name) {
      formData.append('name', name);
    }
    return this.http.post<Recording>(`${this.baseUrl}/upload`, formData);
  }

  /** Same as uploadRecording but emits HttpEvents (upload progress + final response). */
  uploadRecordingWithProgress(file: File): Observable<HttpEvent<Recording>> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post<Recording>(`${this.baseUrl}/upload`, formData, {
      observe: 'events',
      reportProgress: true,
    });
  }

  /**
   * Trim a recording to the given half-open frame range [start_frame, end_frame).
   * Creates a NEW recording; original is untouched.
   */
  trimRecording(recordingId: string, body: TrimRecordingRequest): Observable<Recording> {
    return this.http.post<Recording>(`${this.baseUrl}/${recordingId}/trim`, body);
  }

  /** Service role only: is S3-compatible blob storage configured with valid credentials? */
  getBlobStorageStatus(): Observable<BlobStorageStatus> {
    return this.http.get<BlobStorageStatus>(`${this.baseUrl}/blob-storage/status`);
  }

  /** Service role only: queue a background upload (202). Outcome lands in metadata.blob_upload. */
  uploadToBlobStorage(recordingId: string): Observable<{recording_id: string; status: 'queued'}> {
    return this.http.post<{recording_id: string; status: 'queued'}>(`${this.baseUrl}/${recordingId}/blob-upload`, {});
  }

  /** Service role only: cancel a queued or running blob upload. */
  cancelBlobUpload(recordingId: string): Observable<{recording_id: string; status: 'cancelled'}> {
    return this.http.post<{recording_id: string; status: 'cancelled'}>(
      `${this.baseUrl}/${recordingId}/blob-upload/cancel`,
      {},
    );
  }
}
