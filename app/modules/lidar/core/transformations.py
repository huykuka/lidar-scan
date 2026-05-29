"""
Transformation and mathematical utilities for lidar point cloud processing.
"""
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


def gravity_to_roll_pitch(ax: float, ay: float, az: float) -> tuple[float, float]:
    """Derive roll and pitch (in degrees) from a raw accelerometer / gravity vector.

    The sensor's linear_acceleration field contains gravity when stationary.
    Assuming the sensor's Z-axis points roughly upward:

        roll  = atan2(ay, az)          — tilt around X
        pitch = atan2(-ax, √(ay² + az²)) — tilt around Y

    Returns:
        (roll_deg, pitch_deg)
    """
    roll = np.degrees(np.arctan2(ay, az))
    pitch = np.degrees(np.arctan2(-ax, np.sqrt(ay ** 2 + az ** 2)))
    return float(roll), float(pitch)


def imu_gravity_alignment_matrix(ax: float, ay: float, az: float) -> np.ndarray:
    """Build a pure-rotation 4×4 matrix that aligns the gravity vector with -Z.

    When applied to a point cloud the result is "gravity-compensated" — the
    world Z axis points opposite to gravity regardless of how the sensor is
    physically mounted.

    Args:
        ax, ay, az: Linear acceleration readings (m/s²). Expected to be
            dominated by the gravity component when the sensor is stationary.

    Returns:
        4×4 rotation-only transformation matrix (no translation).
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
