"""
Unit tests for calibration provenance tracking (source_sensor_id, processing_chain).

Tests the BufferedFrame data structure and frame aggregation logic.
"""
import pytest
import numpy as np
from collections import deque
from unittest.mock import Mock, AsyncMock, patch

from app.modules.calibration.calibration_node import CalibrationNode, BufferedFrame


class TestBufferedFrame:
    """Test BufferedFrame dataclass"""
    
    def test_buffered_frame_creation(self):
        """Test creating a BufferedFrame with all fields"""
        points = np.random.rand(100, 3).astype(np.float32)
        timestamp = 1234567890.0
        source_sensor_id = "sensor-A"
        processing_chain = ["sensor-A", "crop-1", "downsample-1"]
        node_id = "downsample-1"
        
        frame = BufferedFrame(
            points=points,
            timestamp=timestamp,
            source_sensor_id=source_sensor_id,
            processing_chain=processing_chain,
            node_id=node_id
        )
        
        assert np.array_equal(frame.points, points)
        assert frame.timestamp == timestamp
        assert frame.source_sensor_id == source_sensor_id
        assert frame.processing_chain == processing_chain
        assert frame.node_id == node_id


class TestCalibrationNodeProvenance:
    """Test CalibrationNode provenance tracking"""
    
    @pytest.fixture
    def mock_manager(self):
        """Create a mock NodeManager"""
        manager = Mock()
        manager.forward_data = AsyncMock()
        manager.reload_config = Mock()
        return manager
    
    @pytest.fixture
    def calibration_node(self, mock_manager):
        """Create a CalibrationNode with mocked manager"""
        config = {
            "name": "Test Calibration",
            "max_buffered_frames": 30
        }
        return CalibrationNode(mock_manager, "calib-node-1", config)
    
    @pytest.mark.asyncio
    async def test_on_input_extracts_provenance_direct_sensor(self, calibration_node):
        """Test on_input extracts source_sensor_id and processing_chain from direct sensor"""
        payload = {
            "lidar_id": "sensor-A",
            "node_id": "sensor-A",
            "points": np.random.rand(100, 3).astype(np.float32),
            "timestamp": 1234567890.0,
            "processing_chain": ["sensor-A"]
        }
        
        await calibration_node.on_input(payload)
        
        # Verify frame buffer has entry for sensor-A
        assert "sensor-A" in calibration_node._frame_buffer
        assert len(calibration_node._frame_buffer["sensor-A"]) == 1
        
        # Verify buffered frame has correct provenance
        frame = calibration_node._frame_buffer["sensor-A"][0]
        assert frame.source_sensor_id == "sensor-A"
        assert frame.processing_chain == ["sensor-A"]
        assert frame.node_id == "sensor-A"
        assert frame.timestamp == 1234567890.0
    
    @pytest.mark.asyncio
    async def test_on_input_extracts_provenance_complex_chain(self, calibration_node):
        """Test on_input extracts provenance from sensor behind processing nodes"""
        payload = {
            "lidar_id": "sensor-A",  # Canonical leaf sensor
            "node_id": "downsample-1",  # Last processing node
            "points": np.random.rand(100, 3).astype(np.float32),
            "timestamp": 1234567890.0,
            "processing_chain": ["sensor-A", "crop-1", "downsample-1"]
        }
        
        await calibration_node.on_input(payload)
        
        # Verify frame buffer is keyed by source_sensor_id (lidar_id)
        assert "sensor-A" in calibration_node._frame_buffer
        assert "downsample-1" not in calibration_node._frame_buffer
        
        # Verify buffered frame has correct provenance
        frame = calibration_node._frame_buffer["sensor-A"][0]
        assert frame.source_sensor_id == "sensor-A"
        assert frame.processing_chain == ["sensor-A", "crop-1", "downsample-1"]
        assert frame.node_id == "downsample-1"
    
    @pytest.mark.asyncio
    async def test_on_input_ring_buffer_eviction(self, calibration_node):
        """Test frame buffer evicts oldest frames when full"""
        calibration_node._max_frames = 5
        
        # Send 10 frames
        for i in range(10):
            payload = {
                "lidar_id": "sensor-A",
                "node_id": "sensor-A",
                "points": np.random.rand(100, 3).astype(np.float32) * i,  # Unique points
                "timestamp": float(i),
                "processing_chain": ["sensor-A"]
            }
            await calibration_node.on_input(payload)
        
        # Should only have 5 frames (most recent)
        assert len(calibration_node._frame_buffer["sensor-A"]) == 5
        
        # Verify we have frames 5-9 (0-4 were evicted)
        timestamps = [f.timestamp for f in calibration_node._frame_buffer["sensor-A"]]
        assert timestamps == [5.0, 6.0, 7.0, 8.0, 9.0]
    
    @pytest.mark.asyncio
    async def test_on_input_reference_sensor_assignment(self, calibration_node):
        """Test first sensor becomes reference, subsequent ones become sources"""
        # First sensor
        payload_a = {
            "lidar_id": "sensor-A",
            "node_id": "sensor-A",
            "points": np.random.rand(100, 3).astype(np.float32),
            "timestamp": 1.0,
            "processing_chain": ["sensor-A"]
        }
        await calibration_node.on_input(payload_a)
        
        assert calibration_node._reference_sensor_id == "sensor-A"
        assert len(calibration_node._source_sensor_ids) == 0
        
        # Second sensor
        payload_b = {
            "lidar_id": "sensor-B",
            "node_id": "sensor-B",
            "points": np.random.rand(100, 3).astype(np.float32),
            "timestamp": 2.0,
            "processing_chain": ["sensor-B"]
        }
        await calibration_node.on_input(payload_b)
        
        assert calibration_node._reference_sensor_id == "sensor-A"
        assert "sensor-B" in calibration_node._source_sensor_ids
    
    def test_aggregate_frames_single_frame(self, calibration_node):
        """Test aggregating a single frame"""
        # Manually populate buffer
        points = np.random.rand(100, 3).astype(np.float32)
        frame = BufferedFrame(
            points=points,
            timestamp=1.0,
            source_sensor_id="sensor-A",
            processing_chain=["sensor-A", "crop-1"],
            node_id="crop-1"
        )
        calibration_node._frame_buffer["sensor-A"] = deque([frame], maxlen=30)
        
        # Aggregate 1 frame
        result = calibration_node._aggregate_frames("sensor-A", sample_frames=1)
        
        assert result is not None
        aggregated, source_id, chain = result
        assert np.array_equal(aggregated, points)
        assert source_id == "sensor-A"
        assert chain == ["sensor-A", "crop-1"]
    
    def test_aggregate_frames_multiple_frames(self, calibration_node):
        """Test aggregating multiple frames"""
        # Manually populate buffer with 3 frames
        frames = []
        for i in range(3):
            points = np.ones((100, 3), dtype=np.float32) * i
            frame = BufferedFrame(
                points=points,
                timestamp=float(i),
                source_sensor_id="sensor-A",
                processing_chain=["sensor-A"],
                node_id="sensor-A"
            )
            frames.append(frame)
        
        calibration_node._frame_buffer["sensor-A"] = deque(frames, maxlen=30)
        
        # Aggregate all 3 frames
        result = calibration_node._aggregate_frames("sensor-A", sample_frames=3)
        
        assert result is not None
        aggregated, source_id, chain = result
        assert aggregated.shape[0] == 300  # 3 frames × 100 points
        assert source_id == "sensor-A"
        assert chain == ["sensor-A"]  # Latest frame's chain
    
    def test_aggregate_frames_requests_more_than_available(self, calibration_node):
        """Test aggregating when requesting more frames than available"""
        # Populate buffer with 2 frames
        frames = []
        for i in range(2):
            points = np.ones((100, 3), dtype=np.float32) * i
            frame = BufferedFrame(
                points=points,
                timestamp=float(i),
                source_sensor_id="sensor-A",
                processing_chain=["sensor-A"],
                node_id="sensor-A"
            )
            frames.append(frame)
        
        calibration_node._frame_buffer["sensor-A"] = deque(frames, maxlen=30)
        
        # Request 5 frames, but only 2 available
        result = calibration_node._aggregate_frames("sensor-A", sample_frames=5)
        
        assert result is not None
        aggregated, source_id, chain = result
        assert aggregated.shape[0] == 200  # Only 2 frames available
    
    def test_aggregate_frames_sensor_not_found(self, calibration_node):
        """Test aggregating for non-existent sensor returns None"""
        result = calibration_node._aggregate_frames("sensor-X", sample_frames=1)
        assert result is None
    
    def test_aggregate_frames_empty_buffer(self, calibration_node):
        """Test aggregating from empty buffer returns None"""
        calibration_node._frame_buffer["sensor-A"] = deque(maxlen=30)
        result = calibration_node._aggregate_frames("sensor-A", sample_frames=1)
        assert result is None
    
    def test_get_status_reports_buffer_sizes(self, calibration_node):
        """Test get_status includes per-sensor buffer sizes"""
        # Populate buffers
        for sensor_id in ["sensor-A", "sensor-B"]:
            frames = []
            for i in range(3 if sensor_id == "sensor-A" else 5):
                frame = BufferedFrame(
                    points=np.random.rand(10, 3).astype(np.float32),
                    timestamp=float(i),
                    source_sensor_id=sensor_id,
                    processing_chain=[sensor_id],
                    node_id=sensor_id
                )
                frames.append(frame)
            calibration_node._frame_buffer[sensor_id] = deque(frames, maxlen=30)
        
        status = calibration_node.get_status()
        
        # Should report buffer sizes as dict, not list
        assert isinstance(status["buffered_frames"], dict)
        assert status["buffered_frames"]["sensor-A"] == 3
        assert status["buffered_frames"]["sensor-B"] == 5
