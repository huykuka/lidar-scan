"""
Recording file format for point cloud data.

Recordings are MCAP files (https://mcap.dev) with one ``foxglove.PointCloud``
protobuf message per frame, so they open directly in Foxglove Studio and other
MCAP-aware tools. This format is generic and can be used by any node that
produces point cloud data (LiDAR sensors, fusion nodes, processing operations).

File structure (MCAP):
    - channel ``/<node_id>/points`` (foxglove.PointCloud, zstd-compressed chunks)
    - metadata record ``lidar_recording`` with key ``metadata_json``: recording
      metadata, per-frame timestamps and frame counts

Legacy ZIP archives (metadata.json + frame_NNNNN.pcd) remain readable through
``RecordingReader``; use scripts/migrate_recordings_to_mcap.py to convert them.
"""
import json
import zipfile
from pathlib import Path
from typing import Any, Iterator
import numpy as np
import threading


MCAP_SUFFIX = ".mcap"
ZIP_SUFFIX = ".zip"
METADATA_RECORD_NAME = "lidar_recording"

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

def pack_pcd_bytes(points: np.ndarray, field_names: list[str] | None = None, binary: bool = True) -> bytes:
    """
    Creates a standard PCD file (binary or ASCII) preserving all fields.
    
    Binary format is 10x faster and 3-4x smaller than ASCII.
    Detects known schemas based on column counts if field_names are not provided.
    
    Args:
        points: NumPy array of shape (N, dims) with point cloud data
        field_names: Optional list of field names (e.g., ["x", "y", "z", "intensity"])
        binary: If True, use binary format (default). If False, use ASCII.
    
    Returns:
        Bytes representing a standard PCD file
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
    
    if binary:
        # Binary format: header + binary data (10x faster, 3-4x smaller)
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
DATA binary
"""
        header_bytes = header.encode('ascii')
        
        # Convert to float32 and get raw bytes
        points_float32 = points.astype(np.float32)
        data_bytes = points_float32.tobytes()
        
        return header_bytes + data_bytes
    else:
        # ASCII format (legacy - slow for large point clouds)
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
    """
    Parses a standard PCD file (binary or ASCII) natively from memory.
    Automatically detects format from header.
    
    Args:
        data: Bytes representing a PCD file
    
    Returns:
        NumPy array of shape (N, dims) with point cloud data
    """
    # Parse header to determine format
    header_end_idx = data.find(b"\nDATA ")
    if header_end_idx == -1:
        raise ValueError("Invalid PCD format: no DATA section found")
    
    header = data[:header_end_idx + 100].decode('ascii', errors='ignore')
    
    # Extract metadata from header
    points_count = 0
    dims = 3
    is_binary = False
    
    for line in header.split('\n'):
        if line.startswith("POINTS "):
            points_count = int(line.split()[1])
        elif line.startswith("FIELDS "):
            dims = len(line.split()) - 1
        elif line.startswith("DATA "):
            is_binary = "binary" in line.lower()
    
    if is_binary:
        # Binary format: fast parsing
        # Find the start of binary data (after "DATA binary\n")
        binary_data_idx = data.find(b"DATA binary")
        if binary_data_idx == -1:
            raise ValueError("Invalid PCD format: expected DATA binary")
        
        start_idx = data.find(b"\n", binary_data_idx) + 1
        
        # Read binary data as float32
        binary_data = data[start_idx:]
        expected_bytes = points_count * dims * 4  # 4 bytes per float32
        
        if len(binary_data) < expected_bytes:
            raise ValueError(f"Insufficient binary data: expected {expected_bytes} bytes, got {len(binary_data)}")
        
        # Parse as float32 array and reshape
        points = np.frombuffer(binary_data[:expected_bytes], dtype=np.float32)
        points = points.reshape((points_count, dims))
        
        return points
    else:
        # ASCII format: slower parsing
        ascii_data_idx = data.find(b"DATA ascii")
        if ascii_data_idx == -1:
            raise ValueError("Invalid PCD format: expected DATA ascii")
        
        start_idx = data.find(b"\n", ascii_data_idx) + 1
        
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


def resolve_field_names(dims: int, field_names: list[str] | None = None) -> list[str]:
    """Pick per-column names for a point array with ``dims`` columns."""
    if field_names and len(field_names) >= dims:
        return list(field_names[:dims])
    if dims == 16:
        return list(SICK_SCAN_SCHEMA)
    if dims == 14:
        return list(PIPELINE_SCHEMA)
    standard = ["x", "y", "z", "intensity", "ring", "timestamp"]
    return [standard[i] if i < len(standard) else f"attr_{i}" for i in range(dims)]


