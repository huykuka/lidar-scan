"""
Unit tests for RecordingService - manages active recording sessions.
"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

import numpy as np
import pytest

from app.services.shared.recorder import RecordingService, RecordingHandle


class TestRecordingHandle:
    """Tests for RecordingHandle class"""

    def test_create_handle(self, tmp_path):
        """Test creating a recording handle"""
        from app.services.shared.recording import RecordingWriter

        file_path = tmp_path / "test.zip"
        metadata = {"sensor_id": "test_sensor"}
        writer = RecordingWriter(file_path, metadata)

        handle = RecordingHandle("rec-123", "test_node", writer, metadata)

        assert handle.recording_id == "rec-123"
        assert handle.node_id == "test_node"
        assert handle.writer is writer
        assert handle.metadata == metadata
        assert handle.frame_count == 0
        assert handle.last_timestamp is None

        writer.finalize()

    def test_get_info(self, tmp_path):
        """Test getting recording info from handle"""
        from app.services.shared.recording import RecordingWriter

        file_path = tmp_path / "test.zip"
        metadata = {"sensor_id": "test_sensor"}
        writer = RecordingWriter(file_path, metadata)

        handle = RecordingHandle("rec-123", "test_node", writer, metadata)
        handle.frame_count = 42

        info = handle.get_info()

        assert info["recording_id"] == "rec-123"
        assert info["node_id"] == "test_node"
        assert info["frame_count"] == 42
        assert "duration_seconds" in info
        assert "started_at" in info

        writer.finalize()


class TestRecordingService:
    """Tests for RecordingService class"""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a RecordingService with temporary directory"""
        recordings_dir = tmp_path / "recordings"
        return RecordingService(recordings_dir)

    @pytest.mark.asyncio
    async def test_initialization(self, tmp_path):
        """Test service initialization"""
        recordings_dir = tmp_path / "recordings"
        service = RecordingService(recordings_dir)

        assert service.recordings_dir == recordings_dir
        assert recordings_dir.exists()
        assert len(service.active_recordings) == 0

    @pytest.mark.asyncio
    async def test_initialization_default_dir(self):
        """Test service initialization with default directory"""
        service = RecordingService()

        assert service.recordings_dir == Path("recordings")
        assert service.recordings_dir.exists()

    @pytest.mark.asyncio
    async def test_start_recording(self, service):
        """Test starting a recording"""
        recording_id, file_path = await service.start_recording(
            node_id="test_node",
            name="Test Recording",
            metadata={"sensor_id": "sensor_1"}
        )

        assert recording_id is not None
        assert len(recording_id) > 0
        # file_path is created on start (ZIP opened)
        assert Path(file_path).exists()

        # Check active recordings
        assert len(service.active_recordings) == 1
        assert recording_id in service.active_recordings

        handle = service.active_recordings[recording_id]
        assert handle.node_id == "test_node"
        assert handle.metadata["name"] == "Test Recording"
        assert handle.metadata["sensor_id"] == "sensor_1"

        # Cleanup
        await service.stop_recording(recording_id)

    @pytest.mark.asyncio
    async def test_start_recording_duplicate_node_allowed(self, service):
        """Test that starting recording on same node twice is allowed (intentional design)"""
        recording_id1, _ = await service.start_recording(node_id="test_node")
        recording_id2, _ = await service.start_recording(node_id="test_node")

        # Both should be active (intentional: allows multiple isolated capture loops)
        assert len(service.active_recordings) == 2

        # Cleanup
        await service.stop_recording(recording_id1)
        await service.stop_recording(recording_id2)

    @pytest.mark.asyncio
    async def test_stop_recording_returns_stopping_status(self, service):
        """Test that stop_recording returns 'stopping' status immediately"""
        recording_id, _ = await service.start_recording(node_id="test_node")

        info = await service.stop_recording(recording_id)

        assert info["recording_id"] == recording_id
        assert info["node_id"] == "test_node"
        assert info["status"] == "stopping"
        # stop_recording does NOT remove from active_recordings (finalize does)
        assert recording_id in service.active_recordings

    @pytest.mark.asyncio
    async def test_finalize_recording(self, service):
        """Test finalizing a recording produces file info"""
        recording_id, _ = await service.start_recording(node_id="test_node")

        # Record some frames
        points = np.random.rand(100, 3).astype(np.float32)
        await service.record_node_payload("test_node", points, 1000.0)

        # Stop (mark as stopping)
        await service.stop_recording(recording_id)

        # Finalize (actually writes file and removes from active)
        info = await service.finalize_recording(recording_id)

        assert info["recording_id"] == recording_id
        assert info["node_id"] == "test_node"
        assert info["status"] == "stopped"
        assert "file_path" in info
        assert "file_size_bytes" in info
        assert "duration_seconds" in info
        assert "average_fps" in info

        # Finalize removes from active recordings
        assert recording_id not in service.active_recordings

    @pytest.mark.asyncio
    async def test_stop_nonexistent_recording(self, service):
        """Test stopping a recording that doesn't exist"""
        with pytest.raises(KeyError, match="not found"):
            await service.stop_recording("nonexistent_id")

    @pytest.mark.asyncio
    async def test_record_node_payload(self, service):
        """Test recording a frame via record_node_payload"""
        recording_id, _ = await service.start_recording(node_id="test_node")

        points = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0]
        ], dtype=np.float32)
        timestamp = 1234567890.123

        await service.record_node_payload("test_node", points, timestamp)

        # Check frame was counted
        handle = service.active_recordings[recording_id]
        assert handle.frame_count == 1
        assert handle.last_timestamp == timestamp

        # Cleanup
        await service.stop_recording(recording_id)

    @pytest.mark.asyncio
    async def test_record_multiple_frames(self, service):
        """Test recording multiple frames"""
        recording_id, _ = await service.start_recording(node_id="test_node")

        # Record 10 frames
        for i in range(10):
            points = np.random.rand(100, 3).astype(np.float32)
            timestamp = 1000.0 + i * 0.1
            await service.record_node_payload("test_node", points, timestamp)

        handle = service.active_recordings[recording_id]
        assert handle.frame_count == 10
        assert abs(handle.last_timestamp - 1000.9) < 0.001

        # Cleanup
        await service.stop_recording(recording_id)

    @pytest.mark.asyncio
    async def test_record_frame_wrong_node(self, service):
        """Test recording frame with wrong node_id does nothing"""
        recording_id, _ = await service.start_recording(node_id="test_node")

        points = np.random.rand(100, 3).astype(np.float32)
        await service.record_node_payload("other_node", points, 1000.0)

        handle = service.active_recordings[recording_id]
        assert handle.frame_count == 0

        # Cleanup
        await service.stop_recording(recording_id)

    @pytest.mark.asyncio
    async def test_concurrent_recordings(self, service):
        """Test recording multiple nodes concurrently"""
        rec_id1, _ = await service.start_recording(node_id="node1")
        rec_id2, _ = await service.start_recording(node_id="node2")
        rec_id3, _ = await service.start_recording(node_id="node3")

        assert len(service.active_recordings) == 3

        # Record frames for each node
        for node_id in ["node1", "node2", "node3"]:
            points = np.random.rand(50, 3).astype(np.float32)
            await service.record_node_payload(node_id, points, 1000.0)

        # Check all recordings have frames
        for rec_id in [rec_id1, rec_id2, rec_id3]:
            handle = service.active_recordings[rec_id]
            assert handle.frame_count == 1

        # Stop all recordings
        info1 = await service.stop_recording(rec_id1)
        info2 = await service.stop_recording(rec_id2)
        info3 = await service.stop_recording(rec_id3)

        assert info1["node_id"] == "node1"
        assert info2["node_id"] == "node2"
        assert info3["node_id"] == "node3"

    @pytest.mark.asyncio
    async def test_get_active_recordings(self, service):
        """Test getting list of active recordings"""
        assert service.get_active_recordings() == []

        rec_id1, _ = await service.start_recording(node_id="node1")
        rec_id2, _ = await service.start_recording(node_id="node2")

        active = service.get_active_recordings()

        assert len(active) == 2
        assert any(r["recording_id"] == rec_id1 for r in active)
        assert any(r["recording_id"] == rec_id2 for r in active)

        for recording in active:
            assert "recording_id" in recording
            assert "node_id" in recording
            assert "frame_count" in recording
            assert "duration_seconds" in recording
            assert "started_at" in recording

        # Cleanup
        await service.stop_recording(rec_id1)
        await service.stop_recording(rec_id2)

    @pytest.mark.asyncio
    async def test_is_recording(self, service):
        """Test checking if node is being recorded"""
        assert service.is_recording("test_node") is False

        rec_id, _ = await service.start_recording(node_id="test_node")

        assert service.is_recording("test_node") is True
        assert service.is_recording("other_node") is False

        # stop_recording only marks as stopping, node is still "active" until finalized
        await service.stop_recording(rec_id)
        # After stop (stopping status), it's still in active_recordings
        # is_recording checks node_id presence in active_recordings
        assert service.is_recording("test_node") is True

        # After finalize, it is removed
        await service.finalize_recording(rec_id)
        assert service.is_recording("test_node") is False

    @pytest.mark.asyncio
    async def test_get_recording_for_node(self, service):
        """Test getting recording info for specific node"""
        assert service.get_recording_for_node("test_node") is None

        rec_id, _ = await service.start_recording(node_id="test_node")

        info = service.get_recording_for_node("test_node")

        assert info is not None
        assert info["recording_id"] == rec_id
        assert info["node_id"] == "test_node"
        assert "frame_count" in info

        assert service.get_recording_for_node("other_node") is None

        # Cleanup
        await service.stop_recording(rec_id)

    @pytest.mark.asyncio
    async def test_stop_all_recordings(self, service):
        """Test stopping all active recordings (marks all as stopping)"""
        rec_id1, _ = await service.start_recording(node_id="node1")
        rec_id2, _ = await service.start_recording(node_id="node2")
        rec_id3, _ = await service.start_recording(node_id="node3")

        # Record some frames
        for node_id in ["node1", "node2", "node3"]:
            points = np.random.rand(50, 3).astype(np.float32)
            await service.record_node_payload(node_id, points, 1000.0)

        results = await service.stop_all_recordings()

        assert len(results) == 3

        # stop_all_recordings marks all as stopping; they remain in active until finalized
        node_ids = {r["node_id"] for r in results}
        assert node_ids == {"node1", "node2", "node3"}

        for result in results:
            assert result["status"] == "stopping"

    @pytest.mark.asyncio
    async def test_stop_all_recordings_empty(self, service):
        """Test stopping all recordings when none are active"""
        results = await service.stop_all_recordings()
        assert results == []

    @pytest.mark.asyncio
    async def test_file_naming_pattern(self, service):
        """Test recording file naming uses capture_{timestamp}_{uuid8}.zip pattern"""
        rec_id, file_path = await service.start_recording(node_id="sensor1_raw_points")

        filename = Path(file_path).name

        # Should start with 'capture_'
        assert filename.startswith("capture_")

        # Should have .zip extension
        assert filename.endswith(".zip")

        # Should contain date/time stamp (YYYYMMDD_HHMMSS format)
        import re
        assert re.search(r"\d{8}_\d{6}", filename)

        # Should contain short UUID (8 hex chars before .zip)
        assert re.search(r"[a-f0-9]{8}\.zip$", filename)

        # Cleanup
        await service.stop_recording(rec_id)

    @pytest.mark.asyncio
    async def test_metadata_preservation(self, service):
        """Test that metadata is preserved through recording lifecycle"""
        custom_metadata = {
            "sensor_id": "sensor_123",
            "sensor_model": "SICK TiM781",
            "pose": {"x": 1.0, "y": 2.0, "z": 3.0},
            "pipeline": "downsample_voxel"
        }

        rec_id, _ = await service.start_recording(
            node_id="test_node",
            name="Custom Recording",
            metadata=custom_metadata
        )

        handle = service.active_recordings[rec_id]
        assert handle.metadata["sensor_id"] == "sensor_123"
        assert handle.metadata["sensor_model"] == "SICK TiM781"
        assert handle.metadata["name"] == "Custom Recording"

        # Stop (no file_path in stopping result)
        info = await service.stop_recording(rec_id)
        assert info["metadata"]["sensor_id"] == "sensor_123"
        assert info["metadata"]["sensor_model"] == "SICK TiM781"

    @pytest.mark.asyncio
    async def test_thread_safety(self, service):
        """Test concurrent access with asyncio lock"""
        tasks = []
        for i in range(5):
            task = service.start_recording(node_id=f"node_{i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert len(service.active_recordings) == 5

        stop_tasks = []
        for rec_id, _ in results:
            task = service.stop_recording(rec_id)
            stop_tasks.append(task)

        stop_results = await asyncio.gather(*stop_tasks)
        assert len(stop_results) == 5
        # They remain in active_recordings after stop (stopping status)
        assert len(service.active_recordings) == 5


class TestRecordingServiceSingleton:
    """Tests for global singleton pattern"""

    def test_get_recorder_singleton(self):
        """Test that get_recorder returns same instance"""
        from app.services.shared.recorder import get_recorder

        recorder1 = get_recorder()
        recorder2 = get_recorder()

        assert recorder1 is recorder2

    def test_get_recorder_creates_default_dir(self):
        """Test that get_recorder creates default directory"""
        from app.services.shared.recorder import get_recorder

        recorder = get_recorder()

        assert recorder.recordings_dir == Path("recordings")
        assert recorder.recordings_dir.exists()
