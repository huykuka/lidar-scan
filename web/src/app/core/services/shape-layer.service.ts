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
 * Manages the lifecycle of Three.js shape objects on Layer 2 (SHAPE_LAYER)
 * **for a single scene/canvas instance**.
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
   * Per-scene id → Object3D map.
   * Keyed by the backend-assigned stable shape id (16-char hex).
   * Guaranteed unique within this service instance (= within one canvas).
   */
  private readonly shapeMap = new Map<string, THREE.Object3D>();

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
      // Hot-reload / scene-swap: clean up previous scene to prevent orphans.
      // The shapeMap is also cleared because those Object3Ds belong to the
      // old scene and must not be re-added to the new scene as stale entries.
      this._removeAllFromScene(this.scene);
      this.shapeMap.clear();
    }
    this.scene = scene;
  }

  /**
   * Process one ShapeFrame: add new shapes, mutate existing ones in-place,
   * dispose stale ones — all scoped to *this* scene instance.
   *
   * Diff algorithm:
   *   1. Build a Set of incoming ids for O(1) lookup.
   *   2. Remove any tracked shape whose id is absent from the incoming set.
   *   3. For each incoming shape:
   *        • If not yet tracked → build + add to scene (scene.add called once).
   *        • If already tracked → mutate in-place (scene.add never called again).
   */
  applyFrame(frame: ShapeFrame): void {
    if (!this.scene) return;

    const incomingIds = new Set(frame.shapes.map((s) => s.id));

    // ── 1. Remove stale shapes ───────────────────────────────────────────────
    for (const [id, obj] of this.shapeMap) {
      if (!incomingIds.has(id)) {
        this.scene.remove(obj);
        this.disposeObject(obj);
        this.shapeMap.delete(id);
      }
    }

    // ── 2. Add or update shapes ──────────────────────────────────────────────
    for (const shape of frame.shapes) {
      if (shape.id === '') {
        console.warn(
          '[ShapeLayerService] Backend contract violation: shape has empty id — skipping.',
          shape,
        );
        continue;
      }

      if (!this.shapeMap.has(shape.id)) {
        // New shape — build, register on SHAPE_LAYER, add to scene exactly once.
        const obj = this.buildShape(shape);
        if (!obj) continue; // unknown type — already logged

        obj.layers.set(SHAPE_LAYER);
        this.scene.add(obj);
        this.shapeMap.set(shape.id, obj);
      } else {
        // Existing shape — mutate in-place; scene.add is NEVER called here.
        const existing = this.shapeMap.get(shape.id)!;
        this.updateShape(existing, shape);
      }
    }
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

  /** Remove every tracked object from `targetScene` and dispose GPU resources. */
  private _removeAllFromScene(targetScene: THREE.Scene): void {
    for (const obj of this.shapeMap.values()) {
      targetScene.remove(obj);
      this.disposeObject(obj);
    }
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
