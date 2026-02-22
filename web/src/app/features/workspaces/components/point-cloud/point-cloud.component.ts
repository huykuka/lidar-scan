import {
  Component,
  ElementRef,
  OnInit,
  OnDestroy,
  ViewChild,
  input,
  effect,
  output,
} from '@angular/core';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

@Component({
  selector: 'app-point-cloud',
  standalone: true,
  template: `<div
    #container
    class="w-full h-full min-h-0 bg-transparent rounded-lg overflow-hidden"
  ></div>`,
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
export class PointCloudComponent implements OnInit, OnDestroy {
  @ViewChild('container', { static: true }) containerRef!: ElementRef<HTMLDivElement>;

  // Inputs for customization
  pointSize = input<number>(0.1);
  pointColor = input<string>('#00ff00');
  showGrid = input<boolean>(true);
  showAxes = input<boolean>(true);

  // Three.js instances
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;
  private pointsObj!: THREE.Points;
  private geometry!: THREE.BufferGeometry;
  private material!: THREE.PointsMaterial;
  private gridHelper?: THREE.GridHelper;
  private axesHelper?: THREE.AxesHelper;

  private lastCount = 0;

  private animationId?: number;
  private readonly MAX_POINTS = 50000;

  constructor() {
    // React to input changes
    effect(() => {
      if (this.material) {
        this.material.size = this.pointSize();
      }
    });

    effect(() => {
      if (this.material) {
        this.material.color.set(this.pointColor());
      }
    });

    effect(() => {
      if (this.gridHelper) {
        this.gridHelper.visible = !!this.showGrid();
      }
    });

    effect(() => {
      if (this.axesHelper) {
        this.axesHelper.visible = !!this.showAxes();
      }
    });
  }

  ngOnInit() {
    this.initThree();
    this.animate();
  }

  ngOnDestroy() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
    }
    this.renderer.dispose();
  }

  private initThree() {
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
    this.gridHelper = new THREE.GridHelper(20, 20, 0x555555, 0x333333);
    this.gridHelper.visible = !!this.showGrid();
    this.scene.add(this.gridHelper);

    this.axesHelper = new THREE.AxesHelper(5);
    this.axesHelper.visible = !!this.showAxes();
    this.scene.add(this.axesHelper);

    // Point Cloud
    this.geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(this.MAX_POINTS * 3);
    this.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    this.material = new THREE.PointsMaterial({
      size: this.pointSize(),
      color: this.pointColor(),
    });

    this.pointsObj = new THREE.Points(this.geometry, this.material);
    this.pointsObj.frustumCulled = false;

    // Rotate to match LiDAR coordinate system (Z-up vs Three.js Y-up)
    this.pointsObj.rotation.x = -Math.PI / 2;
    this.pointsObj.rotation.z = -Math.PI / 2;

    this.scene.add(this.pointsObj);

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
      this.camera.aspect = container.clientWidth / container.clientHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(container.clientWidth, container.clientHeight);
    });
    resizeObserver.observe(container);
  }

  updatePoints(positionsArray: Float32Array, count: number) {
    if (!this.geometry) return;

    this.lastCount = count;

    const positions = this.geometry.attributes['position'].array as Float32Array;
    const limit = Math.min(count * 3, this.MAX_POINTS * 3);

    if (count > 0) {
      positions.set(positionsArray.subarray(0, limit));
    }

    this.geometry.setDrawRange(0, count);
    this.geometry.attributes['position'].needsUpdate = true;
  }

  resetCamera() {
    this.camera.position.set(15, 15, 15);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  fitToPoints(paddingFactor = 1.25) {
    if (!this.geometry || !this.controls) return;
    if (!this.lastCount || this.lastCount <= 0) return;

    const attr = this.geometry.getAttribute('position') as THREE.BufferAttribute;
    const positions = attr.array as Float32Array;
    const count = Math.min(this.lastCount, this.MAX_POINTS);

    let minX = Infinity,
      minY = Infinity,
      minZ = Infinity;
    let maxX = -Infinity,
      maxY = -Infinity,
      maxZ = -Infinity;

    for (let i = 0; i < count; i++) {
      const x = positions[i * 3];
      const y = positions[i * 3 + 1];
      const z = positions[i * 3 + 2];
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (z < minZ) minZ = z;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
      if (z > maxZ) maxZ = z;
    }

    if (!isFinite(minX) || !isFinite(maxX)) return;

    const center = new THREE.Vector3(
      (minX + maxX) / 2,
      (minY + maxY) / 2,
      (minZ + maxZ) / 2,
    );
    const size = new THREE.Vector3(maxX - minX, maxY - minY, maxZ - minZ);
    const radius = Math.max(size.x, size.y, size.z) / 2;

    const fov = (this.camera.fov * Math.PI) / 180;
    const distance = (radius / Math.tan(fov / 2)) * paddingFactor + 0.1;

    // Keep the current view direction but reposition to fit
    const dir = new THREE.Vector3().subVectors(this.camera.position, this.controls.target).normalize();
    this.controls.target.copy(center);
    this.camera.position.copy(center.clone().add(dir.multiplyScalar(distance)));
    this.controls.update();
  }

  capturePng(filename = 'workspace.png') {
    if (!this.renderer) return;
    const dataUrl = this.renderer.domElement.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filename;
    a.click();
  }

  clear() {
    this.updatePoints(new Float32Array(0), 0);
  }

  private animate() {
    this.animationId = requestAnimationFrame(() => this.animate());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
