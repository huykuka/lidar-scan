import * as THREE from 'three';
import {CubeDescriptor, LabelDescriptor, PlaneDescriptor, SHAPE_LAYER} from '@core/models/shapes.model';

/**
 * LiDAR → Three.js coordinate alignment.
 * The point cloud applies rotation.x = -PI/2, rotation.z = -PI/2
 * at the THREE.Points level. All shape wrappers must apply the same
 * transform so world coords align with the point cloud.
 *
 * IMPORTANT: The outerGroup is a pure rotation pivot — its position stays at
 * the world origin (0,0,0). The LiDAR-space position is applied on the inner
 * mesh (child of outerGroup) so it is correctly interpreted in the rotated
 * (LiDAR) coordinate frame — matching exactly how point cloud vertices work.
 */
function applyLidarRotation(group: THREE.Group): void {
  group.rotation.x = -Math.PI / 2;
  group.rotation.z = -Math.PI / 2;
}

/**
 * Builds a stable fingerprint string for a LabelDescriptor.
 * Used to skip Canvas/texture recreation when label content has not changed.
 * Stored on sprite.userData['labelKey'] after each render.
 */
function labelFingerprint(d: LabelDescriptor): string {
  return `${d.text}|${d.font_size}|${d.color}|${d.background_color}|${d.scale ?? 1.0}`;
}

/**
 * Static factory & mutator methods for Three.js shape objects.
 * Every build* method wraps geometry in a THREE.Group with LiDAR → Three.js
 * coordinate transform applied (except labels, which are Sprites and thus
 * always camera-facing — no rotation group needed).
 */
export class ShapeBuilders {
  // ── Cube ───────────────────────────────────────────────────────────────────

  static buildCube(d: CubeDescriptor): THREE.Group {
    const outerGroup = new THREE.Group();
    applyLidarRotation(outerGroup);
    // NOTE: outerGroup.position stays at (0,0,0) — it is a pure rotation pivot.
    // The LiDAR-space center is applied on the inner mesh so it is interpreted
    // in the rotated (LiDAR) coordinate frame, matching point cloud vertices.
    outerGroup.layers.set(SHAPE_LAYER);

    const geometry = new THREE.BoxGeometry(d.size[0], d.size[1], d.size[2]);
    let mesh: THREE.Object3D;

    if (d.wireframe) {
      const edges = new THREE.EdgesGeometry(geometry);
      geometry.dispose(); // edges clones what it needs
      const material = new THREE.LineBasicMaterial({
        color: d.color,
        transparent: d.opacity < 1,
        opacity: d.opacity,
      });
      mesh = new THREE.LineSegments(edges, material);
    } else {
      const material = new THREE.MeshBasicMaterial({
        color: d.color,
        transparent: true,
        opacity: d.opacity,
        depthWrite: false,
      });
      mesh = new THREE.Mesh(geometry, material);
    }

    // Apply LiDAR-space center position and per-shape Euler rotation on the
    // inner mesh (local space = LiDAR space due to outerGroup rotation).
    mesh.position.set(d.center[0], d.center[1], d.center[2]);
    mesh.rotation.set(d.rotation[0], d.rotation[1], d.rotation[2]);
    mesh.layers.set(SHAPE_LAYER);
    outerGroup.add(mesh);

    // Optional label above the box — embedded as a child of outerGroup so it
    // lives in LiDAR local space (same frame as the inner mesh).
    // The Z-axis in LiDAR space is "up", so offset along LiDAR Z by half the
    // box height plus a fixed clearance to avoid overlap.
    if (d.label) {
      const labelSprite = ShapeBuilders.buildLabel({
        id: d.id,
        node_name: d.node_name,
        type: 'label',
        position: [
          d.center[0],
          d.center[1],
          d.center[2] + d.size[2] / 2 + 0.5, // 0.5 m clearance above box top
        ],
        text: d.label,
        font_size: 16,
        color: '#ffffff',
        background_color: '#00000088',
        scale: 1.0,
      });
      outerGroup.add(labelSprite);
    }

    return outerGroup;
  }

