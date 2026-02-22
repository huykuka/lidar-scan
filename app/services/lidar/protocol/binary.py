"""
Binary protocol utilities for LiDAR data transmission.

Implements the LIDR binary format for efficient WebSocket streaming:
    Offset | Size | Type    | Description
    -------|------|---------|------------
    0      | 4    | char[4] | Magic "LIDR"
    4      | 4    | uint32  | Version
    8      | 8    | float64 | Timestamp
    16     | 4    | uint32  | Point count
    20     | N*12 | float32 | Points (x, y, z) * count
"""
import struct
import numpy as np


MAGIC_BYTES = b'LIDR'
VERSION = 1


def pack_points_binary(points: np.ndarray, timestamp: float) -> bytes:
    """
    Packs point cloud data into LIDR binary format.
    
    Args:
        points: Numpy array of shape (N, 3) or (N, M) where M >= 3
                Only the first 3 columns (x, y, z) are packed
        timestamp: Unix timestamp as float64
    
    Returns:
        Binary data in LIDR format
    """
    count = len(points)
    
    # Pack header: magic (4 bytes), version (4 bytes), timestamp (8 bytes), count (4 bytes)
    header = struct.pack('<4sIdI', MAGIC_BYTES, VERSION, timestamp, count)
    
    # Ensure we only send X, Y, Z (first 3 columns) to match the (N * 12 bytes) format
    points_xyz = points[:, :3].astype(np.float32)
    
    return header + points_xyz.tobytes()


def unpack_points_binary(data: bytes) -> tuple[np.ndarray, float]:
    """
    Unpacks point cloud data from LIDR binary format.
    
    Args:
        data: Binary data in LIDR format
    
    Returns:
        Tuple of (points, timestamp) where:
            - points is numpy array of shape (N, 3)
            - timestamp is float64
    
    Raises:
        ValueError: If magic bytes don't match or version is unsupported
        struct.error: If data is malformed
    """
    # Unpack header (20 bytes total)
    magic, version, timestamp, count = struct.unpack('<4sIdI', data[:20])
    
    if magic != MAGIC_BYTES:
        raise ValueError(f"Invalid magic bytes: {magic}")
    
    if version != VERSION:
        raise ValueError(f"Unsupported version: {version}")
    
    # Extract points data
    points_data = data[20:]
    expected_size = count * 12  # 3 floats * 4 bytes each
    
    if len(points_data) != expected_size:
        raise ValueError(
            f"Points data size mismatch: expected {expected_size} bytes, got {len(points_data)}"
        )
    
    # Reshape into (N, 3) array
    points = np.frombuffer(points_data, dtype=np.float32).reshape(count, 3)
    
    return points, timestamp
