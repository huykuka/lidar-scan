import {
  ChangeDetectionStrategy,
  AfterViewInit,
  Component,
  effect,
  ElementRef,
  inject,
  input,
  OnDestroy,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { PointCloudDataService, type FramePayload } from '@core/services/point-cloud-data.service';
import { ViewOrientation, SplitLayoutStoreService } from '@core/services/split-layout-store.service';
import { WorkspaceStoreService } from '@core/services/stores/workspace-store.service';
import { ShapeLayerService } from '@core/services/shape-layer.service';
import { ShapesWsService } from '@core/services/shapes-ws.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-point-cloud',
  imports: [SynergyComponentsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,

  /**
   * ShapeLayerService is provided HERE — at the component level — so that
   * Angular creates a **fresh, isolated instance** for every PointCloudComponent
   * in the DOM tree (i.e. every split-view pane).
   *
   * This is the architectural guarantee that prevents:
   *   • Scene cross-contamination (shapes from pane A appearing in pane B)
   *   • The "last init wins" race where the global singleton's `scene` ref
   *     is overwritten by the most-recently-mounted pane
   *   • disposeAll() in one pane nuking shape objects owned by another pane
   *
   * DO NOT move this back to providedIn: 'root'.
   */
  providers: [ShapeLayerService],
  template: ` <div #container class="w-full h-full min-h-0 bg-transparent overflow-hidden"></div>
    @if (hasError()) {
      <div
        class="absolute inset-0 flex flex-col items-center justify-center bg-black/70 rounded-lg z-10 p-4 text-center"
      >
        <syn-icon name="error" class="text-4xl text-red-400 mb-2" />
        <p class="text-white font-semibold text-sm">Rendering Error</p>
        <p class="text-syn-color-neutral-300 text-xs mt-1 break-all">{{ errorMessage() }}</p>
      </div>
    }`,
  styles: [
    `
      :host {
        display: block;
        width: 100%;
        height: 100%;
        position: relative;
      }
    `,
  ],
})
export class PointCloudComponent implements AfterViewInit, OnDestroy {
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
  /** When true, reduces MAX_POINTS cap to MAX_POINTS_LOD for performance */
  adaptiveLod = input<boolean>(false);

  // ── FE-12: Error boundary signals ────────────────────────────────────────
  /** Set to true if initThree() throws — causes the error overlay to appear. */
  readonly hasError = signal(false);
  /** Human-readable error message captured from the caught exception. */
  readonly errorMessage = signal('');

  // Three.js instances
  private scene!: THREE.Scene;
  /** Perspective camera — active when viewType() === 'perspective' */
  private perspCamera!: THREE.PerspectiveCamera;
  /** Orthographic camera — active for top / front / side views */
  private orthoCamera!: THREE.OrthographicCamera;
  private renderer!: THREE.WebGLRenderer;
  private controls!: OrbitControls;
  private readonly controlsChangeHandler = () => this.requestRender();

  /** ResizeObserver — keeps canvas size in sync when pane dimensions change */
  private resizeObserver?: ResizeObserver;

  /** Injected data service — provides shared frame signals per topic */
  readonly dataService = inject(PointCloudDataService);

  /** Injected workspace store — provides selected topics with colors */
  private readonly workspaceStore = inject(WorkspaceStoreService);
  /** Injected split layout store — used to react to camera reset requests */
  private readonly splitLayout = inject(SplitLayoutStoreService);

  /** Injected shape layer service — owns Three.js shape objects on Layer 2 */
  private readonly shapeLayerService = inject(ShapeLayerService);

  /** Injected shapes WebSocket service — streams ShapeFrame events */
  private readonly shapesWsService = inject(ShapesWsService);

  /** RxJS subscription for the shapes stream — cleaned up in ngOnDestroy */
  private shapesSubscription?: Subscription;

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
  private readonly lastAppliedFrames = new Map<string, FramePayload>();

  /** Previous snapshot of enabled topics used to diff against next update. */
  private prevTopicSnapshot = new Map<string, string>(); // topic → color

