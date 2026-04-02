"""
Tests for WebSocket ConnectionManager
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.services.websocket.manager import ConnectionManager, SYSTEM_TOPICS


class TestConnectionManager:
    """Test suite for ConnectionManager"""
    
    def test_initialization(self):
        """Test manager initializes with empty state"""
        manager = ConnectionManager()
        assert manager.active_connections == {}
        assert manager._interceptors == {}
    
    def test_register_topic(self):
        """Test topic registration creates empty connection list"""
        manager = ConnectionManager()
        manager.register_topic("test_topic")
        
        assert "test_topic" in manager.active_connections
        assert manager.active_connections["test_topic"] == []
    
    def test_register_topic_idempotent(self):
        """Test registering same topic twice doesn't overwrite"""
        manager = ConnectionManager()
        manager.register_topic("test_topic")
        manager.active_connections["test_topic"].append("dummy")
        manager.register_topic("test_topic")
        
        # Should still have the dummy connection
        assert manager.active_connections["test_topic"] == ["dummy"]
    
    def test_reset_active_connections(self):
        """Test reset clears all connections and interceptors"""
        manager = ConnectionManager()
        manager.active_connections["topic1"] = ["conn1"]
        manager._interceptors["topic2"] = ["future1"]
        
        manager.reset_active_connections()
        
        assert manager.active_connections == {}
        assert manager._interceptors == {}
    
    @pytest.mark.asyncio
    async def test_connect_new_topic(self):
        """Test connecting to a new topic"""
        manager = ConnectionManager()
        websocket = AsyncMock()
        
        await manager.connect(websocket, "new_topic")
        
        websocket.accept.assert_called_once()
        assert "new_topic" in manager.active_connections
        assert websocket in manager.active_connections["new_topic"]
    
    @pytest.mark.asyncio
    async def test_connect_existing_topic(self):
        """Test connecting to existing topic adds to list"""
        manager = ConnectionManager()
        websocket1 = AsyncMock()
        websocket2 = AsyncMock()
        
        await manager.connect(websocket1, "topic")
        await manager.connect(websocket2, "topic")
        
        assert len(manager.active_connections["topic"]) == 2
        assert websocket1 in manager.active_connections["topic"]
        assert websocket2 in manager.active_connections["topic"]
    
    def test_disconnect_removes_connection(self):
        """Test disconnect removes websocket from topic"""
        manager = ConnectionManager()
        websocket = Mock()
        manager.active_connections["topic"] = [websocket]
        
        manager.disconnect(websocket, "topic")
        
        assert websocket not in manager.active_connections["topic"]
    
    def test_disconnect_nonexistent_websocket(self):
        """Test disconnect handles missing websocket gracefully"""
        manager = ConnectionManager()
        websocket = Mock()
        manager.active_connections["topic"] = []
        
        # Should not raise
        manager.disconnect(websocket, "topic")
    
    def test_disconnect_nonexistent_topic(self):
        """Test disconnect handles missing topic gracefully"""
        manager = ConnectionManager()
        websocket = Mock()
        
        # Should not raise
        manager.disconnect(websocket, "nonexistent")
    
    @pytest.mark.asyncio
    async def test_broadcast_bytes_to_connections(self):
        """Test broadcasting bytes to websocket connections"""
        manager = ConnectionManager()
        websocket1 = AsyncMock()
        websocket2 = AsyncMock()
        await manager.connect(websocket1, "topic")
        await manager.connect(websocket2, "topic")
        
        message = b"test_data"
        await manager.broadcast("topic", message)
        # Yield to event loop so fire-and-forget tasks execute
        await asyncio.sleep(0)
        
        websocket1.send_bytes.assert_called_once_with(message)
        websocket2.send_bytes.assert_called_once_with(message)
    
    @pytest.mark.asyncio
    async def test_broadcast_json_to_connections(self):
        """Test broadcasting JSON to websocket connections"""
        manager = ConnectionManager()
        websocket = AsyncMock()
        await manager.connect(websocket, "topic")
        
        message = {"type": "test", "data": 123}
        await manager.broadcast("topic", message)
        # Yield to event loop so fire-and-forget tasks execute
        await asyncio.sleep(0)
        
        websocket.send_json.assert_called_once_with(message)
    
    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        """Test broadcast removes connections that fail"""
        manager = ConnectionManager()
        dead_ws = AsyncMock()
        dead_ws.send_bytes.side_effect = Exception("Connection dead")
        alive_ws = AsyncMock()
        
        await manager.connect(dead_ws, "topic")
        await manager.connect(alive_ws, "topic")
        
        await manager.broadcast("topic", b"data")
        # Yield to event loop so fire-and-forget tasks execute
        await asyncio.sleep(0)
        
        # Dead connection should be removed
        assert dead_ws not in manager.active_connections["topic"]
        assert alive_ws in manager.active_connections["topic"]
    
    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_topic(self):
        """Test broadcasting to nonexistent topic doesn't raise"""
        manager = ConnectionManager()
        
        # Should not raise
        await manager.broadcast("nonexistent", b"data")
    
    @pytest.mark.asyncio
    async def test_broadcast_resolves_interceptor_futures(self):
        """Test broadcast resolves pending interceptor futures"""
        manager = ConnectionManager()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        manager._interceptors["topic"] = [future]
        
        message = b"test_data"
        await manager.broadcast("topic", message)
        
        assert future.done()
        assert future.result() == message
        assert "topic" not in manager._interceptors
    
    @pytest.mark.asyncio
    async def test_wait_for_next_returns_message(self):
        """Test wait_for_next returns broadcast message"""
        manager = ConnectionManager()
        
        message = b"test_data"
        
        # Broadcast after a short delay
        async def delayed_broadcast():
            await asyncio.sleep(0.1)
            await manager.broadcast("topic", message)
        
        task = asyncio.create_task(delayed_broadcast())
        result = await manager.wait_for_next("topic", timeout=1.0)
        await task
        
        assert result == message
    
    @pytest.mark.asyncio
    async def test_wait_for_next_timeout(self):
        """Test wait_for_next raises TimeoutError"""
        manager = ConnectionManager()
        
        with pytest.raises(asyncio.TimeoutError):
            await manager.wait_for_next("topic", timeout=0.1)
        
        # Interceptor should be cleaned up
        assert "topic" not in manager._interceptors or not manager._interceptors["topic"]
    
    @pytest.mark.asyncio
    async def test_wait_for_next_multiple_waiters(self):
        """Test multiple waiters all receive the message"""
        manager = ConnectionManager()
        
        message = b"test_data"
        
        async def wait_and_check():
            result = await manager.wait_for_next("topic", timeout=1.0)
            return result
        
        # Create multiple waiting tasks
        tasks = [asyncio.create_task(wait_and_check()) for _ in range(3)]
        
        # Give tasks time to register
        await asyncio.sleep(0.1)
        
        # Broadcast
        await manager.broadcast("topic", message)
        
        # All should receive the message
        results = await asyncio.gather(*tasks)
        assert all(r == message for r in results)
    
    @pytest.mark.asyncio
    async def test_broadcast_both_connections_and_interceptors(self):
        """Test broadcast sends to both websockets and interceptors"""
        manager = ConnectionManager()
        
        # Setup websocket connection
        websocket = AsyncMock()
        await manager.connect(websocket, "topic")
        
        # Setup interceptor
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        manager._interceptors["topic"] = [future]
        
        message = b"test_data"
        await manager.broadcast("topic", message)
        # Yield to event loop so fire-and-forget tasks execute
        await asyncio.sleep(0)
        
        # Both should receive
        websocket.send_bytes.assert_called_once_with(message)
        assert future.done()
        assert future.result() == message


