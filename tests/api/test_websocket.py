"""
Tests for WebSocket API endpoints
"""
import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from app.app import app


class TestWebSocketTopicsEndpoint:
    """Test suite for /api/v1/topics endpoint"""
    
    def test_list_topics_empty(self):
        """Test /topics returns empty list when no topics"""
        with patch('app.api.v1.websocket.manager') as mock_manager:
            mock_manager.get_public_topics.return_value = []
            
            client = TestClient(app)
            response = client.get("/api/v1/topics")
            
            assert response.status_code == 200
            data = response.json()
            assert "topics" in data
            assert data["topics"] == []
            assert "description" in data
    
    def test_list_topics_with_lidar_topics(self):
        """Test /topics returns lidar topics"""
        with patch('app.api.v1.websocket.manager') as mock_manager:
            mock_manager.get_public_topics.return_value = [
                "sensor1_raw_points",
                "sensor1_processed_points"
            ]
            
            client = TestClient(app)
            response = client.get("/api/v1/topics")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["topics"]) == 2
            assert "sensor1_raw_points" in data["topics"]
            assert "sensor1_processed_points" in data["topics"]
    
    def test_list_topics_excludes_system_topics(self):
        """Test /topics does not return system topics"""
        with patch('app.api.v1.websocket.manager') as mock_manager:
            # Manager should already filter, but verify endpoint calls right method
            mock_manager.get_public_topics.return_value = [
                "sensor1_raw_points",
                "fused_points"
            ]
            
            client = TestClient(app)
            response = client.get("/api/v1/topics")
            
            assert response.status_code == 200
            data = response.json()
            assert "system_status" not in data["topics"]
            assert "sensor1_raw_points" in data["topics"]
            
            # Verify it called get_public_topics (not active_connections directly)
            mock_manager.get_public_topics.assert_called_once()
    
    def test_list_topics_includes_description(self):
        """Test /topics includes topic descriptions"""
        with patch('app.api.v1.websocket.manager') as mock_manager:
            mock_manager.get_public_topics.return_value = []
            
            client = TestClient(app)
            response = client.get("/api/v1/topics")
            
            assert response.status_code == 200
            data = response.json()
            assert "description" in data
            assert isinstance(data["description"], dict)
            assert "raw_points" in data["description"]
            assert "processed_points" in data["description"]


class TestWebSocketStatusConnection:
    """Test suite for WebSocket status streaming"""
    
    @pytest.mark.asyncio
    async def test_websocket_status_endpoint_exists(self):
        """Test /ws/system_status endpoint exists"""
        # Note: Full WebSocket testing requires more complex setup
        # This test just verifies the endpoint is defined
        from app.api.v1.websocket import router
        
        # Check route exists
        routes = [route.path for route in router.routes]
        assert "/ws/{topic}" in routes
    
    def test_system_status_topic_is_valid(self):
        """Test system_status is a valid WebSocket topic"""
        # Verify the topic can be connected to (endpoint accepts it)
        from app.services.websocket.manager import manager
        
        # Register the topic (simulating what broadcaster does)
        manager.register_topic("system_status")
        
        # Verify it's registered
        assert "system_status" in manager.active_connections
    
    def test_lidar_topics_are_valid(self):
        """Test lidar topics can be registered"""
        from app.services.websocket.manager import manager
        
        # Register lidar topics
        manager.register_topic("sensor1_raw_points")
        manager.register_topic("sensor1_processed_points")
        
        # Verify they're registered
        assert "sensor1_raw_points" in manager.active_connections
        assert "sensor1_processed_points" in manager.active_connections
