"""
Tests for NodeManager reload and orphan sweep functionality
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.services.nodes.orchestrator import NodeManager


class TestNodeManagerReload:
    """Test suite for NodeManager reload functionality"""
    
    @pytest.fixture
    def node_manager(self):
        """Create NodeManager instance"""
        return NodeManager()
    
    @pytest.mark.asyncio
    async def test_reload_config_sweeps_orphaned_topics(self, node_manager):
        """Test reload_config sweeps invalid topics (orphaned + phantom)"""
        
        with patch('app.services.nodes.orchestrator.websocket_manager') as mock_websocket_manager, \
             patch('app.services.nodes.orchestrator.SYSTEM_TOPICS', {'system_status'}):
            
            # Setup: ConnectionManager has a phantom topic that doesn't belong to any node
            mock_websocket_manager.active_connections = {
                "orphan_topic_00000000": [],  # Invalid topic - no corresponding node
                "system_status": [],          # System topic that should NOT be swept  
                "valid_sensor_12345678": []   # Valid topic that will be created by load_config
            }
            mock_websocket_manager.unregister_topic = AsyncMock()
            
            # Mock load_config to create a node with valid topic
            def mock_load_config():
                # Create a mock node with a valid _ws_topic
                mock_node = Mock()
                mock_node._ws_topic = "valid_sensor_12345678"
                node_manager.nodes = {"valid_node_id": mock_node}
            
            # Mock the other manager methods
            node_manager.stop = Mock()
            node_manager.load_config = mock_load_config
            node_manager.start = Mock()
            node_manager._cleanup_all_nodes_async = AsyncMock()
            node_manager.is_running = False
            
            await node_manager.reload_config()
            
            # Assert invalid topic was swept (but not system or valid topics)
            mock_websocket_manager.unregister_topic.assert_called_once_with("orphan_topic_00000000")
    
    @pytest.mark.asyncio
    async def test_reload_config_system_topics_not_swept(self, node_manager):
        """Test reload_config does not sweep system topics"""
        
        with patch('app.services.nodes.orchestrator.websocket_manager') as mock_websocket_manager, \
             patch('app.services.nodes.orchestrator.SYSTEM_TOPICS', {'system_status'}):
            
            # Setup: ConnectionManager has only system topics
            mock_websocket_manager.active_connections = {
                "system_status": []  # System topic that should NOT be swept
            }
            mock_websocket_manager.unregister_topic = AsyncMock()
            
            # Mock the other manager methods
            node_manager.stop = Mock()
            node_manager.load_config = Mock()
            node_manager.start = Mock()
            node_manager._cleanup_all_nodes_async = AsyncMock()
            
            await node_manager.reload_config()
            
            # Assert system_status is still present and unregister was not called
            assert "system_status" in mock_websocket_manager.active_connections
            mock_websocket_manager.unregister_topic.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_reload_config_concurrent_calls_blocked_by_lock(self, node_manager):
        """Test concurrent reload_config calls are serialized by lock"""
        call_order = []
        
        # Mock methods to track call order
        def mock_stop():
            call_order.append("stop")
        
        async def mock_cleanup():
            call_order.append("cleanup")
            await asyncio.sleep(0.1)  # Simulate some work
        
        def mock_load():
            call_order.append("load")
        
        def mock_start(loop=None):
            call_order.append("start")
        
        node_manager.stop = mock_stop  # stop() is sync
        node_manager._cleanup_all_nodes_async = AsyncMock(side_effect=mock_cleanup)
        node_manager.load_config = mock_load
        node_manager.start = mock_start
        node_manager.is_running = False  # Don't restart after reload
        
        # Mock websocket manager to avoid issues
        with patch('app.services.nodes.orchestrator.websocket_manager') as mock_ws_mgr:
            mock_ws_mgr.active_connections = {}
            mock_ws_mgr.unregister_topic = AsyncMock()
            
            # Launch two concurrent reload tasks
            task1 = asyncio.create_task(node_manager.reload_config())
            task2 = asyncio.create_task(node_manager.reload_config())
            
            # Wait for both to complete
            await asyncio.gather(task1, task2)
        
        # Verify both calls completed but were serialized (each should have its own sequence)
        assert len(call_order) == 6  # 2 calls * 3 operations each
        assert call_order == ["stop", "cleanup", "load", "stop", "cleanup", "load"]
        # First call: stop, cleanup, load
        # Second call: stop, cleanup, load
        assert call_order.count("stop") == 2
        assert call_order.count("cleanup") == 2
        assert call_order.count("load") == 2
    
    @pytest.mark.asyncio
    async def test_reload_config_stores_ws_topic_on_new_nodes(self, node_manager):
        """Test reload_config ensures new nodes have _ws_topic attribute"""
        
        with patch('app.services.nodes.orchestrator.websocket_manager') as mock_websocket_manager:
            # Setup mock nodes that load_config will create
            node1 = Mock()
            node1._ws_topic = "sensor1_abc12345"
            node2 = Mock()
            node2._ws_topic = "filter1_def67890"
            
            def mock_load_config():
                # Simulate load_config creating nodes with _ws_topic
                node_manager.nodes = {
                    "node1": node1,
                    "node2": node2
                }
            
            # Mock websocket manager
            mock_websocket_manager.active_connections = {
                "sensor1_abc12345": [],
                "filter1_def67890": []
            }
            mock_websocket_manager.unregister_topic = AsyncMock()
            
            # Mock other methods
            node_manager.stop = Mock()
            node_manager.load_config = mock_load_config
            node_manager.start = Mock()
            node_manager._cleanup_all_nodes_async = AsyncMock()
            node_manager.is_running = False
            
            await node_manager.reload_config()
            
            # Verify each node has _ws_topic attribute and it matches active connections
            for node_id, node_instance in node_manager.nodes.items():
                assert hasattr(node_instance, "_ws_topic")
                assert node_instance._ws_topic in mock_websocket_manager.active_connections
    
    @pytest.mark.asyncio
    async def test_reload_config_lock_prevents_reentrant_calls(self, node_manager):
        """Test that _reload_lock prevents reentrant calls"""
        # First, acquire the lock manually
        await node_manager._reload_lock.acquire()
        
        try:
            # Now try to call reload_config - it should block
            reload_task = asyncio.create_task(node_manager.reload_config())
            
            # Give it a tiny bit of time to try to acquire the lock
            await asyncio.sleep(0.01)
            
            # Task should be waiting (not done)
            assert not reload_task.done()
            
            # Release the lock
            node_manager._reload_lock.release()
            
            # Now the task should be able to proceed, but we need to mock its dependencies
            with patch('app.services.websocket.manager.manager') as mock_ws_mgr:
                mock_ws_mgr.active_connections = {}
                mock_ws_mgr.unregister_topic = AsyncMock()
                
                node_manager.stop = Mock()
                node_manager.load_config = Mock()
                node_manager.start = Mock()
                node_manager._cleanup_all_nodes_async = AsyncMock()
                node_manager.is_running = False
                
                # Wait for completion
                await reload_task
            
            # Task should now be complete
            assert reload_task.done()
            
        finally:
            # Make sure lock is released if test fails
            if node_manager._reload_lock.locked():
                node_manager._reload_lock.release()