import {Injectable} from '@angular/core';
import * as THREE from 'three';
import {
  CubeDescriptor,
  LabelDescriptor,
  PlaneDescriptor,
  SHAPE_LAYER,
  ShapeDescriptor,
  ShapeFrame,
} from '@core/models/shapes.model';
import {ShapeBuilders} from '@core/utils/shape-builders';

/**
 * How long (ms) a shape stays visible after it was last reported by the backend.
 * Prevents flicker when bounding boxes temporarily disappear for a frame or two.
 */
export const SHAPE_DECAY_MS = 500;

/**
 * During the last FADE_WINDOW_MS of the decay period, the shape's opacity
 * is linearly faded toward 0, giving a visual hint that it's going stale.
 */
export const SHAPE_FADE_WINDOW_MS = 200;

/**
 * Exponential smoothing factor for spatial interpolation between frames.
 * 0 = no movement (frozen), 1 = snap instantly to target.
 * At 0.3, a shape covers ~70% of the distance to its target each frame.
 */
export const SHAPE_LERP_ALPHA = 0.3;

/** Linear interpolation between two scalar values. */
function lerpValue(current: number, target: number, alpha: number): number {
  return current + (target - current) * alpha;
}

/** Deep-clone a ShapeDescriptor (plain-object, no class instances). */
function cloneDescriptor(d: ShapeDescriptor): ShapeDescriptor {
  if (d.type === 'cube') {
    const c = d as CubeDescriptor;
    return {
      ...c,
      center: [...c.center] as [number, number, number],
      size: [...c.size] as [number, number, number],
      rotation: [...c.rotation] as [number, number, number],
    };
  }
  if (d.type === 'plane') {
    const p = d as PlaneDescriptor;
    return {
      ...p,
      center: [...p.center] as [number, number, number],
      normal: [...p.normal] as [number, number, number],
    };
  }
  // label
  const l = d as LabelDescriptor;
  return {
    ...l,
    position: [...l.position] as [number, number, number],
  };
}

/** Internal tracking entry per shape. */
interface ShapeEntry {
  obj: THREE.Object3D;
  lastSeen: number;               // Date.now() when last present in a frame
  descriptor: ShapeDescriptor;    // latest descriptor from the backend
  /** Where the shape SHOULD be (the backend's authoritative state). */
  targetDescriptor: ShapeDescriptor;
  /** Current interpolated state — converges toward targetDescriptor each frame. */
  lerpedDescriptor: ShapeDescriptor;
  baseOpacity: number;            // original opacity from the descriptor
}

/**
 * Manages the lifecycle of Three.js shape objects on Layer 2 (SHAPE_LAYER)
 * **for a single scene/canvas instance**.
 *
 * # Decay-based anti-flicker
 *
 * Instead of immediately removing shapes that are absent from the latest frame,
 * this service keeps them visible for up to `SHAPE_DECAY_MS` milliseconds.
 * During the last `SHAPE_FADE_WINDOW_MS` of that window, the shape's opacity
 * fades linearly to 0, then it is disposed.  This prevents flicker when the
 * backend temporarily emits empty or partial frames.
 *
 * # Exponential smoothing (lerp)
 *
 * When a shape's position/size changes between frames, the service interpolates
 * the current rendered state toward the target using `SHAPE_LERP_ALPHA` each
 * frame. Non-spatial properties (color, opacity, text) update immediately.
 * Labels whose text changes also snap their position immediately to avoid
 * briefly showing new text at the old position.
 *
 * # Split-view safety — one instance per PointCloudComponent
 *
 * This service is intentionally NOT `providedIn: 'root'`.  It is listed in the
 * `providers` array of `PointCloudComponent` so Angular creates a **fresh
 * instance** for every component in the DOM tree.  This guarantees:
 *
 *   • Each scene gets its own `shapeMap` — there is no shared mutable state
 *     between canvases.
 *   • Calling `disposeAll()` in one component's `ngOnDestroy` cannot affect
 *     the shape objects owned by another component.
 *   • There is no "last init wins" race when multiple panes call `init(scene)`
 *     during the same Angular change-detection cycle.
 *
 * NEVER restore `providedIn: 'root'` without reverting to an explicit
 * multi-scene registry (scene-id → shapeMap) to preserve these guarantees.
 *
 * NEVER touches point cloud geometry (Layer 0).
 */
