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

  // Three.js instances
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;
  private pointsObj!: THREE.Points;
  private geometry!: THREE.BufferGeometry;
  private material!: THREE.PointsMaterial;

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
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    // Controls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0, 0);

    // Grid & Axes
    const grid = new THREE.GridHelper(20, 20, 0x555555, 0x333333);
    this.scene.add(grid);
    const axes = new THREE.AxesHelper(5);
    this.scene.add(axes);

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

  clear() {
    this.updatePoints(new Float32Array(0), 0);
  }

  private animate() {
    this.animationId = requestAnimationFrame(() => this.animate());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
