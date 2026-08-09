import {
  ChangeDetectionStrategy,
  Component,
  computed,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  inject,
  OnDestroy,
  OnInit,
  signal,
  effect,
  viewChild,
} from '@angular/core';
import {DecimalPipe} from '@angular/common';
import {ActivatedRoute, Router} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {RecordingApiService} from '@core/services/api/recording-api.service';
import {NavigationService} from '@core/services';
import {RecordingViewerInfo} from '@core/models';
import {FormsModule} from '@angular/forms';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {RecordingPlaybackStreamService, RecordingPlaybackEvent} from '@core/services/recording-playback-stream.service';
import {LidrFrame} from '@core/services/lidr-parser';
import {ToastService} from '@core/services/toast.service';
import {RecordingStoreService} from '@core/services/stores/recording-store.service';

import {NgtsPointsBuffer} from 'angular-three-soba/performances';
import {NgtCanvas, NgtCanvasContent, NgtCanvasImpl} from 'angular-three/dom';
import {ThreedSceneGraphComponent, ViewportOverlayComponent} from '@shared/components';
import {ViewOrientation} from '@core/services/split-layout-store.service';
import {copyStreamedXyz, flushPointCloudGeometry, nextFrameIndex, readyAction, shouldApplyFrame} from './recording-viewer-stream-state';

const MAX_POINTS = 250_000;

@Component({
  selector: 'app-recording-viewer',
  imports: [
    SynergyComponentsModule,
    FormsModule,
    DecimalPipe,
    NgtCanvas,
    NgtCanvasContent,
    ThreedSceneGraphComponent,
    NgtsPointsBuffer,
    NgtCanvasImpl,
    ViewportOverlayComponent,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './recording-viewer.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display:flex;flex-direction:column;flex:1;min-height:0;width:100%' },
  styleUrl: './recording-viewer.component.css',
})
export class RecordingViewerComponent implements OnInit, OnDestroy {
  // ── State ──────────────────────────────────────────────────────────────────
  recordingId = signal<string | null>(null);
  recordingName = signal<string>('Loading...');
  info = signal<RecordingViewerInfo | null>(null);
  currentFrame = signal(0);
  isPlaying = signal(false);
  isLoading = signal(false);
  playbackSpeed = signal(1.0);
  error = signal<string | null>(null);
  streamState = signal<'loading' | 'streaming' | 'eof' | 'error'>('loading');

  // ── Trim state ─────────────────────────────────────────────────────────────
  inFrame = signal<number | null>(null);
  outFrame = signal<number | null>(null);
  previewing = signal(false);
  creating = signal(false);

  // ── Display settings ───────────────────────────────────────────────────────
  pointSize = signal(0.05);
  pointColor = signal('red');
  showGrid = signal(true);
  viewOrientation = signal<ViewOrientation>('perspective');
  minIntensity = signal(0);
  showCockpit = signal(true);

  // ── Computed ───────────────────────────────────────────────────────────────
  frameCount = computed(() => this.info()?.frame_count ?? 0);
  duration = computed(() => this.info()?.duration_seconds ?? 0);
  currentTime = computed(() => {
    const fc = this.frameCount();
    const dur = this.duration();
    return fc > 0 ? (this.currentFrame() / fc) * dur : 0;
  });

  trimValid = computed(() => {
    const inF = this.inFrame();
    const outF = this.outFrame();
    return inF !== null && outF !== null && inF < outF;
  });

  // Both set but in >= out (invalid order)
  trimBothSetInvalid = computed(() => {
    const inF = this.inFrame();
    const outF = this.outFrame();
    return inF !== null && outF !== null && inF >= outF;
  });

  canCreate = computed(() => this.trimValid() && !this.creating());

  // Trim range width percentage for overlay
  trimRangeStyle = computed(() => {
    const fc = this.frameCount();
    if (fc === 0) return null;
    const inF = this.inFrame();
    const outF = this.outFrame();
    if (inF === null || outF === null) return null;
    const left = (inF / fc) * 100;
    const width = ((outF - inF) / fc) * 100;
    return { left: `${left}%`, width: `${width}%` };
  });

  // Tick marker positions for in/out on scrubber
  inMarkerStyle = computed(() => {
    const fc = this.frameCount();
    const inF = this.inFrame();
    if (fc === 0 || inF === null) return null;
    const left = (inF / Math.max(fc - 1, 1)) * 100;
    return { left: `${left}%` };
  });

  outMarkerStyle = computed(() => {
    const fc = this.frameCount();
    const outF = this.outFrame();
    if (fc === 0 || outF === null) return null;
    const left = (outF / Math.max(fc - 1, 1)) * 100;
    return { left: `${left}%` };
  });

  // Tooltip for disabled Preview/Create buttons
  trimDisabledTooltip = computed(() => {
    const inF = this.inFrame();
    const outF = this.outFrame();
    if (inF === null && outF === null) return 'Set both In and Out markers to enable';
    if (inF === null) return 'Set an In marker before the Out marker';
    if (outF === null) return 'Set an Out marker after the In marker';
    if (inF >= outF) return 'In marker must come before Out marker';
    return '';
  });

