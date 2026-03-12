"""Tests for node visibility API endpoints and schemas."""

import pytest
import json
from fastapi.testclient import TestClient


class TestNodeVisibilityAPISchemas:
    """Test Pydantic schema changes for visibility support."""
    
    def test_node_record_includes_visible_field(self):
        """Test that NodeRecord schema includes visible field."""
        from app.api.v1.schemas.nodes import NodeRecord
        
        # Test creating NodeRecord with visible field
        node_data = {
            "id": "test_node_id",
            "name": "Test Node",
            "type": "sensor", 
            "category": "sensor",
            "enabled": True,
            "visible": False,
            "config": {"test": "config"},
            "x": 100.0,
            "y": 200.0
        }
        
        node_record = NodeRecord(**node_data)
        assert hasattr(node_record, 'visible')
        assert node_record.visible is False
    
    def test_node_record_visible_defaults_true(self):
        """Test that NodeRecord visible field defaults to True."""
        from app.api.v1.schemas.nodes import NodeRecord
        
        node_data = {
            "id": "test_node_id",
            "name": "Test Node",
            "type": "sensor",
            "category": "sensor", 
            "enabled": True,
            # visible not provided
            "config": {},
            "x": 100.0,
            "y": 200.0
        }
        
        node_record = NodeRecord(**node_data)
        assert node_record.visible is True
    
    def test_node_status_item_includes_visible_field(self):
        """Test that NodeStatusItem schema includes visible field."""
        from app.api.v1.schemas.nodes import NodeStatusItem
        
        status_data = {
            "id": "test_node_id",
            "name": "Test Node",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": False,  # Should support visible field
            "running": True,
            "topic": None,  # Should be None when visible=False
            "last_error": None,
            "throttle_ms": 0.0,
            "throttled_count": 0
        }
        
        status_item = NodeStatusItem(**status_data)
        assert hasattr(status_item, 'visible')
        assert status_item.visible is False
        assert status_item.topic is None
    
    def test_node_visibility_toggle_schema(self):
        """Test NodeVisibilityToggle DTO schema."""
        from app.api.v1.nodes.service import NodeVisibilityToggle
        
        # Test valid toggle
        toggle_data = {"visible": False}
        toggle = NodeVisibilityToggle(**toggle_data)
        assert toggle.visible is False
        
        # Test required field validation
        with pytest.raises(ValueError):
            NodeVisibilityToggle()  # Missing required visible field


