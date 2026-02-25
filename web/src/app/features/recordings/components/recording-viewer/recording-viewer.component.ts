import {
  Component,
  computed,
  effect,
  inject,
  OnInit,
  signal,
  ViewChild,
  ElementRef,
  AfterViewInit,
  OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { RecordingApiService } from '../../../../core/services/api/recording-api.service';
import { NavigationService } from '../../../../core/services/navigation.service';
import { RecordingViewerInfo } from '../../../../core/models/recording.model';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { FormsModule } from '@angular/forms';
import JSZip from 'jszip';

interface PCDData {
  points: Float32Array;
  intensities: Float32Array;
  count: number;
}

@Component({
  selector: 'app-recording-viewer',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule, FormsModule],
  templateUrl: './recording-viewer.component.html',
  styleUrl: './recording-viewer.component.css',
})
export class RecordingViewerComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('container', { static: true }) containerRef!: ElementRef<HTMLDivElement>;

  private recordingApi = inject(RecordingApiService);
  private navService = inject(NavigationService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  // State
  recordingId = signal<string | null>(null);
  recordingName = signal<string>('Loading...');
  info = signal<RecordingViewerInfo | null>(null);
  currentFrame = signal(0);
  isPlaying = signal(false);
  isLoading = signal(false);
  playbackSpeed = signal(1.0);
  error = signal<string | null>(null);
  zipProgress = signal(0);
  isDownloading = signal(false);

  // Display Settings
  pointSize = signal(0.05);
  pointColor = signal('#3b82f6');
  showGrid = signal(true);
  showAxes = signal(true);
  minIntensity = signal(0);
  showCockpit = signal(true);

  toggleCockpit() {
    this.showCockpit.set(!this.showCockpit());
  }

  closeCockpit() {
    this.showCockpit.set(false);
  }

  // Archive handle
  private zip: JSZip | null = null;
  private decodingWorker: Worker | null = null;
  private frameCache = new Map<number, PCDData>();
  private readonly MAX_CACHE_SIZE = 200;
  private framesLoading = new Set<number>();
  private lastPCDData: PCDData | null = null;

  // Three.js objects
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;
  private pointCloud: THREE.Points | null = null;
  private gridHelper: THREE.GridHelper | null = null;
  private axesHelper: THREE.AxesHelper | null = null;
  private animationFrameId: number | null = null;
  private playbackInterval: number | null = null;

  // Computed
  frameCount = computed(() => this.info()?.frame_count ?? 0);
  duration = computed(() => this.info()?.duration_seconds ?? 0);
  currentTime = computed(() => {
    const fc = this.frameCount();
    const dur = this.duration();
    return fc > 0 ? (this.currentFrame() / fc) * dur : 0;
  });

  constructor() {
    // Initialize Web Worker for PCD decoding
    this.decodingWorker = new Worker(new URL('./pcd-decoder.worker.ts', import.meta.url), {
      type: 'module',
    });

    // Update visualization when current frame changes
    effect(() => {
      const frame = this.currentFrame();
      this.ensureFrameBuffered(frame);

      if (this.frameCache.has(frame)) {
        this.updatePointCloud(this.frameCache.get(frame)!);
      }
    });

    // Proactive buffering logic
    effect(() => {
      if (this.isPlaying()) {
        const current = this.currentFrame();
        for (let i = 1; i <= 20; i++) {
          const ahead = current + i;
          if (ahead < this.frameCount()) {
            this.ensureFrameBuffered(ahead);
          }
        }
      }
    });

    // React to display settings
    effect(() => {
      const size = this.pointSize();
      const color = this.pointColor();
      const grid = this.showGrid();
      const axes = this.showAxes();
      const threshold = this.minIntensity();

      if (this.pointCloud) {
        (this.pointCloud.material as THREE.PointsMaterial).size = size;
        (this.pointCloud.material as THREE.PointsMaterial).color.set(color);
      }

      if (this.gridHelper) this.gridHelper.visible = grid;
      if (this.axesHelper) this.axesHelper.visible = axes;

      // Re-render if intensity changes
      if (this.lastPCDData) {
        this.updatePointCloud(this.lastPCDData);
      }
    });
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

  ngAfterViewInit() {
    this.initThreeJS();
    this.animate();
  }

  ngOnDestroy() {
    if (this.decodingWorker) {
      this.decodingWorker.terminate();
      this.decodingWorker = null;
    }

    this.stopPlayback();

    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    this.cleanupThreeJS();
    this.frameCache.clear();
  }

  private cleanupThreeJS() {
    if (this.pointCloud) {
      this.pointCloud.geometry.dispose();
      (this.pointCloud.material as THREE.Material).dispose();
      this.pointCloud = null;
    }

    if (this.gridHelper) {
      this.gridHelper.geometry.dispose();
      (this.gridHelper.material as THREE.Material).dispose();
    }

    if (this.axesHelper) {
      this.axesHelper.geometry.dispose();
      (this.axesHelper.material as THREE.Material).dispose();
    }

    this.renderer?.dispose();
    this.controls?.dispose();
  }

  private initThreeJS() {
    const container = this.containerRef.nativeElement;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0a0b); // Deeper dark

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;

    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    this.camera.position.set(20, 20, 20);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;

    // Helpers
    this.gridHelper = new THREE.GridHelper(40, 40, 0x334155, 0x1e293b);
    this.gridHelper.rotation.x = 0;
    this.gridHelper.visible = this.showGrid();
    this.scene.add(this.gridHelper);

    this.axesHelper = new THREE.AxesHelper(10);
    this.axesHelper.visible = this.showAxes();
    this.scene.add(this.axesHelper);

    const resizeObserver = new ResizeObserver(() => {
      window.requestAnimationFrame(() => {
        if (!container || container.clientWidth <= 0 || container.clientHeight <= 0) return;
        this.camera.aspect = container.clientWidth / container.clientHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(container.clientWidth, container.clientHeight);
      });
    });
    resizeObserver.observe(container);
  }

  private animate = () => {
    this.animationFrameId = requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };

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

  private downloadRecordingArchive(id: string) {
    this.isDownloading.set(true);
    this.recordingApi.getRecordingZip(id).subscribe({
      next: async (blob) => {
        try {
          this.zip = await JSZip.loadAsync(blob);
          this.isDownloading.set(false);
          this.isLoading.set(false);
          this.ensureFrameBuffered(0);
        } catch (err: any) {
          this.error.set(`Extraction Error: ${err.message}`);
          this.isLoading.set(false);
        }
      },
      error: (err) => {
        this.error.set(`Stream Interrupted: ${err.message}`);
        this.isLoading.set(false);
      },
    });
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
        this.updatePointCloud(this.frameCache.get(frameIndex)!);
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

  private updatePointCloud(pcdData: PCDData) {
    this.lastPCDData = pcdData;

    // Filtering
    const threshold = this.minIntensity();
    let finalPoints: Float32Array;
    let count = 0;

    if (threshold > 0) {
      const tmp = new Float32Array(pcdData.points.length);
      for (let i = 0; i < pcdData.count; i++) {
        if (pcdData.intensities[i] >= threshold) {
          tmp[count * 3] = pcdData.points[i * 3];
          tmp[count * 3 + 1] = pcdData.points[i * 3 + 1];
          tmp[count * 3 + 2] = pcdData.points[i * 3 + 2];
          count++;
        }
      }
      finalPoints = tmp.slice(0, count * 3);
    } else {
      finalPoints = pcdData.points;
      count = pcdData.count;
    }

    if (this.pointCloud) {
      this.scene.remove(this.pointCloud);
      this.pointCloud.geometry.dispose();
      (this.pointCloud.material as THREE.Material).dispose();
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(finalPoints, 3));
    const material = new THREE.PointsMaterial({
      size: this.pointSize(),
      color: new THREE.Color(this.pointColor()),
      sizeAttenuation: true,
    });

    this.pointCloud = new THREE.Points(geometry, material);
    this.pointCloud.rotation.x = -Math.PI / 2;
    this.pointCloud.rotation.z = -Math.PI / 2;
    this.scene.add(this.pointCloud);
  }

  onPlay() {
    this.isPlaying() ? this.stopPlayback() : this.startPlayback();
  }

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
  }

  onSeek(e: any) {
    this.currentFrame.set(parseInt(e.target.value, 10));
  }

  onSpeedChange(s: number) {
    this.playbackSpeed.set(s);
    if (this.isPlaying()) {
      this.stopPlayback();
      this.startPlayback();
    }
  }

  onStepForward() {
    this.currentFrame.set(Math.min(this.currentFrame() + 1, this.frameCount() - 1));
  }
  onStepBackward() {
    this.currentFrame.set(Math.max(this.currentFrame() - 1, 0));
  }

  goBack() {
    this.router.navigate(['/recordings']);
  }

  formatTime(s: number): string {
    const m = Math.floor(s / 60);
    const r = Math.floor(s % 60);
    return `${m}:${r.toString().padStart(2, '0')}`;
  }
}
