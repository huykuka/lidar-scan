/**
 * Canonical 6-DOF sensor pose model.
 * This is the single source of truth for pose types across the frontend.
 *
 * **Unit convention:**
 * - Position (x, y, z) is stored in **meters** (backend unit).
 * - The UI (PoseFormComponent) converts to **millimeters** for display.
 * - Angles (roll, pitch, yaw) are in **degrees** [-180, +180].
 */

/** Canonical 6-DOF sensor pose. Position in meters; angles in degrees [-180, +180]. */
export interface Pose {
  /** Translation X in meters */
  x: number;
  /** Translation Y in meters */
  y: number;
  /** Translation Z in meters */
  z: number;
  /** Rotation around X axis in degrees [-180, +180] */
  roll: number;
  /** Rotation around Y axis in degrees [-180, +180] */
  pitch: number;
  /** Rotation around Z axis in degrees [-180, +180] */
  yaw: number;
}

/** Zero pose constant — all position and orientation values set to 0. */
export const ZERO_POSE: Pose = { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 };
