"""
Binary protocol utilities for LiDAR data transmission.

Implements the LIDR binary format for efficient WebSocket streaming:
    
LIDR v1 (legacy):
    Offset | Size | Type    | Description
    -------|------|---------|------------
    0      | 4    | char[4] | Magic "LIDR"
    4      | 4    | uint32  | Version (1)
    8      | 8    | float64 | Timestamp
    16     | 4    | uint32  | Point count
    20     | N*12 | float32 | Points (x, y, z) * count

LIDR v2 (ML extensions):
    Offset | Size | Type    | Description
    -------|------|---------|------------
    0      | 4    | char[4] | Magic "LIDR"
    4      | 4    | uint32  | Version (2)
    8      | 8    | float64 | Timestamp
    16     | 4    | uint32  | Point count
    20     | 4    | uint32  | Flags (bit 0=labels, bit 1=boxes)
    24     | N*12 | float32 | Points (x, y, z) * count
    24+N*12| N*4  | int32   | Labels * count (if flags & 0x01)
    (var)  | 4    | uint32  | JSON length (if flags & 0x02)
    (var)  | var  | bytes   | JSON boxes data (if flags & 0x02)
"""
import struct
import json
import numpy as np
from typing import Dict, Any, List, Optional, Tuple


MAGIC_BYTES = b'LIDR'
VERSION_V1 = 1
VERSION_V2 = 2

# LIDR v2 flags
FLAG_HAS_LABELS = 0x01
FLAG_HAS_BOXES = 0x02


