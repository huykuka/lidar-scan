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
  showGrid = input<boolean>(true);
  showAxes = input<boolean>(true);

  // Three.js instances
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;
  
  // Multiple point clouds support
  private pointClouds: Map<
    string,
    {
      pointsObj: THREE.Points;
      geometry: THREE.BufferGeometry;
      material: THREE.PointsMaterial;
      lastCount: number;
    }
  > = new Map();
  
  private gridHelper?: THREE.GridHelper;
  private axesHelper?: THREE.AxesHelper;

  private animationId?: number;
  private readonly MAX_POINTS = 50000;

  constructor() {
    // React to input changes
    effect(() => {
      // Update point size for all clouds
      const size = this.pointSize();
      this.pointClouds.forEach(({ material }) => {
        material.size = size;
      });
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
    // Dispose all point clouds
    this.pointClouds.forEach(({ geometry, material }) => {
      geometry.dispose();
      material.dispose();
    });
    this.pointClouds.clear();
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

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
      this.camera.aspect = container.clientWidth / container.clientHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(container.clientWidth, container.clientHeight);
    });
    resizeObserver.observe(container);
  }

  /**
   * Add or update a point cloud for a specific topic
   * @param topic Topic identifier
   * @param color Color for this point cloud
   */
  addOrUpdatePointCloud(topic: string, color: string) {
    if (this.pointClouds.has(topic)) {
      // Update existing cloud color
      const cloud = this.pointClouds.get(topic)!;
      cloud.material.color.set(color);
      return;
    }

    // Create new point cloud
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(this.MAX_POINTS * 3);
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.PointsMaterial({
      size: this.pointSize(),
      color: color,
    });

    const pointsObj = new THREE.Points(geometry, material);
    pointsObj.frustumCulled = false;

    // Rotate to match LiDAR coordinate system (Z-up vs Three.js Y-up)
    pointsObj.rotation.x = -Math.PI / 2;
    pointsObj.rotation.z = -Math.PI / 2;

    this.scene.add(pointsObj);

    this.pointClouds.set(topic, {
      pointsObj,
      geometry,
      material,
      lastCount: 0,
    });
  }

  /**
   * Remove a point cloud for a specific topic
   * @param topic Topic identifier
   */
  removePointCloud(topic: string) {
    const cloud = this.pointClouds.get(topic);
    if (!cloud) return;

    this.scene.remove(cloud.pointsObj);
    cloud.geometry.dispose();
    cloud.material.dispose();
    this.pointClouds.delete(topic);
  }

  /**
   * Update points for a specific topic
   * @param topic Topic identifier
   * @param positionsArray Point positions as Float32Array
   * @param count Number of points
   */
  updatePointsForTopic(topic: string, positionsArray: Float32Array, count: number) {
    const cloud = this.pointClouds.get(topic);
    if (!cloud) return;

    cloud.lastCount = count;

    const positions = cloud.geometry.attributes['position'].array as Float32Array;
    const limit = Math.min(count * 3, this.MAX_POINTS * 3);

    if (count > 0) {
      positions.set(positionsArray.subarray(0, limit));
    }

    cloud.geometry.setDrawRange(0, count);
    cloud.geometry.attributes['position'].needsUpdate = true;
  }

  /**
   * Legacy method for backwards compatibility - updates the first point cloud
   */
  updatePoints(positionsArray: Float32Array, count: number) {
    // If no point clouds exist, create a default one
    if (this.pointClouds.size === 0) {
      this.addOrUpdatePointCloud('default', '#00ff00');
    }

    // Update first (or only) point cloud
    const firstTopic = Array.from(this.pointClouds.keys())[0];
    this.updatePointsForTopic(firstTopic, positionsArray, count);
  }

  /**
   * Get total point count across all clouds
   */
  getTotalPointCount(): number {
    let total = 0;
    this.pointClouds.forEach(({ lastCount }) => {
      total += lastCount;
    });
    return total;
  }

  resetCamera() {
    this.camera.position.set(15, 15, 15);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  /**
   * Set camera to top view (looking down at XZ plane)
   */
  setTopView() {
    const distance = 30;
    this.camera.position.set(0, distance, 0);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  /**
   * Set camera to front view (looking along Y axis)
   */
  setFrontView() {
    const distance = 30;
    this.camera.position.set(0, 0, distance);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  /**
   * Set camera to side view (looking along X axis)
   */
  setSideView() {
    const distance = 30;
    this.camera.position.set(distance, 0, 0);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  /**
   * Set camera to isometric view (45° angle)
   */
  setIsometricView() {
    const distance = 30;
    this.camera.position.set(distance, distance, distance);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  fitToPoints(paddingFactor = 1.25) {
    if (!this.controls) return;
    if (this.pointClouds.size === 0) return;

    let minX = Infinity,
      minY = Infinity,
      minZ = Infinity;
    let maxX = -Infinity,
      maxY = -Infinity,
      maxZ = -Infinity;

    // Calculate bounding box across all point clouds
    this.pointClouds.forEach(({ geometry, lastCount }) => {
      if (lastCount <= 0) return;

      const attr = geometry.getAttribute('position') as THREE.BufferAttribute;
      const positions = attr.array as Float32Array;
      const count = Math.min(lastCount, this.MAX_POINTS);

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
    });

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
    // Clear all point clouds
    this.pointClouds.forEach((cloud, topic) => {
      this.updatePointsForTopic(topic, new Float32Array(0), 0);
    });
  }

  private animate() {
    this.animationId = requestAnimationFrame(() => this.animate());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
