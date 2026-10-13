"""
Unit tests for recording format module - MCAP (foxglove.PointCloud) encoding/decoding.
"""
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.services.shared.recording import (
    RecordingWriter,
    RecordingReader,
    get_recording_info,
)


def mcap_path(p: Path) -> Path:
    """Return the .mcap equivalent of a path (writer always stores .mcap)."""
    return p.with_suffix(".mcap")


class TestRecordingWriter:
    """Tests for RecordingWriter class"""

    def test_create_recording_file(self, tmp_path):
        """Test creating a new recording file (always stored as .mcap)"""
        file_path = tmp_path / "test_recording.lidr"
        metadata = {"sensor_id": "test_sensor", "topic": "test_topic"}

        writer = RecordingWriter(file_path, metadata)
        # Writer opens the file immediately
        assert writer._writer is not None
        assert writer.frame_count == 0
        assert writer.metadata == metadata
        writer.finalize()

        # Stored as .mcap regardless of input extension
        assert mcap_path(file_path).exists()

    def test_write_single_frame(self, tmp_path):
        """Test writing a single frame"""
        file_path = tmp_path / "test_recording.zip"
        metadata = {"sensor_id": "test_sensor"}

        points = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0]
        ], dtype=np.float32)
        timestamp = 1234567890.123

        writer = RecordingWriter(file_path, metadata)
        writer.write_frame(points, timestamp)

        assert writer.frame_count == 1
        assert writer.start_timestamp == timestamp
        assert writer.end_timestamp == timestamp

        info = writer.finalize()

        assert info["frame_count"] == 1
        assert info["duration_seconds"] == 0.0
        assert info["file_path"] == str(mcap_path(file_path))

    def test_write_multiple_frames(self, tmp_path):
        """Test writing multiple frames"""
        file_path = tmp_path / "test_recording.zip"
        metadata = {"sensor_id": "test_sensor"}

        writer = RecordingWriter(file_path, metadata)

        for i in range(10):
            points = np.random.rand(100, 3).astype(np.float32)
            timestamp = 1000.0 + i * 0.1  # 10Hz
            writer.write_frame(points, timestamp)

        assert writer.frame_count == 10
        assert writer.start_timestamp == 1000.0
        assert abs(writer.end_timestamp - 1000.9) < 0.001

        info = writer.finalize()

        assert info["frame_count"] == 10
        assert abs(info["duration_seconds"] - 0.9) < 0.001
        assert abs(info["average_fps"] - 11.11) < 0.1  # ~10Hz

    def test_write_varying_point_counts(self, tmp_path):
        """Test writing frames with different point counts"""
        file_path = tmp_path / "test_recording.zip"
        metadata = {"sensor_id": "test_sensor"}

        writer = RecordingWriter(file_path, metadata)

        point_counts = [10, 100, 50, 200, 5]
        for i, count in enumerate(point_counts):
            points = np.random.rand(count, 3).astype(np.float32)
            timestamp = 1000.0 + i
            writer.write_frame(points, timestamp)

        assert writer.frame_count == len(point_counts)
        info = writer.finalize()
        assert info["frame_count"] == len(point_counts)

    def test_context_manager(self, tmp_path):
        """Test using RecordingWriter as context manager"""
        file_path = tmp_path / "test_recording.zip"
        metadata = {"sensor_id": "test_sensor"}

        points = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)

        with RecordingWriter(file_path, metadata) as writer:
            writer.write_frame(points, 1000.0)
            assert writer.frame_count == 1

        # File should be finalized and closed (writer released)
        assert mcap_path(file_path).exists()
        assert writer._writer is None


