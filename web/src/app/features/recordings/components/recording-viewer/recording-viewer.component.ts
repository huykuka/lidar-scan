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
import { DialogService } from '../../../../core/services/dialog.service';
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
})
export class RecordingViewerComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('container', { static: true }) containerRef!: ElementRef<HTMLDivElement>;

  private recordingApi = inject(RecordingApiService);
  private dialogService = inject(DialogService);

  // Data passed from parent (set by DialogService)
  recordingId!: string;
  recordingName!: string;

  // State
  info = signal<RecordingViewerInfo | null>(null);
  currentFrame = signal(0);
  isPlaying = signal(false);
  isLoading = signal(false);
  loadingProgress = signal(0); // 0-100
  playbackSpeed = signal(1.0);
  error = signal<string | null>(null);

  // Frame cache - preload all frames
  private decodingWorker: Worker | null = null; // Web worker to offload PCD parsing
  private frameCache: PCDData[] = [];
  private framesLoaded = false;

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
    this.decodingWorker = new Worker(new URL('./pcd-decoder.worker.ts', import.meta.url), { type: 'module' });
    
    // Update visualization when current frame changes
    effect(() => {
      const frame = this.currentFrame();
      if (this.framesLoaded && this.frameCache[frame]) {
        this.updatePointCloud(this.frameCache[frame]);
      }
    });
  }

  ngOnInit() {
    // Load info and preload all frames when component initializes
    if (this.recordingId) {
      this.loadRecordingInfo(this.recordingId);
    }
  }

  ngAfterViewInit() {
    this.initThreeJS();
    this.animate();
  }

  ngOnDestroy() {
    // Terminate the decoding Web Worker to release resources
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
    
    // Clear frame cache
    this.frameCache = [];
  }

  private initThreeJS() {
    const container = this.containerRef.nativeElement;

    // Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x2a2a2b);

    // Camera
    this.camera = new THREE.PerspectiveCamera(
      75,
      container.clientWidth / container.clientHeight,
      0.1,
      1000,
    );
    this.camera.position.set(15, 15, 15);
    this.camera.lookAt(0, 0, 0);

    // Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setSize(container.clientWidth, container.clientHeight);
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
      this.camera.aspect = container.clientWidth / container.clientHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(container.clientWidth, container.clientHeight);
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
    this.framesLoaded = false;
    this.frameCache = [];

    this.recordingApi.getRecordingInfo(id).subscribe({
      next: (info) => {
        this.info.set(info);
        this.currentFrame.set(0);
        // Start preloading all frames
        this.preloadAllFrames(id, info.frame_count);
      },
      error: (err) => {
        this.error.set(`Failed to load recording info: ${err.message}`);
        this.isLoading.set(false);
      },
    });
  }

  private async preloadAllFrames(recordingId: string, frameCount: number) {
    this.loadingProgress.set(0);
    this.frameCache = new Array(frameCount);

    // Load frames in parallel (batch of 10 at a time to avoid overwhelming the server)
    const batchSize = 10;
    let loaded = 0;

    for (let i = 0; i < frameCount; i += batchSize) {
      const batch = [];
      const batchEnd = Math.min(i + batchSize, frameCount);

      for (let j = i; j < batchEnd; j++) {
        batch.push(this.loadSingleFrame(recordingId, j));
      }

      try {
        await Promise.all(batch);
        loaded += batch.length;
        this.loadingProgress.set(Math.round((loaded / frameCount) * 100));
      } catch (err: any) {
        this.error.set(`Failed to load frames: ${err.message}`);
        this.isLoading.set(false);
        return;
      }
    }

    this.framesLoaded = true;
    this.isLoading.set(false);

    // Display first frame
    if (this.frameCache[0]) {
      this.updatePointCloud(this.frameCache[0]);
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
            
            // Send text to worker for decoding
            this.decodingWorker!.postMessage({
              action: 'decode',
              payload: { text, frameIndex },
            });
            
            // Listen for worker response
            const onMessage = (event: MessageEvent) => {
              const { action, payload } = event.data;
              if (action === 'decoded' && payload.frameIndex === frameIndex) {
                this.decodingWorker!.removeEventListener('message', onMessage);
                
                if (payload.result) {
                  this.frameCache[frameIndex] = payload.result;
                  resolve();
                } else {
                  reject(new Error(`Failed to parse frame ${frameIndex}`));
                }
              }
            };
            
            this.decodingWorker!.addEventListener('message', onMessage);
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
