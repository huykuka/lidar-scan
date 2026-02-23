"""
Recording file format for LiDAR data archives.

Implements the Indexed LIDR Archive format for efficient recording and playback:

File Structure:
    [File Header - 72 bytes fixed]
      - Magic: "LIDRARCH" (8 bytes)
      - Version: uint32 (4 bytes)
      - Frame count: uint32 (4 bytes)
      - Metadata offset: uint64 (8 bytes) - pointer to JSON metadata
      - Index offset: uint64 (8 bytes) - pointer to frame index
      - First frame offset: uint64 (8 bytes)
      - Recording start timestamp: float64 (8 bytes)
      - Recording end timestamp: float64 (8 bytes)
      - Reserved: 16 bytes (future use)

    [Frames Section - variable size]
      - Frame 0: [LIDR Binary - 20 byte header + N*12 bytes points]
      - Frame 1: [LIDR Binary]
      - ...

    [Frame Index - frame_count * 16 bytes]
      - Frame 0: [offset: uint64, size: uint32, reserved: uint32]
      - Frame 1: [offset: uint64, size: uint32, reserved: uint32]
      - ...

    [Metadata Section - variable size JSON]
      {
        "sensor_id": "lidar_01",
        "topic": "lidar01_raw_points",
        "name": "Front Lidar",
        ...
      }
"""
import json
import struct
from pathlib import Path
from typing import Any, BinaryIO, Iterator

import numpy as np

from .binary import pack_points_binary, unpack_points_binary


RECORDING_MAGIC = b'LIDRARCH'
RECORDING_VERSION = 1
HEADER_SIZE = 72  # 8+4+4+8+8+8+8+8+16 bytes
INDEX_ENTRY_SIZE = 16  # offset (8) + size (4) + reserved (4)


class RecordingWriter:
    """
    Writer for creating LIDR archive files.
    
    Usage:
        writer = RecordingWriter("recording.lidr", metadata)
        writer.write_frame(points1, timestamp1)
        writer.write_frame(points2, timestamp2)
        writer.finalize()
    """
    
    def __init__(self, file_path: str | Path, metadata: dict[str, Any]):
        """
        Initialize recording writer.
        
        Args:
            file_path: Output file path
            metadata: Recording metadata dictionary
        """
        self.file_path = Path(file_path)
        self.metadata = metadata
        self.file: BinaryIO | None = None
        self.frame_count = 0
        self.frame_index: list[tuple[int, int]] = []  # [(offset, size), ...]
        self.start_timestamp: float | None = None
        self.end_timestamp: float | None = None
        self.first_frame_offset = HEADER_SIZE
        
        # Create parent directory if needed
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Open file and write placeholder header
        self.file = open(self.file_path, 'wb')
        self._write_header_placeholder()
    
    def _write_header_placeholder(self):
        """Write placeholder header (will be updated in finalize)."""
        header = struct.pack(
            '<8sIIQQQdd16s',
            RECORDING_MAGIC,
            RECORDING_VERSION,
            0,  # frame_count (placeholder)
            0,  # metadata_offset (placeholder)
            0,  # index_offset (placeholder)
            HEADER_SIZE,  # first_frame_offset
            0.0,  # start_timestamp (placeholder)
            0.0,  # end_timestamp (placeholder)
            b'\x00' * 16  # reserved
        )
        assert len(header) == HEADER_SIZE
        self.file.write(header)
    
    def write_frame(self, points: np.ndarray, timestamp: float):
        """
        Write a frame to the recording.
        
        Args:
            points: Point cloud array (N, 3) or (N, M)
            timestamp: Frame timestamp
        """
        if self.file is None:
            raise RuntimeError("Recording file is not open")
        
        # Track timestamps
        if self.start_timestamp is None:
            self.start_timestamp = timestamp
        self.end_timestamp = timestamp
        
        # Pack frame using LIDR binary format
        frame_data = pack_points_binary(points, timestamp)
        
        # Record frame position and size
        offset = self.file.tell()
        size = len(frame_data)
        self.frame_index.append((offset, size))
        
        # Write frame data
        self.file.write(frame_data)
        self.frame_count += 1
    
    def finalize(self) -> dict[str, Any]:
        """
        Finalize recording by writing index, metadata, and updating header.
        
        Returns:
            Recording info dictionary
        """
        if self.file is None:
            raise RuntimeError("Recording file is not open")
        
        # Write frame index
        index_offset = self.file.tell()
        for offset, size in self.frame_index:
            index_entry = struct.pack('<QII', offset, size, 0)  # reserved = 0
            self.file.write(index_entry)
        
        # Write metadata
        metadata_offset = self.file.tell()
        metadata_json = json.dumps(self.metadata, indent=2).encode('utf-8')
        self.file.write(metadata_json)
        
        # Update header with final values
        self.file.seek(0)
        header = struct.pack(
            '<8sIIQQQdd16s',
            RECORDING_MAGIC,
            RECORDING_VERSION,
            self.frame_count,
            metadata_offset,
            index_offset,
            self.first_frame_offset,
            self.start_timestamp or 0.0,
            self.end_timestamp or 0.0,
            b'\x00' * 16  # reserved
        )
        self.file.write(header)
        
        # Close file
        file_size = self.file.tell()
        self.file.close()
        self.file = None
        
        # Calculate stats
        duration = (self.end_timestamp or 0.0) - (self.start_timestamp or 0.0)
        avg_fps = self.frame_count / duration if duration > 0 else 0.0
        
        return {
            "file_path": str(self.file_path),
            "file_size_bytes": file_size,
            "frame_count": self.frame_count,
            "duration_seconds": duration,
            "average_fps": avg_fps,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp
        }
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file is not None:
            if exc_type is None:
                self.finalize()
            else:
                self.file.close()
                self.file = None


