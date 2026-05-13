import {
  AfterViewInit,
  Component,
  effect,
  ElementRef,
  inject,
  input,
  OnDestroy,
  signal,
  viewChild,
} from '@angular/core';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {PcdParserService} from '@core/services/pcd-parser.service';

const MAX_POINTS = 500_000;

@Component({
  selector: 'app-pcd-viewer',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './pcd-viewer.component.html',
  styleUrl: './pcd-viewer.component.css',
})
export class PcdViewerComponent implements AfterViewInit, OnDestroy {
  pcdUrl = input<string>('');

  protected isLoading = signal(false);
  protected hasError = signal(false);
  protected errorMessage = signal('');

  readonly containerRef = viewChild<ElementRef<HTMLDivElement>>('container');

  private parser = inject(PcdParserService);

  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;
  private geometry!: THREE.BufferGeometry;
  private pointsObj!: THREE.Points;
  private animationId?: number;
  private resizeObserver?: ResizeObserver;
  private isThreeInit = false;

  constructor() {
    effect(() => {
      const url = this.pcdUrl();
      if (url && this.isThreeInit) {
        void this.loadPcd(url);
      }
    });
  }

  ngAfterViewInit(): void {
    try {
      this.initThree();
      this.isThreeInit = true;
      this.animate();

      const url = this.pcdUrl();
      if (url) {
        void this.loadPcd(url);
      }
    } catch (err) {
      this.hasError.set(true);
      this.errorMessage.set(err instanceof Error ? err.message : 'Failed to initialize renderer');
    }
  }

  ngOnDestroy(): void {
    this.animationId && cancelAnimationFrame(this.animationId);
    this.resizeObserver?.disconnect();
    this.geometry?.dispose();
    (this.pointsObj?.material as THREE.Material)?.dispose();
    this.renderer?.dispose();
  }

  private initThree(): void {
    const container = this.containerRef()!.nativeElement;
    const w = container.clientWidth || 400;
    const h = container.clientHeight || 300;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#0a0a0a');

    this.camera = new THREE.PerspectiveCamera(50, w / h, 0.01, 1000);
    this.camera.position.set(10, 10, 10);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({antialias: true});
    this.renderer.setSize(w, h);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;

    // Grid helper for orientation
    const grid = new THREE.GridHelper(20, 20, 0x444444, 0x222222);
    this.scene.add(grid);

    // Pre-allocate geometry with max buffer size (mutated in-place on load)
    this.geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(MAX_POINTS * 3);
    const colors = new Float32Array(MAX_POINTS * 3);
    this.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    this.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    this.geometry.setDrawRange(0, 0);

    const material = new THREE.PointsMaterial({
      size: 0.05,
      vertexColors: true,
      sizeAttenuation: true,
    });
    this.pointsObj = new THREE.Points(this.geometry, material);
    this.pointsObj.frustumCulled = false;
    this.scene.add(this.pointsObj);

    this.resizeObserver = new ResizeObserver(() => this.syncSize());
    this.resizeObserver.observe(container);
  }

  private async loadPcd(url: string): Promise<void> {
    this.isLoading.set(true);
    this.hasError.set(false);

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const buffer = await response.arrayBuffer();
      const result = this.parser.parse(buffer);

      // Warn if too many points (do not crash)
      if (result.pointCount > MAX_POINTS) {
        console.warn(`[PcdViewer] Point count ${result.pointCount} exceeds cap ${MAX_POINTS}; truncating.`);
      }

      const count = Math.min(result.pointCount, MAX_POINTS);

      // Mutate buffer in-place — no geometry recreation
      const posAttr = this.geometry.attributes['position'] as THREE.BufferAttribute;
      const colAttr = this.geometry.attributes['color'] as THREE.BufferAttribute;
      (posAttr.array as Float32Array).set(result.positions.subarray(0, count * 3));
      (colAttr.array as Float32Array).set(result.colors.subarray(0, count * 3));
      posAttr.needsUpdate = true;
      colAttr.needsUpdate = true;
      this.geometry.setDrawRange(0, count);
      this.geometry.computeBoundingSphere();
    } catch (err) {
      console.error('[PcdViewer] Failed to load or parse PCD:', err);
      this.hasError.set(true);
      this.errorMessage.set('Unable to render point cloud');
    } finally {
      this.isLoading.set(false);
    }
  }

  private syncSize(): void {
    const container = this.containerRef()?.nativeElement;
    if (!container) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w > 0 && h > 0) {
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w, h);
    }
  }

  private animate(): void {
    this.animationId = requestAnimationFrame(() => this.animate());
    this.controls?.update();
    this.renderer?.render(this.scene, this.camera);
  }
}
