import {
  Component,
  computed,
  effect,
  inject,
  OnDestroy,
  output,
  signal,
  untracked,
} from '@angular/core';
import { Subscription } from 'rxjs';
import { DatePipe, DecimalPipe } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { RecordingApiService } from '@core/services/api/recording-api.service';
import { NodeEditorFacadeService } from '@features/settings/services/node-editor-facade.service';
import { NodeEditorComponent } from '@core/models/node-plugin.model';
import { NodeEditorHeaderComponent } from '@plugins/shared/node-editor-header/node-editor-header.component';
import { Recording } from '@core/models/recording.model';
import {
  PLAYBACK_SPEED_OPTIONS,
  PlaybackConfig,
  PlaybackSpeed,
  VALID_PLAYBACK_SPEEDS,
} from '@plugins/playback/playback.model';

@Component({
  selector: 'app-playback-node-editor',
  standalone: true,
  imports: [SynergyComponentsModule, NodeEditorHeaderComponent, DatePipe, DecimalPipe],
  providers: [NodeEditorFacadeService],
  templateUrl: './playback-node-editor.component.html',
  styleUrl: './playback-node-editor.component.css',
})
export class PlaybackNodeEditorComponent implements NodeEditorComponent, OnDestroy {
  saved = output<void>();
  cancelled = output<void>();

  // ── Exposed constants for template ─────────────────────────────────────────
  protected readonly speedOptions = PLAYBACK_SPEED_OPTIONS;

  // ── State signals ────────────────────────────────────────────────────────────
  protected recordings = signal<Recording[]>([]);
  protected selectedRecording = signal<Recording | null>(null);
  protected recordingId = signal<string>('');
  protected playbackSpeed = signal<PlaybackSpeed>(1.0);
  protected loopable = signal<boolean>(false);
  protected throttleMs = signal<number>(0);
  protected isSaving = signal<boolean>(false);
  protected isLoadingRecordings = signal<boolean>(false);

  protected isSaveDisabled = computed(
    () => !this.recordingId() || this.isSaving(),
  );

  // ── Services ─────────────────────────────────────────────────────────────────
  private nodeStore = inject(NodeStoreService);
  private recordingApi = inject(RecordingApiService);
  private facade = inject(NodeEditorFacadeService);

  private recordingSub?: Subscription;
  private detailSub?: Subscription;

  constructor() {
    // Pre-populate from existing node config when selected node changes
    effect(() => {
      const node = this.nodeStore.selectedNode();
      untracked(() => {
        const cfg = node?.config as Partial<PlaybackConfig> | undefined;
        if (cfg?.recording_id) {
          this.recordingId.set(cfg.recording_id);
          // Load metadata for pre-existing selection
          this.loadRecordingDetail(cfg.recording_id);
        }
        this.setPlaybackSpeed((cfg?.playback_speed as PlaybackSpeed) ?? 1.0);
        this.loopable.set(cfg?.loopable ?? false);
        this.throttleMs.set(cfg?.throttle_ms ?? 0);
      });
    });

    this.loadRecordings();
  }

  ngOnDestroy(): void {
    this.recordingSub?.unsubscribe();
    this.detailSub?.unsubscribe();
  }

  // ── Public methods (called from template + spec) ────────────────────────────

  protected onRecordingSelect(id: string): void {
    this.recordingId.set(id);
    if (!id) {
      this.selectedRecording.set(null);
      return;
    }
    this.loadRecordingDetail(id);
  }

  protected toggleLoopable(): void {
    this.loopable.update((v) => !v);
  }

  protected setPlaybackSpeed(value: number): void {
    if (!VALID_PLAYBACK_SPEEDS.has(value)) {
      console.warn(
        `[PlaybackNodeEditor] Invalid playback_speed "${value}". ` +
          `Must be one of ${[...VALID_PLAYBACK_SPEEDS].sort().join(', ')}. Resetting to 1.0.`,
      );
      this.playbackSpeed.set(1.0);
      return;
    }
    this.playbackSpeed.set(value as PlaybackSpeed);
  }

  protected onSpeedChange(event: Event): void {
    const value = parseFloat((event.target as HTMLSelectElement).value);
    this.setPlaybackSpeed(value);
  }

  protected onLoopableChange(event: Event): void {
    this.loopable.set((event.target as HTMLInputElement).checked);
  }

  async onSave(): Promise<void> {
    if (!this.recordingId()) return;

    this.isSaving.set(true);

    const config: PlaybackConfig = {
      recording_id: this.recordingId(),
      playback_speed: this.playbackSpeed(),
      loopable: this.loopable(),
      throttle_ms: this.throttleMs(),
    };

    const node = this.nodeStore.selectedNode();
    const success = await this.facade.saveNode({
      name: node?.name ?? 'Playback',
      config,
      definition: {
        type: 'playback',
        display_name: 'Playback',
        category: 'sensor',
        description: 'Replay a recording as synthetic sensor data',
        icon: 'play_circle',
        websocket_enabled: true,
        properties: [],
        inputs: [],
        outputs: [],
      },
      existingNode: node ?? {},
    });

    this.isSaving.set(false);

    if (success) {
      this.saved.emit();
    }
  }

  onCancel(): void {
    this.cancelled.emit();
  }

  // ── Private helpers ──────────────────────────────────────────────────────────

  private loadRecordings(): void {
    this.isLoadingRecordings.set(true);
    this.recordingSub?.unsubscribe();
    this.recordingSub = this.recordingApi.getRecordings().subscribe({
      next: (res) => {
        this.recordings.set(res.recordings);
        this.isLoadingRecordings.set(false);
      },
      error: (err) => {
        console.error('[PlaybackNodeEditor] Failed to load recordings', err);
        this.recordings.set([]);
        this.isLoadingRecordings.set(false);
      },
    });
  }

  private loadRecordingDetail(id: string): void {
    this.detailSub?.unsubscribe();
    this.detailSub = this.recordingApi.getRecording(id).subscribe({
      next: (rec) => this.selectedRecording.set(rec),
      error: (err) => {
        console.error(`[PlaybackNodeEditor] Failed to load recording ${id}`, err);
        this.selectedRecording.set(null);
      },
    });
  }
}