class RecordingReader:
    """
    Reader for LIDR archive files.
    
    Usage:
        reader = RecordingReader("recording.lidr")
        print(reader.metadata)
        for points, timestamp in reader.iter_frames():
            process(points, timestamp)
    """
    
    def __init__(self, file_path: str | Path):
        """
        Initialize recording reader.
        
        Args:
            file_path: Path to recording file
        
        Raises:
            ValueError: If file format is invalid
        """
        self.file_path = Path(file_path)
        
        if not self.file_path.exists():
            raise FileNotFoundError(f"Recording file not found: {file_path}")
        
        with open(self.file_path, 'rb') as f:
            self._read_header(f)
            self._read_index(f)
            self._read_metadata(f)
    
    def _read_header(self, f: BinaryIO):
        """Read and parse file header."""
        header_data = f.read(HEADER_SIZE)
        
        if len(header_data) != HEADER_SIZE:
            raise ValueError("File too small to be valid LIDR archive")
        
        (magic, version, frame_count, metadata_offset, index_offset,
         first_frame_offset, start_timestamp, end_timestamp, _reserved) = struct.unpack(
            '<8sIIQQQdd16s', header_data
        )
        
        if magic != RECORDING_MAGIC:
            raise ValueError(f"Invalid magic bytes: {magic}")
        
        if version != RECORDING_VERSION:
            raise ValueError(f"Unsupported version: {version}")
        
        self.frame_count = frame_count
        self.metadata_offset = metadata_offset
        self.index_offset = index_offset
        self.first_frame_offset = first_frame_offset
        self.start_timestamp = start_timestamp
        self.end_timestamp = end_timestamp
        self.duration = end_timestamp - start_timestamp
    
    def _read_index(self, f: BinaryIO):
        """Read frame index."""
        f.seek(self.index_offset)
        index_data = f.read(self.frame_count * INDEX_ENTRY_SIZE)
        
        self.frame_index: list[tuple[int, int]] = []
        for i in range(self.frame_count):
            entry_data = index_data[i * INDEX_ENTRY_SIZE:(i + 1) * INDEX_ENTRY_SIZE]
            offset, size, _reserved = struct.unpack('<QII', entry_data)
            self.frame_index.append((offset, size))
    
    def _read_metadata(self, f: BinaryIO):
        """Read metadata JSON."""
        f.seek(self.metadata_offset)
        # Read until end of file
        metadata_json = f.read()
        self.metadata = json.loads(metadata_json.decode('utf-8'))
    
    def get_frame(self, frame_index: int) -> tuple[np.ndarray, float]:
        """
        Get a specific frame by index.
        
        Args:
            frame_index: Frame number (0-based)
        
        Returns:
            Tuple of (points, timestamp)
        
        Raises:
            IndexError: If frame_index is out of range
        """
        if frame_index < 0 or frame_index >= self.frame_count:
            raise IndexError(f"Frame index {frame_index} out of range [0, {self.frame_count})")
        
        offset, size = self.frame_index[frame_index]
        
        with open(self.file_path, 'rb') as f:
            f.seek(offset)
            frame_data = f.read(size)
        
        return unpack_points_binary(frame_data)
    
    def iter_frames(self, start: int = 0, end: int | None = None) -> Iterator[tuple[np.ndarray, float]]:
        """
        Iterate through frames.
        
        Args:
            start: Starting frame index (inclusive)
            end: Ending frame index (exclusive), None for all frames
        
        Yields:
            Tuple of (points, timestamp) for each frame
        """
        if end is None:
            end = self.frame_count
        
        with open(self.file_path, 'rb') as f:
            for i in range(start, min(end, self.frame_count)):
                offset, size = self.frame_index[i]
                f.seek(offset)
                frame_data = f.read(size)
                yield unpack_points_binary(frame_data)
    
    def get_info(self) -> dict[str, Any]:
        """
        Get recording information.
        
        Returns:
            Dictionary with recording stats
        """
        return {
            "file_path": str(self.file_path),
            "file_size_bytes": self.file_path.stat().st_size,
            "frame_count": self.frame_count,
            "duration_seconds": self.duration,
            "average_fps": self.frame_count / self.duration if self.duration > 0 else 0.0,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "metadata": self.metadata
        }


def get_recording_info(file_path: str | Path) -> dict[str, Any]:
    """
    Get recording info without loading all frames.
    
    Args:
        file_path: Path to recording file
    
    Returns:
        Recording info dictionary
    """
    reader = RecordingReader(file_path)
    return reader.get_info()