  static updateCube(obj: THREE.Group, d: CubeDescriptor): void {
    // The inner mesh holds the LiDAR-space position; outerGroup stays at origin.
    const mesh = obj.children.find(
      (c) => c instanceof THREE.LineSegments || c instanceof THREE.Mesh,
    ) as THREE.LineSegments | THREE.Mesh | undefined;

    if (!mesh) return;

    // Update position and rotation on the inner mesh (in LiDAR local space)
    mesh.position.set(d.center[0], d.center[1], d.center[2]);
    mesh.rotation.set(d.rotation[0], d.rotation[1], d.rotation[2]);

    // Update material color/opacity
    const mat = mesh.material as THREE.LineBasicMaterial | THREE.MeshBasicMaterial;
    if (mat) {
      (mat as any).color?.set(d.color);
      mat.opacity = d.opacity;
      mat.transparent = d.opacity < 1;
      mat.needsUpdate = true;
    }

    // Update embedded label sprite if present
    const sprite = obj.children.find((c) => c instanceof THREE.Sprite) as
      | THREE.Sprite
      | undefined;
    if (sprite && d.label) {
      ShapeBuilders.updateLabel(sprite, {
        id: d.id,
        node_name: d.node_name,
        type: 'label',
        position: [
          d.center[0],
          d.center[1],
          d.center[2] + d.size[2] / 2 + 0.5,
        ],
        text: d.label,
        font_size: 16,
        color: '#ffffff',
        background_color: '#00000088',
        scale: 1.0,
      } as LabelDescriptor);
    } else if (sprite && !d.label) {
      // Label was removed from descriptor — hide the sprite rather than
      // disposing it (avoids object recreation on next re-add).
      sprite.visible = false;
    } else if (!sprite && d.label) {
      // Label was added after initial build — create and attach it now.
      const newSprite = ShapeBuilders.buildLabel({
        id: d.id,
        node_name: d.node_name,
        type: 'label',
        position: [
          d.center[0],
          d.center[1],
          d.center[2] + d.size[2] / 2 + 0.5,
        ],
        text: d.label,
        font_size: 16,
        color: '#ffffff',
        background_color: '#00000088',
        scale: 1.0,
      });
      obj.add(newSprite);
    }
  }

  // ── Plane ──────────────────────────────────────────────────────────────────

