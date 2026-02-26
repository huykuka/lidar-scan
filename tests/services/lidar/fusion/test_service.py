import pytest
import numpy as np
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.fusion.service import FusionService
from app.services.websocket.manager import manager

@pytest.fixture
def mock_manager():
    with patch("app.modules.fusion.service.manager", new_callable=MagicMock) as mock:
        mock.broadcast = AsyncMock()
        yield mock

@pytest.fixture
def mock_lidar_service():
    service = MagicMock()
    # Provide a couple mock sensors
    s1 = MagicMock()
    s1.id = "sensor1"
    s1.topic_prefix = "topic1"
    s1.transformation = np.eye(4)
    
    s2 = MagicMock()
    s2.id = "sensor2"
    s2.topic_prefix = "topic2"
    s2.transformation = np.eye(4)
    
    service.nodes = {"sensor1": s1, "sensor2": s2}
    service._handle_incoming_data = AsyncMock()
    return service

def test_fusion_service_init(mock_lidar_service):
    fusion = FusionService(mock_lidar_service, topic="test_fusion", sensor_ids=["sensor1"])
    assert fusion._topic == "test_fusion"
    assert fusion.topic_filter == {"topic1"}
    
def test_enable_disable(mock_lidar_service):
    fusion = FusionService(mock_lidar_service)
    original_handle = mock_lidar_service._handle_incoming_data
    
    fusion.enable()
    assert fusion._enabled
    assert mock_lidar_service._handle_incoming_data is not original_handle
    
    fusion.disable()
    assert not fusion._enabled
    assert mock_lidar_service._handle_incoming_data is original_handle

@pytest.mark.asyncio
async def test_on_frame_basic(mock_lidar_service, mock_manager):
    fusion = FusionService(mock_lidar_service, topic="test_fusion")
    
    payload1 = {
        "lidar_id": "sensor1",
        "timestamp": 123.0,
        "points": np.array([[1.0, 2.0, 3.0]])
    }
    
    payload2 = {
        "lidar_id": "sensor2",
        "timestamp": 124.0,
        "points": np.array([[4.0, 5.0, 6.0]])
    }
    
    # Send first frame - waiting for second
    await fusion._on_frame(payload1)
    mock_manager.broadcast.assert_not_called()
    
    # Send second frame - should fuse and broadcast
    with patch("app.modules.fusion.service.pack_points_binary", return_value=b"fused"):
        await fusion._on_frame(payload2)
    
    mock_manager.broadcast.assert_called_once_with("test_fusion", b"fused")
    assert fusion.last_broadcast_ts == 124.0

@pytest.mark.asyncio
async def test_on_frame_filtered(mock_lidar_service, mock_manager):
    fusion = FusionService(mock_lidar_service, topic="test_fusion", sensor_ids=["sensor1"])
    
    payload1 = {
        "lidar_id": "sensor1",
        "timestamp": 123.0,
        "points": np.array([[1.0, 2.0, 3.0]])
    }
    
    payload2 = {
        "lidar_id": "sensor2",
        "timestamp": 124.0,
        "points": np.array([[4.0, 5.0, 6.0]])
    }
    
    # Only expecting sensor1, so this should broadcast immediately
    with patch("app.modules.fusion.service.pack_points_binary", return_value=b"fused"):
        await fusion._on_frame(payload1)
        
    mock_manager.broadcast.assert_called_once()
    
    # Sensor 2 is filtered out, shouldn't trigger anything
    await fusion._on_frame(payload2)
    
    assert mock_manager.broadcast.call_count == 1
