/**
 * TypeScript interfaces for the 3D Shape Rendering protocol.
 * Matches the backend Pydantic models in app/services/nodes/shapes.py
 * and the API contract in .opencode/plans/3d-shapes/api-spec.md.
 */

// ── Layer constant ────────────────────────────────────────────────────────────
/** Three.js layer bit used for all 3D shape objects.
 *  Layer 0 = point clouds / grid / axes (default).
 *  Layer 2 = 3D shapes (cubes, planes, labels).
 */
export const SHAPE_LAYER = 2;

// ── Base ──────────────────────────────────────────────────────────────────────
export interface BaseShape {
  /** Backend-assigned stable unique ID (16-char hex). */
  id: string;
  /** Human-readable name of the emitting DAG node. */
  node_name: string;
  /** Shape discriminator. */
  type: string;
}

// ── Cube ──────────────────────────────────────────────────────────────────────
export interface CubeDescriptor extends BaseShape {
  type: 'cube';
  /** World position [x, y, z] in meters. */
  center: [number, number, number];
  /** Full extents [sx, sy, sz] in meters. */
  size: [number, number, number];
  /** Euler rotation [rx, ry, rz] in radians (XYZ order). Defaults to [0,0,0]. */
  rotation: [number, number, number];
  /** CSS hex color string. */
  color: string;
  /** 0.0 (transparent) to 1.0 (opaque). */
  opacity: number;
  /** If true, render as wireframe edges only; false = solid fill. */
  wireframe: boolean;
  /** Optional text label attached to the top of the box. */
  label: string | null;
}

// ── Plane ─────────────────────────────────────────────────────────────────────
export interface PlaneDescriptor extends BaseShape {
  type: 'plane';
  /** Plane center in world space [x, y, z]. */
  center: [number, number, number];
  /** Unit normal vector [nx, ny, nz]. */
  normal: [number, number, number];
  /** Rendered patch width in meters. */
  width: number;
  /** Rendered patch height in meters. */
  height: number;
  /** CSS hex color string. */
  color: string;
  /** 0.0 to 1.0 */
  opacity: number;
}

// ── Label ─────────────────────────────────────────────────────────────────────
export interface LabelDescriptor extends BaseShape {
  type: 'label';
  /** World position [x, y, z]. */
  position: [number, number, number];
  /** Text to display. */
  text: string;
  /** Canvas font size in pixels. */
  font_size: number;
  /** Text color (CSS hex). */
  color: string;
  /** Background fill — supports alpha hex (e.g. "#000000cc"). */
  background_color: string;
  /** World-space scale multiplier. */
  scale: number;
}

// ── Union ─────────────────────────────────────────────────────────────────────
export type ShapeDescriptor = CubeDescriptor | PlaneDescriptor | LabelDescriptor;

// ── Frame ─────────────────────────────────────────────────────────────────────
/** Published to WS topic 'shapes' every frame. */
export interface ShapeFrame {
  /** Unix epoch seconds (float64). */
  timestamp: number;
  /** All currently active shapes. Empty array clears all shapes. */
  shapes: ShapeDescriptor[];
}