class TestRecordingReader:
    """Tests for RecordingReader class"""

    def test_read_recording(self, tmp_path):
        """Test reading a recording file"""
        file_path = tmp_path / "test_recording.zip"
        metadata = {"sensor_id": "test_sensor", "topic": "test_topic"}

        original_points = []
        original_timestamps = []

        with RecordingWriter(file_path, metadata) as writer:
            for i in range(5):
                points = np.random.rand(10, 3).astype(np.float32)
                timestamp = 1000.0 + i * 0.1
                writer.write_frame(points, timestamp)
                original_points.append(points)
                original_timestamps.append(timestamp)

        reader = RecordingReader(file_path)

        assert reader.frame_count == 5
        # metadata has extra keys added by finalize(); check original keys are present
        for k, v in metadata.items():
            assert reader.metadata[k] == v
        assert reader.start_timestamp == 1000.0
        assert abs(reader.end_timestamp - 1000.4) < 0.001
        assert abs(reader.duration - 0.4) < 0.001

    def test_get_frame_by_index(self, tmp_path):
        """Test getting specific frames by index"""
        file_path = tmp_path / "test_recording.zip"
        metadata = {"sensor_id": "test_sensor"}

        original_points = []

        with RecordingWriter(file_path, metadata) as writer:
            for i in range(10):
                points = np.array([[i * 1.0, i * 2.0, i * 3.0]], dtype=np.float32)
                writer.write_frame(points, 1000.0 + i)
                original_points.append(points)

        reader = RecordingReader(file_path)

        points, timestamp = reader.get_frame(0)
        np.testing.assert_array_almost_equal(points, original_points[0])
        assert timestamp == 1000.0

        points, timestamp = reader.get_frame(5)
        np.testing.assert_array_almost_equal(points, original_points[5])
        assert timestamp == 1005.0

        points, timestamp = reader.get_frame(9)
        np.testing.assert_array_almost_equal(points, original_points[9])
        assert timestamp == 1009.0

    def test_get_frame_out_of_range(self, tmp_path):
        """Test getting frame with invalid index"""
        file_path = tmp_path / "test_recording.zip"

        with RecordingWriter(file_path, {}) as writer:
            points = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
            writer.write_frame(points, 1000.0)

        reader = RecordingReader(file_path)

        with pytest.raises(IndexError):
            reader.get_frame(-1)

        with pytest.raises(IndexError):
            reader.get_frame(10)

    def test_iter_frames(self, tmp_path):
        """Test iterating through all frames"""
        file_path = tmp_path / "test_recording.zip"

        num_frames = 20
        with RecordingWriter(file_path, {}) as writer:
            for i in range(num_frames):
                points = np.array([[i * 1.0, i * 2.0, i * 3.0]], dtype=np.float32)
                writer.write_frame(points, 1000.0 + i * 0.1)

        reader = RecordingReader(file_path)
        frames = list(reader.iter_frames())

        assert len(frames) == num_frames

        for i, (points, timestamp) in enumerate(frames):
            assert points.shape == (1, 3)
            assert abs(timestamp - (1000.0 + i * 0.1)) < 0.001

    def test_iter_frames_with_range(self, tmp_path):
        """Test iterating through a subset of frames"""
        file_path = tmp_path / "test_recording.zip"

        with RecordingWriter(file_path, {}) as writer:
            for i in range(20):
                points = np.array([[i * 1.0, i * 2.0, i * 3.0]], dtype=np.float32)
                writer.write_frame(points, 1000.0 + i)

        reader = RecordingReader(file_path)
        frames = list(reader.iter_frames(start=5, end=10))

        assert len(frames) == 5

        for i, (points, timestamp) in enumerate(frames):
            expected_idx = i + 5
            assert points[0, 0] == expected_idx * 1.0
            assert timestamp == 1000.0 + expected_idx

    def test_get_info(self, tmp_path):
        """Test getting recording info"""
        file_path = tmp_path / "test_recording.zip"
        metadata = {
            "sensor_id": "test_sensor",
            "topic": "test_topic",
            "pipeline_name": "basic"
        }

        with RecordingWriter(file_path, metadata) as writer:
            for i in range(100):
                points = np.random.rand(50, 3).astype(np.float32)
                writer.write_frame(points, 1000.0 + i * 0.1)

        reader = RecordingReader(file_path)
        info = reader.get_info()

        assert info["frame_count"] == 100
        assert info["file_path"] == str(mcap_path(file_path))
        assert info["file_size_bytes"] > 0
        assert abs(info["duration_seconds"] - 9.9) < 0.1
        assert abs(info["average_fps"] - 10.0) < 0.5
        # metadata has extra finalize keys; check originals
        for k, v in metadata.items():
            assert info["metadata"][k] == v