  static buildPlane(d: PlaneDescriptor): THREE.Group {
    const outerGroup = new THREE.Group();
    applyLidarRotation(outerGroup);
    // NOTE: outerGroup.position stays at (0,0,0) — pure rotation pivot.
    // LiDAR-space center is applied on the inner mesh.
    outerGroup.layers.set(SHAPE_LAYER);

    const geometry = new THREE.PlaneGeometry(d.width, d.height);
    const material = new THREE.MeshBasicMaterial({
      color: d.color,
      transparent: true,
      opacity: d.opacity,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geometry, material);

    // Apply LiDAR-space center position on the inner mesh (local = LiDAR space)
    mesh.position.set(d.center[0], d.center[1], d.center[2]);

    // Orient plane so Three.js +Z aligns with the provided normal
    const normalVec = new THREE.Vector3(d.normal[0], d.normal[1], d.normal[2]).normalize();
    const defaultNormal = new THREE.Vector3(0, 0, 1);
    if (!normalVec.equals(defaultNormal)) {
      const quaternion = new THREE.Quaternion();
      quaternion.setFromUnitVectors(defaultNormal, normalVec);
      mesh.quaternion.copy(quaternion);
    }

    mesh.layers.set(SHAPE_LAYER);
    outerGroup.add(mesh);

    return outerGroup;
  }

  static updatePlane(obj: THREE.Group, d: PlaneDescriptor): void {
    // outerGroup stays at origin; update position on inner mesh.
    const mesh = obj.children.find((c) => c instanceof THREE.Mesh) as THREE.Mesh | undefined;
    if (!mesh) return;

    mesh.position.set(d.center[0], d.center[1], d.center[2]);
    const normalVec = new THREE.Vector3(d.normal[0], d.normal[1], d.normal[2]).normalize();
    const defaultNormal = new THREE.Vector3(0, 0, 1);
    if (!normalVec.equals(defaultNormal)) {
      const quaternion = new THREE.Quaternion();
      quaternion.setFromUnitVectors(defaultNormal, normalVec);
      mesh.quaternion.copy(quaternion);
    } else {
      mesh.quaternion.identity();
    }

    const mat = mesh.material as THREE.MeshBasicMaterial;
    if (mat) {
      mat.color.set(d.color);
      mat.opacity = d.opacity;
      mat.transparent = true;
      mat.needsUpdate = true;
    }
  }

  // ── Label ──────────────────────────────────────────────────────────────────

  static buildLabel(d: LabelDescriptor): THREE.Sprite {
    const texture = ShapeBuilders.createLabelTexture(d);
    const material = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      depthTest: false,       // always visible on top — never occluded
      opacity: d.opacity ?? 0.85,
    });
    const sprite = new THREE.Sprite(material);
    sprite.renderOrder = 999; // draw after all opaque/transparent geometry
    sprite.position.set(d.position[0], d.position[1], d.position[2]);
    const s = d.scale ?? 1.0;
    // Compact aspect ratio (2.5 : 0.6) — readable but less intrusive.
    sprite.scale.set(2.0 * s, 0.5 * s, 1.0);
    sprite.layers.set(SHAPE_LAYER);
    // Store fingerprint so updateLabel can skip unnecessary texture recreation.
    sprite.userData['labelKey'] = labelFingerprint(d);
    return sprite;
  }

  /**
   * Update sprite position and — only when content actually changed — redraw
   * the canvas texture.  Skipping the GPU upload every frame eliminates the
   * visible flicker that occurred with the previous "always-redraw" approach.
   */
  static updateLabel(obj: THREE.Sprite, d: LabelDescriptor): void {
    obj.position.set(d.position[0], d.position[1], d.position[2]);
    const s = d.scale ?? 1.0;
    obj.scale.set(2.0 * s, 0.5 * s, 1.0);

    // Update opacity if provided
    const mat = obj.material as THREE.SpriteMaterial;
    if (d.opacity !== undefined) {
      mat.opacity = d.opacity;
      mat.needsUpdate = true;
    }

    // ── Dirty-check: only rebuild the canvas texture when the visible
    //    content (text, size, colours) has actually changed. ─────────────────
    const newKey = labelFingerprint(d);
    if (obj.userData['labelKey'] === newKey) {
      // Nothing changed — skip texture recreation entirely.
      return;
    }

    const oldMap = (obj.material as THREE.SpriteMaterial).map;
    const newTexture = ShapeBuilders.createLabelTexture(d);
    (obj.material as THREE.SpriteMaterial).map = newTexture;
    (obj.material as THREE.SpriteMaterial).needsUpdate = true;
    oldMap?.dispose();

    obj.userData['labelKey'] = newKey;
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  private static createLabelTexture(d: LabelDescriptor): THREE.CanvasTexture {
    // Use a 4:1 canvas for good text readability at typical label lengths.
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');

    // ctx may be null in test environments (jsdom without canvas support)
    if (ctx) {
      // Background — support 8-digit hex with alpha (#rrggbbaa)
      const bg = ShapeBuilders.parseCssColorWithAlpha(d.background_color);
      ctx.fillStyle = bg;
      // Use roundRect if available (modern browsers); fall back to fillRect.
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(0, 0, canvas.width, canvas.height, 10);
      } else {
        ctx.rect(0, 0, canvas.width, canvas.height);
      }
      ctx.fill();

      // Text — clamp font size between 12 and 64 px (canvas pixels).
      const fontSize = Math.max(12, Math.min(d.font_size * 2, 64));
      ctx.font = `bold ${fontSize}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = d.color;
      // Leave 16 px horizontal padding on each side.
      ctx.fillText(d.text, canvas.width / 2, canvas.height / 2, canvas.width - 32);
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    return texture;
  }

  /**
   * Converts 8-digit hex color (#rrggbbaa) to an rgba() CSS string that the
   * Canvas 2D API understands. Falls back to the original string for 6-digit
   * hex and named colors.
   */
  static parseCssColorWithAlpha(color: string): string {
    if (/^#[0-9a-fA-F]{8}$/.test(color)) {
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);
      const a = parseInt(color.slice(7, 9), 16) / 255;
      return `rgba(${r},${g},${b},${a.toFixed(3)})`;
    }
    return color;
  }
}
