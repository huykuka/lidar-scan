"""
Recording file format for LiDAR data archives.

Implements a ZIP-based PCD archive format for compatibility and compression:

File Structure (ZIP):
    - metadata.json: Contains recording metadata, timestamps, and frame counts.
    - frame_00000.pcd: Standard binary PCD file for frame 0
    - frame_00001.pcd: Standard binary PCD file for frame 1
    ...
"""
import json
import zipfile
from pathlib import Path
from typing import Any, Iterator
import numpy as np


# Known schemas for automatic detection
SICK_SCAN_SCHEMA = [
    "x", "y", "z", "lidar_nsec", "lidar_sec", "timestamp", "ring", 
    "elevation", "ts", "azimuth", "range", "reflector", "echo", "intensity",
    "attr_14", "attr_15"
]

PIPELINE_SCHEMA = [
    "x", "y", "z", "lidar_nsec", "lidar_sec", "t", "layer", 
    "elevation", "ts", "azimuth", "range", "reflector", "echo", "intensity"
]

def pack_pcd_bytes(points: np.ndarray, field_names: list[str] | None = None) -> bytes:
    """
    Creates a standard ASCII PCD file string natively in memory.
    Detects known schemas based on column counts if field_names are not provided.
    """
    count = len(points)
    dims = points.shape[1] if len(points.shape) > 1 else 3
    
    # Determine field names
    fields = []
    if field_names and len(field_names) >= dims:
        fields = field_names[:dims]
    else:
        # Automatic detection based on dimension count
        if dims == 16:
            fields = SICK_SCAN_SCHEMA
        elif dims == 14:
            fields = PIPELINE_SCHEMA
        else:
            # Generic naming for unknown layouts
            standard = ["x", "y", "z", "intensity", "ring", "timestamp"]
            for i in range(dims):
                if i < len(standard):
                    fields.append(standard[i])
                else:
                    fields.append(f"attr_{i}")
            
    fields_str = " ".join(fields)
    size_str = " ".join(["4"] * dims)
    type_str = " ".join(["F"] * dims)
    count_str = " ".join(["1"] * dims)
    
    header = f"""# .PCD v0.7 - Point Cloud Data file format
VERSION 0.7
FIELDS {fields_str}
SIZE {size_str}
TYPE {type_str}
COUNT {count_str}
WIDTH {count}
HEIGHT 1
VIEWPOINT 0 0 0 1 0 0 0
POINTS {count}
DATA ascii
"""
    # Create ASCII data lines with 6 decimal places for precision
    data_lines = []
    for point in points:
        line = " ".join(map(lambda x: f"{x:.6f}", point))
        data_lines.append(line)
    
    return (header + "\n".join(data_lines) + "\n").encode('ascii')


def unpack_pcd_bytes(data: bytes) -> np.ndarray:
    """Parses a standard ASCII PCD file natively from memory."""
    # Find start of data
    ascii_data_idx = data.find(b"DATA ascii")
    if ascii_data_idx == -1:
        raise ValueError("Invalid PCD format: expected DATA ascii")
        
    start_idx = data.find(b"\n", ascii_data_idx) + 1
        
    header = data[:start_idx].decode('ascii')
    points_count = 0
    dims = 3
    for line in header.split('\n'):
        if line.startswith("POINTS "):
            points_count = int(line.split()[1])
        elif line.startswith("FIELDS "):
            dims = len(line.split()) - 1
            
    # ASCII parsing
    points_text = data[start_idx:].decode('ascii')
    # Filter out empty lines and split each line into values
    lines = [line.strip().split() for line in points_text.split('\n') if line.strip()]
    if len(lines) < points_count:
        points_count = len(lines)
    
    # Convert to numpy array
    points = np.zeros((points_count, dims), dtype=np.float32)
    for i in range(points_count):
        line_vals = lines[i]
        num_vals = min(len(line_vals), dims)
        points[i, :num_vals] = [float(v) for v in line_vals[:num_vals]]
            
    return points