  // Segment summary when valid
  segmentFrameCount = computed(() => {
    if (!this.trimValid()) return 0;
    return this.outFrame()! - this.inFrame()!;
  });

  segmentDuration = computed(() => {
    if (!this.trimValid()) return 0;
    return this.frameToTime(this.outFrame()!) - this.frameToTime(this.inFrame()!);
  });

  // ── Services ───────────────────────────────────────────────────────────────
  private recordingApi = inject(RecordingApiService);
  private playbackStream = inject(RecordingPlaybackStreamService);
  private navService = inject(NavigationService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private toast = inject(ToastService);
  private recordingStore = inject(RecordingStoreService);
  private destroyRef = inject(DestroyRef);

  // ── Archive / worker ───────────────────────────────────────────────────────
  private latestGeneration = 0;
  private pendingSeekGeneration: number | null = null;
  private pendingSeekFrame: number | null = null;
  private streamSession = 0;
  private autoStartSession = -1;
  private resumeFrameIndex: number | null = null;

  // ── Point cloud buffer ─────────────────────────────────────────────────────
  protected readonly positionsBuffer = new Float32Array(MAX_POINTS * 3);
  protected readonly pointCount = signal(0);
  private readonly pointsBufferRef = viewChild<NgtsPointsBuffer>('pointBuf');

  constructor() {
    this.playbackStream.events.pipe(takeUntilDestroyed()).subscribe((event) => this.handleStreamEvent(event));

    // Stream frames can arrive before angular-three creates pointsRef(). Track
    // count separately so geometry flush retries when viewChild becomes ready.
    effect(() => {
      const points = this.pointsBufferRef()?.pointsRef()?.nativeElement;
      if (!points) return;
      flushPointCloudGeometry(points, this.pointCount());
    });
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  toggleCockpit() {
    this.showCockpit.set(!this.showCockpit());
  }
  closeCockpit() {
    this.showCockpit.set(false);
  }

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.recordingId.set(id);
      this.loadRecordingInfo(id);
    } else {
      this.error.set('No recording ID provided');
    }
  }

  ngOnDestroy() {
    this.playbackStream.disconnect();
    this.stopPlayback();
    this.clearPointCloud();
  }

  onPlay() {
    if (this.isPlaying()) this.stopPlayback();
    else this.startPlayback();
  }
  onSeek(e: any) {
    const raw = parseInt(e.target.value, 10);
    if (Number.isNaN(raw)) return;
    const max = Math.max(this.frameCount() - 1, 0);
    const frameIndex = Math.min(Math.max(raw, 0), max);
    this.currentFrame.set(frameIndex);
    this.pendingSeekFrame = frameIndex;
    this.resumeFrameIndex = frameIndex;
    this.playbackStream.seek(frameIndex);
  }
  goBack() {
    this.router.navigate(['/recordings']);
  }

  formatTime(s: number): string {
    const m = Math.floor(s / 60);
    const r = Math.floor(s % 60);
    return `${m}:${r.toString().padStart(2, '0')}`;
  }

  // Linear frame→time mapping: frame / (frameCount-1) * duration
  frameToTime(frame: number): number {
    const fc = this.frameCount();
    const dur = this.duration();
    if (fc <= 1) return 0;
    return (frame / (fc - 1)) * dur;
  }

  // Display string for a frame: "128 · 7.5s"
  frameLabel(frame: number | null): string {
    if (frame === null) return '';
    const t = this.frameToTime(frame);
    return `${frame} · ${t.toFixed(1)}s`;
  }

  // ── Trim actions ───────────────────────────────────────────────────────────
  setInFrame() {
    const current = this.currentFrame();
    const out = this.outFrame();
    // If in >= out, clear out to avoid invalid state
    if (out !== null && current >= out) {
      this.outFrame.set(null);
    }
    this.inFrame.set(current);
    // Cancel preview if bounds change mid-preview
    if (this.previewing()) {
      this.cancelPreview();
    }
  }

  setOutFrame() {
    const current = this.currentFrame();
    const inF = this.inFrame();
    // out must be strictly greater than in
    if (inF !== null && current <= inF) {
      // Reject — don't set
      return;
    }
    this.outFrame.set(current);
    // Cancel preview if bounds change mid-preview
    if (this.previewing()) {
      this.cancelPreview();
    }
  }

  resetTrim() {
    this.inFrame.set(null);
    this.outFrame.set(null);
    if (this.previewing()) {
      this.cancelPreview();
    }
  }

  togglePreview() {
    if (this.previewing()) {
      this.cancelPreview();
    } else {
      this.startPreview();
    }
  }

  startPreview() {
    if (!this.trimValid()) return;
    const inF = this.inFrame()!;
    this.previewing.set(true);
    this.isPlaying.set(true);
    // Seek to inFrame, then start
    this.playbackStream.seek(inF);
    this.playbackStream.start(inF);
  }

  cancelPreview() {
    this.previewing.set(false);
    this.isPlaying.set(false);
    this.playbackStream.pause();
  }

