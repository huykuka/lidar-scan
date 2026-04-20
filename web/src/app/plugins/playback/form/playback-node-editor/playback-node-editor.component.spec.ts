import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { PlaybackNodeEditorComponent } from './playback-node-editor.component';
import { RecordingApiService } from '@core/services/api/recording-api.service';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { NodeEditorFacadeService } from '@features/settings/services/node-editor-facade.service';
import { NodeConfig } from '@core/models/node.model';
import { ListRecordingsResponse, Recording } from '@core/models/recording.model';
import { PLAYBACK_SPEED_OPTIONS } from '@plugins/playback/playback.model';

// ── Mock data (api-spec.md §5) ──────────────────────────────────────────────
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

const MOCK_RECORDING_2: Recording = {
  id: 'rec2000rec2000rec2000rec2000rec20',
  name: 'indoor_lab_scan',
  node_id: 'sensor-002',
  file_path: 'recordings/rec2000.zip',
  file_size_bytes: 2097152,
  frame_count: 60,
  duration_seconds: 6.0,
  recording_timestamp: '2026-04-02T08:00:00Z',
  metadata: { node_id: 'sensor-002', name: 'indoor_lab_scan', recording_timestamp: '2026-04-02T08:00:00Z' },
  created_at: '2026-04-02T08:01:00Z',
};

const MOCK_LIST: ListRecordingsResponse = {
  recordings: [MOCK_RECORDING, MOCK_RECORDING_2],
  active_recordings: [],
};

const MOCK_EMPTY_LIST: ListRecordingsResponse = {
  recordings: [],
  active_recordings: [],
};

const MOCK_NODE: NodeConfig = {
  id: 'node-playback-001',
  name: 'Playback',
  type: 'playback',
  category: 'sensor',
  enabled: true,
  config: {
    recording_id: '',
    playback_speed: 1.0,
    loopable: false,
    throttle_ms: 0,
  },
  x: 100,
  y: 100,
};

