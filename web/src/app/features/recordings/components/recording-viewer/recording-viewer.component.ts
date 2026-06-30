import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  OnDestroy,
  OnInit,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { RecordingApiService } from '@core/services/api/recording-api.service';
import { NavigationService } from '@core/services';
import { RecordingViewerInfo } from '@core/models';
import * as THREE from 'three';
import { FormsModule } from '@angular/forms';
import JSZip from 'jszip';

import { NgtCanvas } from 'angular-three/dom';
import { NgtsGrid } from 'angular-three-soba/abstractions';
import { NgtsOrbitControls } from 'angular-three-soba/controls';
import { NgtsPerspectiveCamera } from 'angular-three-soba/cameras';
import { NgtsGizmoHelper, NgtsGizmoViewport } from 'angular-three-soba/gizmos';
import { NgtsPointsBuffer } from 'angular-three-soba/performances';
import { NgtArgs } from 'angular-three';

interface PCDData {
  points: Float32Array;
  intensities: Float32Array;
  count: number;
}

const MAX_POINTS = 250_000;

@Component({
  selector: 'app-recording-viewer',
  imports: [
    SynergyComponentsModule,
    FormsModule,
    DecimalPipe,
    NgtCanvas,
    NgtsGrid,
    NgtsOrbitControls,
    NgtsPerspectiveCamera,
    NgtsGizmoHelper,
    NgtsGizmoViewport,
    NgtsPointsBuffer,
    NgtArgs,
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
  isDownloading = signal(false);
  downloadProgress = signal<number>(-1);

  // ── Display settings ───────────────────────────────────────────────────────
  pointSize = signal(0.05);
  pointColor = signal('#3b82f6');
  showGrid = signal(true);
  showAxes = signal(true);
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

  // ── Services ───────────────────────────────────────────────────────────────
  private recordingApi = inject(RecordingApiService);
  private navService = inject(NavigationService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  // ── Archive / worker ───────────────────────────────────────────────────────
  private zip: JSZip | null = null;
  private decodingWorker: Worker | null = null;
  private frameCache = new Map<number, PCDData>();
  private readonly MAX_CACHE_SIZE = 200;
  private framesLoading = new Set<number>();
  private lastFrameData: PCDData | null = null;

  // ── Point cloud buffer ─────────────────────────────────────────────────────
  protected readonly positionsBuffer = new Float32Array(MAX_POINTS * 3);
  private readonly pointsBufferRef = viewChild<NgtsPointsBuffer>('pointBuf');

  // ── Template options ───────────────────────────────────────────────────────
  protected readonly cameraOptions = {
    makeDefault: true,
    position: [20, 20, 20] as [number, number, number],
    fov: 45,
    near: 0.1,
    far: 1000,
  };

  protected readonly gridOptions = {
    cellSize: 1,
    sectionSize: 5,
    cellThickness: 0.5,
    sectionThickness: 1.3,
    cellColor: '#797676',
    infiniteGrid: false,
    fadeDistance: 9_999,
    fadeStrength: 1.5,
    side: THREE.DoubleSide,
    planeArgs: [30, 30] as [number, number],
  };

  protected readonly Math = Math;

  constructor() {
    this.decodingWorker = new Worker(new URL('./pcd-decoder.worker.ts', import.meta.url), {
      type: 'module',
    });

    effect(() => {
      const frame = this.currentFrame();
      this.ensureFrameBuffered(frame);
      if (this.frameCache.has(frame)) {
        this.applyFrame(this.frameCache.get(frame)!);
      }
    });

    effect(() => {
      this.minIntensity();
      if (this.lastFrameData) this.applyFrame(this.lastFrameData);
    });

    effect(() => {
      if (this.isPlaying()) {
        const current = this.currentFrame();
        for (let i = 1; i <= 20; i++) {
          const ahead = current + i;
          if (ahead < this.frameCount()) this.ensureFrameBuffered(ahead);
        }
      }
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
    if (this.decodingWorker) {
      this.decodingWorker.terminate();
      this.decodingWorker = null;
    }
    this.stopPlayback();
    this.frameCache.clear();
  }

  onPlay() {
    this.isPlaying() ? this.stopPlayback() : this.startPlayback();
  }
  onSeek(e: any) {
    this.currentFrame.set(parseInt(e.target.value, 10));
  }
  goBack() {
    this.router.navigate(['/recordings']);
  }

  formatTime(s: number): string {
    const m = Math.floor(s / 60);
    const r = Math.floor(s % 60);
    return `${m}:${r.toString().padStart(2, '0')}`;
  }

  // ── Data loading ───────────────────────────────────────────────────────────
  private loadRecordingInfo(id: string) {
    this.isLoading.set(true);
    this.error.set(null);

    this.recordingApi.getRecordingInfo(id).subscribe({
      next: (info) => {
        this.info.set(info);
        this.recordingName.set(info.name);
        this.navService.setPageConfig({
          title: 'Recording Insight',
          subtitle: `Analyzing: ${info.name}`,
        });
        this.downloadRecordingArchive(id);
      },
      error: (err) => {
        this.error.set(`Diagnostic Failed: ${err.message}`);
        this.isLoading.set(false);
      },
    });
  }

  private async downloadRecordingArchive(id: string): Promise<void> {
    this.isDownloading.set(true);
    this.downloadProgress.set(-1);
    try {
      const blob = await this.recordingApi.getRecordingZip(id, (pct) => {
        this.downloadProgress.set(pct);
      });
      this.zip = await JSZip.loadAsync(blob);
      this.isDownloading.set(false);
      this.downloadProgress.set(-1);
      this.isLoading.set(false);
      this.ensureFrameBuffered(0);
    } catch (err: any) {
      this.error.set(`Stream Interrupted: ${err.message}`);
      this.isLoading.set(false);
      this.isDownloading.set(false);
    }
  }

  private async ensureFrameBuffered(frameIndex: number) {
    if (
      !this.zip ||
      frameIndex < 0 ||
      this.frameCache.has(frameIndex) ||
      this.framesLoading.has(frameIndex)
    ) {
      return;
    }

    if (this.frameCache.size >= this.MAX_CACHE_SIZE) {
      const current = this.currentFrame();
      let furthest = -1;
      let maxDist = -1;
      for (const idx of this.frameCache.keys()) {
        const dist = Math.abs(idx - current);
        if (dist > maxDist) {
          maxDist = dist;
          furthest = idx;
        }
      }
      this.frameCache.delete(furthest);
    }

    this.framesLoading.add(frameIndex);
    try {
      await this.loadSingleFrame(frameIndex);
      this.framesLoading.delete(frameIndex);
      if (frameIndex === this.currentFrame()) {
        this.applyFrame(this.frameCache.get(frameIndex)!);
      }
    } catch (err) {
      this.framesLoading.delete(frameIndex);
    }
  }

  private async loadSingleFrame(frameIndex: number): Promise<void> {
    const filename = `frame_${frameIndex.toString().padStart(5, '0')}.pcd`;
    const file = this.zip!.file(filename);
    if (!file) throw new Error(`${filename} Missing`);

    const buffer = await file.async('uint8array');
    return new Promise((resolve, reject) => {
      const onMessage = (e: MessageEvent) => {
        if (e.data.action === 'decoded' && e.data.payload.frameIndex === frameIndex) {
          this.decodingWorker?.removeEventListener('message', onMessage);
          if (e.data.payload.result) {
            this.frameCache.set(frameIndex, e.data.payload.result);
            resolve();
          } else reject();
        }
      };
      this.decodingWorker?.addEventListener('message', onMessage);
      this.decodingWorker?.postMessage({ action: 'decode', payload: { buffer, frameIndex } }, [
        buffer.buffer,
      ]);
    });
  }

  // ── Point cloud update ─────────────────────────────────────────────────────
  private applyFrame(pcdData: PCDData) {
    this.lastFrameData = pcdData;

    const threshold = this.minIntensity();
    let src = pcdData.points;
    let count = pcdData.count;

    if (threshold > 0) {
      const tmp = new Float32Array(pcdData.points.length);
      let outIdx = 0;
      for (let i = 0; i < pcdData.count; i++) {
        if (pcdData.intensities[i] >= threshold) {
          tmp[outIdx * 3] = pcdData.points[i * 3];
          tmp[outIdx * 3 + 1] = pcdData.points[i * 3 + 1];
          tmp[outIdx * 3 + 2] = pcdData.points[i * 3 + 2];
          outIdx++;
        }
      }
      src = tmp;
      count = outIdx;
    }

    const actualCount = Math.min(count, MAX_POINTS);
    this.positionsBuffer.set(src.subarray(0, actualCount * 3));

    const buf = this.pointsBufferRef();
    const points = buf?.pointsRef()?.nativeElement;
    if (!points) return;

    if (actualCount === 0) {
      points.visible = false;
      return;
    }
    points.visible = true;

    const geo = points.geometry;
    if (!geo) return;
    geo.setDrawRange(0, actualCount);
    const attr = geo.attributes['position'];
    if (attr) attr.needsUpdate = true;
  }

  // ── Playback ───────────────────────────────────────────────────────────────
  private playbackInterval: number | null = null;

  private startPlayback() {
    this.isPlaying.set(true);
    const fps = this.frameCount() > 0 ? this.frameCount() / this.duration() : 20;
    const interval = 1000 / (fps * this.playbackSpeed());

    this.playbackInterval = window.setInterval(() => {
      const next = this.currentFrame() + 1;
      if (next < this.frameCount()) {
        this.currentFrame.set(next);
      } else {
        this.stopPlayback();
        this.currentFrame.set(0);
      }
    }, interval);
  }

  private stopPlayback() {
    this.isPlaying.set(false);
    if (this.playbackInterval) clearInterval(this.playbackInterval);
    this.playbackInterval = null;
  }
}