class RecordingWriter:
    """
    Writer for creating ZIP PCD archives.
    
    Usage:
        writer = RecordingWriter("recording.zip", metadata)
        writer.write_frame(points1, timestamp1)
        writer.write_frame(points2, timestamp2)
        writer.finalize()
    """
    
    def __init__(self, file_path: str | Path, metadata: dict[str, Any]):
        self.file_path = Path(file_path).with_suffix(".zip")
        self.metadata = metadata
        self.frame_count = 0
        self.timestamps: list[float] = []
        self.start_timestamp: float | None = None
        self.end_timestamp: float | None = None
        
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.zipf = zipfile.ZipFile(self.file_path, 'w', compression=zipfile.ZIP_DEFLATED)
    
    def write_frame(self, points: np.ndarray, timestamp: float):
        if self.zipf is None:
            raise RuntimeError("Recording file is not open")
        
        if self.start_timestamp is None:
            self.start_timestamp = timestamp
        self.end_timestamp = timestamp
        
        # Pass field names from metadata if available
        field_names = self.metadata.get("fields")
        pcd_bytes = pack_pcd_bytes(points, field_names=field_names)
        self.zipf.writestr(f"frame_{self.frame_count:05d}.pcd", pcd_bytes)
        
        self.timestamps.append(timestamp)
        self.frame_count += 1
    
    def finalize(self) -> dict[str, Any]:
        if self.zipf is None:
            raise RuntimeError("Recording file is not open")
        
        self.metadata["timestamps"] = self.timestamps
        self.metadata["frame_count"] = self.frame_count
        self.metadata["start_timestamp"] = self.start_timestamp
        self.metadata["end_timestamp"] = self.end_timestamp
        
        self.zipf.writestr("metadata.json", json.dumps(self.metadata, indent=2))
        self.zipf.close()
        self.zipf = None
        
        file_size = self.file_path.stat().st_size
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
        if self.zipf is not None:
            if exc_type is None:
                self.finalize()
            else:
                self.zipf.close()
                self.zipf = None


class RecordingReader:
    """
    Reader for ZIP PCD archives.
    
    Usage:
        reader = RecordingReader("recording.zip")
        print(reader.metadata)
        for points, timestamp in reader.iter_frames():
            process(points, timestamp)
    """
    
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path).with_suffix(".zip")
        
        if not self.file_path.exists():
            # Try falling back to old .lidr formats gently
            if Path(file_path).with_suffix(".lidr").exists():
                raise TypeError("This is a legacy .lidr file and cannot be read by the ZIP PCD reader.")
            raise FileNotFoundError(f"Recording file not found: {self.file_path}")
        
        self.zipf = zipfile.ZipFile(self.file_path, 'r')
        
        try:
            metadata_bytes = self.zipf.read("metadata.json")
            self.metadata = json.loads(metadata_bytes.decode('utf-8'))
        except KeyError:
            raise ValueError("Invalid recording ZIP: missing metadata.json")
            
        self.frame_count = self.metadata.get("frame_count", 0)
        self.timestamps = self.metadata.get("timestamps", [0.0] * self.frame_count)
        self.start_timestamp = self.metadata.get("start_timestamp", 0.0)
        self.end_timestamp = self.metadata.get("end_timestamp", 0.0)
        self.duration = self.end_timestamp - self.start_timestamp
    
    def get_frame(self, frame_index: int) -> tuple[np.ndarray, float]:
        if frame_index < 0 or frame_index >= self.frame_count:
            raise IndexError(f"Frame index {frame_index} out of range [0, {self.frame_count})")
        
        filename = f"frame_{frame_index:05d}.pcd"
        pcd_bytes = self.zipf.read(filename)
        points = unpack_pcd_bytes(pcd_bytes)
        
        return points, self.timestamps[frame_index]
    
    def iter_frames(self, start: int = 0, end: int | None = None) -> Iterator[tuple[np.ndarray, float]]:
        if end is None:
            end = self.frame_count
            
        for i in range(start, min(end, self.frame_count)):
            yield self.get_frame(i)
    
    def get_info(self) -> dict[str, Any]:
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
    reader = RecordingReader(file_path)
    return reader.get_info()
