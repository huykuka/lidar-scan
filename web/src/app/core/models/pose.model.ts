/**
 * Canonical 6-DOF sensor pose model.
 * This is the single source of truth for pose types across the frontend.
 */

/** Canonical 6-DOF sensor pose. Position in mm; angles in degrees [-180, +180]. */
export interface Pose {
  /** Translation X in millimeters */
  x: number;
  /** Translation Y in millimeters */
  y: number;
  /** Translation Z in millimeters */
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
