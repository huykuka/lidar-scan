import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { firstValueFrom } from 'rxjs';
import { RecordingApiService } from './recording-api.service';
import { ListRecordingsResponse, Recording } from '../../models/recording.model';

/** Mock data aligned to api-spec.md §5 */
const MOCK_RECORDING: Recording = {
  id: 'demo0001demo0001demo0001demo0001',
  name: 'demo_outdoor_scan',
  node_id: 'sensor-001',
  file_path: 'recordings/demo0001.zip',
  file_size_bytes: 5242880,
  frame_count: 150,
  duration_seconds: 15.0,
  recording_timestamp: '2026-04-01T10:00:00Z',
  metadata: { node_id: 'sensor-001', name: 'demo_outdoor_scan', recording_timestamp: '2026-04-01T10:00:00Z' },
  created_at: '2026-04-01T10:01:00Z',
};

const MOCK_LIST_RESPONSE: ListRecordingsResponse = {
  recordings: [MOCK_RECORDING],
  active_recordings: [],
};

describe('RecordingApiService — playback-related methods', () => {
  let service: RecordingApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(RecordingApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  describe('getRecordings()', () => {
    it('should exist as a method on the service', () => {
      expect(typeof service.getRecordings).toBe('function');
    });

    it('should call GET /api/v1/recordings and return ListRecordingsResponse', async () => {
      const p = firstValueFrom(service.getRecordings());
      const req = httpMock.expectOne((r) => r.method === 'GET' && r.url.endsWith('/recordings'));
      req.flush(MOCK_LIST_RESPONSE);

      const res = await p;
      expect(res).toEqual(MOCK_LIST_RESPONSE);
      expect(res.recordings.length).toBe(1);
      expect(res.active_recordings.length).toBe(0);
    });

    it('should return recordings with all required fields for playback panel', async () => {
      const p = firstValueFrom(service.getRecordings());
      const req = httpMock.expectOne((r) => r.url.endsWith('/recordings'));
      req.flush(MOCK_LIST_RESPONSE);

      const res = await p as ListRecordingsResponse;
      const rec = res.recordings[0];
      expect(rec.id).toBeDefined();
      expect(rec.name).toBeDefined();
      expect(rec.frame_count).toBeGreaterThan(0);
      expect(rec.duration_seconds).toBeGreaterThan(0);
      expect(rec.recording_timestamp).toBeDefined();
    });
  });

  describe('getRecording(id)', () => {
    it('should call GET /api/v1/recordings/{id} and return a single Recording', async () => {
      const testId = 'demo0001demo0001demo0001demo0001';
      const p = firstValueFrom(service.getRecording(testId));
      const req = httpMock.expectOne((r) => r.url.endsWith(`/recordings/${testId}`));
      expect(req.request.method).toBe('GET');
      req.flush(MOCK_RECORDING);

      const rec = await p;
      expect(rec).toEqual(MOCK_RECORDING);
      expect(rec.id).toBe(testId);
    });

    it('should include frame_count and duration_seconds for metadata display', async () => {
      const id = 'demo0001demo0001demo0001demo0001';
      const p = firstValueFrom(service.getRecording(id));
      const req = httpMock.expectOne((r) => r.url.includes(`/recordings/${id}`));
      req.flush(MOCK_RECORDING);

      const rec = await p;
      expect(rec.frame_count).toBe(150);
      expect(rec.duration_seconds).toBe(15.0);
      expect(rec.recording_timestamp).toBe('2026-04-01T10:00:00Z');
    });
  });
});