class TestNodeVisibilityAPIEndpoints:
    """Test API endpoints for node visibility functionality."""
    
    @pytest.fixture
    def test_client(self, tmp_path, monkeypatch):
        """Create test client with visibility support."""
        db_file = tmp_path / "test_api_visibility.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

        from app.db.migrate import ensure_schema
        from app.db.session import init_engine

        engine = init_engine()
        ensure_schema(engine)

        from app.app import app
        return TestClient(app)
    
    def test_get_nodes_includes_visible_field(self, test_client):
        """Test GET /api/v1/nodes includes visible field."""
        # Create a test node with visibility
        node_data = {
            "name": "API Test Node",
            "type": "sensor",
            "category": "sensor", 
            "enabled": True,
            "visible": False,
            "config": {}
        }
        
        # Create node
        create_response = test_client.post("/api/v1/nodes", json=node_data)
        assert create_response.status_code == 200
        node_id = create_response.json()["id"]
        
        # List nodes
        list_response = test_client.get("/api/v1/nodes")
        assert list_response.status_code == 200
        
        nodes = list_response.json()
        test_node = next(n for n in nodes if n["id"] == node_id)
        assert "visible" in test_node
        assert test_node["visible"] is False
    
    def test_get_single_node_includes_visible_field(self, test_client):
        """Test GET /api/v1/nodes/{node_id} includes visible field."""
        # Create node
        node_data = {
            "name": "Single Node Test",
            "type": "sensor",
            "category": "sensor",
            "enabled": True, 
            "visible": True,
            "config": {}
        }
        
        create_response = test_client.post("/api/v1/nodes", json=node_data)
        node_id = create_response.json()["id"]
        
        # Get single node
        get_response = test_client.get(f"/api/v1/nodes/{node_id}")
        assert get_response.status_code == 200
        
        node = get_response.json()
        assert "visible" in node
        assert node["visible"] is True
    
    def test_post_nodes_accepts_visible_field(self, test_client):
        """Test POST /api/v1/nodes accepts visible in request."""
        node_data = {
            "name": "Create With Visible",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": False,  # Explicitly set to False
            "config": {"test": "value"}
        }
        
        response = test_client.post("/api/v1/nodes", json=node_data)
        assert response.status_code == 200
        
        # Verify it was stored correctly
        node_id = response.json()["id"]
        get_response = test_client.get(f"/api/v1/nodes/{node_id}")
        node = get_response.json()
        assert node["visible"] is False
    
    def test_put_node_visible_endpoint_exists(self, test_client):
        """Test PUT /api/v1/nodes/{node_id}/visible endpoint."""
        # Create a node first
        node_data = {
            "name": "Toggle Test Node",
            "type": "sensor", 
            "category": "sensor",
            "enabled": True,
            "visible": True,
            "config": {}
        }
        
        create_response = test_client.post("/api/v1/nodes", json=node_data)
        node_id = create_response.json()["id"]
        
        # Toggle visibility to False
        toggle_data = {"visible": False}
        put_response = test_client.put(f"/api/v1/nodes/{node_id}/visible", json=toggle_data)
        assert put_response.status_code == 200
        assert put_response.json() == {"status": "success"}
        
        # Verify change took effect
        get_response = test_client.get(f"/api/v1/nodes/{node_id}")
        node = get_response.json()
        assert node["visible"] is False
    
    def test_put_node_visible_toggle_back_to_true(self, test_client):
        """Test PUT /api/v1/nodes/{node_id}/visible can toggle back to visible."""
        # Create invisible node
        node_data = {
            "name": "Toggle Back Test",
            "type": "sensor",
            "category": "sensor", 
            "enabled": True,
            "visible": False,
            "config": {}
        }
        
        create_response = test_client.post("/api/v1/nodes", json=node_data)
        node_id = create_response.json()["id"]
        
        # Toggle to visible
        toggle_data = {"visible": True}
        put_response = test_client.put(f"/api/v1/nodes/{node_id}/visible", json=toggle_data)
        assert put_response.status_code == 200
        
        # Verify change
        get_response = test_client.get(f"/api/v1/nodes/{node_id}")
        node = get_response.json()
        assert node["visible"] is True
    
    def test_put_node_visible_returns_404_for_missing_node(self, test_client):
        """Test PUT /api/v1/nodes/{node_id}/visible returns 404 for missing node."""
        toggle_data = {"visible": False}
        response = test_client.put("/api/v1/nodes/nonexistent_node_id/visible", json=toggle_data)
        assert response.status_code == 404
        assert "Node not found" in response.json()["detail"]
    
    def test_put_node_visible_validates_request_body(self, test_client):
        """Test PUT /api/v1/nodes/{node_id}/visible validates request body."""
        # Create node first
        node_data = {
            "name": "Validation Test",
            "type": "sensor", 
            "category": "sensor",
            "enabled": True,
            "config": {}
        }
        
        create_response = test_client.post("/api/v1/nodes", json=node_data)
        node_id = create_response.json()["id"]
        
        # Test missing visible field
        invalid_data = {}
        response = test_client.put(f"/api/v1/nodes/{node_id}/visible", json=invalid_data)
        assert response.status_code == 422  # Validation error
        
        # Test invalid visible value
        invalid_data = {"visible": "not_a_boolean"}
        response = test_client.put(f"/api/v1/nodes/{node_id}/visible", json=invalid_data)
        assert response.status_code == 422  # Validation error
    
    def test_get_nodes_status_includes_visible_field(self, test_client):
        """Test GET /api/v1/nodes/status/all includes visible field."""
        # Create a test node
        node_data = {
            "name": "Status Test Node",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": False,
            "config": {}
        }
        
        create_response = test_client.post("/api/v1/nodes", json=node_data)
        node_id = create_response.json()["id"]
        
        # Get status
        status_response = test_client.get("/api/v1/nodes/status/all")
        assert status_response.status_code == 200
        
        status_data = status_response.json()
        test_node_status = next(n for n in status_data["nodes"] if n["id"] == node_id)
        
        assert "visible" in test_node_status
        assert test_node_status["visible"] is False
        # When visible=False, topic should be None
        assert test_node_status["topic"] is None
    
    def test_node_create_update_schema_includes_visible(self):
        """Test NodeCreateUpdate schema includes visible field."""
        from app.api.v1.nodes.service import NodeCreateUpdate
        
        # Test with visible field
        node_data = {
            "name": "Schema Test",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": False,
            "config": {}
        }
        
        create_update = NodeCreateUpdate(**node_data)
        assert hasattr(create_update, 'visible')
        assert create_update.visible is False
        
        # Test default value
        node_data_no_visible = {
            "name": "Schema Test 2",
            "type": "sensor", 
            "category": "sensor",
            "enabled": True,
            "config": {}
        }
        
        create_update_default = NodeCreateUpdate(**node_data_no_visible)
        assert create_update_default.visible is True  # Should default to True


class TestSystemTopicProtection:
    """Test that system topics are protected from visibility changes."""
    
    @pytest.fixture
    def test_client(self, tmp_path, monkeypatch):
        """Create test client."""
        db_file = tmp_path / "test_system_topics.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

        from app.db.migrate import ensure_schema
        from app.db.session import init_engine

        engine = init_engine()
        ensure_schema(engine)

        from app.app import app
        return TestClient(app)
    
    def test_system_topic_protection_placeholder(self, test_client):
        """Placeholder test for system topic protection.
        
        This will be implemented when we have access to SYSTEM_TOPICS constant
        and can create nodes with system topic names.
        """
        # Note: This test is a placeholder since we need to understand
        # how system topics are identified in the current codebase.
        # The actual implementation should:
        # 1. Create a node that would generate a system topic
        # 2. Try to set its visibility to False
        # 3. Expect a 400 Bad Request response
        pass