def _log_times_ns(timestamps: list[float]) -> list[int]:
    """Deterministic, strictly increasing MCAP log times for frame timestamps.

    Writer and reader both derive log times from the frame timestamps, so a frame
    can be located through the MCAP chunk index without scanning the file.
    """
    out: list[int] = []
    last = -1
    for ts in timestamps:
        ns = max(int(round(float(ts) * 1e9)), last + 1, 0)
        out.append(ns)
        last = ns
    return out


class RecordingWriter:
    """
    Writer for MCAP recordings (one ``foxglove.PointCloud`` message per frame).
    Thread-safe for concurrent async writes.

    Usage:
        writer = RecordingWriter("recording.mcap", metadata)
        writer.write_frame(points1, timestamp1)
        writer.write_frame(points2, timestamp2)
        writer.finalize()
    """

    def __init__(self, file_path: str | Path, metadata: dict[str, Any]):
        from mcap_protobuf.writer import Writer

        self.file_path = Path(file_path).with_suffix(MCAP_SUFFIX)
        self.metadata = metadata
        self.frame_count = 0
        self.timestamps: list[float] = []
        self.start_timestamp: float | None = None
        self.end_timestamp: float | None = None
        self._last_log_ns = -1
        self._lock = threading.Lock()
        self._topic = _topic_for(metadata)
        self._frame_id = str(metadata.get("node_id") or "lidar")

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.file_path, "wb")
        self._writer = Writer(self._fh)

    def _write_locked(self, points: np.ndarray, timestamp: float) -> None:
        if self.start_timestamp is None:
            self.start_timestamp = timestamp
        self.end_timestamp = timestamp

        log_ns = max(int(round(float(timestamp) * 1e9)), self._last_log_ns + 1, 0)
        self._last_log_ns = log_ns

        msg = _build_point_cloud(points, timestamp, log_ns, self._frame_id, self.metadata.get("fields"))
        self._writer.write_message(
            self._topic, msg, log_time=log_ns, publish_time=log_ns, sequence=self.frame_count
        )
        self.timestamps.append(timestamp)
        self.frame_count += 1

    def write_frame(self, points: np.ndarray, timestamp: float):
        with self._lock:
            if self._writer is None:
                raise RuntimeError("Recording file is not open")
            self._write_locked(points, timestamp)

    def write_batch(self, frames: list[tuple[np.ndarray, float]]):
        """Write multiple frames in a single batch operation for better performance."""
        with self._lock:
            if self._writer is None:
                raise RuntimeError("Recording file is not open")
            for points, timestamp in frames:
                self._write_locked(points, timestamp)

    def finalize(self) -> dict[str, Any]:
        with self._lock:
            if self._writer is None:
                raise RuntimeError("Recording file is not open")

            self.metadata["timestamps"] = self.timestamps
            self.metadata["frame_count"] = self.frame_count
            self.metadata["start_timestamp"] = self.start_timestamp
            self.metadata["end_timestamp"] = self.end_timestamp

            self._writer._writer.add_metadata(
                METADATA_RECORD_NAME, {"metadata_json": json.dumps(self.metadata)}
            )
            self._writer.finish()
            self._fh.close()
            self._writer = None

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
                "end_timestamp": self.end_timestamp,
            }

    def abort(self) -> None:
        """Close the file without writing the MCAP footer."""
        with self._lock:
            if self._writer is not None:
                self._fh.close()
                self._writer = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, tb):
        if self._writer is not None:
            if exc_type is None:
                self.finalize()
            else:
                self.abort()


def _topic_for(metadata: dict[str, Any]) -> str:
    node = str(metadata.get("node_id") or "lidar")
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in node)
    return f"/{safe}/points"


def _build_point_cloud(
    points: np.ndarray,
    timestamp: float,
    log_ns: int,
    frame_id: str,
    field_names: list[str] | None,
):
    from foxglove_schemas_protobuf.PackedElementField_pb2 import PackedElementField
    from foxglove_schemas_protobuf.PointCloud_pb2 import PointCloud

    pts = np.ascontiguousarray(points, dtype=np.float32)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 3) if pts.size % 3 == 0 else pts.reshape(-1, 1)
    dims = pts.shape[1]

    msg = PointCloud()
    msg.timestamp.seconds, msg.timestamp.nanos = divmod(log_ns, 1_000_000_000)
    msg.frame_id = frame_id
    msg.pose.orientation.w = 1.0
    msg.point_stride = dims * 4
    for i, name in enumerate(resolve_field_names(dims, field_names)):
        msg.fields.append(PackedElementField(name=name, offset=i * 4, type=PackedElementField.FLOAT32))
    msg.data = pts.tobytes()
    return msg


