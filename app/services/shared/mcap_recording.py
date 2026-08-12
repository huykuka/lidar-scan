"""MCAP-based recording format for point cloud data archives.

Implements read/write of foxglove.PointCloud protobuf messages inside MCAP.
Provides McapRecordingWriter and McapRecordingReader with the same public API
as RecordingWriter / RecordingReader so all consumers can be swapped transparently.

Wire format invariant: the live LIDR WebSocket protocol (binary.py +
_encode_stream_frame) is NOT affected by this module.

Timestamp parity: per-frame timestamps are stored as verbatim float64 values in
metadata.json (attachment).  The nsec/Timestamp fields inside the protobuf message
are *derived* from those floats and are metadata-only; they never feed back into the
LIDR encoder, so byte-identical LIDR frames are guaranteed.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Iterator

import numpy as np

# ---------------------------------------------------------------------------
# Field-name schema helpers (mirrors recording.py constants)
# ---------------------------------------------------------------------------
SICK_SCAN_SCHEMA: list[str] = [
    "x", "y", "z", "lidar_nsec", "lidar_sec", "timestamp", "ring",
    "elevation", "ts", "azimuth", "range", "reflector", "echo", "intensity",
    "attr_14", "attr_15",
]

PIPELINE_SCHEMA: list[str] = [
    "x", "y", "z", "lidar_nsec", "lidar_sec", "t", "layer",
    "elevation", "ts", "azimuth", "range", "reflector", "echo", "intensity",
]

_UNKNOWN_STD = ["x", "y", "z", "intensity", "ring", "timestamp"]


def _detect_fields(dims: int, meta_fields: list[str] | None) -> list[str]:
    """Return field names for *dims* columns.

    Priority:
    1. metadata["fields"] if len >= dims
    2. SICK_SCAN_SCHEMA (16) / PIPELINE_SCHEMA (14) by column count
    3. fallback: first 6 standard names, then attr_N
    """
    if meta_fields and len(meta_fields) >= dims:
        return list(meta_fields[:dims])
    if dims == 16:
        return list(SICK_SCAN_SCHEMA)
    if dims == 14:
        return list(PIPELINE_SCHEMA)
    fields: list[str] = []
    for i in range(dims):
        if i < len(_UNKNOWN_STD):
            fields.append(_UNKNOWN_STD[i])
        else:
            fields.append(f"attr_{i}")
    return fields


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _ts_to_sec_nsec(ts: float) -> tuple[int, int]:
    """Convert float64 Unix seconds → (sec, nsec) with nsec normalisation."""
    sec = int(ts)
    nsec = round((ts - sec) * 1_000_000_000)
    if nsec >= 1_000_000_000:
        sec += 1
        nsec = 0
    return sec, nsec


# ---------------------------------------------------------------------------
# MCAP topic / channel constants
# ---------------------------------------------------------------------------
_TOPIC = "pointcloud"
_ENCODING = "protobuf"
_SCHEMA_NAME = "foxglove.PointCloud"
_METADATA_ATTACHMENT_NAME = "metadata.json"


# ---------------------------------------------------------------------------
# McapRecordingWriter
# ---------------------------------------------------------------------------

class McapRecordingWriter:
    """Write a foxglove.PointCloud MCAP archive.

    API mirrors RecordingWriter so consumers are drop-in replaceable.

    Usage::

        writer = McapRecordingWriter("recording.mcap", metadata)
        writer.write_frame(points_np, timestamp_float)
        writer.write_batch([(pts, ts), ...])
        info = writer.finalize()
    """

    def __init__(self, file_path: str | Path, metadata: dict[str, Any]) -> None:
        self.file_path = Path(file_path)
        self.metadata: dict[str, Any] = dict(metadata)
        self.frame_count: int = 0
        self.timestamps: list[float] = []
        self.start_timestamp: float | None = None
        self.end_timestamp: float | None = None
        self._lock = threading.Lock()
        self._closed = False

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_handle = open(self.file_path, "wb")
        # mcap_protobuf Writer wraps the raw file and registers schemas automatically.
        from mcap_protobuf.writer import Writer as _PBWriter
        self._writer = _PBWriter(self._file_handle)

        # Pre-register pointcloud channel so zero-frame recordings are valid MCAP
        self._pre_register_pointcloud_channel()

    def _pre_register_pointcloud_channel(self) -> None:
        """Register the foxglove.PointCloud schema + channel up-front.

        This ensures zero-frame recordings have a valid 'pointcloud' channel
        so McapRecordingReader can open and validate them.
        """
        from foxglove_schemas_protobuf.PointCloud_pb2 import PointCloud as _FPC
        from mcap_protobuf.writer import register_schema as _reg
        # Access underlying mcap.writer.Writer
        raw_writer = self._writer._writer
        schema_id = _reg(raw_writer, _FPC)
        self._writer._schemas[_TOPIC] = (schema_id, _FPC.DESCRIPTOR.full_name)
        channel_id = raw_writer.register_channel(
            topic=_TOPIC,
            message_encoding=_ENCODING,
            schema_id=schema_id,
        )
        self._writer._channels[_TOPIC] = channel_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_message(self, points: np.ndarray, timestamp: float):
        """Build a foxglove.PointCloud protobuf message from a numpy frame."""
        from foxglove_schemas_protobuf.PointCloud_pb2 import PointCloud as _FPC
        from foxglove_schemas_protobuf.PackedElementField_pb2 import PackedElementField as _PEF
        from google.protobuf.timestamp_pb2 import Timestamp as _TS

        assert sys.byteorder == "little", "McapRecordingWriter requires a little-endian host"

        dims = points.shape[1] if points.ndim == 2 else 3
        field_names = _detect_fields(dims, self.metadata.get("fields"))

        sec, nsec = _ts_to_sec_nsec(timestamp)

        # Pose identity (or from metadata if provided)
        from foxglove_schemas_protobuf.Pose_pb2 import Pose as _Pose  # type: ignore[attr-defined]
        from foxglove_schemas_protobuf.Vector3_pb2 import Vector3 as _V3  # type: ignore[attr-defined]
        from foxglove_schemas_protobuf.Quaternion_pb2 import Quaternion as _Q  # type: ignore[attr-defined]

        meta_pose = self.metadata.get("pose") or {}
        position = _V3(
            x=float(meta_pose.get("x", 0.0)),
            y=float(meta_pose.get("y", 0.0)),
            z=float(meta_pose.get("z", 0.0)),
        )
        orientation = _Q(x=0.0, y=0.0, z=0.0, w=1.0)
        pose = _Pose(position=position, orientation=orientation)

        # PackedElementField list
        packed_fields = [
            _PEF(name=name, offset=i * 4, type=_PEF.FLOAT32)
            for i, name in enumerate(field_names)
        ]

        # Convert to float32 C-contiguous little-endian bytes
        arr = np.ascontiguousarray(
            points.astype(np.float32) if points.dtype != np.float32 else points
        )
        data_bytes = arr.tobytes(order="C")

        frame_id = self.metadata.get("node_id", "lidar")

        msg = _FPC(
            timestamp=_TS(seconds=sec, nanos=nsec),
            frame_id=str(frame_id),
            pose=pose,
            point_stride=dims * 4,
            fields=packed_fields,
            data=data_bytes,
        )
        return msg

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def write_frame(self, points: np.ndarray, timestamp: float) -> None:
        """Write a single frame to the MCAP file."""
        with self._lock:
            if self._closed:
                raise RuntimeError("McapRecordingWriter is already closed/finalized")

            if self.start_timestamp is None:
                self.start_timestamp = timestamp
            self.end_timestamp = timestamp

            msg = self._build_message(points, timestamp)
            log_time = round(timestamp * 1_000_000_000)

            self._writer.write_message(
                topic=_TOPIC,
                message=msg,
                log_time=log_time,
                publish_time=log_time,
            )

            self.timestamps.append(timestamp)
            self.frame_count += 1

    def write_batch(self, frames: list[tuple[np.ndarray, float]]) -> None:
        """Write multiple frames atomically (single lock acquisition)."""
        with self._lock:
            if self._closed:
                raise RuntimeError("McapRecordingWriter is already closed/finalized")

            for points, timestamp in frames:
                if self.start_timestamp is None:
                    self.start_timestamp = timestamp
                self.end_timestamp = timestamp

                msg = self._build_message(points, timestamp)
                log_time = round(timestamp * 1_000_000_000)
                self._writer.write_message(
                    topic=_TOPIC,
                    message=msg,
                    log_time=log_time,
                    publish_time=log_time,
                )
                self.timestamps.append(timestamp)
                self.frame_count += 1

    def finalize(self) -> dict[str, Any]:
        """Flush, write metadata attachment, close, return summary dict."""
        with self._lock:
            if self._closed:
                raise RuntimeError("McapRecordingWriter is already closed/finalized")

            self.metadata["timestamps"] = self.timestamps
            self.metadata["frame_count"] = self.frame_count
            self.metadata["start_timestamp"] = self.start_timestamp
            self.metadata["end_timestamp"] = self.end_timestamp

            # Write metadata as MCAP attachment (single canonical location)
            # mcap_protobuf.Writer wraps mcap.writer.Writer as ._writer
            meta_bytes = json.dumps(self.metadata, indent=2).encode("utf-8")
            self._writer._writer.add_attachment(
                name=_METADATA_ATTACHMENT_NAME,
                media_type="application/json",
                data=meta_bytes,
                create_time=0,
                log_time=0,
            )

            self._writer.finish()
            self._file_handle.flush()
            import os
            os.fsync(self._file_handle.fileno())
            self._file_handle.close()
            self._closed = True

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

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "McapRecordingWriter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self._closed:
            if exc_type is None:
                self.finalize()
            else:
                try:
                    self._writer.finish()
                except Exception:
                    pass
                try:
                    self._file_handle.close()
                except Exception:
                    pass
                self._closed = True


# ---------------------------------------------------------------------------
# _ZipRecordingReader  (internal shim — ZIP fallback / migration source)
# ---------------------------------------------------------------------------

class _ZipRecordingReader:
    """Thin shim wrapping the legacy RecordingReader API.

    Used internally by McapRecordingReader as a fallback when only a .zip file
    is present (e.g. before startup migration) and by the migration routine itself.
    NOT part of the public API.
    """

    def __init__(self, file_path: str | Path) -> None:
        from app.services.shared.recording import RecordingReader as _ZR
        self._inner = _ZR(str(file_path))
        self.metadata: dict[str, Any] = self._inner.metadata
        self.frame_count: int = self._inner.frame_count
        self.timestamps: list[float] = self._inner.timestamps
        self.start_timestamp: float = self._inner.start_timestamp
        self.end_timestamp: float = self._inner.end_timestamp
        self.duration: float = self._inner.duration

    def get_frame(self, index: int) -> tuple[np.ndarray, float]:
        if index < 0 or index >= self.frame_count:
            raise IndexError(f"Frame index {index} out of range [0, {self.frame_count})")
        return self._inner.get_frame(index)

    def iter_frames(self, start: int = 0, end: int | None = None) -> Iterator[tuple[np.ndarray, float]]:
        actual_end = min(end, self.frame_count) if end is not None else self.frame_count
        for i in range(start, actual_end):
            yield self.get_frame(i)

    def get_info(self) -> dict[str, Any]:
        return self._inner.get_info()

    def close(self) -> None:
        self._inner.close()


# ---------------------------------------------------------------------------
# McapRecordingReader
# ---------------------------------------------------------------------------

class McapRecordingReader:
    """Read a foxglove.PointCloud MCAP archive.

    API mirrors RecordingReader (attrs + methods) so all consumers are
    drop-in replaceable.

    Fallback: if the .mcap file is absent but a .zip is present, opens the
    .zip via the internal _ZipRecordingReader shim.  If the .mcap is present
    but corrupt, raises ValueError immediately (no silent fallback).

    Validation on open:
    - Exactly one ``pointcloud`` channel required.
    - Extra non-pointcloud channels are *permitted*.
    - schema.name must be ``foxglove.PointCloud`` and encoding ``protobuf``.
    - Missing metadata.json attachment → ValueError.
    - Corrupt container → ValueError.

    Lazy decoding:
    - Constructor only validates + reads metadata; NO point data decoded.
    - get_frame(i) decodes a single frame on demand.
    - Sequential-cursor optimisation: a running iterator is advanced for
      monotonically increasing index requests (dominant playback pattern,
      O(1) amortised).  Out-of-order access resets the iterator from the
      start (O(n) worst case, acceptable for seek operations).
    - A threading.Lock serialises cursor access so asyncio.to_thread callers
      (stream_recording) are safe even if two tasks call get_frame concurrently.
    """

    def __init__(self, file_path: str | Path) -> None:
        p = Path(file_path)
        # If the path exists as-is (e.g. .mcap.part temp file), use it directly
        if p.exists() and p.suffix not in (".zip",):
            mcap_path = p
            zip_path = p.with_suffix(".zip")
        else:
            mcap_path = p.with_suffix(".mcap")
            zip_path = p.with_suffix(".zip")

        # Decide which path to open
        if mcap_path.exists():
            self._open_mcap(mcap_path)
        elif zip_path.exists():
            # Fallback: ZIP present, .mcap absent
            self._shim: _ZipRecordingReader | None = _ZipRecordingReader(zip_path)
            self._use_shim = True
            self._file_handle = None
            self._mcap_path = zip_path
            self.metadata = self._shim.metadata
            self.frame_count = self._shim.frame_count
            self.timestamps = self._shim.timestamps
            self.start_timestamp = self._shim.start_timestamp
            self.end_timestamp = self._shim.end_timestamp
            self.duration = self._shim.duration
        else:
            raise FileNotFoundError(
                f"Recording file not found: neither {mcap_path} nor {zip_path} exists"
            )

    def _open_mcap(self, mcap_path: Path) -> None:
        """Open and validate an MCAP file.  Builds lightweight frame index only — NO point decoding."""
        self._shim = None
        self._use_shim = False
        self._mcap_path = mcap_path
        self._file_handle = None

        try:
            from mcap.reader import make_reader as _make_reader
            from mcap_protobuf.decoder import DecoderFactory as _PBDecoder
            fh = open(mcap_path, "rb")
            self._file_handle = fh
            reader = _make_reader(fh, decoder_factories=[_PBDecoder()])
        except Exception as exc:
            if self._file_handle is not None:
                try:
                    self._file_handle.close()
                except Exception:
                    pass
                self._file_handle = None
            raise ValueError(f"Corrupt MCAP container: {exc}") from exc

        self._reader = reader

        try:
            # --- Validate channels ------------------------------------------------
            try:
                stats = reader.get_summary()
            except Exception as exc:
                raise ValueError(f"Corrupt MCAP container (no summary): {exc}") from exc

            channels = list(stats.channels.values()) if stats and stats.channels else []
            pc_channels = [c for c in channels if c.topic == _TOPIC]
            if len(pc_channels) == 0:
                raise ValueError(
                    f"Invalid recording: no '{_TOPIC}' channel found in MCAP"
                )
            if len(pc_channels) > 1:
                raise ValueError(
                    f"Invalid recording: multiple '{_TOPIC}' channels in MCAP"
                )

            ch = pc_channels[0]
            if ch.message_encoding != _ENCODING:
                raise ValueError(
                    f"Invalid recording: channel encoding is '{ch.message_encoding}', expected '{_ENCODING}'"
                )

            # Schema lookup
            schema_id = ch.schema_id
            schemas = stats.schemas if stats and stats.schemas else {}
            schema = schemas.get(schema_id)
            if schema is None or schema.name != _SCHEMA_NAME:
                actual = schema.name if schema else "None"
                raise ValueError(
                    f"Invalid recording: schema name is '{actual}', expected '{_SCHEMA_NAME}'"
                )

            # --- Read metadata attachment (cheap, no point data) ------------------
            self.metadata = self._read_metadata_attachment(reader)

            # --- Build lightweight frame index from summary statistics ------------
            # Use message_count from summary to set frame_count; no decoding needed.
            frame_count_from_meta = self.metadata.get("frame_count")
            if frame_count_from_meta is not None:
                self.frame_count = int(frame_count_from_meta)
            elif stats and stats.statistics and stats.statistics.message_count is not None:
                # Sum only the pointcloud channel messages
                pc_chan_id = ch.id
                chan_counts = stats.statistics.channel_message_counts or {}
                self.frame_count = int(chan_counts.get(pc_chan_id, stats.statistics.message_count))
            else:
                # Fallback: count message index entries (no decoding, just header scan)
                self.frame_count = self._count_messages_from_index(stats, pc_chan_id=ch.id)

        except Exception:
            # Close file handle on any validation/decode error
            try:
                fh.close()
            except Exception:
                pass
            self._file_handle = None
            raise

        # Populate attrs from metadata
        self.timestamps = self.metadata.get("timestamps") or []
        self.start_timestamp = float(self.metadata.get("start_timestamp") or (self.timestamps[0] if self.timestamps else 0.0))
        self.end_timestamp = float(self.metadata.get("end_timestamp") or (self.timestamps[-1] if self.timestamps else 0.0))
        self.duration = self.end_timestamp - self.start_timestamp

        # Sequential cursor state — guarded by _lock
        # _cursor_iter: active iter_decoded_messages generator positioned at _cursor_pos
        # _cursor_pos: the index that will be returned by the NEXT next() call
        self._lock = threading.Lock()
        self._cursor_iter = None   # type: Any
        self._cursor_pos: int = 0

    def _count_messages_from_index(self, stats, pc_chan_id: int | None = None) -> int:
        """Count pointcloud messages from summary without decoding point data."""
        if stats is None:
            return 0
        # Try channel_message_counts first (pointcloud channel only)
        if stats.statistics and stats.statistics.channel_message_counts:
            chan_counts = stats.statistics.channel_message_counts
            if pc_chan_id is not None and pc_chan_id in chan_counts:
                return int(chan_counts[pc_chan_id])
            # Fallback: total (may over-count if multiple channels, but this path only
            # reached when metadata.frame_count missing AND channel stats unavailable)
            return sum(chan_counts.values())
        if stats.statistics and stats.statistics.message_count is not None:
            return int(stats.statistics.message_count)
        return 0

    def _read_metadata_attachment(self, reader) -> dict[str, Any]:
        """Extract metadata.json from MCAP attachments. Raises ValueError if missing."""
        try:
            for attachment in reader.iter_attachments():
                if attachment.name == _METADATA_ATTACHMENT_NAME:
                    return json.loads(attachment.data.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid recording: error reading metadata attachment: {exc}") from exc
        raise ValueError("Invalid recording: missing metadata.json attachment")

    def _reset_cursor(self) -> None:
        """Reset the sequential cursor to position 0.  Must be called under self._lock."""
        # Close the old iterator if possible
        if self._cursor_iter is not None:
            try:
                self._cursor_iter.close()
            except Exception:
                pass
        self._cursor_iter = self._reader.iter_decoded_messages(topics=[_TOPIC])
        self._cursor_pos = 0

    def _advance_cursor_to(self, index: int) -> tuple[np.ndarray, float]:
        """Advance the sequential cursor to *index* and decode that single frame.

        Must be called under self._lock.  Resets from position 0 when index
        is behind the current cursor position.
        """
        if self._cursor_iter is None or index < self._cursor_pos:
            self._reset_cursor()

        # Skip frames between cursor_pos and index
        while self._cursor_pos < index:
            try:
                next(self._cursor_iter)
            except StopIteration:
                raise IndexError(f"Frame index {index} out of range [0, {self.frame_count})")
            self._cursor_pos += 1

        # Decode exactly frame at index
        try:
            schema, channel, message, proto_msg = next(self._cursor_iter)
        except StopIteration:
            raise IndexError(f"Frame index {index} out of range [0, {self.frame_count})")

        self._cursor_pos += 1

        try:
            arr, ts_proto = self._proto_to_numpy(proto_msg)
        except Exception as exc:
            raise ValueError(f"Malformed protobuf message in MCAP at frame {index}: {exc}") from exc

        # Timestamp parity: prefer verbatim float64 from metadata timestamps
        if self.timestamps and index < len(self.timestamps):
            ts = float(self.timestamps[index])
        else:
            ts = ts_proto

        return arr, ts

    @staticmethod
    def _proto_to_numpy(msg) -> tuple[np.ndarray, float]:
        """Convert a foxglove.PointCloud proto to (ndarray float32, timestamp float64)."""
        # Recover float64 timestamp from Timestamp message
        sec = msg.timestamp.seconds
        nsec = msg.timestamp.nanos
        ts = float(sec) + float(nsec) / 1_000_000_000.0

        data = bytes(msg.data)
        n_fields = len(msg.fields)
        stride = msg.point_stride  # bytes per point
        if stride == 0 or n_fields == 0:
            return np.zeros((0, 3), dtype=np.float32), ts

        n_points = len(data) // stride
        if n_points == 0:
            return np.zeros((0, n_fields), dtype=np.float32), ts

        arr = np.frombuffer(data, dtype=np.float32).reshape(n_points, n_fields)
        # Ensure writeable copy
        arr = np.array(arr, dtype=np.float32)
        return arr, ts

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def get_frame(self, index: int) -> tuple[np.ndarray, float]:
        """Return (points ndarray, timestamp float) for frame at *index*.

        Decodes only the requested frame.  Thread-safe via internal lock.
        """
        if self._use_shim:
            return self._shim.get_frame(index)
        if index < 0 or index >= self.frame_count:
            raise IndexError(f"Frame index {index} out of range [0, {self.frame_count})")
        with self._lock:
            return self._advance_cursor_to(index)

    def iter_frames(self, start: int = 0, end: int | None = None) -> Iterator[tuple[np.ndarray, float]]:
        """Iterate frames in order.  *end* is clamped to frame_count."""
        actual_end = min(end, self.frame_count) if end is not None else self.frame_count
        for i in range(start, actual_end):
            yield self.get_frame(i)

    def get_info(self) -> dict[str, Any]:
        """Return info dict matching RecordingReader.get_info()."""
        return {
            "file_path": str(self._mcap_path),
            "file_size_bytes": self._mcap_path.stat().st_size,
            "frame_count": self.frame_count,
            "duration_seconds": self.duration,
            "average_fps": self.frame_count / self.duration if self.duration > 0 else 0.0,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "metadata": self.metadata,
        }

    def close(self) -> None:
        """Close file handles and release cursor iterator.

        Thread-safe: acquires lock before nulling cursor and file handle so
        an in-flight get_frame() either completes first or finds both as None.
        """
        if self._use_shim and self._shim is not None:
            self._shim.close()
        elif hasattr(self, "_lock"):
            with self._lock:
                if self._cursor_iter is not None:
                    try:
                        self._cursor_iter.close()
                    except Exception:
                        pass
                    self._cursor_iter = None
                fh = self._file_handle
                self._file_handle = None
            # Close file outside lock (blocking I/O should not hold the lock)
            if fh is not None:
                try:
                    fh.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "McapRecordingReader":
        return self

    def __exit__(self, *args) -> None:
        self.close()