def pack_points_binary(points: np.ndarray, timestamp: float, payload: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Packs point cloud data into LIDR binary format (v1 or v2 based on ML data presence).
    
    Args:
        points: Numpy array of shape (N, 3) or (N, M) where M >= 3
                Only the first 3 columns (x, y, z) are packed
        timestamp: Unix timestamp as float64
        payload: Optional payload dict containing ML data (ml_labels, bounding_boxes)
    
    Returns:
        Binary data in LIDR v1 or v2 format
    """
    count = len(points)
    
    # Ensure we only send X, Y, Z (first 3 columns) to match the (N * 12 bytes) format
    points_xyz = points[:, :3].astype(np.float32)
    
    # Check for ML data to determine version
    ml_labels = payload.get("ml_labels") if payload else None
    bounding_boxes = payload.get("bounding_boxes") if payload else None
    
    has_labels = ml_labels is not None and len(ml_labels) > 0
    has_boxes = bounding_boxes is not None and len(bounding_boxes) > 0
    
    # Use v2 if any ML data present, otherwise v1
    if has_labels or has_boxes:
        return _pack_v2_frame(points_xyz, timestamp, count, ml_labels, bounding_boxes)
    else:
        return _pack_v1_frame(points_xyz, timestamp, count)


def _pack_v1_frame(points_xyz: np.ndarray, timestamp: float, count: int) -> bytes:
    """Pack LIDR v1 frame (backward compatibility)"""
    # Pack header: magic (4 bytes), version (4 bytes), timestamp (8 bytes), count (4 bytes)
    header = struct.pack('<4sIdI', MAGIC_BYTES, VERSION_V1, timestamp, count)
    return header + points_xyz.tobytes()


def _pack_v2_frame(
    points_xyz: np.ndarray, 
    timestamp: float, 
    count: int, 
    ml_labels: Optional[np.ndarray], 
    bounding_boxes: Optional[List[Dict[str, Any]]]
) -> bytes:
    """Pack LIDR v2 frame with ML extensions"""
    
    # Build flags
    flags = 0
    if ml_labels is not None and len(ml_labels) > 0:
        flags |= FLAG_HAS_LABELS
    if bounding_boxes is not None and len(bounding_boxes) > 0:
        flags |= FLAG_HAS_BOXES
    
    # Pack header: magic (4), version (4), timestamp (8), count (4), flags (4)
    header = struct.pack('<4sIdII', MAGIC_BYTES, VERSION_V2, timestamp, count, flags)
    
    # Add XYZ data
    data = header + points_xyz.tobytes()
    
    # Add labels if present
    if flags & FLAG_HAS_LABELS and ml_labels is not None:
        labels_int32 = ml_labels.astype(np.int32)
        data += labels_int32.tobytes()
    
    # Add bounding boxes if present  
    if flags & FLAG_HAS_BOXES and bounding_boxes is not None:
        # Serialize bounding boxes as JSON
        boxes_json = json.dumps(bounding_boxes).encode('utf-8')
        json_length = len(boxes_json)
        
        # Add length prefix + JSON data
        data += struct.pack('<I', json_length)
        data += boxes_json
    
    return data


def unpack_points_binary(data: bytes) -> Tuple[np.ndarray, float, Dict[str, Any]]:
    """
    Unpacks point cloud data from LIDR binary format (v1 or v2).
    
    Args:
        data: Binary data in LIDR format
    
    Returns:
        Tuple of (points, timestamp, metadata) where:
            - points is numpy array of shape (N, 3)
            - timestamp is float64
            - metadata contains ML data (labels, boxes) for v2
    
    Raises:
        ValueError: If magic bytes don't match or version is unsupported
        struct.error: If data is malformed
    """
    if len(data) < 20:
        raise ValueError(f"Data too short: {len(data)} bytes, need at least 20")
        
    # Unpack header (20 bytes minimum for v1)
    magic, version, timestamp, count = struct.unpack('<4sIdI', data[:20])
    
    if magic != MAGIC_BYTES:
        raise ValueError(f"Invalid magic bytes: {magic}")
    
    metadata = {}
    
    if version == VERSION_V1:
        return _unpack_v1_frame(data, timestamp, count, metadata)
    elif version == VERSION_V2:
        return _unpack_v2_frame(data, timestamp, count, metadata)
    else:
        raise ValueError(f"Unsupported version: {version}")


def _unpack_v1_frame(data: bytes, timestamp: float, count: int, metadata: Dict[str, Any]) -> Tuple[np.ndarray, float, Dict[str, Any]]:
    """Unpack LIDR v1 frame"""
    # Extract points data (starts at offset 20)
    points_data = data[20:]
    expected_size = count * 12  # 3 floats * 4 bytes each
    
    if len(points_data) != expected_size:
        raise ValueError(
            f"Points data size mismatch: expected {expected_size} bytes, got {len(points_data)}"
        )
    
    # Reshape into (N, 3) array
    points = np.frombuffer(points_data, dtype=np.float32).reshape(count, 3)
    
    return points, timestamp, metadata


def _unpack_v2_frame(data: bytes, timestamp: float, count: int, metadata: Dict[str, Any]) -> Tuple[np.ndarray, float, Dict[str, Any]]:
    """Unpack LIDR v2 frame with ML extensions"""
    if len(data) < 24:
        raise ValueError(f"LIDR v2 data too short: {len(data)} bytes, need at least 24")
    
    # Extract flags (offset 20-24)
    flags = struct.unpack('<I', data[20:24])[0]
    
    # Extract XYZ points (starts at offset 24)
    points_start = 24
    points_size = count * 12  # 3 floats * 4 bytes each
    points_end = points_start + points_size
    
    if len(data) < points_end:
        raise ValueError(f"Insufficient data for points: need {points_end} bytes, got {len(data)}")
    
    points_data = data[points_start:points_end]
    points = np.frombuffer(points_data, dtype=np.float32).reshape(count, 3)
    
    # Parse optional ML data
    offset = points_end
    
    # Extract labels if present
    if flags & FLAG_HAS_LABELS:
        labels_size = count * 4  # int32
        if len(data) < offset + labels_size:
            raise ValueError(f"Insufficient data for labels: need {labels_size} bytes at offset {offset}")
        
        labels_data = data[offset:offset + labels_size]
        labels = np.frombuffer(labels_data, dtype=np.int32)
        metadata["ml_labels"] = labels
        offset += labels_size
    
    # Extract bounding boxes if present
    if flags & FLAG_HAS_BOXES:
        if len(data) < offset + 4:
            raise ValueError(f"Insufficient data for JSON length at offset {offset}")
        
        json_length = struct.unpack('<I', data[offset:offset + 4])[0]
        offset += 4
        
        if len(data) < offset + json_length:
            raise ValueError(f"Insufficient data for JSON: need {json_length} bytes at offset {offset}")
        
        json_data = data[offset:offset + json_length]
        try:
            bounding_boxes = json.loads(json_data.decode('utf-8'))
            metadata["bounding_boxes"] = bounding_boxes
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to decode bounding boxes JSON: {e}")
    
    return points, timestamp, metadata


def pack_recording_binary(points: np.ndarray, timestamp: float) -> bytes:
    """
    Packs point cloud data into LIDR archive binary format, supporting N-dimensional fields.
    
    Args:
        points: Numpy array of shape (N, M) where M is the number of fields (e.g. X, Y, Z, Intensity)
        timestamp: Unix timestamp as float64
    
    Returns:
        Binary data in LIDR format
    """
    count = len(points)
    dims = points.shape[1] if len(points.shape) > 1 else 0
    
    # Pack header: magic (4), version (4), timestamp (8), count (4), dims (4)
    # Version 2 allows arbitrary dimensions.
    header = struct.pack('<4sIdII', b'LIDR', VERSION_V2, timestamp, count, dims)
    
    points_float32 = points.astype(np.float32)
    
    return header + points_float32.tobytes()


def unpack_recording_binary(data: bytes) -> tuple[np.ndarray, float]:
    """
    Unpacks point cloud data from LIDR archive binary format.
    
    Args:
        data: Binary data in LIDR format
    
    Returns:
        Tuple of (points, timestamp) where:
            - points is numpy array of shape (N, M)
            - timestamp is float64
    """
    # Unpack header (24 bytes total)
    magic, version, timestamp, count, dims = struct.unpack('<4sIdII', data[:24])
    
    if magic != b'LIDR':
        raise ValueError(f"Invalid magic bytes: {magic}")
    
    if version != VERSION_V2:
        raise ValueError(f"Unsupported recording version: {version}")
    
    # Extract points data
    points_data = data[24:]
    expected_size = count * dims * 4  # 4 bytes per float32
    
    if len(points_data) != expected_size:
        raise ValueError(
            f"Points data size mismatch: expected {expected_size} bytes, got {len(points_data)}"
        )
    
    # Reshape into (N, M) array
    points = np.frombuffer(points_data, dtype=np.float32).reshape(count, dims)
    
    return points, timestamp