// ── Test Suite ───────────────────────────────────────────────────────────────
describe('PlaybackNodeEditorComponent', () => {
  let component: PlaybackNodeEditorComponent;
  let fixture: ComponentFixture<PlaybackNodeEditorComponent>;
  let mockRecordingApi: ReturnType<typeof buildMockApi>;
  let mockNodeStore: ReturnType<typeof buildMockStore>;
  let mockFacade: { saveNode: ReturnType<typeof vi.fn> };

  function buildMockApi() {
    return {
      getRecordings: vi.fn().mockReturnValue(of(MOCK_LIST)),
      getRecording: vi.fn().mockReturnValue(of(MOCK_RECORDING)),
    };
  }

  function buildMockStore(nodeOverride: Partial<NodeConfig> = {}) {
    return {
      selectedNode: signal<NodeConfig>({ ...MOCK_NODE, ...nodeOverride }),
      nodeDefinitions: signal([]),
      setState: vi.fn(),
    };
  }

  async function createComponent(
    apiOverride?: Partial<ReturnType<typeof buildMockApi>>,
    nodeOverride?: Partial<NodeConfig>,
  ) {
    mockRecordingApi = { ...buildMockApi(), ...apiOverride };
    mockNodeStore = buildMockStore(nodeOverride);
    mockFacade = { saveNode: vi.fn().mockResolvedValue(true) };

    await TestBed.configureTestingModule({
      imports: [PlaybackNodeEditorComponent],
      providers: [
        { provide: RecordingApiService, useValue: mockRecordingApi },
        { provide: NodeStoreService, useValue: mockNodeStore },
      ],
    })
      .overrideComponent(PlaybackNodeEditorComponent, {
        set: {
          providers: [{ provide: NodeEditorFacadeService, useValue: mockFacade }],
        },
      })
      .compileComponents();

    fixture = TestBed.createComponent(PlaybackNodeEditorComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    // Let effect() run
    await fixture.whenStable();
    fixture.detectChanges();
  }

  // ── Creation ────────────────────────────────────────────────────────────────
  describe('creation', () => {
    it('should create', async () => {
      await createComponent();
      expect(component).toBeTruthy();
    });

    it('should call getRecordings() on init', async () => {
      await createComponent();
      expect(mockRecordingApi.getRecordings).toHaveBeenCalledOnce();
    });
  });

  // ── Recordings dropdown population ──────────────────────────────────────────
  describe('recordings signal', () => {
    it('should populate recordings from getRecordings() response', async () => {
      await createComponent();
      expect(component['recordings']().length).toBe(2);
    });

    it('should contain only completed recordings (active_recordings excluded)', async () => {
      const listWithActive: ListRecordingsResponse = {
        recordings: [MOCK_RECORDING],
        active_recordings: [{ recording_id: 'active-001', node_id: 'n', frame_count: 10, duration_seconds: 1, started_at: '' }],
      };
      await createComponent({ getRecordings: vi.fn().mockReturnValue(of(listWithActive)) });
      // active_recordings should NOT appear in the recordings signal
      expect(component['recordings']().length).toBe(1);
    });

    it('should set recordings to empty array when no recordings exist', async () => {
      await createComponent({ getRecordings: vi.fn().mockReturnValue(of(MOCK_EMPTY_LIST)) });
      expect(component['recordings']().length).toBe(0);
    });

    it('should handle getRecordings() error gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      await createComponent({ getRecordings: vi.fn().mockReturnValue(throwError(() => new Error('Network error'))) });
      expect(component['recordings']().length).toBe(0);
      consoleSpy.mockRestore();
    });
  });

  // ── Speed options ────────────────────────────────────────────────────────────
  describe('speed options', () => {
    it('should expose PLAYBACK_SPEED_OPTIONS', async () => {
      await createComponent();
      expect(component['speedOptions']).toEqual(PLAYBACK_SPEED_OPTIONS);
    });

    it('should default playbackSpeed signal to 1.0', async () => {
      await createComponent();
      expect(component['playbackSpeed']()).toBe(1.0);
    });

    it('should only accept values from PLAYBACK_SPEED_OPTIONS (no > 1.0)', async () => {
      await createComponent();
      const validValues = PLAYBACK_SPEED_OPTIONS.map((o) => o.value);
      expect(validValues.every((v) => v <= 1.0)).toBe(true);
    });

    it('should reset to 1.0 and warn if an invalid speed is set', async () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      await createComponent();
      // Simulate an invalid speed being injected (e.g. stale config from backend)
      component['setPlaybackSpeed'](2.0 as any);
      expect(component['playbackSpeed']()).toBe(1.0);
      expect(warnSpy).toHaveBeenCalled();
      warnSpy.mockRestore();
    });
  });

  // ── Loopable toggle ─────────────────────────────────────────────────────────
  describe('loopable toggle', () => {
    it('should default loopable signal to false', async () => {
      await createComponent();
      expect(component['loopable']()).toBe(false);
    });

    it('should toggle loopable signal', async () => {
      await createComponent();
      component['toggleLoopable']();
      expect(component['loopable']()).toBe(true);
      component['toggleLoopable']();
      expect(component['loopable']()).toBe(false);
    });
  });

  // ── Recording selection + metadata ──────────────────────────────────────────
  describe('recording selection', () => {
    it('should call getRecording(id) when a recording is selected', async () => {
      await createComponent();
      component['onRecordingSelect']('demo0001demo0001demo0001demo0001');
      expect(mockRecordingApi.getRecording).toHaveBeenCalledWith('demo0001demo0001demo0001demo0001');
    });

    it('should populate selectedRecording signal after selection', async () => {
      await createComponent();
      component['onRecordingSelect']('demo0001demo0001demo0001demo0001');
      await fixture.whenStable();
      expect(component['selectedRecording']()).toEqual(MOCK_RECORDING);
    });

    it('should update recordingId signal to the selected id', async () => {
      await createComponent();
      component['onRecordingSelect']('demo0001demo0001demo0001demo0001');
      expect(component['recordingId']()).toBe('demo0001demo0001demo0001demo0001');
    });

    it('should clear selectedRecording when empty id is selected', async () => {
      await createComponent();
      component['onRecordingSelect']('demo0001demo0001demo0001demo0001');
      await fixture.whenStable();
      component['onRecordingSelect']('');
      await fixture.whenStable();
      expect(component['selectedRecording']()).toBeNull();
    });
  });

  // ── Config output ────────────────────────────────────────────────────────────
  describe('config output (PlaybackConfig)', () => {
    it('should emit correct PlaybackConfig on save', async () => {
      await createComponent();
      component['onRecordingSelect']('demo0001demo0001demo0001demo0001');
      await fixture.whenStable();

      const savedEvents: any[] = [];
      component.saved.subscribe(() => savedEvents.push(true));

      await component.onSave();

      expect(mockFacade.saveNode).toHaveBeenCalled();
      const payload = mockFacade.saveNode.mock.calls[0][0];
      expect(payload.config).toEqual({
        recording_id: 'demo0001demo0001demo0001demo0001',
        playback_speed: 1.0,
        loopable: false,
        throttle_ms: 0,
      });
    });

    it('should include updated loopable in config', async () => {
      await createComponent();
      component['onRecordingSelect']('demo0001demo0001demo0001demo0001');
      component['toggleLoopable']();
      await component.onSave();

      const payload = mockFacade.saveNode.mock.calls[0][0];
      expect(payload.config.loopable).toBe(true);
    });

    it('should include updated playback_speed in config', async () => {
      await createComponent();
      component['onRecordingSelect']('demo0001demo0001demo0001demo0001');
      component['setPlaybackSpeed'](0.5);
      await component.onSave();

      const payload = mockFacade.saveNode.mock.calls[0][0];
      expect(payload.config.playback_speed).toBe(0.5);
    });

    it('should not call saveNode when recording_id is empty', async () => {
      await createComponent();
      // No recording selected
      await component.onSave();
      expect(mockFacade.saveNode).not.toHaveBeenCalled();
    });
  });

  // ── Pre-populate from existing node config ────────────────────────────────
  describe('pre-population from existing node config', () => {
    it('should pre-populate recordingId from node config', async () => {
      await createComponent(
        { getRecording: vi.fn().mockReturnValue(of(MOCK_RECORDING)) },
        { config: { recording_id: 'demo0001demo0001demo0001demo0001', playback_speed: 0.5, loopable: true, throttle_ms: 0 } },
      );
      expect(component['recordingId']()).toBe('demo0001demo0001demo0001demo0001');
    });

    it('should pre-populate playbackSpeed from node config', async () => {
      await createComponent(
        {},
        { config: { recording_id: '', playback_speed: 0.25, loopable: false, throttle_ms: 0 } },
      );
      expect(component['playbackSpeed']()).toBe(0.25);
    });

    it('should pre-populate loopable from node config', async () => {
      await createComponent(
        {},
        { config: { recording_id: '', playback_speed: 1.0, loopable: true, throttle_ms: 0 } },
      );
      expect(component['loopable']()).toBe(true);
    });
  });
});
