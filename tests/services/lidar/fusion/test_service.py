import pytest
import numpy as np
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.fusion.service import FusionService
from app.services.websocket.manager import manager

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
    service.forward_data = AsyncMock()
    return service


def test_fusion_service_init(mock_lidar_service):
    """FusionService with sensor_ids filter stores the filter set correctly."""
    fusion = FusionService(mock_lidar_service, sensor_ids=["sensor1"])
    assert fusion._filter == {"sensor1"}


def test_enable_disable(mock_lidar_service):
    fusion = FusionService(mock_lidar_service)

    fusion.enable()
    assert fusion._enabled

    fusion.disable()
    assert not fusion._enabled


@pytest.mark.asyncio
async def test_on_frame_basic(mock_lidar_service):
    """Both sensors contribute → fused and forwarded via forward_data."""
    fusion = FusionService(mock_lidar_service)

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
    mock_lidar_service.forward_data.assert_not_called()

    # Send second frame - should fuse and forward
    await fusion._on_frame(payload2)

    mock_lidar_service.forward_data.assert_called_once()
    assert fusion.last_broadcast_ts == 124.0


@pytest.mark.asyncio
async def test_on_frame_filtered(mock_lidar_service):
    """With sensor_ids filter, only the listed sensor triggers forwarding."""
    fusion = FusionService(mock_lidar_service, sensor_ids=["sensor1"])

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

    # Only expecting sensor1, so this should forward immediately
    await fusion._on_frame(payload1)
    mock_lidar_service.forward_data.assert_called_once()

    # Sensor 2 is filtered out, shouldn't trigger anything
    await fusion._on_frame(payload2)
    assert mock_lidar_service.forward_data.call_count == 1