class TestSystemTopicsFiltering:
    """Test suite for system topics filtering"""
    
    def test_system_topics_constant_defined(self):
        """Test SYSTEM_TOPICS constant is defined"""
        assert isinstance(SYSTEM_TOPICS, set)
        assert "system_status" in SYSTEM_TOPICS
    
    def test_get_public_topics_empty(self):
        """Test get_public_topics returns empty list when no topics"""
        manager = ConnectionManager()
        
        public_topics = manager.get_public_topics()
        
        assert public_topics == []
    
    def test_get_public_topics_filters_system_topics(self):
        """Test get_public_topics excludes system topics"""
        manager = ConnectionManager()
        
        # Register both system and public topics
        manager.register_topic("system_status")
        manager.register_topic("sensor1_raw_points")
        manager.register_topic("sensor1_processed_points")
        
        public_topics = manager.get_public_topics()
        
        # System topic should be filtered out
        assert "system_status" not in public_topics
        assert "sensor1_raw_points" in public_topics
        assert "sensor1_processed_points" in public_topics
    
    def test_get_public_topics_returns_sorted(self):
        """Test get_public_topics returns sorted list"""
        manager = ConnectionManager()
        
        # Register in random order
        manager.register_topic("zebra_points")
        manager.register_topic("alpha_points")
        manager.register_topic("beta_points")
        
        public_topics = manager.get_public_topics()
        
        assert public_topics == ["alpha_points", "beta_points", "zebra_points"]
    
    def test_get_public_topics_only_system_topics(self):
        """Test get_public_topics returns empty when only system topics"""
        manager = ConnectionManager()
        
        # Register only system topics
        for topic in SYSTEM_TOPICS:
            manager.register_topic(topic)
        
        public_topics = manager.get_public_topics()
        
        assert public_topics == []
    
    def test_get_public_topics_mixed(self):
        """Test get_public_topics with mix of system and public topics"""
        manager = ConnectionManager()
        
        # Register mix of topics
        manager.register_topic("system_status")
        manager.register_topic("lidar1_raw_points")
        manager.register_topic("lidar2_raw_points")
        manager.register_topic("fused_points")
        
        public_topics = manager.get_public_topics()
        
        # Should only include public topics
        assert len(public_topics) == 3
        assert "system_status" not in public_topics
        assert all(t in public_topics for t in ["lidar1_raw_points", "lidar2_raw_points", "fused_points"])