  onCreateTrim() {
    if (!this.canCreate()) return;
    const id = this.recordingId();
    if (!id) return;
    const inF = this.inFrame()!;
    const outF = this.outFrame()!;

    this.creating.set(true);
    this.recordingApi.trimRecording(id, { start_frame: inF, end_frame: outF, name: null })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          // 202: trim started in background — reset immediately, don't wait for copy
          this.creating.set(false);
          this.inFrame.set(null);
          this.outFrame.set(null);
          this.toast.success('Trim started — processing in background');
          this.recordingStore.loadRecordings();
        },
        error: () => {
          // http-toast.interceptor handles display; still reset creating
          this.creating.set(false);
        },
      });
  }

  // ── Data loading ───────────────────────────────────────────────────────────
  private loadRecordingInfo(id: string) {
    this.isLoading.set(true);
    this.error.set(null);

    this.recordingApi.getRecordingInfo(id).subscribe({
      next: (info) => {
        this.info.set(info);
        this.recordingName.set(info.name);
        this.isLoading.set(false);
        this.navService.setPageConfig({
          title: 'Recording Insight',
          subtitle: `Analyzing: ${info.name}`,
        });
        this.streamState.set('loading');
        this.streamSession += 1;
        this.autoStartSession = -1;
        this.playbackStream.connect(id);
      },
      error: (err) => {
        this.error.set(`Diagnostic Failed: ${err.message}`);
        this.isLoading.set(false);
        this.streamState.set('error');
      },
    });
  }

  private handleStreamEvent(event: RecordingPlaybackEvent) {
    if (event.type === 'ready') {
      this.info.update((value) => value ? {...value, frame_count: event.frameCount} : value);
      this.isLoading.set(false);
      const action = readyAction(event.frameCount, this.streamSession, this.autoStartSession);
      if (action === 'eof') {
        this.streamState.set('eof');
        this.isPlaying.set(false);
        this.clearPointCloud();
        return;
      }
      this.streamState.set('streaming');
      if (action === 'ignore') return;
      this.autoStartSession = this.streamSession;
      this.isPlaying.set(true);
      this.playbackStream.start(0);
    } else if (event.type === 'seeked') {
      this.latestGeneration = event.generation;
      this.pendingSeekGeneration = event.generation;
      this.currentFrame.set(event.frameIndex);
      this.streamState.set('streaming');
    } else if (event.type === 'paused') {
      this.latestGeneration = event.generation;
      this.resumeFrameIndex = event.frameIndex;
      this.currentFrame.set(Math.min(event.frameIndex, Math.max(this.frameCount() - 1, 0)));
      this.isPlaying.set(false);
      if (this.previewing()) {
        this.previewing.set(false);
      }
    } else if (event.type === 'frame') {
      const isPendingSeekFrame = this.pendingSeekGeneration === event.generation
        && this.pendingSeekFrame === event.frameIndex;
      if (shouldApplyFrame(this.isPlaying(), event.generation, this.latestGeneration, isPendingSeekFrame ? event.generation : null)) {
        // Preview out-of-bounds check: half-open [in, out) → stop BEFORE rendering frame==out
        if (this.previewing()) {
          const outF = this.outFrame();
          if (outF !== null && event.frameIndex >= outF) {
            this.playbackStream.pause();
            this.previewing.set(false);
            this.isPlaying.set(false);
            return; // Don't apply this frame
          }
        }
        this.applyFrame(event);
        if (isPendingSeekFrame) {
          this.pendingSeekGeneration = null;
          this.pendingSeekFrame = null;
        }
      }
    } else if (event.type === 'eof') {
      this.streamState.set('eof');
      this.isPlaying.set(false);
      if (this.previewing()) {
        this.previewing.set(false);
      }
    } else if (event.type === 'error') {
      this.error.set(event.message); this.streamState.set('error'); this.isLoading.set(false);
      if (this.previewing()) {
        this.previewing.set(false);
      }
    }
  }

  // ── Point cloud update ─────────────────────────────────────────────────────
  private applyFrame(frame: LidrFrame) {
    const src = frame.xyz;
    const count = frame.pointCount;
    this.currentFrame.set(frame.frameIndex);

    const points = this.pointsBufferRef()?.pointsRef()?.nativeElement;
    const actualCount = points
      ? copyStreamedXyz(points, this.positionsBuffer, src, count, MAX_POINTS)
      : Math.min(count, MAX_POINTS);
    if (!points) this.positionsBuffer.set(src.subarray(0, actualCount * 3));
    this.pointCount.set(actualCount);
  }

  private clearPointCloud() {
    this.pointCount.set(0);
    const points = this.pointsBufferRef()?.pointsRef()?.nativeElement;
    if (!points) return;
    flushPointCloudGeometry(points, 0);
  }

  // ── Playback ───────────────────────────────────────────────────────────────
  private startPlayback() {
    this.isPlaying.set(true);
    const frameIndex = this.resumeFrameIndex ?? nextFrameIndex(this.currentFrame(), this.frameCount());
    this.resumeFrameIndex = null;
    this.playbackStream.start(frameIndex);
  }

  private stopPlayback() {
    this.isPlaying.set(false);
    this.playbackStream.pause();
  }
}
