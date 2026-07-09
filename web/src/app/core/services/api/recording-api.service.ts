import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {Observable} from 'rxjs';
import {environment} from '../../../../environments/environment';
import {AuthService} from '../auth.service';
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
  private auth = inject(AuthService);
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
   * Download a recording zip using native fetch with progress reporting.
   * Returns a Promise that resolves to the Blob.
   * onProgress callback receives 0–100 (or -1 if Content-Length is absent).
   */
  async getRecordingZip(recordingId: string, onProgress?: (pct: number) => void): Promise<Blob> {
    const url = `${this.baseUrl}/${recordingId}/download`;

    // Include auth token manually since we bypass HttpClient/interceptors
    const token = this.auth.getToken();
    const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

    const res = await fetch(url, { headers });

    if (!res.ok) {
      throw new Error(`Http failure response for ${url}: ${res.status} ${res.statusText}`);
    }

    const contentLength = res.headers.get('Content-Length');
    const total = contentLength ? parseInt(contentLength, 10) : 0;

    if (!res.body) {
      return res.blob();
    }

    const reader = res.body.getReader();
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let loaded = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.length;
      if (onProgress) {
        onProgress(total > 0 ? Math.round((loaded / total) * 100) : -1);
      }
    }

    return new Blob(chunks, { type: 'application/octet-stream' });
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