class TestRecordingFormat:
    """Tests for recording file format structure"""

    def test_mcap_file_structure(self, tmp_path):
        """Recording is a valid MCAP with one foxglove.PointCloud message per frame"""
        from mcap.reader import make_reader

        file_path = tmp_path / "test_recording.mcap"

        with RecordingWriter(file_path, {"node_id": "n1"}) as writer:
            writer.write_frame(np.array([[1.0, 2.0, 3.0]], dtype=np.float32), 1000.0)
            writer.write_frame(np.array([[4.0, 5.0, 6.0]], dtype=np.float32), 1000.0)  # duplicate ts

        with open(mcap_path(file_path), "rb") as fh:
            assert fh.read(8) == b"\x89MCAP0\r\n"
            fh.seek(0)
            summary = make_reader(fh).get_summary()
            assert [c.topic for c in summary.channels.values()] == ["/n1/points"]
            assert [s.name for s in summary.schemas.values()] == ["foxglove.PointCloud"]
            assert summary.statistics.message_count == 2

        reader = RecordingReader(file_path)
        try:
            assert reader.frame_count == 2
            assert reader.get_frame(1)[0].tolist() == [[4.0, 5.0, 6.0]]
        finally:
            reader.close()

    def test_legacy_zip_still_readable_and_convertible(self, tmp_path):
        """Legacy ZIP archives open via RecordingReader and convert to MCAP"""
        import json
        import zipfile

        from app.services.shared.recording import convert_zip_to_mcap, pack_pcd_bytes

        zip_file = tmp_path / "legacy.zip"
        pts = [np.random.rand(5 + i, 3).astype(np.float32) for i in range(3)]
        with zipfile.ZipFile(zip_file, "w") as zf:
            for i, p in enumerate(pts):
                zf.writestr(f"frame_{i:05d}.pcd", pack_pcd_bytes(p))
            zf.writestr("metadata.json", json.dumps({
                "node_id": "n", "frame_count": 3, "timestamps": [1.0, 2.0, 3.0],
                "start_timestamp": 1.0, "end_timestamp": 3.0,
            }))

        legacy = RecordingReader(zip_file)
        assert legacy.frame_count == 3
        legacy.close()

        info = convert_zip_to_mcap(zip_file, tmp_path / "legacy.mcap")
        assert info["frame_count"] == 3
        reader = RecordingReader(tmp_path / "legacy.mcap")
        try:
            for i, p in enumerate(pts):
                got, ts = reader.get_frame(i)
                np.testing.assert_array_equal(got, p)
                assert ts == float(i + 1)
            assert [f[1] for f in reader.iter_frames(1, 3)] == [2.0, 3.0]
        finally:
            reader.close()

    def test_frame_index_integrity(self, tmp_path):
        """Test that frame index correctly points to frames"""
        file_path = tmp_path / "test_recording.zip"

        with RecordingWriter(file_path, {}) as writer:
            for i in range(10):
                count = 10 + i * 5
                points = np.random.rand(count, 3).astype(np.float32)
                writer.write_frame(points, 1000.0 + i)

        reader = RecordingReader(file_path)

        for i in range(10):
            points, timestamp = reader.get_frame(i)
            expected_count = 10 + i * 5
            assert points.shape[0] == expected_count
            assert points.shape[1] == 3
            assert timestamp == 1000.0 + i

    def test_metadata_preservation(self, tmp_path):
        """Test that original metadata keys are correctly stored and retrieved"""
        file_path = tmp_path / "test_recording.zip"

        metadata = {
            "sensor_id": "lidar_01",
            "topic": "lidar01_raw_points",
            "name": "Front Lidar",
            "mode": "real",
            "pipeline_name": "reflector",
            "pose": {
                "x": 1.5,
                "y": 0.0,
                "z": 2.0,
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 45.0
            }
        }

        with RecordingWriter(file_path, metadata) as writer:
            points = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
            writer.write_frame(points, 1000.0)

        reader = RecordingReader(file_path)
        # finalize() adds extra keys (timestamps, frame_count, etc.); check originals
        for k, v in metadata.items():
            assert reader.metadata[k] == v


class TestGetRecordingInfo:
    """Tests for get_recording_info convenience function"""

    def test_get_info_without_loading_frames(self, tmp_path):
        """Test getting info without loading all frames into memory"""
        file_path = tmp_path / "test_recording.zip"

        with RecordingWriter(file_path, {"sensor_id": "test"}) as writer:
            for i in range(1000):
                points = np.random.rand(100, 3).astype(np.float32)
                writer.write_frame(points, 1000.0 + i * 0.1)

        info = get_recording_info(file_path)

        assert info["frame_count"] == 1000
        assert info["file_size_bytes"] > 0
        assert abs(info["duration_seconds"] - 99.9) < 0.5
        assert abs(info["average_fps"] - 10.0) < 0.5


class TestRecordingEdgeCases:
    """Tests for edge cases and error handling"""
    def test_invalid_file(self, tmp_path):
        """Test reading a file that is not a valid ZIP"""
        # Write an invalid .zip file (not a real ZIP)
        file_path = tmp_path / "invalid.zip"
        with open(file_path, 'wb') as f:
            f.write(b'INVALID_DATA')

        with pytest.raises(Exception):
            RecordingReader(file_path)

    def test_legacy_lidr_file_raises_type_error(self, tmp_path):
        """Test reading a .lidr file raises TypeError (legacy format unsupported)"""
        lidr_file = tmp_path / "recording.lidr"
        with open(lidr_file, 'wb') as f:
            f.write(b'LIDR\x01\x00\x00\x00SOME_LEGACY_DATA')

        # RecordingReader looks for .zip; if .lidr exists instead, raises TypeError
        with pytest.raises(TypeError, match="legacy"):
            RecordingReader(lidr_file)

    def test_file_not_found(self, tmp_path):
        """Test reading non-existent file"""
        file_path = tmp_path / "nonexistent.zip"

        with pytest.raises(FileNotFoundError):
            RecordingReader(file_path)

    def test_large_frame(self, tmp_path):
        """Test recording with very large point cloud"""
        file_path = tmp_path / "test_recording.zip"

        large_points = np.random.rand(100000, 3).astype(np.float32)

        with RecordingWriter(file_path, {}) as writer:
            writer.write_frame(large_points, 1000.0)

        reader = RecordingReader(file_path)
        points, timestamp = reader.get_frame(0)

        assert points.shape == (100000, 3)
        np.testing.assert_array_almost_equal(points, large_points, decimal=5)