@Injectable()
export class ShapeLayerService {
  private scene: THREE.Scene | null = null;

  /**
   * Per-scene id → ShapeEntry map.
   * Keyed by the backend-assigned stable shape id (16-char hex).
   * Guaranteed unique within this service instance (= within one canvas).
   */
  private readonly shapeMap = new Map<string, ShapeEntry>();

  /** Overridable clock for testing. */
  now: () => number = () => Date.now();

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Store a reference to the Three.js scene owned by this component instance.
   * Must be called from PointCloudComponent.ngAfterViewInit(), after initThree().
   *
   * Calling `init()` again with a *different* scene (e.g. after a hot-reload)
   * safely disposes all objects from the previous scene first.
   */
  init(scene: THREE.Scene): void {
    if (this.scene && this.scene !== scene) {
      this._removeAllFromScene(this.scene);
      this.shapeMap.clear();
    }
    this.scene = scene;
  }

  /**
   * Process one ShapeFrame: add new shapes, update targets for existing ones,
   * lerp ALL tracked shapes toward their targets, and mark missing shapes for
   * decay rather than immediate removal.
   *
   * Decay algorithm:
   *   1. For each incoming shape: update lastSeen + targetDescriptor.
   *      New shapes snap immediately (no lerp on first frame).
   *   2. Lerp ALL tracked entries toward their target this frame.
   *   3. For shapes NOT in the incoming set: do NOT remove yet — let them
   *      decay. Their lastSeen stays unchanged; lerping continues.
   *   4. Call `reapDecayed()` to remove shapes that have exceeded SHAPE_DECAY_MS
   *      and fade shapes that are within the SHAPE_FADE_WINDOW_MS.
   */
  applyFrame(frame: ShapeFrame): void {
    if (!this.scene) return;

    const now = this.now();

    // ── 1. Add or update targets for shapes present in this frame ────────────
    for (const shape of frame.shapes) {
      if (shape.id === '') {
        console.warn(
          '[ShapeLayerService] Backend contract violation: shape has empty id — skipping.',
          shape,
        );
        continue;
      }

      const entry = this.shapeMap.get(shape.id);
      if (!entry) {
        // New shape — build, register on SHAPE_LAYER, add to scene exactly once.
        // Snap immediately to the initial position (no lerp on first frame).
        const obj = this.buildShape(shape);
        if (!obj) continue; // unknown type — already logged

        obj.layers.set(SHAPE_LAYER);
        this.scene.add(obj);
        this.shapeMap.set(shape.id, {
          obj,
          lastSeen: now,
          descriptor: shape,
          targetDescriptor: shape,
          lerpedDescriptor: cloneDescriptor(shape),
          baseOpacity: this.extractOpacity(shape),
        });
      } else {
        // Existing shape — update the target; lerp step happens below for all entries.
        entry.lastSeen = now;
        entry.descriptor = shape;
        entry.targetDescriptor = shape;
        entry.baseOpacity = this.extractOpacity(shape);
        // Restore full opacity in case it was being faded.
        this.setObjectOpacity(entry.obj, entry.baseOpacity);
      }
    }

    // ── 2. Lerp ALL tracked shapes toward their targets ──────────────────────
    // Runs every frame so shapes keep gliding even across frames where their
    // id is absent (decay window).
    for (const entry of this.shapeMap.values()) {
      this.lerpShape(entry);
    }

    // ── 3. Reap decayed shapes and fade expiring ones ────────────────────────
    this.reapDecayed(now);
  }

