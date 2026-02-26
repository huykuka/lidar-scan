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
from app.services.shared.binary import pack_points_binary


class TestRecordingHandle:
    """Tests for RecordingHandle class"""
    
    def test_create_handle(self, tmp_path):
        """Test creating a recording handle"""
        from app.services.shared.recording import RecordingWriter
        
        file_path = tmp_path / "test.lidr"
        metadata = {"sensor_id": "test_sensor"}
        writer = RecordingWriter(file_path, metadata)
        
        handle = RecordingHandle("rec-123", "test_topic", writer, metadata)
        
        assert handle.recording_id == "rec-123"
        assert handle.topic == "test_topic"
        assert handle.writer is writer
        assert handle.metadata == metadata
        assert handle.frame_count == 0
        assert handle.last_timestamp is None
        
        writer.finalize()
    
    def test_get_info(self, tmp_path):
        """Test getting recording info from handle"""
        from app.services.shared.recording import RecordingWriter
        
        file_path = tmp_path / "test.lidr"
        metadata = {"sensor_id": "test_sensor"}
        writer = RecordingWriter(file_path, metadata)
        
        handle = RecordingHandle("rec-123", "test_topic", writer, metadata)
        handle.frame_count = 42
        
        info = handle.get_info()
        
        assert info["recording_id"] == "rec-123"
        assert info["topic"] == "test_topic"
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
            topic="test_topic",
            name="Test Recording",
            metadata={"sensor_id": "sensor_1"}
        )
        
        assert recording_id is not None
        assert len(recording_id) > 0
        assert Path(file_path).exists()
        
        # Check active recordings
        assert len(service.active_recordings) == 1
        assert recording_id in service.active_recordings
        
        handle = service.active_recordings[recording_id]
        assert handle.topic == "test_topic"
        assert handle.metadata["name"] == "Test Recording"
        assert handle.metadata["sensor_id"] == "sensor_1"
        
        # Cleanup
        await service.stop_recording(recording_id)
    
    @pytest.mark.asyncio
    async def test_start_recording_duplicate_topic(self, service):
        """Test that starting recording on same topic twice raises error"""
        # Start first recording
        recording_id1, _ = await service.start_recording(topic="test_topic")
        
        # Try to start second recording on same topic
        with pytest.raises(ValueError, match="already being recorded"):
            await service.start_recording(topic="test_topic")
        
        # Cleanup
        await service.stop_recording(recording_id1)
    
    @pytest.mark.asyncio
    async def test_stop_recording(self, service):
        """Test stopping a recording"""
        # Start recording
        recording_id, _ = await service.start_recording(topic="test_topic")
        
        # Write some frames
        points = np.random.rand(100, 3).astype(np.float32)
        frame_data = pack_points_binary(points, 1000.0)
        await service.record_frame("test_topic", frame_data)
        
        # Stop recording
        info = await service.stop_recording(recording_id)
        
        assert info["recording_id"] == recording_id
        assert info["topic"] == "test_topic"
        assert info["frame_count"] == 1
        assert "file_path" in info
        assert "file_size_bytes" in info
        assert "duration_seconds" in info
        assert "average_fps" in info
        
        # Verify recording is removed from active list
        assert recording_id not in service.active_recordings
        
        # Verify file exists
        assert Path(info["file_path"]).exists()
    
    @pytest.mark.asyncio
    async def test_stop_nonexistent_recording(self, service):
        """Test stopping a recording that doesn't exist"""
        with pytest.raises(KeyError, match="not found"):
            await service.stop_recording("nonexistent_id")
    
    @pytest.mark.asyncio
    async def test_record_frame(self, service):
        """Test recording a frame"""
        # Start recording
        recording_id, _ = await service.start_recording(topic="test_topic")
        
        # Create frame data
        points = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0]
        ], dtype=np.float32)
        timestamp = 1234567890.123
        frame_data = pack_points_binary(points, timestamp)
        
        # Record frame
        await service.record_frame("test_topic", frame_data)
        
        # Check frame was recorded
        handle = service.active_recordings[recording_id]
        assert handle.frame_count == 1
        assert handle.last_timestamp == timestamp
        
        # Cleanup
        await service.stop_recording(recording_id)
    
    @pytest.mark.asyncio
    async def test_record_multiple_frames(self, service):
        """Test recording multiple frames"""
        # Start recording
        recording_id, _ = await service.start_recording(topic="test_topic")
        
        # Record 10 frames
        for i in range(10):
            points = np.random.rand(100, 3).astype(np.float32)
            timestamp = 1000.0 + i * 0.1
            frame_data = pack_points_binary(points, timestamp)
            await service.record_frame("test_topic", frame_data)
        
        # Check frames were recorded
        handle = service.active_recordings[recording_id]
        assert handle.frame_count == 10
        assert handle.last_timestamp == 1000.9
        
        # Cleanup
        info = await service.stop_recording(recording_id)
        assert info["frame_count"] == 10
    
    @pytest.mark.asyncio
    async def test_record_frame_wrong_topic(self, service):
        """Test recording frame with wrong topic does nothing"""
        # Start recording
        recording_id, _ = await service.start_recording(topic="test_topic")
        
        # Record frame with different topic
        points = np.random.rand(100, 3).astype(np.float32)
        frame_data = pack_points_binary(points, 1000.0)
        await service.record_frame("other_topic", frame_data)
        
        # Check no frames were recorded
        handle = service.active_recordings[recording_id]
        assert handle.frame_count == 0
        
        # Cleanup
        await service.stop_recording(recording_id)
    
    @pytest.mark.asyncio
    async def test_record_frame_invalid_data(self, service):
        """Test recording frame with invalid data doesn't crash"""
        # Start recording
        recording_id, _ = await service.start_recording(topic="test_topic")
        
        # Try to record invalid frame data
        await service.record_frame("test_topic", b"invalid_data")
        
        # Check no frames were recorded
        handle = service.active_recordings[recording_id]
        assert handle.frame_count == 0
        
        # Cleanup
        await service.stop_recording(recording_id)
    
    @pytest.mark.asyncio
    async def test_concurrent_recordings(self, service):
        """Test recording multiple topics concurrently"""
        # Start multiple recordings
        rec_id1, _ = await service.start_recording(topic="topic1")
        rec_id2, _ = await service.start_recording(topic="topic2")
        rec_id3, _ = await service.start_recording(topic="topic3")
        
        assert len(service.active_recordings) == 3
        
        # Record frames for each topic
        for topic in ["topic1", "topic2", "topic3"]:
            points = np.random.rand(50, 3).astype(np.float32)
            frame_data = pack_points_binary(points, 1000.0)
            await service.record_frame(topic, frame_data)
        
        # Check all recordings have frames
        for rec_id in [rec_id1, rec_id2, rec_id3]:
            handle = service.active_recordings[rec_id]
            assert handle.frame_count == 1
        
        # Stop all recordings
        info1 = await service.stop_recording(rec_id1)
        info2 = await service.stop_recording(rec_id2)
        info3 = await service.stop_recording(rec_id3)
        
        assert info1["topic"] == "topic1"
        assert info2["topic"] == "topic2"
        assert info3["topic"] == "topic3"
    
    @pytest.mark.asyncio
    async def test_get_active_recordings(self, service):
        """Test getting list of active recordings"""
        # No active recordings initially
        assert service.get_active_recordings() == []
        
        # Start recordings
        rec_id1, _ = await service.start_recording(topic="topic1")
        rec_id2, _ = await service.start_recording(topic="topic2")
        
        # Get active recordings
        active = service.get_active_recordings()
        
        assert len(active) == 2
        assert any(r["recording_id"] == rec_id1 for r in active)
        assert any(r["recording_id"] == rec_id2 for r in active)
        
        for recording in active:
            assert "recording_id" in recording
            assert "topic" in recording
            assert "frame_count" in recording
            assert "duration_seconds" in recording
            assert "started_at" in recording
        
        # Cleanup
        await service.stop_recording(rec_id1)
        await service.stop_recording(rec_id2)
    
    @pytest.mark.asyncio
    async def test_is_recording(self, service):
        """Test checking if topic is being recorded"""
        # Not recording initially
        assert service.is_recording("test_topic") is False
        
        # Start recording
        rec_id, _ = await service.start_recording(topic="test_topic")
        
        # Now recording
        assert service.is_recording("test_topic") is True
        assert service.is_recording("other_topic") is False
        
        # Stop recording
        await service.stop_recording(rec_id)
        
        # Not recording anymore
        assert service.is_recording("test_topic") is False
    
    @pytest.mark.asyncio
    async def test_get_recording_for_topic(self, service):
        """Test getting recording info for specific topic"""
        # No recording initially
        assert service.get_recording_for_topic("test_topic") is None
        
        # Start recording
        rec_id, _ = await service.start_recording(topic="test_topic")
        
        # Get recording info
        info = service.get_recording_for_topic("test_topic")
        
        assert info is not None
        assert info["recording_id"] == rec_id
        assert info["topic"] == "test_topic"
        assert "frame_count" in info
        
        # Other topic returns None
        assert service.get_recording_for_topic("other_topic") is None
        
        # Cleanup
        await service.stop_recording(rec_id)
    
    @pytest.mark.asyncio
    async def test_stop_all_recordings(self, service):
        """Test stopping all active recordings"""
        # Start multiple recordings
        rec_id1, _ = await service.start_recording(topic="topic1")
        rec_id2, _ = await service.start_recording(topic="topic2")
        rec_id3, _ = await service.start_recording(topic="topic3")
        
        # Record some frames
        for topic in ["topic1", "topic2", "topic3"]:
            points = np.random.rand(50, 3).astype(np.float32)
            frame_data = pack_points_binary(points, 1000.0)
            await service.record_frame(topic, frame_data)
        
        # Stop all
        results = await service.stop_all_recordings()
        
        assert len(results) == 3
        assert len(service.active_recordings) == 0
        
        # Check all recordings were stopped
        topics = {r["topic"] for r in results}
        assert topics == {"topic1", "topic2", "topic3"}
        
        for result in results:
            assert result["frame_count"] == 1
            assert Path(result["file_path"]).exists()
    
    @pytest.mark.asyncio
    async def test_stop_all_recordings_empty(self, service):
        """Test stopping all recordings when none are active"""
        results = await service.stop_all_recordings()
        assert results == []
    
    @pytest.mark.asyncio
    async def test_file_naming_pattern(self, service):
        """Test recording file naming includes topic and timestamp"""
        rec_id, file_path = await service.start_recording(
            topic="sensor1_raw_points"
        )
        
        filename = Path(file_path).name
        
        # Should contain topic
        assert "sensor1_raw_points" in filename
        
        # Should have .lidr extension
        assert filename.endswith(".lidr")
        
        # Should contain date/time stamp (YYYYMMDD_HHMMSS format)
        import re
        assert re.search(r"\d{8}_\d{6}", filename)
        
        # Should contain short UUID
        assert re.search(r"[a-f0-9]{8}\.lidr$", filename)
        
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
            topic="test_topic",
            name="Custom Recording",
            metadata=custom_metadata
        )
        
        # Check metadata in handle
        handle = service.active_recordings[rec_id]
        assert handle.metadata["sensor_id"] == "sensor_123"
        assert handle.metadata["sensor_model"] == "SICK TiM781"
        assert handle.metadata["name"] == "Custom Recording"
        
        # Stop and check metadata in result
        info = await service.stop_recording(rec_id)
        assert info["metadata"]["sensor_id"] == "sensor_123"
        assert info["metadata"]["sensor_model"] == "SICK TiM781"
    
    @pytest.mark.asyncio
    async def test_thread_safety(self, service):
        """Test concurrent access with asyncio lock"""
        # Start multiple recordings concurrently
        tasks = []
        for i in range(5):
            task = service.start_recording(topic=f"topic_{i}")
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert len(results) == 5
        assert len(service.active_recordings) == 5
        
        # Stop all concurrently
        stop_tasks = []
        for rec_id, _ in results:
            task = service.stop_recording(rec_id)
            stop_tasks.append(task)
        
        stop_results = await asyncio.gather(*stop_tasks)
        assert len(stop_results) == 5
        assert len(service.active_recordings) == 0


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
