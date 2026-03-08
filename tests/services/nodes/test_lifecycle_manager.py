"""
Tests for LifecycleManager async functionality
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.services.nodes.managers.lifecycle import LifecycleManager


class TestLifecycleManagerAsync:
    """Test suite for async LifecycleManager functionality"""
    
    @pytest.fixture
    def mock_manager(self):
        """Create a mock NodeManager instance"""
        manager = Mock()
        manager.nodes = {}
        manager.node_runtime_status = {}
        manager.downstream_map = {}
        manager._throttle_config = {}
        manager._last_process_time = {}
        manager._throttled_count = {}
        return manager
    
    @pytest.fixture
    def lifecycle_manager(self, mock_manager):
        """Create LifecycleManager instance with mock NodeManager"""
        return LifecycleManager(mock_manager)
    
    @pytest.mark.asyncio
    @patch('app.services.nodes.managers.lifecycle.manager')
    async def test_remove_node_async_uses_stored_ws_topic(self, mock_websocket_manager, lifecycle_manager):
        """Test remove_node_async uses stored _ws_topic attribute"""
        # Setup mock node instance with stored topic
        node_instance = Mock()
        node_instance._ws_topic = "stored_topic_abc12345"
        node_instance.name = "different_name"
        node_id = "test_node_id"
        
        # Add to manager's nodes
        lifecycle_manager.manager.nodes[node_id] = node_instance
        
        # Mock the websocket manager unregister_topic
        mock_websocket_manager.unregister_topic = AsyncMock()
        
        await lifecycle_manager.remove_node_async(node_id)
        
        # Assert unregister_topic was called with stored topic (not re-derived name)
        mock_websocket_manager.unregister_topic.assert_called_once_with("stored_topic_abc12345")
    
    @pytest.mark.asyncio
    @patch('app.services.nodes.managers.lifecycle.manager')
    @patch('app.services.nodes.managers.lifecycle.slugify_topic_prefix')
    async def test_remove_node_async_falls_back_to_derived_topic(self, mock_slugify, mock_websocket_manager, lifecycle_manager):
        """Test remove_node_async falls back to derived topic when _ws_topic is absent"""
        # Setup mock node instance WITHOUT _ws_topic
        node_instance = Mock()
        node_instance.name = "Front Lidar"
        node_id = "abc12345xyz"
        
        # Remove _ws_topic attribute to simulate absence
        if hasattr(node_instance, '_ws_topic'):
            delattr(node_instance, '_ws_topic')
        
        # Add to manager's nodes
        lifecycle_manager.manager.nodes[node_id] = node_instance
        
        # Mock slugify function
        mock_slugify.return_value = "front_lidar"
        
        # Mock the websocket manager unregister_topic
        mock_websocket_manager.unregister_topic = AsyncMock()
        
        await lifecycle_manager.remove_node_async(node_id)
        
        # Assert unregister_topic was called with derived topic
        mock_websocket_manager.unregister_topic.assert_called_once_with("front_lidar_abc12345")
        mock_slugify.assert_called_once_with("Front Lidar")
    
    @pytest.mark.asyncio
    @patch('app.services.nodes.managers.lifecycle.manager')
    async def test_remove_node_async_missing_node_is_noop(self, mock_websocket_manager, lifecycle_manager):
        """Test remove_node_async with nonexistent node_id is a no-op"""
        # Mock the websocket manager unregister_topic
        mock_websocket_manager.unregister_topic = AsyncMock()
        
        # Should not raise any exception
        await lifecycle_manager.remove_node_async("nonexistent_id")
        
        # unregister_topic should not be called
        mock_websocket_manager.unregister_topic.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('app.services.nodes.managers.lifecycle.manager')
    async def test_remove_node_async_full_cleanup_sequence(self, mock_websocket_manager, lifecycle_manager):
        """Test remove_node_async executes full cleanup sequence"""
        # Setup mock node instance
        node_instance = Mock()
        node_instance._ws_topic = "test_topic_12345678"
        node_instance.stop = Mock()
        node_id = "test_node_12345678"
        
        # Add to manager's nodes and other tracking dicts
        lifecycle_manager.manager.nodes[node_id] = node_instance
        lifecycle_manager.manager.node_runtime_status[node_id] = {"status": "running"}
        lifecycle_manager.manager.downstream_map[node_id] = ["target1", "target2"]
        lifecycle_manager.manager._throttle_config[node_id] = 100.0
        lifecycle_manager.manager._last_process_time[node_id] = 123456.789
        lifecycle_manager.manager._throttled_count[node_id] = 5
        
        # Mock the websocket manager unregister_topic
        mock_websocket_manager.unregister_topic = AsyncMock()
        
        await lifecycle_manager.remove_node_async(node_id)
        
        # Assert all cleanup steps occurred
        # 1. Node removed from nodes dict
        assert node_id not in lifecycle_manager.manager.nodes
        
        # 2. Node stop method called
        node_instance.stop.assert_called_once()
        
        # 3. WebSocket topic unregistered
        mock_websocket_manager.unregister_topic.assert_called_once_with("test_topic_12345678")
        
        # 4. Runtime status cleaned up
        assert node_id not in lifecycle_manager.manager.node_runtime_status
        
        # 5. Downstream routing cleaned up
        assert node_id not in lifecycle_manager.manager.downstream_map
        
        # 6. Throttle state cleaned up
        assert node_id not in lifecycle_manager.manager._throttle_config
        assert node_id not in lifecycle_manager.manager._last_process_time
        assert node_id not in lifecycle_manager.manager._throttled_count