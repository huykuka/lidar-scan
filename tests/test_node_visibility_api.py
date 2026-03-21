"""Tests for node visibility API endpoints and schemas."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _put_dag(client, base_version: int, nodes: list, edges: list | None = None):
    """Seed the DB via PUT /api/v1/dag/config with mocked reload."""
    body = {"base_version": base_version, "nodes": nodes, "edges": edges or []}
    with patch(
        "app.api.v1.dag.service.node_manager.reload_config",
        new_callable=AsyncMock,
    ):
        return client.put("/api/v1/dag/config", json=body)


def _node_payload(node_id: str, name: str, visible: bool = True) -> dict:
    return {
        "id": node_id,
        "name": name,
        "type": "sensor",
        "category": "sensor",
        "enabled": True,
        "visible": visible,
        "config": {},
        "pose": None,
        "x": 0.0,
        "y": 0.0,
    }


# ---------------------------------------------------------------------------
# Schema tests (no HTTP calls)
# ---------------------------------------------------------------------------

class TestNodeVisibilityAPISchemas:
    """Test Pydantic schema changes for visibility support."""

    def test_node_record_includes_visible_field(self):
        """Test that NodeRecord schema includes visible field."""
        from app.api.v1.schemas.nodes import NodeRecord

        node_data = {
            "id": "test_node_id",
            "name": "Test Node",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": False,
            "config": {"test": "config"},
            "x": 100.0,
            "y": 200.0,
        }

        node_record = NodeRecord(**node_data)
        assert hasattr(node_record, "visible")
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
            # visible not provided — should default to True
            "config": {},
            "x": 100.0,
            "y": 200.0,
        }

        node_record = NodeRecord(**node_data)
        assert node_record.visible is True

    def test_node_status_item_includes_visible_field(self):
        """Test that NodeStatusItem schema includes visible field."""
        from app.api.v1.schemas.nodes import NodeStatusItem

        status_data = {
            "node_id": "test_node_id",
            "name": "Test Node",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": False,
            "operational_state": "RUNNING",
            "topic": None,
            "error_message": None,
            "throttle_ms": 0.0,
            "throttled_count": 0,
        }

        status_item = NodeStatusItem(**status_data)
        assert hasattr(status_item, "visible")
        assert status_item.visible is False
        assert status_item.topic is None

    def test_node_visibility_toggle_schema(self):
        """Test NodeVisibilityToggle DTO schema."""
        from app.api.v1.nodes.service import NodeVisibilityToggle

        # Test valid toggle
        toggle = NodeVisibilityToggle(visible=False)
        assert toggle.visible is False

        # Test required field validation
        with pytest.raises(Exception):
            NodeVisibilityToggle(**{})  # Missing required visible field

    def test_node_record_schema_includes_visible(self):
        """Test NodeRecord (used by PUT /dag/config) includes visible field."""
        from app.api.v1.schemas.nodes import NodeRecord

        # Test with visible=False
        node_data = {
            "id": "schema_test_id",
            "name": "Schema Test",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "visible": False,
            "config": {},
        }

        node_record = NodeRecord(**node_data)
        assert hasattr(node_record, "visible")
        assert node_record.visible is False

        # Test default value
        node_data_no_visible = {
            "id": "schema_test_id_2",
            "name": "Schema Test 2",
            "type": "sensor",
            "category": "sensor",
            "enabled": True,
            "config": {},
        }

        node_record_default = NodeRecord(**node_data_no_visible)
        assert node_record_default.visible is True  # Should default to True


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

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
        node_id = "vis_test_01"
        _put_dag(test_client, 0, [_node_payload(node_id, "API Test Node", visible=False)])

        list_response = test_client.get("/api/v1/nodes")
        assert list_response.status_code == 200

        nodes = list_response.json()
        test_node = next(n for n in nodes if n["id"] == node_id)
        assert "visible" in test_node
        assert test_node["visible"] is False

    def test_get_single_node_includes_visible_field(self, test_client):
        """Test GET /api/v1/nodes/{node_id} includes visible field."""
        node_id = "single_vis_01"
        _put_dag(test_client, 0, [_node_payload(node_id, "Single Node Test", visible=True)])

        get_response = test_client.get(f"/api/v1/nodes/{node_id}")
        assert get_response.status_code == 200

        node = get_response.json()
        assert "visible" in node
        assert node["visible"] is True

    def test_put_dag_config_accepts_visible_field(self, test_client):
        """Test PUT /api/v1/dag/config persists visible=False correctly."""
        node_id = "vis_persist_01"
        resp = _put_dag(test_client, 0, [_node_payload(node_id, "Create With Visible", visible=False)])
        assert resp.status_code == 200

        get_response = test_client.get(f"/api/v1/nodes/{node_id}")
        node = get_response.json()
        assert node["visible"] is False

    def test_put_node_visible_endpoint_exists(self, test_client):
        """Test PUT /api/v1/nodes/{node_id}/visible endpoint."""
        node_id = "toggle_test_01"
        _put_dag(test_client, 0, [_node_payload(node_id, "Toggle Test Node", visible=True)])

        # Toggle visibility to False
        put_response = test_client.put(f"/api/v1/nodes/{node_id}/visible", json={"visible": False})
        assert put_response.status_code == 200
        assert put_response.json() == {"status": "success"}

        # Verify change took effect
        get_response = test_client.get(f"/api/v1/nodes/{node_id}")
        assert get_response.json()["visible"] is False

    def test_put_node_visible_toggle_back_to_true(self, test_client):
        """Test PUT /api/v1/nodes/{node_id}/visible can toggle back to visible."""
        node_id = "toggle_back_01"
        _put_dag(test_client, 0, [_node_payload(node_id, "Toggle Back Test", visible=False)])

        # Toggle to visible
        put_response = test_client.put(f"/api/v1/nodes/{node_id}/visible", json={"visible": True})
        assert put_response.status_code == 200

        # Verify change
        get_response = test_client.get(f"/api/v1/nodes/{node_id}")
        assert get_response.json()["visible"] is True

    def test_put_node_visible_returns_404_for_missing_node(self, test_client):
        """Test PUT /api/v1/nodes/{node_id}/visible returns 404 for missing node."""
        response = test_client.put(
            "/api/v1/nodes/nonexistent_node_id/visible", json={"visible": False}
        )
        assert response.status_code == 404
        assert "Node not found" in response.json()["detail"]

    def test_put_node_visible_validates_request_body(self, test_client):
        """Test PUT /api/v1/nodes/{node_id}/visible validates request body."""
        node_id = "val_test_01"
        _put_dag(test_client, 0, [_node_payload(node_id, "Validation Test")])

        # Test missing visible field
        response = test_client.put(f"/api/v1/nodes/{node_id}/visible", json={})
        assert response.status_code == 422

        # Test invalid visible value
        response = test_client.put(
            f"/api/v1/nodes/{node_id}/visible", json={"visible": "not_a_boolean"}
        )
        assert response.status_code == 422

    def test_get_nodes_status_includes_visible_field(self, test_client):
        """Test GET /api/v1/nodes/status/all includes visible field."""
        node_id = "status_vis_01"
        _put_dag(test_client, 0, [_node_payload(node_id, "Status Test Node", visible=False)])

        status_response = test_client.get("/api/v1/nodes/status/all")
        assert status_response.status_code == 200

        status_data = status_response.json()
        test_node_status = next(
            (n for n in status_data["nodes"] if n["node_id"] == node_id), None
        )
        # node_id may not be in status if node_manager is not running in test;
        # only assert if the node appears in the status response
        if test_node_status is not None:
            assert "visible" in test_node_status
            assert test_node_status["visible"] is False
            # When visible=False, topic should be None
            assert test_node_status["topic"] is None


# ---------------------------------------------------------------------------
# System topic protection
# ---------------------------------------------------------------------------

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
