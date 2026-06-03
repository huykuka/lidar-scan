"""
Transformation and mathematical utilities for lidar point cloud processing.
"""
import math

import numpy as np
from typing import Dict


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
    """Build a leveling matrix from the IMU orientation quaternion.

    The quaternion encodes the sensor→world rotation (per ROS sensor_msgs/Imu).
    Applying the resulting matrix to sensor-frame points produces
    gravity-aligned (leveled) points.  Only roll and pitch are used — yaw is
    excluded because it drifts and is irrelevant for mounting adjustment.

    Args:
        w, x, y, z: Unit quaternion from SickScanImuMsg.orientation.

    Returns:
        4×4 rotation-only transformation matrix.
    """
    roll, pitch, _yaw = quaternion_to_rpy(w, x, y, z)
    return create_transformation_matrix(0, 0, 0, roll=roll, pitch=pitch, yaw=0)


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