  /**
   * Remove and dispose all managed shape objects from *this* scene.
   * Call from PointCloudComponent.ngOnDestroy() to prevent GPU memory leaks.
   */
  disposeAll(): void {
    if (this.scene) {
      this._removeAllFromScene(this.scene);
    }
    this.shapeMap.clear();
    this.scene = null;
  }

  /** Read-only access to current shape count (useful for tests / diagnostics). */
  get shapeCount(): number {
    return this.shapeMap.size;
  }

  // ── Private helpers ────────────────────────────────────────────────────────

  /**
   * Advance `entry.lerpedDescriptor` one step toward `entry.targetDescriptor`
   * using `SHAPE_LERP_ALPHA`, then call the appropriate ShapeBuilders update
   * method with the interpolated descriptor.
   *
   * Rules:
   *  • Spatial properties (position/center/size/rotation) are lerped.
   *  • Non-spatial properties (color, opacity, text, wireframe, etc.) snap immediately.
   *  • Labels whose text has changed also snap their position to avoid showing
   *    new text at the stale position.
   */
  private lerpShape(entry: ShapeEntry): void {
    const target = entry.targetDescriptor;
    const lerped = entry.lerpedDescriptor;
    const α = SHAPE_LERP_ALPHA;

    if (target.type === 'cube') {
      const t = target as CubeDescriptor;
      const l = lerped as CubeDescriptor;

      // Lerp spatial fields
      l.center = [
        lerpValue(l.center[0], t.center[0], α),
        lerpValue(l.center[1], t.center[1], α),
        lerpValue(l.center[2], t.center[2], α),
      ];
      l.size = [
        lerpValue(l.size[0], t.size[0], α),
        lerpValue(l.size[1], t.size[1], α),
        lerpValue(l.size[2], t.size[2], α),
      ];
      l.rotation = [
        lerpValue(l.rotation[0], t.rotation[0], α),
        lerpValue(l.rotation[1], t.rotation[1], α),
        lerpValue(l.rotation[2], t.rotation[2], α),
      ];

      // Non-spatial: snap immediately
      l.color = t.color;
      l.opacity = t.opacity;
      l.wireframe = t.wireframe;
      l.label = t.label;
    } else if (target.type === 'plane') {
      const t = target as PlaneDescriptor;
      const l = lerped as PlaneDescriptor;

      // Lerp center
      l.center = [
        lerpValue(l.center[0], t.center[0], α),
        lerpValue(l.center[1], t.center[1], α),
        lerpValue(l.center[2], t.center[2], α),
      ];

      // Non-spatial: snap immediately
      l.normal = [...t.normal] as [number, number, number];
      l.width = t.width;
      l.height = t.height;
      l.color = t.color;
      l.opacity = t.opacity;
    } else if (target.type === 'label') {
      const t = target as LabelDescriptor;
      const l = lerped as LabelDescriptor;

      // If text changed, snap position immediately so new text renders at target
      if (l.text !== t.text) {
        l.position = [...t.position] as [number, number, number];
      } else {
        l.position = [
          lerpValue(l.position[0], t.position[0], α),
          lerpValue(l.position[1], t.position[1], α),
          lerpValue(l.position[2], t.position[2], α),
        ];
      }

      // Non-spatial: snap immediately
      l.text = t.text;
      l.font_size = t.font_size;
      l.color = t.color;
      l.background_color = t.background_color;
      l.scale = t.scale;
      l.opacity = t.opacity;
    }

    this.updateShape(entry.obj, entry.lerpedDescriptor);
  }

