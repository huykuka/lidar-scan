import {AfterViewInit, Component, effect, ElementRef, inject, input, OnDestroy, OnInit, viewChild} from '@angular/core';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {PointCloudDataService} from '@core/services/point-cloud-data.service';
import {ViewOrientation} from '@core/services/split-layout-store.service';
import {WorkspaceStoreService} from '@core/services/stores/workspace-store.service';

@Component({
  selector: 'app-point-cloud',
  template: `
    <div
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
export class PointCloudComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly containerRef = viewChild.required<ElementRef<HTMLDivElement>>('container');

  // Inputs for customization
  pointSize = input<number>(0.1);
  showGrid = input<boolean>(true);
  showAxes = input<boolean>(true);
  backgroundColor = input<string>('#000000');

  // ── New signal inputs (FE-04) ─────────────────────────────────────────────
  /** Camera mode: perspective (default) or orthographic (top/front/side) */
  viewType = input<ViewOrientation>('perspective');
  /** Stable pane ID — used to key into PointCloudDataService.frames() */
  viewId = input<string>('');
  /** When true, caps rendering at MAX_POINTS_LOD to reduce GPU load */
  adaptiveLod = input<boolean>(false);

  // Three.js instances
  private scene!: THREE.Scene;
  /** Perspective camera — active when viewType() === 'perspective' */
  private perspCamera!: THREE.PerspectiveCamera;
  /** Orthographic camera — active for top / front / side views */
  private orthoCamera!: THREE.OrthographicCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;

  /** ResizeObserver — keeps canvas size in sync when pane dimensions change */
  private resizeObserver?: ResizeObserver;

  /** Injected data service — provides shared frame signals per topic */
  readonly dataService = inject(PointCloudDataService);

  /** Injected workspace store — provides selected topics with colors */
  private readonly workspaceStore = inject(WorkspaceStoreService);

  // Multiple point clouds support
  readonly pointClouds: Map<
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
  private axesLabels: THREE.Sprite[] = [];
  private gridLabels: THREE.Sprite[] = [];
  private currentGridSize = 50;

  private animationId?: number;
  /** Full-quality cap (default: no adaptive LOD) */
  readonly MAX_POINTS = 50_000;
  /** Reduced cap used when adaptiveLod input is true */
  readonly MAX_POINTS_LOD = 25_000;

  /**
   * Returns the active Three.js camera based on the current viewType input.
   * Perspective view → PerspectiveCamera; all orthometric views → OrthographicCamera.
   */
  private get activeCamera(): THREE.Camera {
    return this.viewType() === 'perspective' ? this.perspCamera : this.orthoCamera;
  }

  /**
   * Returns the effective MAX_POINTS limit, respecting adaptiveLod flag.
   * Exposed as a helper so it can be tested without a live WebGL context.
   */
  getEffectiveMaxPoints(lodActive: boolean): number {
    return lodActive ? this.MAX_POINTS_LOD : this.MAX_POINTS;
  }

  constructor() {
    // React to input changes
    effect(() => {
      // Update point size for all clouds
      const size = this.pointSize();
      this.pointClouds.forEach(({material}) => {
        material.size = size;
      });
    });

    effect(() => {
      if (this.gridHelper) {
        const isVisible = this.showGrid();
        this.gridHelper.visible = isVisible;
        this.gridLabels.forEach((l) => (l.visible = isVisible));
      }
    });

    effect(() => {
      if (this.axesHelper) {
        const isVisible = this.showAxes();
        this.axesHelper.visible = isVisible;
        this.axesLabels.forEach((l) => (l.visible = isVisible));
      }
    });

    effect(() => {
      const color = this.backgroundColor();
      if (this.scene) {
        this.scene.background = new THREE.Color(color);
      }
    });

    // ── FE-04: React to viewType changes → switch camera preset ──────────────
    effect(() => {
      const vt = this.viewType();
      if (this.controls) {
        // Only call initCamera once Three.js is bootstrapped
        this.initCamera(vt);
      }
    });

    effect(() => {
      if (!this.scene) return;
      this.syncTopicClouds();
    });

    // ── FE-04: Subscribe to PointCloudDataService frames signal ──────────────
    effect(() => {
      const frames = this.dataService.frames();
      if (!frames.size) return;
      frames.forEach((frame, topic) => {
        if (this.pointClouds.has(topic)) {
          this.updatePointsForTopic(topic, frame.points, frame.count);
        }
      });
    });
  }

  ngOnInit() {
  }

  ngAfterViewInit() {
    this.initThree();
    // Initialize point clouds for all currently selected topics now that
    // the Three.js scene is ready. Subsequent changes are handled by effect().
    this.syncTopicClouds();
    this.animate();
    // ResizeObserver keeps canvas in sync whenever the pane is resized
    // (including the initial paint, layout-switch re-paints, and divider drags).
    this.resizeObserver = new ResizeObserver(() => this.syncSize());
    this.resizeObserver.observe(this.containerRef().nativeElement);
  }

  ngOnDestroy() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
    }
    this.resizeObserver?.disconnect();
    // Dispose all point clouds
    this.pointClouds.forEach(({geometry, material}) => {
      geometry.dispose();
      material.dispose();
    });
    this.pointClouds.clear();
    // Dispose renderer if it was ever initialized
    this.renderer?.dispose();
    // Null cameras for GC (Three.js cameras have no .dispose())
    this.perspCamera = null as unknown as THREE.PerspectiveCamera;
    this.orthoCamera = null as unknown as THREE.OrthographicCamera;
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
      // Bug fix: sizeAttenuation: false keeps point size in screen-pixels (not
      // world units), so all panels — perspective AND orthographic — render dots
      // at the same pixel size regardless of camera type or frustum dimensions.
      sizeAttenuation: false,
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

    // ── FE-04: Adaptive LOD — cap points when pane is small ──────────────────
    const effectiveMax = this.getEffectiveMaxPoints(this.adaptiveLod());

    cloud.lastCount = Math.min(count, effectiveMax);

    const positions = cloud.geometry.attributes['position'].array as Float32Array;
    const limit = Math.min(count * 3, effectiveMax * 3);

    if (count > 0) {
      positions.set(positionsArray.subarray(0, limit));
    }

    cloud.geometry.setDrawRange(0, cloud.lastCount);
    cloud.geometry.attributes['position'].needsUpdate = true;
  }


  resetCamera() {
    this.perspCamera.position.set(15, 15, 15);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }


  /**
   * Synchronise Three.js point cloud objects with the currently selected topics.
   * Called once from ngAfterViewInit (after scene is ready) and from the
   * selectedTopics effect() for subsequent changes.
   */
  private syncTopicClouds(): void {
    const selectedTopics = this.workspaceStore.selectedTopics();
    const enabledSet = new Set(selectedTopics.filter(t => t.enabled).map(t => t.topic));

    // Remove clouds for topics no longer enabled
    Array.from(this.pointClouds.keys()).forEach(topic => {
      if (!enabledSet.has(topic)) {
        this.removePointCloud(topic);
      }
    });

    // Add or update clouds for enabled topics
    selectedTopics.forEach(({ topic, color, enabled }) => {
      if (!enabled) return;
      this.addOrUpdatePointCloud(topic, color);
    });
  }

  private syncSize() {
    const container = this.containerRef().nativeElement;
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w > 0 && h > 0) {
      const aspect = w / h;

      // Update perspective camera
      if (this.perspCamera) {
        this.perspCamera.aspect = aspect;
        this.perspCamera.updateProjectionMatrix();
      }

      // Update orthographic camera frustum
      if (this.orthoCamera) {
        const frustumSize = 40;
        this.orthoCamera.left = (-frustumSize * aspect) / 2;
        this.orthoCamera.right = (frustumSize * aspect) / 2;
        this.orthoCamera.top = frustumSize / 2;
        this.orthoCamera.bottom = -frustumSize / 2;
        this.orthoCamera.updateProjectionMatrix();
      }

      this.renderer.setSize(w, h);
    }
  }

  private initThree() {
    const container = this.containerRef().nativeElement;
    const aspect = container.clientWidth / Math.max(container.clientHeight, 1);
    const frustumSize = 40;

    // Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(this.backgroundColor());

    // ── Perspective camera (default / perspective view) ───────────────────────
    this.perspCamera = new THREE.PerspectiveCamera(50, aspect, 0.1, 1000);
    this.perspCamera.position.set(15, 15, 15);
    this.perspCamera.lookAt(0, 0, 0);

    // ── Orthographic camera (top / front / side views) ────────────────────────
    this.orthoCamera = new THREE.OrthographicCamera(
      (-frustumSize * aspect) / 2,
      (frustumSize * aspect) / 2,
      frustumSize / 2,
      -frustumSize / 2,
      0.1,
      1000,
    );
    this.orthoCamera.position.set(0, 30, 0);
    this.orthoCamera.lookAt(0, 0, 0);

    // Renderer
    this.renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    // Controls — always attach to the active camera's type
    this.controls = new OrbitControls(this.perspCamera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0, 0);

    // Apply initial camera preset from viewType input
    this.initCamera(this.viewType());

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

    // Resize observer
    const resizeObserver = new ResizeObserver(() => this.syncSize());
    resizeObserver.observe(container);
  }

  /**
   * Configure the camera position and controls based on the view orientation.
   * Perspective → PerspectiveCamera at (15,15,15), rotation enabled.
   * top/front/side → OrthographicCamera at respective axis positions, rotation disabled.
   */
  private initCamera(viewType: ViewOrientation): void {
    if (!this.controls) return;

    const distance = 30;

    if (viewType === 'perspective') {
      this.perspCamera.position.set(15, 15, 15);
      this.perspCamera.lookAt(0, 0, 0);
      this.controls.object = this.perspCamera;
      this.controls.enableRotate = true;
    } else {
      switch (viewType) {
        case 'top':
          this.orthoCamera.position.set(0, distance, 0);
          break;
        case 'front':
          this.orthoCamera.position.set(0, 0, distance);
          break;
        case 'side':
          this.orthoCamera.position.set(distance, 0, 0);
          break;
      }
      this.orthoCamera.lookAt(0, 0, 0);
      this.controls.object = this.orthoCamera;
      this.controls.enableRotate = false;
    }

    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  private animate() {
    this.animationId = requestAnimationFrame(() => this.animate());
    this.controls.update();

    // Dynamically scale text sprites based on active camera distance
    const cam = this.activeCamera;
    const spritesToScale = [...this.gridLabels, ...this.axesLabels];
    spritesToScale.forEach((label) => {
      if (!label.visible) return;
      const distance = cam.position.distanceTo(label.position);
      // Determine a base scale factor that makes it readable but appropriately small
      const scaleBase = Math.max(0.2, distance * 0.05);
      label.scale.set(scaleBase * 2, scaleBase, 1);
    });

    this.renderer.render(this.scene, this.activeCamera);
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
      spriteX.visible = this.showGrid();
      this.gridLabels.push(spriteX);
      this.scene.add(spriteX);

      const spriteZ = this.createTextSprite(`${i}m`);
      spriteZ.position.set(halfSize + stepLines * 0.2, 0, i);
      spriteZ.visible = this.showGrid();
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
