"""
Tests for Status Broadcaster Service
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from app.services import status_broadcaster


class TestStatusBroadcaster:
    """Test suite for status broadcaster service"""
    
    def test_build_status_message_structure(self):
        """Test _build_status_message returns correct structure"""
        with patch('app.services.status_broadcaster.LidarRepository') as MockLidarRepo, \
             patch('app.services.status_broadcaster.FusionRepository') as MockFusionRepo, \
             patch('app.services.status_broadcaster.lidar_service') as mock_service:
            
            # Setup mocks
            MockLidarRepo.return_value.list.return_value = []
            MockFusionRepo.return_value.list.return_value = []
            mock_service.lidar_runtime = {}
            mock_service.processes = {}
            mock_service.sensors = []
            mock_service.fusions = []
            
            result = status_broadcaster._build_status_message()
            
            assert "lidars" in result
            assert "fusions" in result
            assert isinstance(result["lidars"], list)
            assert isinstance(result["fusions"], list)
    
    def test_build_status_message_with_lidar(self):
        """Test _build_status_message includes lidar data"""
        with patch('app.services.status_broadcaster.LidarRepository') as MockLidarRepo, \
             patch('app.services.status_broadcaster.FusionRepository') as MockFusionRepo, \
             patch('app.services.status_broadcaster.lidar_service') as mock_service, \
             patch('app.services.status_broadcaster.time') as mock_time:
            
            # Setup time
            mock_time.time.return_value = 100.0
            
            # Setup lidar config
            MockLidarRepo.return_value.list.return_value = [{
                "id": "lidar1",
                "name": "Test Lidar",
                "enabled": True,
                "mode": "real",
                "topic_prefix": "test_lidar",
                "pipeline_name": "downsample",
            }]
            MockFusionRepo.return_value.list.return_value = []
            
            # Setup runtime
            mock_process = Mock()
            mock_process.is_alive.return_value = True
            mock_service.processes = {"lidar1": mock_process}
            mock_service.lidar_runtime = {
                "lidar1": {
                    "last_frame_at": 95.0,  # 5 seconds ago
                    "last_error": None,
                    "connection_status": "connected"
                }
            }
            
            # Setup sensor
            mock_sensor = Mock()
            mock_sensor.id = "lidar1"
            mock_sensor.topic_prefix = "test_lidar"
            mock_service.sensors = [mock_sensor]
            mock_service.fusions = []
            
            result = status_broadcaster._build_status_message()
            
            assert len(result["lidars"]) == 1
            lidar_status = result["lidars"][0]
            assert lidar_status["id"] == "lidar1"
            assert lidar_status["name"] == "Test Lidar"
            assert lidar_status["enabled"] is True
            assert lidar_status["running"] is True
            assert lidar_status["connection_status"] == "connected"
            assert lidar_status["frame_age_seconds"] == 5.0
    
    def test_build_status_message_with_fusion(self):
        """Test _build_status_message includes fusion data"""
        with patch('app.services.status_broadcaster.LidarRepository') as MockLidarRepo, \
             patch('app.services.status_broadcaster.FusionRepository') as MockFusionRepo, \
             patch('app.services.status_broadcaster.lidar_service') as mock_service, \
             patch('app.services.status_broadcaster.time') as mock_time:
            
            # Setup time
            mock_time.time.return_value = 200.0
            
            # Setup fusion config
            MockLidarRepo.return_value.list.return_value = []
            MockFusionRepo.return_value.list.return_value = [{
                "id": "fusion1",
                "topic": "fused_points",
                "sensor_ids": ["lidar1", "lidar2"],
                "enabled": True,
            }]
            
            # Setup fusion service
            mock_fusion = Mock()
            mock_fusion.id = "fusion1"
            mock_fusion.enabled = True
            mock_fusion.last_broadcast_at = 195.0  # 5 seconds ago
            mock_fusion.last_error = None
            
            mock_service.lidar_runtime = {}
            mock_service.processes = {}
            mock_service.sensors = []
            mock_service.fusions = [mock_fusion]
            
            result = status_broadcaster._build_status_message()
            
            assert len(result["fusions"]) == 1
            fusion_status = result["fusions"][0]
            assert fusion_status["id"] == "fusion1"
            assert fusion_status["topic"] == "fused_points"
            assert fusion_status["enabled"] is True
            assert fusion_status["running"] is True
            assert fusion_status["broadcast_age_seconds"] == 5.0
    
    @pytest.mark.asyncio
    async def test_status_broadcast_loop_registers_topic(self):
        """Test _status_broadcast_loop registers system_status topic"""
        with patch('app.services.status_broadcaster.manager') as mock_manager, \
             patch('app.services.status_broadcaster._build_status_message') as mock_build:
            
            mock_build.return_value = {"lidars": [], "fusions": []}
            
            # Set stop event immediately
            status_broadcaster._stop_event = asyncio.Event()
            status_broadcaster._stop_event.set()
            
            await status_broadcaster._status_broadcast_loop()
            
            mock_manager.register_topic.assert_called_once_with("system_status")
    
    @pytest.mark.asyncio
    async def test_status_broadcast_loop_broadcasts_status(self):
        """Test _status_broadcast_loop broadcasts status messages"""
        with patch('app.services.status_broadcaster.manager') as mock_manager, \
             patch('app.services.status_broadcaster._build_status_message') as mock_build:
            
            status_data = {"lidars": [], "fusions": []}
            mock_build.return_value = status_data
            
            # Create stop event
            stop_event = asyncio.Event()
            status_broadcaster._stop_event = stop_event
            
            # Run loop in background
            loop_task = asyncio.create_task(status_broadcaster._status_broadcast_loop())
            
            # Wait a bit for first broadcast
            await asyncio.sleep(0.1)
            
            # Stop the loop
            stop_event.set()
            await loop_task
            
            # Should have broadcast at least once
            mock_manager.broadcast.assert_called_with("system_status", status_data)
    
    @pytest.mark.asyncio
    async def test_status_broadcast_loop_handles_errors(self):
        """Test _status_broadcast_loop continues after errors"""
        with patch('app.services.status_broadcaster.manager') as mock_manager, \
             patch('app.services.status_broadcaster._build_status_message') as mock_build:
            
            # First call raises error, second succeeds
            mock_build.side_effect = [Exception("Test error"), {"lidars": [], "fusions": []}]
            
            # Create stop event
            stop_event = asyncio.Event()
            status_broadcaster._stop_event = stop_event
            
            # Run loop in background
            loop_task = asyncio.create_task(status_broadcaster._status_broadcast_loop())
            
            # Wait for error and recovery
            await asyncio.sleep(2.5)  # More than 2 second interval
            
            # Stop the loop
            stop_event.set()
            await loop_task
            
            # Should have attempted broadcast twice (once failed, once succeeded)
            assert mock_build.call_count == 2
    
    def test_start_status_broadcaster(self):
        """Test start_status_broadcaster creates task"""
        # Reset state
        status_broadcaster._broadcast_task = None
        status_broadcaster._stop_event = None
        
        with patch('asyncio.create_task') as mock_create_task:
            status_broadcaster.start_status_broadcaster()
            
            mock_create_task.assert_called_once()
            assert status_broadcaster._stop_event is not None
            assert not status_broadcaster._stop_event.is_set()
    
    def test_start_status_broadcaster_idempotent(self):
        """Test start_status_broadcaster doesn't restart if already running"""
        # Set as running
        status_broadcaster._broadcast_task = Mock()
        
        with patch('asyncio.create_task') as mock_create_task:
            status_broadcaster.start_status_broadcaster()
            
            # Should not create new task
            mock_create_task.assert_not_called()
    
    def test_stop_status_broadcaster(self):
        """Test stop_status_broadcaster cancels task"""
        # Setup running state
        mock_task = Mock()
        mock_event = Mock()
        status_broadcaster._broadcast_task = mock_task
        status_broadcaster._stop_event = mock_event
        
        status_broadcaster.stop_status_broadcaster()
        
        mock_event.set.assert_called_once()
        mock_task.cancel.assert_called_once()
        assert status_broadcaster._broadcast_task is None
        assert status_broadcaster._stop_event is None
    
    def test_stop_status_broadcaster_when_not_running(self):
        """Test stop_status_broadcaster handles not running state"""
        status_broadcaster._broadcast_task = None
        status_broadcaster._stop_event = None
        
        # Should not raise
        status_broadcaster.stop_status_broadcaster()
