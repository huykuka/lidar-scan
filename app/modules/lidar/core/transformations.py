"""
Transformation and mathematical utilities for lidar point cloud processing.
"""
import math
from typing import Dict

import numpy as np


def create_transformation_matrix(
        x: float, y: float, z: float,
        roll: float = 0, pitch: float = 0, yaw: float = 0
) -> np.ndarray:
    """
    Creates a 4x4 transformation matrix from translation and rotation parameters.
    
    Args:
        x, y, z: Translation in meters
        roll, pitch, yaw: Rotation in degrees
    
    Returns:
        4x4 numpy array representing the transformation matrix
    """
    # Convert degrees to radians for internal math
    roll_rad = np.radians(roll)
    pitch_rad = np.radians(pitch)
    yaw_rad = np.radians(yaw)

    # Translation
    T = np.eye(4)
    T[:3, 3] = [x, y, z]

    # Rotation (Z-Y-X order)
    cr, sr = np.cos(roll_rad), np.sin(roll_rad)
    cp, sp = np.cos(pitch_rad), np.sin(pitch_rad)
    cy, sy = np.cos(yaw_rad), np.sin(yaw_rad)

    R = np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr]
    ])

    T[:3, :3] = R
    return T


def transform_points(points: np.ndarray, T: np.ndarray) -> np.ndarray:
    """
    Applies a 4x4 transformation matrix T to (N, 3) or (N, M) points.
    Efficiently handles rotation and translation using numpy.
    
    Args:
        points: Numpy array of shape (N, 3) or (N, M) where M >= 3
        T: 4x4 transformation matrix
    
    Returns:
        Transformed points with the same shape as input
    """
    if points is None or len(points) == 0:
        return points

    # Skip if identity matrix
    if np.array_equal(T, np.eye(4)):
        return points

    # R is top-left 3x3, t is top-right 3x1
    R = T[:3, :3]
    t = T[:3, 3]

    # Apply transformation only to the first 3 columns (x, y, z)
    result = points.copy()
    result[:, :3] = points[:, :3] @ R.T + t
    return result


def quaternion_to_rpy(
        w: float, x: float, y: float, z: float,
) -> tuple[float, float, float]:
    """Convert an orientation quaternion to roll/pitch/yaw (degrees).

    Uses the same ZYX-intrinsic (XYZ-extrinsic) convention as the SICK
    multiScan SDK and ROS sensor_msgs/Imu.  The quaternion represents the
    rotation from sensor frame to a gravity-aligned world frame.

    Reference implementation (Lua, from SICK AppSpace demo)::

        roll  = atan2(2*(w*x + y*z), 1 - 2*(x*x + y*y))
        pitch = asin(2*(w*y - z*x))
        yaw   = atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))

    Args:
        w, x, y, z: Unit quaternion components (scalar-last layout in the
            struct, but *w* is passed first here to match the SICK Lua API).

    Returns:
        (roll_deg, pitch_deg, yaw_deg)
    """
    # Roll (X-axis rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (Y-axis rotation) — clamp to avoid NaN near ±90°
    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)

    # Yaw (Z-axis rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def quaternion_is_valid(w: float, x: float, y: float, z: float) -> bool:
    """Return True if the quaternion has a reasonable unit norm (not zeros)."""
    norm_sq = w * w + x * x + y * y + z * z
    return norm_sq > 0.5


def imu_orientation_matrix(
        w: float, x: float, y: float, z: float,
) -> np.ndarray:
    """Build an orientation matrix from the IMU quaternion.

    The quaternion encodes the sensor→world rotation (per ROS sensor_msgs/Imu).
    Applying the resulting matrix to sensor-frame points produces
    world-aligned points.  All three axes (roll, pitch, yaw) are applied —
    this is intended for continuous auto-level on dynamic platforms where the
    full real-time orientation is needed.

    Args:
        w, x, y, z: Unit quaternion from SickScanImuMsg.orientation.

    Returns:
        4×4 rotation-only transformation matrix.
    """
    roll, pitch, yaw = quaternion_to_rpy(w, x, y, z)
    return create_transformation_matrix(0, 0, 0, roll=roll, pitch=pitch, yaw=yaw)