def _decode_point_cloud(data: bytes) -> np.ndarray:
    """Decode a foxglove.PointCloud payload into an (N, dims) float32 array."""
    from foxglove_schemas_protobuf.PackedElementField_pb2 import PackedElementField
    from foxglove_schemas_protobuf.PointCloud_pb2 import PointCloud

    msg = PointCloud()
    msg.ParseFromString(data)
    stride = msg.point_stride
    if stride == 0 or not msg.fields:
        return np.zeros((0, 0), dtype=np.float32)

    fields = list(msg.fields)
    n = len(msg.data) // stride
    f32 = PackedElementField.FLOAT32
    if (
        stride == len(fields) * 4
        and all(f.type == f32 and f.offset == i * 4 for i, f in enumerate(fields))
    ):
        return np.frombuffer(msg.data, dtype=np.float32, count=n * len(fields)).reshape(n, len(fields)).copy()

    # Generic path (files written by other tools): gather columns by offset/type.
    np_types = {
        PackedElementField.UINT8: "u1", PackedElementField.INT8: "i1",
        PackedElementField.UINT16: "<u2", PackedElementField.INT16: "<i2",
        PackedElementField.UINT32: "<u4", PackedElementField.INT32: "<i4",
        PackedElementField.FLOAT32: "<f4", PackedElementField.FLOAT64: "<f8",
    }
    dtype = np.dtype({
        "names": [f.name for f in fields],
        "formats": [np_types.get(f.type, "<f4") for f in fields],
        "offsets": [f.offset for f in fields],
        "itemsize": stride,
    })
    arr = np.frombuffer(msg.data, dtype=dtype, count=n)
    return np.stack([arr[f.name].astype(np.float32) for f in fields], axis=1) if n else np.zeros((0, len(fields)), np.float32)


class McapRecordingReader:
    """Reader for MCAP recordings holding ``foxglove.PointCloud`` messages."""

    def __init__(self, file_path: str | Path):
        from mcap.reader import make_reader

        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Recording file not found: {self.file_path}")

        self._lock = threading.Lock()
        self._fh = open(self.file_path, "rb")
        try:
            self._reader = make_reader(self._fh)
            summary = self._reader.get_summary()
            if summary is None:
                raise ValueError("Invalid MCAP recording: missing summary section")

            schemas = {s.id: s for s in summary.schemas.values()}
            topics = [
                c.topic for c in summary.channels.values()
                if schemas.get(c.schema_id) is not None
                and schemas[c.schema_id].name == "foxglove.PointCloud"
            ]
            if not topics:
                raise ValueError("Invalid recording: no foxglove.PointCloud channel found")
            self._topic = topics[0]

            self.metadata: dict[str, Any] = {}
            for rec in self._reader.iter_metadata():
                if rec.name == METADATA_RECORD_NAME and "metadata_json" in rec.metadata:
                    self.metadata = json.loads(rec.metadata["metadata_json"])
                    break

            timestamps = self.metadata.get("timestamps")
            if timestamps is not None:
                self.timestamps: list[float] = list(timestamps)
                self._log_times = _log_times_ns(self.timestamps)
            else:
                # Third-party MCAP: index frames by scanning message headers once.
                self._log_times = [
                    m.log_time for _, _, m in self._reader.iter_messages(topics=[self._topic])
                ]
                self.timestamps = [t / 1e9 for t in self._log_times]
        except Exception:
            self._fh.close()
            raise

        self.frame_count = len(self._log_times)
        self.start_timestamp = self.metadata.get(
            "start_timestamp", self.timestamps[0] if self.timestamps else 0.0
        )
        self.end_timestamp = self.metadata.get(
            "end_timestamp", self.timestamps[-1] if self.timestamps else 0.0
        )
        self.duration = (self.end_timestamp or 0.0) - (self.start_timestamp or 0.0)

    def get_frame(self, frame_index: int) -> tuple[np.ndarray, float]:
        if frame_index < 0 or frame_index >= self.frame_count:
            raise IndexError(f"Frame index {frame_index} out of range [0, {self.frame_count})")
        log_ns = self._log_times[frame_index]
        with self._lock:
            for _, _, message in self._reader.iter_messages(
                topics=[self._topic], start_time=log_ns, end_time=log_ns + 1
            ):
                return _decode_point_cloud(message.data), self.timestamps[frame_index]
        raise ValueError(f"Frame {frame_index} missing from recording")

    def iter_frames(self, start: int = 0, end: int | None = None) -> Iterator[tuple[np.ndarray, float]]:
        end = self.frame_count if end is None else min(end, self.frame_count)
        if start >= end:
            return
        with self._lock:
            # Materialize the byte payloads under the lock; decode lazily outside it.
            payloads = [
                m.data for _, _, m in self._reader.iter_messages(
                    topics=[self._topic],
                    start_time=self._log_times[start],
                    end_time=self._log_times[end - 1] + 1,
                )
            ]
        for i, data in zip(range(start, end), payloads):
            yield _decode_point_cloud(data), self.timestamps[i]

    def get_info(self) -> dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "file_size_bytes": self.file_path.stat().st_size,
            "frame_count": self.frame_count,
            "duration_seconds": self.duration,
            "average_fps": self.frame_count / self.duration if self.duration > 0 else 0.0,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "metadata": self.metadata,
        }

    def close(self) -> None:
        """Close the file handle after streaming or random-access use."""
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None


