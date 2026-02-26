import struct
import numpy as np
import open3d as o3d
from typing import Tuple

def unpack_lidr_binary(data: bytes) -> Tuple[np.ndarray, float]:
    """
    Unpacks points from binary format:
    Magic (4 bytes): 'LIDR'
    Version (4 bytes): 1 (uint32)
    Timestamp (8 bytes): float64
    Point Count (4 bytes): uint32
    Points (N * 12 bytes): x, y, z as float32
    """
    header_size = 4 + 4 + 8 + 4
    if len(data) < header_size:
        raise ValueError("Data too short to contain LIDR header")
        
    magic, version, timestamp, count = struct.unpack('<4sIdI', data[:header_size])
    if magic != b'LIDR':
        raise ValueError(f"Invalid magic: {magic}")
        
    points = np.frombuffer(data[header_size:], dtype=np.float32).reshape(count, 3)
    return points, timestamp

def save_to_pcd(points: np.ndarray, output_path: str, binary: bool = False):
    """Saves a (N, 3) numpy array to a PCD file."""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    o3d.io.write_point_cloud(output_path, pcd, write_ascii=not binary)