def gravity_to_roll_pitch(ax: float, ay: float, az: float) -> tuple[float, float]:
    """Derive roll and pitch (in degrees) from a raw accelerometer / gravity vector.

    Fallback method when the orientation quaternion is unavailable (all zeros).
    The sensor's linear_acceleration field contains gravity when stationary.

        roll  = atan2(ay, az)          — tilt around X
        pitch = atan2(-ax, √(ay² + az²)) — tilt around Y

    Returns:
        (roll_deg, pitch_deg)
    """
    roll = np.degrees(np.arctan2(ay, az))
    pitch = np.degrees(np.arctan2(-ax, np.sqrt(ay ** 2 + az ** 2)))
    return float(roll), float(pitch)


def imu_gravity_alignment_matrix(ax: float, ay: float, az: float) -> np.ndarray:
    """Build a leveling matrix from the raw accelerometer gravity vector.

    Fallback for when orientation quaternion is not available.
    Negates the gravity-derived angles to undo sensor tilt.

    Args:
        ax, ay, az: Linear acceleration readings (m/s²).

    Returns:
        4×4 rotation-only transformation matrix.
    """
    roll, pitch = gravity_to_roll_pitch(ax, ay, az)
    # Negate to *undo* the tilt (align gravity back to -Z)
    return create_transformation_matrix(0, 0, 0, roll=-roll, pitch=-pitch, yaw=0)


def plane_normal_to_roll_pitch(
        normal: np.ndarray,
        up: np.ndarray = np.array([0.0, 0.0, 1.0]),
) -> tuple[float, float]:
    """Roll/pitch (degrees) of the minimal rotation aligning *normal* to *up*.

    Used by floor-plane auto-level: given a segmented ground-plane normal
    (in world frame), compute the tilt correction that would make the plane
    horizontal.  Yaw is unconstrained by a single plane and is discarded.

    The returned angles are a *residual* correction to be added to the current
    pose; repeated application converges to a flat floor (normal == up).

    Args:
        normal: Plane normal (need not be unit length or oriented).
        up: World up-axis (defaults to +Z).

    Returns:
        (roll_deg, pitch_deg) — zero when already aligned.
    """
    n = np.asarray(normal, dtype=np.float64)
    n_norm = np.linalg.norm(n)
    if n_norm < 1e-12:
        return 0.0, 0.0
    n = n / n_norm
    u = np.asarray(up, dtype=np.float64)
    u = u / np.linalg.norm(u)

    # Orient the normal toward up so the correction is the minimal one.
    if float(np.dot(n, u)) < 0.0:
        n = -n

    cos_a = float(np.clip(np.dot(n, u), -1.0, 1.0))
    if cos_a > 1.0 - 1e-9:
        return 0.0, 0.0  # already horizontal

    axis = np.cross(n, u)
    axis_norm = np.linalg.norm(axis)
    if axis_norm < 1e-12:
        return 0.0, 0.0
    axis = axis / axis_norm
    angle = math.acos(cos_a)

    # Rodrigues' rotation matrix for (axis, angle).
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    C = 1.0 - c
    R = np.array([
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
    ])

    # Decompose using the same ZYX convention as create_transformation_matrix.
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -R[2, 0]))))
    roll = math.degrees(math.atan2(R[2, 1], R[2, 2]))
    return roll, pitch


def pose_to_dict(
        x: float, y: float, z: float,
        roll: float, pitch: float, yaw: float
) -> Dict[str, float]:
    """
    Converts pose parameters to a dictionary.
    
    Args:
        x, y, z: Translation in meters
        roll, pitch, yaw: Rotation in degrees
    
    Returns:
        Dictionary with keys: x, y, z, roll, pitch, yaw
    """
    result: Dict[str, float] = {
        "x": float(x),
        "y": float(y),
        "z": float(z),
        "roll": float(roll),
        "pitch": float(pitch),
        "yaw": float(yaw)
    }
    return result
