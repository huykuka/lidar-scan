import {TestBed} from '@angular/core/testing';
import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {firstValueFrom} from 'rxjs';
import {RecordingApiService} from './recording-api.service';
import {ListRecordingsResponse, Recording, TrimRecordingRequest} from '../../models/recording.model';

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

describe('RecordingApiService — trimRecording()', () => {
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

  const MOCK_TRIMMED: Recording = {
    id: 'trimmed-id-00000001',
    name: 'demo_outdoor_scan_trimmed',
    node_id: 'sensor-001',
    file_path: 'recordings/trimmed-id-00000001.zip',
    file_size_bytes: 1048576,
    frame_count: 50,
    duration_seconds: 5.0,
    recording_timestamp: '2026-04-01T10:00:00Z',
    metadata: { node_id: 'sensor-001', name: 'demo_outdoor_scan_trimmed', recording_timestamp: '2026-04-01T10:00:00Z' },
    created_at: '2026-04-01T10:01:00Z',
  };

  it('POSTs to /recordings/{id}/trim with exact body', async () => {
    const body: TrimRecordingRequest = { start_frame: 10, end_frame: 60, name: null };
    const p = firstValueFrom(service.trimRecording('demo0001demo0001demo0001demo0001', body));

    const req = httpMock.expectOne((r) =>
      r.method === 'POST' && r.url.endsWith('/recordings/demo0001demo0001demo0001demo0001/trim'),
    );
    expect(req.request.body).toEqual({ start_frame: 10, end_frame: 60, name: null });
    req.flush(MOCK_TRIMMED);

    const result = await p;
    expect(result.id).toBe('trimmed-id-00000001');
    expect(result.frame_count).toBe(50);
  });

  it('returns the new Recording on success', async () => {
    const body: TrimRecordingRequest = { start_frame: 0, end_frame: 100, name: null };
    const p = firstValueFrom(service.trimRecording('demo0001demo0001demo0001demo0001', body));

    const req = httpMock.expectOne((r) => r.url.includes('/trim'));
    req.flush(MOCK_TRIMMED);

    const result = await p;
    expect(result).toEqual(MOCK_TRIMMED);
  });
});
