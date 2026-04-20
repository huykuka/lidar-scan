import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {Observable} from 'rxjs';
import {environment} from '../../../../environments/environment';
import {
  ListRecordingsResponse,
  Recording,
  RecordingViewerInfo,
  StartRecordingRequest,
  StartRecordingResponse,
} from '../../models/recording.model';

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
    const params = topic ? {topic} : undefined;
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
   * Download a recording zip as a Blob
   */
  getRecordingZip(recordingId: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/${recordingId}/download`, {responseType: 'blob'});
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
}