  /** All scene objects owned by the grid system — disposed on rebuild/destroy */
  private gridObjects: THREE.Object3D[] = [];
  private axesLabels: THREE.Sprite[] = [];
  private gridLabels: THREE.Sprite[] = [];
  private currentGridSize = 30;

  // ── HUD axis gizmo (inset bottom-left) ───────────────────────────────────
  private gizmoScene!: THREE.Scene;
  private gizmoCamera!: THREE.PerspectiveCamera;
  /** Size of the gizmo viewport in CSS pixels */
  private readonly GIZMO_SIZE = 120;

  private animationId?: number;
  /**
   * Dirty flag — when true the next animation-loop tick will actually call
   * renderer.render().  Every mutation that touches the scene graph, camera
   * or material must call requestRender() so the flag is set.
   */
  private needsRender = true;
  /** Full-quality cap (default: no adaptive LOD) */
  readonly MAX_POINTS = 250_000;
  /** Reduced cap used when adaptiveLod input is true */
  readonly MAX_POINTS_LOD = 125_000;

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
      this.pointClouds.forEach(({ material }) => {
        material.size = size;
      });
      this.requestRender();
    });

    effect(() => {
      if (this.gridObjects.length) {
        const isVisible = this.showGrid();
        this.gridObjects.forEach((o) => (o.visible = isVisible));
        this.gridLabels.forEach((l) => (l.visible = isVisible));
        this.requestRender();
      }
    });

    effect(() => {
      if (this.gizmoScene) {
        const isVisible = this.showAxes();
        this.gizmoScene.visible = isVisible;
        this.requestRender();
      }
    });

    effect(() => {
      const color = this.backgroundColor();
      if (this.scene) {
        this.scene.background = new THREE.Color(color);
        this.requestRender();
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

    // React to camera reset requests from the overlay
    effect(() => {
      const req = this.splitLayout.resetCameraRequest();
      if (req?.paneId === this.viewId() && this.controls) {
        this.resetCamera();
      }
    });

    // Re-sync Three.js point cloud objects whenever selected topics change.
    // Deferred until scene is ready; initial call from ngAfterViewInit handles
    // the bootstrap case so no changes are lost.
    effect(() => {
      const selectedTopics = this.workspaceStore.selectedTopics();
      if (!this.scene) return;
      this.diffAndSyncTopics(selectedTopics);
    });

    // ── FE-04: Subscribe to PointCloudDataService frames signal ──────────────
    effect(() => {
      const frames = this.dataService.frames();
      if (!frames.size) return;
      this.syncFrameBuffers(frames);
    });
  }

  ngAfterViewInit() {
    try {
      this.initThree();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error('[PointCloudComponent] Failed to initialize Three.js renderer:', err);
      this.hasError.set(true);
      this.errorMessage.set(message);
      return; // Don't attempt syncTopicClouds or animate
    }
    // Bootstrap: sync topics now that the scene is ready.
    // Subsequent changes are handled by the selectedTopics effect().
    this.diffAndSyncTopics(this.workspaceStore.selectedTopics());
    this.animate();

    // ── FE-06: Initialize shape layer and subscribe to shapes stream ──────────
    this.shapeLayerService.init(this.scene);
    // Enable all camera layers so shape objects on Layer 2 are rendered
    this.perspCamera.layers.enableAll();
    this.orthoCamera.layers.enableAll();
    this.shapesSubscription = this.shapesWsService.frames$.subscribe((frame) => {
      this.shapeLayerService.applyFrame(frame);
      this.requestRender();
    });
    // ResizeObserver keeps canvas in sync whenever the pane is resized
    // (including the initial paint, layout-switch re-paints, and divider drags).
    this.resizeObserver = new ResizeObserver(() => this.syncSize());
    this.resizeObserver.observe(this.containerRef().nativeElement);
  }

  ngOnDestroy() {
    // ── FE-06: Clean up shapes subscription and dispose shape objects ─────────
    this.shapesSubscription?.unsubscribe();
    this.shapeLayerService.disposeAll();

    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
    }
    this.resizeObserver?.disconnect();
    this.controls?.removeEventListener('change', this.controlsChangeHandler);
    this.controls?.dispose();
    this.disposeSpriteGroup(this.gridLabels);
    this.gridLabels = [];
    this.disposeSpriteGroup(this.axesLabels);
    this.axesLabels = [];
    this.disposeGridObjects();
    // Dispose all point clouds
    this.pointClouds.forEach(({ pointsObj, geometry, material }) => {
      this.scene?.remove(pointsObj);
      geometry.dispose();
      material.dispose();
    });
    this.pointClouds.clear();
    this.lastAppliedFrames.clear();
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
      // Already exists — diffAndSyncTopics handles color-only updates separately.
      // This path is kept for callers that bypass the diff (e.g. direct invocation).
      const cloud = this.pointClouds.get(topic)!;
      if (cloud.material.color.getHexString() !== new THREE.Color(color).getHexString()) {
        cloud.material.color.set(color);
        this.requestRender();
      }
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
    this.requestRender();
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
    this.lastAppliedFrames.delete(topic);
    this.requestRender();
  }

  private syncFrameBuffers(frames: Map<string, FramePayload>): void {
    frames.forEach((frame, topic) => {
      if (!this.pointClouds.has(topic)) return;
      if (this.lastAppliedFrames.get(topic) === frame) return;

      this.lastAppliedFrames.set(topic, frame);
      this.updatePointsForTopic(topic, frame.points, frame.count);
    });
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

    const positions = cloud.geometry.attributes['position'].array as Float32Array;

    // Copy incoming point data into the pre-allocated buffer
    const copyCount = Math.min(count, this.MAX_POINTS);
    positions.set(positionsArray.subarray(0, copyCount * 3));

    // Update draw range and mark attribute dirty
    cloud.lastCount = copyCount;
    cloud.geometry.setDrawRange(0, copyCount);
    cloud.geometry.attributes['position'].needsUpdate = true;
    this.requestRender();
  }

  resetCamera() {
    this.initCamera(this.viewType());
  }

  /**
   * Diff the incoming topic list against the previous snapshot and apply only
   * the minimum set of Three.js operations needed:
   *   - Remove clouds for topics that are no longer enabled
   *   - Update material color for topics whose color changed
   *   - Create a new cloud only for genuinely new enabled topics
   *
   * Called both from `ngAfterViewInit` (bootstrap) and the selectedTopics effect.
   */
  private diffAndSyncTopics(
    selectedTopics: { topic: string; color: string; enabled: boolean }[],
  ): void {
    // Build the incoming enabled snapshot: topic → color
    const next = new Map<string, string>();
    for (const { topic, color, enabled } of selectedTopics) {
      if (enabled) next.set(topic, color);
    }

    // 1. Remove clouds that are no longer in the enabled set
    for (const topic of this.pointClouds.keys()) {
      if (!next.has(topic)) this.removePointCloud(topic);
    }

    // 2. Add new or update color-changed clouds
    for (const [topic, color] of next) {
      const prev = this.prevTopicSnapshot.get(topic);
      if (prev === undefined) {
        // New topic — create cloud
        this.addOrUpdatePointCloud(topic, color);
      } else if (prev !== color) {
        // Color changed — update material only (no geometry allocation)
        const cloud = this.pointClouds.get(topic);
        if (cloud) {
          cloud.material.color.set(color);
          this.requestRender();
        }
      }
      // else: topic exists with same color — no-op
    }

    this.prevTopicSnapshot = next;
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
      this.requestRender();
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
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(this.renderer.domElement);

    // Controls — always attach to the active camera's type
    this.controls = new OrbitControls(this.perspCamera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0, 0);

    // Mark frame dirty whenever OrbitControls moves the camera (includes damping ticks)
    this.controls.addEventListener('change', this.controlsChangeHandler);

    // Apply initial camera preset from viewType input
    this.initCamera(this.viewType());

    // Grid & Axes
    this.rebuildGrid();

    // HUD axis gizmo (bottom-left inset)
    this.initGizmo();
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
      // Reset up vector to default; override below where needed
      this.orthoCamera.up.set(0, 1, 0);

      switch (viewType) {
        case 'top':
          this.orthoCamera.position.set(0, distance, 0);
          this.orthoCamera.up.set(0, 0, -1);
          break;
        case 'bottom':
          this.orthoCamera.position.set(0, -distance, 0);
          this.orthoCamera.up.set(0, 0, 1);
          break;
        case 'front':
          this.orthoCamera.position.set(0, 0, distance);
          break;
        case 'end':
          this.orthoCamera.position.set(0, 0, -distance);
          break;
        case 'left':
          this.orthoCamera.position.set(-distance, 0, 0);
          break;
        case 'right':
          this.orthoCamera.position.set(distance, 0, 0);
          break;
      }
      this.orthoCamera.lookAt(0, 0, 0);
      this.controls.object = this.orthoCamera;
      this.controls.enableRotate = false;
    }

    this.controls.target.set(0, 0, 0);
    this.controls.update();
    this.requestRender();
  }

  /**
   * Mark the scene as needing a repaint on the next animation-loop tick.
   * Cheap to call many times per frame — only the next tick will render.
   */
  requestRender(): void {
    this.needsRender = true;
  }

  private animate() {
    this.animationId = requestAnimationFrame(() => this.animate());
    // controls.update() must run every tick for damping to work;
    // it fires the 'change' event (→ requestRender) only when the camera actually moves.
    this.controls.update();

    if (!this.needsRender) return;
    this.needsRender = false;

    // Dynamically scale text sprites based on active camera distance
    const cam = this.activeCamera;
    // Grid labels are fixed-orientation meshes — no per-frame scale needed.

    // Main scene
    this.renderer.render(this.scene, this.activeCamera);

    // HUD gizmo — overlay without clearing the colour buffer (SMC pattern)
    if (this.gizmoScene?.visible !== false) {
      this.renderer.autoClear = false;
      this.renderGizmo();
      this.renderer.autoClear = true;
    }
  }

  /**
   * Build the HUD gizmo scene (SMC pattern):
   *  - OrthographicCamera (no foreshortening — axes stay the same apparent size)
   *  - Three thin line stems + canvas letter sprites (no ArrowHelper, no background disc)
   *  - depthTest:false on sprites so letters always paint on top
   *
   * Axis label → Three.js direction mapping (LiDAR Z-up, point cloud rotated
   * rx=-PI/2 rz=-PI/2):
   *   LiDAR X  →  Three.js +Z  →  red   (syn-color-error-500   #f93a3f)
   *   LiDAR Y  →  Three.js +X  →  green (syn-color-success-500 #4fc275)
   *   LiDAR Z  →  Three.js +Y  →  blue  (syn-color-primary-500 #3183fe)
   */
  private initGizmo(): void {
    this.gizmoScene = new THREE.Scene();
    this.gizmoScene.visible = !!this.showAxes();

    // OrthographicCamera — matches SMC exactly; frustum ±1.7 gives comfortable padding
    this.gizmoCamera = new THREE.OrthographicCamera(
      -1.7, 1.7, 1.7, -1.7, 0.1, 50,
    ) as unknown as THREE.PerspectiveCamera;

    // Synergy design-system colors (sick2025-dark):
    //   error-500   #f93a3f  → LiDAR X
    //   success-500 #4fc275  → LiDAR Y
    //   primary-500 #3183fe  → LiDAR Z (up)
    const AXES: { dir: THREE.Vector3; hex: string; lineColor: number; label: string }[] = [
      { dir: new THREE.Vector3(0, 0, 1), hex: '#f93a3f', lineColor: 0xf93a3f, label: 'X' }, // LiDAR X  → Three.js +Z
      { dir: new THREE.Vector3(1, 0, 0), hex: '#4fc275', lineColor: 0x4fc275, label: 'Y' }, // LiDAR Y  → Three.js +X
      { dir: new THREE.Vector3(0, 1, 0), hex: '#3183fe', lineColor: 0x3183fe, label: 'Z' }, // LiDAR Z  → Three.js +Y
    ];

    for (const { dir, hex, lineColor, label } of AXES) {
      // Thin line stem: origin → 74% of unit vector
      const stem = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(0, 0, 0),
          dir.clone().multiplyScalar(0.74),
        ]),
        new THREE.LineBasicMaterial({ color: lineColor, transparent: true, opacity: 0.9 }),
      );
      this.gizmoScene.add(stem);

      // Letter sprite — bold letter with dark stroke outline, transparent bg
      const sprite = this.createAxisSprite(label, hex);
      sprite.position.copy(dir); // sits at the unit-vector tip
      sprite.scale.set(0.72, 0.72, 1);
      this.gizmoScene.add(sprite);
      this.axesLabels.push(sprite);
    }
  }

  /**
   * Create a canvas sprite: bold axis letter, Synergy-themed colour fill,
   * near-black stroke outline for legibility on dark backgrounds.
   * Outline colour: syn-color-neutral-0 (#000206).
   */
  private createAxisSprite(letter: string, hex: string): THREE.Sprite {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 64;
    const ctx = cv.getContext('2d')!;
    ctx.font = "600 50px 'SICK Intl', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    // syn-color-neutral-0 (#000206) outline for contrast on any bg
    ctx.lineWidth = 7;
    ctx.strokeStyle = 'rgba(0,2,6,0.96)';
    ctx.strokeText(letter, 32, 34);
    ctx.fillStyle = hex;
    ctx.fillText(letter, 32, 34);
    const tex = new THREE.CanvasTexture(cv);
    tex.anisotropy = 4;
    return new THREE.Sprite(
      new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }),
    );
  }

  /**
   * Render the gizmo into a scissored viewport in the bottom-left corner.
   *
   * SMC pattern:
   *  - Gizmo camera position = normalised (mainCam - orbitTarget) * 4
   *    so the gizmo always reflects the orbit direction, even when the
   *    orbit target is not the world origin.
   *  - `renderer.autoClear = false` (set by the caller) — the gizmo is
   *    drawn on top of the main scene without erasing it.
   *  - `clearDepth()` clears depth only so closer gizmo objects don't
   *    get depth-occluded by the main scene geometry.
   */
  private renderGizmo(): void {
    const dpr = this.renderer.getPixelRatio();
    const size = Math.round(this.GIZMO_SIZE * dpr);
    const canvas = this.renderer.domElement;
    const canvasH = canvas.clientHeight * dpr;
    const canvasW = canvas.clientWidth * dpr;

    // Mirror the main camera's view direction relative to the orbit target
    const cam = this.activeCamera as THREE.PerspectiveCamera;
    (this.gizmoCamera as unknown as THREE.OrthographicCamera).position
      .copy(cam.position)
      .sub(this.controls.target)
      .normalize()
      .multiplyScalar(4);
    (this.gizmoCamera as unknown as THREE.OrthographicCamera).up.copy(cam.up);
    (this.gizmoCamera as unknown as THREE.OrthographicCamera).lookAt(0, 0, 0);

    this.renderer.setScissorTest(true);
    this.renderer.setViewport(14, 14, size, size);
    this.renderer.setScissor(14, 14, size, size);
    this.renderer.clearDepth(); // prevent main-scene geometry occluding gizmo
    this.renderer.render(this.gizmoScene, this.gizmoCamera as unknown as THREE.Camera);

    // Restore full viewport
    this.renderer.setScissorTest(false);
    this.renderer.setViewport(0, 0, canvasW, canvasH);
  }

  private rebuildGrid() {
    // ── tear down ───────────────────────────────────────────────────────────
    this.disposeGridObjects();
    this.disposeSpriteGroup(this.gridLabels);
    this.gridLabels = [];

    const visible = !!this.showGrid();
    const S = this.currentGridSize; // 50 m half → full grid 100 m
    const FINE = 1;                 // 1 m fine cells
    const COARSE = 5;               // 5 m coarse cells (labelled)

    // ── Synergy sick2025-dark palette ──────────────────────────────────────
    //   fine lines   → neutral-300  #262f55  (very subtle)
    //   coarse lines → neutral-500  #4d5473  (readable)
    //   center lines → neutral-700  #777ea4  (noticeable, but not garish)
    //   origin X     → error-500    #f93a3f  (LiDAR X = Three.js +Z)
    //   origin Y     → success-500  #4fc275  (LiDAR Y = Three.js +X)
    //   origin Z     → primary-500  #3183fe  (LiDAR Z = Three.js +Y)
    const COL_FINE   = 0x262f55;
    const COL_COARSE = 0x4d5473;
    const COL_CENTER = 0x777ea4;
    const COL_X      = 0xf93a3f; // LiDAR X → Three.js +Z
    const COL_Y      = 0x4fc275; // LiDAR Y → Three.js +X
    const COL_Z      = 0x3183fe; // LiDAR Z → Three.js +Y

    const addLine = (
      points: THREE.Vector3[],
      color: number,
      opacity: number,
      obj?: THREE.Object3D,
    ) => {
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity }),
      );
      line.visible = visible;
      if (obj) {
        (obj as THREE.Group).add(line);
      } else {
        this.scene.add(line);
        this.gridObjects.push(line);
      }
      return line;
    };

    // ── FLOOR grid (Three.js XZ plane = LiDAR XY plane) ──────────────────
    const floorGroup = new THREE.Group();
    floorGroup.visible = visible;

    for (let i = -S; i <= S; i += FINE) {
      const isCoarse = i % COARSE === 0;
      const isCenter = i === 0;
      if (isCenter) continue; // drawn separately as origin lines
      const col = isCoarse ? COL_COARSE : COL_FINE;
      const op  = isCoarse ? 0.55 : 0.25;

      // Lines parallel to Z (vary X)
      addLine(
        [new THREE.Vector3(i, 0, -S), new THREE.Vector3(i, 0, S)],
        col, op, floorGroup,
      );
      // Lines parallel to X (vary Z)
      addLine(
        [new THREE.Vector3(-S, 0, i), new THREE.Vector3(S, 0, i)],
        col, op, floorGroup,
      );
    }
    this.scene.add(floorGroup);
    this.gridObjects.push(floorGroup);

    // ── VERTICAL grid (Three.js XY plane = LiDAR YZ plane) ───────────────
    // Shows elevation structure — visible from front/side/perspective views.
    // Extends from -S to +S in both Y (elevation) and X (horizontal).
    const vertGroup = new THREE.Group();
    vertGroup.visible = visible;

    for (let i = -S; i <= S; i += FINE) {
      const isCoarse = i % COARSE === 0;
      const isCenter = i === 0;
      if (isCenter) continue;
      const col = isCoarse ? COL_COARSE : COL_FINE;
      const opV  = isCoarse ? 0.45 : 0.18;

      // Vertical lines (vary X, full height -S to +S)
      addLine(
        [new THREE.Vector3(i, -S, 0), new THREE.Vector3(i, S, 0)],
        col, opV, vertGroup,
      );
      // Horizontal (elevation) lines — both above and below ground
      addLine(
        [new THREE.Vector3(-S, i, 0), new THREE.Vector3(S, i, 0)],
        col, opV, vertGroup,
      );
    }
    this.scene.add(vertGroup);
    this.gridObjects.push(vertGroup);

    // ── Z-elevation labels on the vertical plane ──────────────────────────
    // Flat in the YZ plane (rotate 90° around Y so text faces along +X).
    // primary-500 blue to match the Z axis colour in the gizmo.
    const LABEL_STEP = 5;
    for (let i = -S; i <= S; i += LABEL_STEP) {
      if (i === 0) continue;
      const lz = this.createTextMesh(`${i}m`, '#3183fe');
      lz.rotation.y = Math.PI / 2; // face along +X so it lies in the YZ plane
      lz.position.set(S + 1.2, i, 0);
      lz.visible = visible;
      this.gridLabels.push(lz as unknown as THREE.Sprite);
      this.scene.add(lz);
    }

    // ── CENTER cross-hair lines (axis-coloured, pass through origin) ──────
    // LiDAR X → Three.js +Z → red
    addLine(
      [new THREE.Vector3(0, 0, -S), new THREE.Vector3(0, 0, S)],
      COL_X, 0.7,
    );
    // LiDAR Y → Three.js +X → green
    addLine(
      [new THREE.Vector3(-S, 0, 0), new THREE.Vector3(S, 0, 0)],
      COL_Y, 0.7,
    );
    // LiDAR Z → Three.js +Y → blue (vertical origin line)
    addLine(
      [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, S, 0)],
      COL_Z, 0.7,
    );
    // Center cross in the floor plane (bright neutral)
    addLine(
      [new THREE.Vector3(-S, 0, 0), new THREE.Vector3(S, 0, 0)],
      COL_CENTER, 0.35,
    );
    addLine(
      [new THREE.Vector3(0, 0, -S), new THREE.Vector3(0, 0, S)],
      COL_CENTER, 0.35,
    );

    // ── ORIGIN dot ────────────────────────────────────────────────────────
    const originGeo = new THREE.BufferGeometry();
    originGeo.setAttribute(
      'position',
      new THREE.BufferAttribute(new Float32Array([0, 0, 0]), 3),
    );
    const originDot = new THREE.Points(
      originGeo,
      new THREE.PointsMaterial({
        color: 0xffffff,
        size: 6,
        sizeAttenuation: false,
        transparent: true,
        opacity: 0.9,
      }),
    );
    originDot.visible = visible;
    this.scene.add(originDot);
    this.gridObjects.push(originDot);

    // ── LABELS ─────────────────────────────────────────────────────────────
    // X-axis labels: along Three.js +Z, laid FLAT in the XZ floor plane (Y=0).
    // Y-axis labels: along Three.js +X, laid FLAT in the YZ vertical plane (Z=0).
    for (let i = -S; i <= S; i += LABEL_STEP) {
      if (i === 0) continue;

      // LiDAR-X labels — flat in XoZ floor plane, ON the X axis line (x=0)
      const lx = this.createTextMesh(`${i}m`);
      lx.rotation.x = -Math.PI / 2;
      lx.position.set(0, 0, i);
      lx.visible = visible;
      this.gridLabels.push(lx as unknown as THREE.Sprite);
      this.scene.add(lx);

      // LiDAR-Y labels — flat in YoZ vertical plane (faces along Z=0, no rotation needed)
      const ly = this.createTextMesh(`${i}m`);
      ly.position.set(i, 0, 0);
      ly.visible = visible;
      this.gridLabels.push(ly as unknown as THREE.Sprite);
      this.scene.add(ly);
    }

    this.requestRender();
  }

  /** Dispose and remove all non-sprite grid objects from the scene. */
  private disposeGridObjects(): void {
    for (const obj of this.gridObjects) {
      this.scene?.remove(obj);
      obj.traverse((child) => {
        if ((child as THREE.Line).geometry) (child as THREE.Line).geometry.dispose();
        if ((child as THREE.Line).material) {
          const mat = (child as THREE.Line).material;
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
          else (mat as THREE.Material).dispose();
        }
      });
    }
    this.gridObjects = [];
  }

  private disposeSpriteGroup(sprites: THREE.Sprite[]): void {
    sprites.forEach((obj) => {
      this.scene?.remove(obj);
      // Works for both Sprite and Mesh cast as Sprite
      const mesh = obj as unknown as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const mat = mesh.material ?? (obj as THREE.Sprite).material;
      if (mat) {
        const materials = Array.isArray(mat) ? mat : [mat];
        materials.forEach((m: THREE.Material & { map?: THREE.Texture }) => {
          m.map?.dispose();
          m.dispose();
        });
      }
    });
  }

  /**
   * Create a flat text mesh using a canvas texture on a PlaneGeometry.
   * Unlike a Sprite, the plane stays in world-space and can be given a fixed
   * rotation so it lies in a specific plane (floor or vertical wall).
   */
  private createTextMesh(message: string, color = '#777ea4'): THREE.Mesh {
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 32;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "400 20px 'SICK Intl', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(0,2,6,0.80)';
    ctx.strokeText(message, canvas.width / 2, canvas.height / 2);
    ctx.fillStyle = color;
    ctx.fillText(message, canvas.width / 2, canvas.height / 2);
    const tex = new THREE.CanvasTexture(canvas);
    tex.minFilter = THREE.LinearFilter;
    // PlaneGeometry sized in world metres: 1.5 m wide × 0.4 m tall
    return new THREE.Mesh(
      new THREE.PlaneGeometry(1.5, 0.4),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, side: THREE.DoubleSide }),
    );
  }
}
