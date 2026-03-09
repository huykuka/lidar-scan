import {
  Component,
  ElementRef,
  OnInit,
  OnDestroy,
  ViewChild,
  input,
  effect,
  output,
  inject,
  HostListener,
} from '@angular/core';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { PointCloudRendererService } from '../../../../ml/services/point-cloud-renderer.service';
import { BoundingBoxRendererService } from '../../../../ml/services/bounding-box-renderer.service';
import { BoundingBox3D } from '../../../../core/models/ml.model';

@Component({
  selector: 'app-point-cloud',
  standalone: true,
  template: `<div
    #container
    class="w-full h-full min-h-0 bg-transparent rounded-lg overflow-hidden focus:outline-none focus:ring-2 focus:ring-blue-500"
    tabindex="0"
    title="ML Controls: M=toggle ML, L=labels, B=boxes, 1/2/3=color modes"
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
  enableMLRendering = input<boolean>(false);
  semanticColorMode = input<'original' | 'semantic' | 'mixed'>('original');

  // ML Services
  private pointCloudRenderer = inject(PointCloudRendererService);
  private boundingBoxRenderer = inject(BoundingBoxRendererService);

  // Three.js instances
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;

  // Multiple point clouds support with ML capabilities
  private pointClouds: Map<
    string,
    {
      pointsObj: THREE.Points;
      geometry: THREE.BufferGeometry;
      material: THREE.PointsMaterial;
      lastCount: number;
      semanticLabels?: Int32Array;
      originalColors?: Float32Array;
    }
  > = new Map();

  private gridHelper?: THREE.GridHelper;
  private axesHelper?: THREE.AxesHelper;
  private axesLabels: THREE.Sprite[] = [];
  private gridLabels: THREE.Sprite[] = [];
  private currentGridSize = 50;

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
        const isVisible = !!this.showGrid();
        this.gridHelper.visible = isVisible;
        this.gridLabels.forEach((l) => (l.visible = isVisible));
      }
    });

    effect(() => {
      if (this.axesHelper) {
        const isVisible = !!this.showAxes();
        this.axesHelper.visible = isVisible;
        this.axesLabels.forEach((l) => (l.visible = isVisible));
      }
    });

    // ML rendering effects
    effect(() => {
      const colorMode = this.semanticColorMode();
      this.pointCloudRenderer.setColorMode(colorMode);
      this.updateAllPointCloudsWithML();
    });

    effect(() => {
      const enableML = this.enableMLRendering();
      this.pointCloudRenderer.setRenderingOptions({ enableSemanticColors: enableML });
      if (!enableML) {
        // Switch back to original rendering when ML is disabled
        this.updateAllPointCloudsWithOriginalColors();
        this.boundingBoxRenderer.clearBoundingBoxes();
      } else {
        this.updateAllPointCloudsWithML();
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
    this.scene.background = new THREE.Color(0x000000);

    // Camera
    this.camera = new THREE.PerspectiveCamera(
      50,
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
    this.rebuildGrid();

    this.axesHelper = new THREE.AxesHelper(5);
    this.axesHelper.visible = !!this.showAxes();
    this.scene.add(this.axesHelper);

    // Axis Labels
    const axisX = this.createTextSprite('Y', '#ff0000');
    axisX.position.set(5.5, 0, 0);
    axisX.visible = !!this.showAxes();

    const axisY = this.createTextSprite('Z', '#00ff00');
    axisY.position.set(0, 5.5, 0);
    axisY.visible = !!this.showAxes();

    const axisZ = this.createTextSprite('X', '#0000ff');
    axisZ.position.set(0, 0, 5.5);
    axisZ.visible = !!this.showAxes();

    this.axesLabels = [axisX, axisY, axisZ];
    this.scene.add(...this.axesLabels);

    // Initialize ML services
    this.boundingBoxRenderer.initialize(this.scene);

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
    const colors = new Float32Array(this.MAX_POINTS * 3);
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: this.pointSize(),
      color: color,
      vertexColors: true, // Enable per-vertex coloring for ML
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
      semanticLabels: undefined,
      originalColors: undefined,
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

    const center = new THREE.Vector3((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2);
    const size = new THREE.Vector3(maxX - minX, maxY - minY, maxZ - minZ);
    const radius = Math.max(size.x, size.y, size.z) / 2;

    const fov = (this.camera.fov * Math.PI) / 180;
    const distance = (radius / Math.tan(fov / 2)) * paddingFactor + 0.1;

    // Keep the current view direction but reposition to fit
    const dir = new THREE.Vector3()
      .subVectors(this.camera.position, this.controls.target)
      .normalize();
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

  /**
   * Update points with ML data (semantic labels and/or bounding boxes)
   * @param topic Topic identifier
   * @param positionsArray Point positions as Float32Array
   * @param count Number of points
   * @param semanticLabels Optional semantic labels for each point
   * @param originalColors Optional original RGB colors for points
   */
  updatePointsWithMLData(
    topic: string,
    positionsArray: Float32Array,
    count: number,
    semanticLabels?: Int32Array,
    originalColors?: Float32Array
  ) {
    const cloud = this.pointClouds.get(topic);
    if (!cloud) return;

    cloud.lastCount = count;
    cloud.semanticLabels = semanticLabels;
    cloud.originalColors = originalColors;

    // Use ML renderer if enabled, otherwise use standard update
    if (this.enableMLRendering() && semanticLabels) {
      this.pointCloudRenderer.updatePointCloudWithLabels(
        cloud.geometry,
        cloud.material,
        positionsArray,
        count,
        semanticLabels,
        originalColors
      );
    } else {
      // Standard point cloud update
      this.updatePointsForTopic(topic, positionsArray, count);
    }
  }

  /**
   * Update bounding boxes for current frame
   * @param boxes Array of 3D bounding boxes
   */
  updateBoundingBoxes(boxes: BoundingBox3D[]) {
    if (this.enableMLRendering()) {
      this.boundingBoxRenderer.updateBoundingBoxes(boxes);
    }
  }

  /**
   * Toggle ML rendering capabilities
   * @param enabled Enable or disable ML features
   */
  setMLRenderingEnabled(enabled: boolean) {
    if (enabled) {
      this.updateAllPointCloudsWithML();
    } else {
      this.updateAllPointCloudsWithOriginalColors();
      this.boundingBoxRenderer.clearBoundingBoxes();
    }
  }

  /**
   * Set semantic color mode for point cloud rendering
   * @param mode Color mode: 'original', 'semantic', or 'mixed'
   */
  setSemanticColorMode(mode: 'original' | 'semantic' | 'mixed') {
    this.pointCloudRenderer.setColorMode(mode);
    this.updateAllPointCloudsWithML();
  }

  /**
   * Update all point clouds with ML rendering
   */
  private updateAllPointCloudsWithML() {
    if (!this.enableMLRendering()) return;

    this.pointClouds.forEach((cloud) => {
      if (cloud.semanticLabels && cloud.lastCount > 0) {
        this.pointCloudRenderer.updatePointCloudWithLabels(
          cloud.geometry,
          cloud.material,
          cloud.geometry.getAttribute('position').array as Float32Array,
          cloud.lastCount,
          cloud.semanticLabels,
          cloud.originalColors
        );
      }
    });
  }

  /**
   * Revert all point clouds to original colors
   */
  private updateAllPointCloudsWithOriginalColors() {
    this.pointClouds.forEach((cloud) => {
      this.pointCloudRenderer.applyOriginalColors(
        cloud.geometry,
        cloud.material,
        cloud.originalColors,
        cloud.lastCount
      );
    });
  }

  /**
   * Keyboard shortcuts for ML features
   */
  @HostListener('window:keydown', ['$event'])
  onKeyDown(event: KeyboardEvent) {
    // Only process when component has focus
    if (!this.containerRef?.nativeElement.contains(document.activeElement)) {
      return;
    }

    switch (event.key.toLowerCase()) {
      case 'm':
        // Toggle ML rendering
        if (!event.ctrlKey && !event.altKey) {
          // This would be handled by parent component
          event.preventDefault();
        }
        break;
      case 'l':
        // Toggle semantic labels
        if (!event.ctrlKey && !event.altKey) {
          this.pointCloudRenderer.toggleSemanticColors();
          this.updateAllPointCloudsWithML();
          event.preventDefault();
        }
        break;
      case 'b':
        // Toggle bounding boxes
        if (!event.ctrlKey && !event.altKey) {
          const currentVisibility = this.boundingBoxRenderer.getActiveBoxCount() > 0;
          this.boundingBoxRenderer.setVisible(!currentVisibility);
          event.preventDefault();
        }
        break;
      case '1':
        this.pointCloudRenderer.setColorMode('original');
        this.updateAllPointCloudsWithML();
        event.preventDefault();
        break;
      case '2':
        this.pointCloudRenderer.setColorMode('semantic');
        this.updateAllPointCloudsWithML();
        event.preventDefault();
        break;
      case '3':
        this.pointCloudRenderer.setColorMode('mixed');
        this.updateAllPointCloudsWithML();
        event.preventDefault();
        break;
    }
  }

  /**
   * Add focus handling for keyboard shortcuts
   */
  focusComponent() {
    this.containerRef.nativeElement.focus();
  }

  private animate() {
    this.animationId = requestAnimationFrame(() => this.animate());
    this.controls.update();

    // Dynamically scale text sprites based on camera distance
    const spritesToScale = [...this.gridLabels, ...this.axesLabels];
    spritesToScale.forEach((label) => {
      if (!label.visible) return;
      const distance = this.camera.position.distanceTo(label.position);
      // Determine a base scale factor that makes it readable but appropriately small
      const scaleBase = Math.max(0.2, distance * 0.05);
      label.scale.set(scaleBase * 2, scaleBase, 1);
    });

    this.renderer.render(this.scene, this.camera);
  }

  private rebuildGrid() {
    if (this.gridHelper) {
      this.scene.remove(this.gridHelper);
      this.gridHelper.dispose();
    }

    const size = this.currentGridSize; // Always 50
    const stepLines = 10; // Labels every 10m
    const divisions = size / stepLines; // 5 divisions across the 50m grid

    this.gridHelper = new THREE.GridHelper(size, divisions, 0x555555, 0x333333);
    this.gridHelper.position.y = -0.1; // lower to avoid z-fighting
    this.gridHelper.visible = !!this.showGrid();
    this.scene.add(this.gridHelper);

    // Remove old labels
    this.gridLabels.forEach((label) => {
      this.scene.remove(label);
      if (label.material.map) label.material.map.dispose();
      label.material.dispose();
    });
    this.gridLabels = [];

    const halfSize = size / 2;
    for (let i = -halfSize; i <= halfSize; i += stepLines) {
      if (i === 0) continue;

      const spriteX = this.createTextSprite(`${i}m`);
      spriteX.position.set(i, 0, halfSize + stepLines * 0.2);
      spriteX.visible = !!this.showGrid();
      this.gridLabels.push(spriteX);
      this.scene.add(spriteX);

      const spriteZ = this.createTextSprite(`${i}m`);
      spriteZ.position.set(halfSize + stepLines * 0.2, 0, i);
      spriteZ.visible = !!this.showGrid();
      this.gridLabels.push(spriteZ);
      this.scene.add(spriteZ);
    }
  }

  private createTextSprite(message: string, color: string = '#888888'): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 64;
    const context = canvas.getContext('2d')!;
    context.fillStyle = 'rgba(0,0,0,0)';
    context.fillRect(0, 0, canvas.width, canvas.height);

    context.font = 'bold 20px ';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillStyle = color;
    context.fillText(message, canvas.width / 2, canvas.height / 2);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const material = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthWrite: true,
    });
    const sprite = new THREE.Sprite(material);

    // Dynamic scaling happens in animate() to make it responsive to zoom
    return sprite;
  }
}