class ZipRecordingReader:
    """
    Reader for legacy ZIP PCD archives (read-only; new recordings are MCAP).
    Kept so recordings made before the MCAP migration remain playable.
    """

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Recording file not found: {self.file_path}")

        self.zipf = zipfile.ZipFile(self.file_path, 'r')

        try:
            metadata_bytes = self.zipf.read("metadata.json")
            self.metadata = json.loads(metadata_bytes.decode('utf-8'))
        except KeyError:
            self.zipf.close()
            raise ValueError("Invalid recording ZIP: missing metadata.json")

        self.frame_count = self.metadata.get("frame_count", 0)
        self.timestamps = self.metadata.get("timestamps", [0.0] * self.frame_count)
        self.start_timestamp = self.metadata.get("start_timestamp", 0.0)
        self.end_timestamp = self.metadata.get("end_timestamp", 0.0)
        self.duration = self.end_timestamp - self.start_timestamp

    def get_frame(self, frame_index: int) -> tuple[np.ndarray, float]:
        if frame_index < 0 or frame_index >= self.frame_count:
            raise IndexError(f"Frame index {frame_index} out of range [0, {self.frame_count})")

        pcd_bytes = self.zipf.read(f"frame_{frame_index:05d}.pcd")
        return unpack_pcd_bytes(pcd_bytes), self.timestamps[frame_index]

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
            "metadata": self.metadata,
        }

    def close(self) -> None:
        if self.zipf is not None:
            self.zipf.close()
            self.zipf = None


def resolve_recording_path(file_path: str | Path) -> Path:
    """Return the existing recording file for ``file_path``.

    Accepts a path with any suffix: prefers ``.mcap``, falls back to a legacy
    ``.zip`` sibling. Raises FileNotFoundError if neither exists.
    """
    p = Path(file_path)
    for candidate in (p, p.with_suffix(MCAP_SUFFIX), p.with_suffix(ZIP_SUFFIX)):
        if candidate.suffix in (MCAP_SUFFIX, ZIP_SUFFIX) and candidate.is_file():
            return candidate
    if p.with_suffix(".lidr").exists():
        raise TypeError("This is a legacy .lidr file and cannot be read.")
    raise FileNotFoundError(f"Recording file not found: {p}")


class RecordingReader:
    """Open a recording of either format; ``RecordingReader(path)`` returns a
    McapRecordingReader (``.mcap``) or ZipRecordingReader (legacy ``.zip``).
    Both expose frame_count, metadata, timestamps, get_frame, iter_frames,
    get_info and close.
    """

    def __new__(cls, file_path: str | Path):  # type: ignore[misc]
        resolved = resolve_recording_path(file_path)
        if resolved.suffix == MCAP_SUFFIX:
            return McapRecordingReader(resolved)
        return ZipRecordingReader(resolved)


def convert_zip_to_mcap(src: str | Path, dest: str | Path, batch_size: int = 50) -> dict[str, Any]:
    """Convert a legacy ZIP PCD recording into an MCAP recording.

    Returns the writer's ``finalize()`` info. The source is left untouched; a
    partial ``dest`` is removed if the conversion fails.
    """
    reader = ZipRecordingReader(src)
    writer: RecordingWriter | None = None
    try:
        metadata = json.loads(json.dumps(reader.metadata))
        for key in ("frame_count", "timestamps", "start_timestamp", "end_timestamp"):
            metadata.pop(key, None)
        writer = RecordingWriter(dest, metadata)
        batch: list[tuple[np.ndarray, float]] = []
        for frame in reader.iter_frames():
            batch.append(frame)
            if len(batch) >= batch_size:
                writer.write_batch(batch)
                batch = []
        if batch:
            writer.write_batch(batch)
        return writer.finalize()
    except Exception:
        if writer is not None:
            writer.abort()
            writer.file_path.unlink(missing_ok=True)
        raise
    finally:
        reader.close()


def get_recording_info(file_path: str | Path) -> dict[str, Any]:
    reader = RecordingReader(file_path)
    try:
        return reader.get_info()
    finally:
        reader.close()