  /**
   * Remove shapes whose decay window has fully expired, and fade shapes
   * that are within the fade window.
   */
  private reapDecayed(now: number): void {
    if (!this.scene) return;

    for (const [id, entry] of this.shapeMap) {
      const age = now - entry.lastSeen;

      if (age > SHAPE_DECAY_MS) {
        // Fully expired — remove and dispose.
        this.scene.remove(entry.obj);
        this.disposeObject(entry.obj);
        this.shapeMap.delete(id);
      } else if (age > SHAPE_DECAY_MS - SHAPE_FADE_WINDOW_MS) {
        // Within fade window — linearly reduce opacity toward 0.
        const fadeRemaining = SHAPE_DECAY_MS - age; // ms left before removal
        const fadeFactor = fadeRemaining / SHAPE_FADE_WINDOW_MS; // 1.0 → 0.0
        this.setObjectOpacity(entry.obj, entry.baseOpacity * fadeFactor);
      }
    }
  }

  /** Remove every tracked object from `targetScene` and dispose GPU resources. */
  private _removeAllFromScene(targetScene: THREE.Scene): void {
    for (const entry of this.shapeMap.values()) {
      targetScene.remove(entry.obj);
      this.disposeObject(entry.obj);
    }
  }

  /** Extract the opacity value from a shape descriptor. */
  private extractOpacity(d: ShapeDescriptor): number {
    if (d.type === 'label') return (d as LabelDescriptor).opacity ?? 0.85;
    return (d as any).opacity ?? 1.0;
  }

  /** Set opacity on a shape's material(s), traversing children. */
  private setObjectOpacity(obj: THREE.Object3D, opacity: number): void {
    obj.traverse((child) => {
      if ((child as any).material) {
        const mat = (child as THREE.Mesh).material;
        if (Array.isArray(mat)) {
          mat.forEach((m) => {
            m.opacity = opacity;
            m.transparent = true;
            m.needsUpdate = true;
          });
        } else {
          (mat as THREE.Material).opacity = opacity;
          (mat as THREE.Material).transparent = true;
          (mat as THREE.Material).needsUpdate = true;
        }
      }
    });
  }

  private buildShape(d: ShapeDescriptor): THREE.Object3D | null {
    switch (d.type) {
      case 'cube':
        return ShapeBuilders.buildCube(d as CubeDescriptor);
      case 'plane':
        return ShapeBuilders.buildPlane(d as PlaneDescriptor);
      case 'label':
        return ShapeBuilders.buildLabel(d as LabelDescriptor);
      default:
        console.warn(
          `[ShapeLayerService] Unknown shape type: "${(d as any).type}" — skipping`,
        );
        return null;
    }
  }

  private updateShape(obj: THREE.Object3D, d: ShapeDescriptor): void {
    switch (d.type) {
      case 'cube':
        ShapeBuilders.updateCube(obj as THREE.Group, d as CubeDescriptor);
        break;
      case 'plane':
        ShapeBuilders.updatePlane(obj as THREE.Group, d as PlaneDescriptor);
        break;
      case 'label':
        ShapeBuilders.updateLabel(obj as THREE.Sprite, d as LabelDescriptor);
        break;
      default:
        // Unrecognised types were never added, so this branch should be
        // unreachable. Log defensively rather than silently ignore.
        console.warn(
          `[ShapeLayerService] updateShape called with unknown type "${(d as any).type}"`,
        );
        break;
    }
  }

  /**
   * Recursively disposes geometry and material for a Three.js object tree.
   * Handles both single-material and multi-material meshes and sprite textures.
   */
  private disposeObject(obj: THREE.Object3D): void {
    obj.traverse((child) => {
      if ((child as any).geometry) {
        (child as THREE.Mesh).geometry.dispose();
      }
      if ((child as any).material) {
        const mat = (child as THREE.Mesh).material;
        if (Array.isArray(mat)) {
          mat.forEach((m) => {
            if ((m as THREE.MeshBasicMaterial).map) {
              (m as THREE.MeshBasicMaterial).map!.dispose();
            }
            m.dispose();
          });
        } else {
          const m = mat as THREE.MeshBasicMaterial;
          if (m.map) m.map.dispose();
          m.dispose();
        }
      }
    });
  }
}
