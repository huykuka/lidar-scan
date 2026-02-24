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
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { RecordingApiService } from '../../../../core/services/api/recording-api.service';
import { RecordingViewerInfo } from '../../../../core/models/recording.model';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { FormsModule } from '@angular/forms';

interface PCDData {
  points: Float32Array;
  count: number;
}

@Component({
  selector: 'app-recording-viewer',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule, FormsModule],
  templateUrl: './recording-viewer.component.html',
  styleUrl: './recording-viewer.component.css',
  styles: [
    `
      :host {
        display: block;
        width: 100%;
        height: 100%;
      }
    `,
  ],
})
export class RecordingViewerComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('container', { static: true }) containerRef!: ElementRef<HTMLDivElement>;

  private recordingApi = inject(RecordingApiService);

  // Data passed from parent (set by DialogService)
  recordingId!: string;
  recordingName!: string;

  // State
  info = signal<RecordingViewerInfo | null>(null);
  currentFrame = signal(0);
  isPlaying = signal(false);
  isLoading = signal(false);
  playbackSpeed = signal(1.0);
  error = signal<string | null>(null);

  // Frame cache - smart loading
  private decodingWorker: Worker | null = null;
  private frameCache = new Map<number, PCDData>();
  private readonly MAX_CACHE_SIZE = 150; // Keep up to 150 frames in memory
  private framesLoading = new Set<number>();

  // Three.js objects
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;
  private pointCloud: THREE.Points | null = null;
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
        // Buffer ahead 15 frames for smooth playback
        for (let i = 1; i <= 15; i++) {
          const ahead = current + i;
          if (ahead < this.frameCount()) {
            this.ensureFrameBuffered(ahead);
          }
        }
      }
    });
  }

  ngOnInit() {
    if (this.recordingId) {
      this.loadRecordingInfo(this.recordingId);
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

    if (this.pointCloud) {
      this.pointCloud.geometry.dispose();
      (this.pointCloud.material as THREE.Material).dispose();
      this.pointCloud = null;
    }

    this.renderer?.dispose();
    this.controls?.dispose();

    this.frameCache.clear();
  }

  private initThreeJS() {
    const container = this.containerRef.nativeElement;

    // Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x2a2a2b);

    // Initial dummy values until resize observer picks up the correct dom flow size
    const initWidth = container.clientWidth > 0 ? container.clientWidth : 800;
    const initHeight = container.clientHeight > 0 ? container.clientHeight : 600;

    // Camera setup with 50 degree FOV matching the workspace viewer
    this.camera = new THREE.PerspectiveCamera(40, initWidth / initHeight, 0.1, 1000);
    this.camera.position.set(15, 15, 15);
    this.camera.lookAt(0, 0, 0);

    // Renderer setup
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setSize(initWidth, initHeight);

    // If init failed because dialog is lazy-rendering with 0x0
    if (container.clientWidth === 0) {
      const waitInterval = setInterval(() => {
        if (container.clientWidth > 0) {
          clearInterval(waitInterval);
          this.camera.aspect = container.clientWidth / container.clientHeight;
          this.camera.updateProjectionMatrix();
          this.renderer.setSize(container.clientWidth, container.clientHeight);
          if (this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
          }
        }
      }, 50);

      // Clear out safety interval eventually
      setTimeout(() => clearInterval(waitInterval), 2000);
    }
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    // Controls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0, 0);

    // Grid & Axes
    const gridHelper = new THREE.GridHelper(20, 20, 0x555555, 0x333333);
    this.scene.add(gridHelper);

    const axesHelper = new THREE.AxesHelper(5);
    this.scene.add(axesHelper);

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
      // Dialog containers sometimes fire ResizeObserver with 0 bounds when just appending
      if (container.clientWidth <= 0 || container.clientHeight <= 0) return;

      this.camera.aspect = container.clientWidth / container.clientHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(container.clientWidth, container.clientHeight);

      // Explicitly trigger a render on resize to avoid black frames until next animation tick
      if (this.scene && this.camera) {
        this.renderer.render(this.scene, this.camera);
      }
    });

    // A small buffer to let the modal completely attach to the DOM before observing
    setTimeout(() => {
      if (!container) return;
      resizeObserver.observe(container);

      // Force an explicit manual resize trigger a few ticks later in case observer missed the CSS layout transition
      setTimeout(() => {
        if (container.clientWidth > 0 && container.clientHeight > 0) {
          this.camera.aspect = container.clientWidth / container.clientHeight;
          this.camera.updateProjectionMatrix();
          this.renderer.setSize(container.clientWidth, container.clientHeight);
        }

        // Start animation loop ONLY AFTER layout stabilizes
        if (this.animationFrameId === null) {
          this.animate();
        }
      }, 300);
    }, 100);
  }

  private animate = () => {
    this.animationFrameId = requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };

  private loadRecordingInfo(id: string) {
    this.isLoading.set(true);
    this.error.set(null);
    this.frameCache.clear();
    this.framesLoading.clear();

    this.recordingApi.getRecordingInfo(id).subscribe({
      next: (info) => {
        this.info.set(info);
        this.currentFrame.set(0);
        this.isLoading.set(false);
        // Load initial frame immediately
        this.ensureFrameBuffered(0);
      },
      error: (err) => {
        this.error.set(`Failed to load recording info: ${err.message}`);
        this.isLoading.set(false);
      },
    });
  }

  /**
   * Ensures a frame is in the cache, fetching it if necessary.
   * Implements a simple cache eviction policy.
   */
  private async ensureFrameBuffered(frameIndex: number) {
    if (frameIndex < 0 || this.frameCache.has(frameIndex) || this.framesLoading.has(frameIndex)) {
      return;
    }

    // Cache management: If too many frames, remove the one furthest from current
    if (this.frameCache.size >= this.MAX_CACHE_SIZE) {
      let furthestFrame = -1;
      let maxDistance = -1;
      const current = this.currentFrame();

      for (const cachedIndex of this.frameCache.keys()) {
        const distance = Math.abs(cachedIndex - current);
        if (distance > maxDistance) {
          maxDistance = distance;
          furthestFrame = cachedIndex;
        }
      }

      if (furthestFrame !== -1) {
        this.frameCache.delete(furthestFrame);
      }
    }

    this.framesLoading.add(frameIndex);

    try {
      await this.loadSingleFrame(this.recordingId, frameIndex);
      this.framesLoading.delete(frameIndex);

      // If we just loaded the current frame, trigger update
      if (frameIndex === this.currentFrame()) {
        this.updatePointCloud(this.frameCache.get(frameIndex)!);
      }
    } catch (err) {
      this.framesLoading.delete(frameIndex);
      console.error(`Failed to load frame ${frameIndex}:`, err);
    }
  }

  private loadSingleFrame(recordingId: string, frameIndex: number): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.decodingWorker) {
        reject(new Error('Worker not initialized'));
        return;
      }

      this.recordingApi.getFrameAsPcd(recordingId, frameIndex).subscribe({
        next: (blob) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            const text = e.target?.result as string;

            if (!this.decodingWorker) {
              reject(new Error('Worker was destroyed'));
              return;
            }

            this.decodingWorker.postMessage({
              action: 'decode',
              payload: { text, frameIndex },
            });

            const onMessage = (event: MessageEvent) => {
              const { action, payload } = event.data;
              if (action === 'decoded' && payload.frameIndex === frameIndex) {
                if (this.decodingWorker) {
                  this.decodingWorker.removeEventListener('message', onMessage);
                }

                if (payload.result) {
                  this.frameCache.set(frameIndex, payload.result);
                  resolve();
                } else {
                  reject(new Error(`Failed to parse frame ${frameIndex}`));
                }
              }
            };

            this.decodingWorker.addEventListener('message', onMessage);
          };
          reader.onerror = () => reject(new Error(`Failed to read frame ${frameIndex}`));
          reader.readAsText(blob);
        },
        error: (err) => reject(err),
      });
    });
  }

  private updatePointCloud(pcdData: PCDData) {
    // Remove old point cloud
    if (this.pointCloud) {
      this.scene.remove(this.pointCloud);
      this.pointCloud.geometry.dispose();
      (this.pointCloud.material as THREE.Material).dispose();
    }

    // Create new geometry
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(pcdData.points, 3));

    // Compute bounding sphere for centering
    geometry.computeBoundingSphere();

    // Create material with larger points
    const material = new THREE.PointsMaterial({
      size: 0.05,
      color: 0x3b82f6,
      sizeAttenuation: true,
    });

    // Create points
    this.pointCloud = new THREE.Points(geometry, material);
    this.pointCloud.frustumCulled = false;

    // Rotate to match LiDAR coordinate system (Z-up vs Three.js Y-up)
    this.pointCloud.rotation.x = -Math.PI / 2;
    this.pointCloud.rotation.z = -Math.PI / 2;

    this.scene.add(this.pointCloud);

    // Auto-frame camera on first frame, but always keep orbit target at origin
    if (this.currentFrame() === 0 && geometry.boundingSphere) {
      const radius = geometry.boundingSphere.radius;

      // Position camera to view the entire point cloud
      const distance = radius * 3;
      this.camera.position.set(0, distance * 0.5, distance);
      this.camera.lookAt(0, 0, 0);
      this.controls.target.set(0, 0, 0);
      this.controls.update();
    }
  }

  // Media controls
  onPlay() {
    if (this.isPlaying()) {
      this.stopPlayback();
    } else {
      this.startPlayback();
    }
  }

  private startPlayback() {
    this.isPlaying.set(true);
    const fps = this.frameCount() > 0 ? this.frameCount() / this.duration() : 25;
    const interval = 1000 / (fps * this.playbackSpeed());

    this.playbackInterval = window.setInterval(() => {
      const nextFrame = this.currentFrame() + 1;
      if (nextFrame < this.frameCount()) {
        this.currentFrame.set(nextFrame);
      } else {
        this.stopPlayback();
        this.currentFrame.set(0); // Loop
      }
    }, interval);
  }

  private stopPlayback() {
    this.isPlaying.set(false);
    if (this.playbackInterval !== null) {
      clearInterval(this.playbackInterval);
      this.playbackInterval = null;
    }
  }

  onSeek(event: Event) {
    const synRange = event.target as any;
    const frame = parseInt(synRange.value, 10);
    this.currentFrame.set(frame);
  }

  onSpeedChange(speed: number) {
    this.playbackSpeed.set(speed);
    if (this.isPlaying()) {
      this.stopPlayback();
      this.startPlayback();
    }
  }

  onStepForward() {
    const nextFrame = Math.min(this.currentFrame() + 1, this.frameCount() - 1);
    this.currentFrame.set(nextFrame);
  }

  onStepBackward() {
    const prevFrame = Math.max(this.currentFrame() - 1, 0);
    this.currentFrame.set(prevFrame);
  }

  formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }
}