class TestUnregisterTopic:
    """Test suite for async unregister_topic functionality"""
    
    @pytest.mark.asyncio
    async def test_unregister_topic_closes_websocket_connections(self):
        """Test unregister_topic closes WebSocket connections with 1001 code"""
        manager = ConnectionManager()
        manager.register_topic("test_topic")
        
        # Add two mock WebSocket objects
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        manager.active_connections["test_topic"] = [ws1, ws2]
        
        await manager.unregister_topic("test_topic")
        
        # Assert close called with 1001 for each WebSocket
        ws1.close.assert_called_once_with(code=1001)
        ws2.close.assert_called_once_with(code=1001)
        
        # Assert topic is absent from active_connections
        assert "test_topic" not in manager.active_connections
    
    @pytest.mark.asyncio
    async def test_unregister_topic_cancels_pending_futures(self):
        """Test unregister_topic cancels pending interceptor futures"""
        manager = ConnectionManager()
        manager.register_topic("test_topic")
        
        # Add two futures to interceptors
        loop = asyncio.get_running_loop()
        future1 = loop.create_future()
        future2 = loop.create_future()
        manager._interceptors["test_topic"] = [future1, future2]
        
        await manager.unregister_topic("test_topic")
        
        # Assert both futures are cancelled
        assert future1.cancelled()
        assert future2.cancelled()
        
        # Assert topic is absent from interceptors
        assert "test_topic" not in manager._interceptors
    
    @pytest.mark.asyncio
    async def test_unregister_topic_idempotent_on_missing_topic(self):
        """Test unregister_topic doesn't raise on non-existent topic"""
        manager = ConnectionManager()
        
        # Should not raise any exception
        await manager.unregister_topic("does_not_exist")
    
    @pytest.mark.asyncio
    async def test_unregister_topic_with_already_cancelled_future(self):
        """Test unregister_topic handles pre-cancelled futures gracefully"""
        manager = ConnectionManager()
        manager.register_topic("test_topic")
        
        # Add a pre-cancelled future
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        future.cancel()
        manager._interceptors["test_topic"] = [future]
        
        # Should not raise any exception
        await manager.unregister_topic("test_topic")
    
    @pytest.mark.asyncio
    async def test_unregister_topic_ws_close_error_does_not_abort_others(self):
        """Test that one failed WebSocket close doesn't prevent others from closing"""
        manager = ConnectionManager()
        manager.register_topic("test_topic")
        
        # Add two WebSocket mocks where first raises RuntimeError on close
        ws1 = AsyncMock()
        ws1.close.side_effect = RuntimeError("Connection already closed")
        ws2 = AsyncMock()
        
        manager.active_connections["test_topic"] = [ws1, ws2]
        
        await manager.unregister_topic("test_topic")
        
        # Both close methods should have been called
        ws1.close.assert_called_once_with(code=1001)
        ws2.close.assert_called_once_with(code=1001)
        
        # Topic should still be cleaned up
        assert "test_topic" not in manager.active_connections
