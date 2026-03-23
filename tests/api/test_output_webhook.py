"""
API integration tests for Output Node webhook configuration endpoints.

Tests: GET /nodes/{node_id}/webhook and PATCH /nodes/{node_id}/webhook

TDD: Tests written before implementation to drive development.
Follows the same pattern as tests/api/test_flow_control_api.py.
"""
import pytest
from unittest.mock import patch, MagicMock, Mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_output_node(client, node_id: str = "out-abc123") -> dict:
    """Helper: persist an output_node via the DAG save endpoint and return its data."""
    payload = {
        "base_version": 0,
        "nodes": [
            {
                "id": node_id,
                "name": "My Output",
                "type": "output_node",
                "category": "flow_control",
                "enabled": True,
                "visible": False,
                "config": {},
                "x": 300.0,
                "y": 150.0,
            }
        ],
        "edges": [],
    }
    resp = client.put("/api/v1/dag/config", json=payload)
    assert resp.status_code == 200, f"Failed to create node: {resp.text}"
    return resp.json()


def _create_non_output_node(client, node_id: str = "sensor-xyz") -> dict:
    """Helper: persist a non-output_node type."""
    payload = {
        "base_version": 0,
        "nodes": [
            {
                "id": node_id,
                "name": "My Sensor",
                "type": "sensor",
                "category": "lidar",
                "enabled": True,
                "visible": True,
                "config": {},
                "x": 100.0,
                "y": 100.0,
            }
        ],
        "edges": [],
    }
    resp = client.put("/api/v1/dag/config", json=payload)
    assert resp.status_code == 200, f"Failed to create node: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# B6.3 — GET /nodes/{node_id}/webhook
# ---------------------------------------------------------------------------

class TestGetWebhookConfig:
    """Tests for GET /api/v1/nodes/{node_id}/webhook."""

    def test_get_webhook_config_returns_defaults_for_new_node(self, client):
        """Fresh output_node returns default webhook config."""
        _create_output_node(client, "out-fresh-1")

        resp = client.get("/api/v1/nodes/out-fresh-1/webhook")

        assert resp.status_code == 200
        data = resp.json()
        assert data["webhook_enabled"] is False
        assert data["webhook_url"] == ""
        assert data["webhook_auth_type"] == "none"
        assert data["webhook_auth_token"] is None
        assert data["webhook_auth_username"] is None
        assert data["webhook_auth_password"] is None
        assert data["webhook_auth_key_name"] == "X-API-Key"
        assert data["webhook_auth_key_value"] is None

    def test_get_webhook_config_unknown_node_returns_404(self, client):
        """Non-existent node returns HTTP 404."""
        resp = client.get("/api/v1/nodes/does-not-exist/webhook")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_webhook_config_wrong_node_type_returns_400(self, client):
        """Node that is not output_node type returns HTTP 400."""
        _create_non_output_node(client, "sensor-wrong-type")

        resp = client.get("/api/v1/nodes/sensor-wrong-type/webhook")

        assert resp.status_code == 400
        assert "output_node" in resp.json()["detail"]

    def test_get_webhook_config_returns_existing_config(self, client):
        """If webhook config was previously set, GET reflects it."""
        _create_output_node(client, "out-configured")

        # First PATCH to configure it
        patch_payload = {
            "webhook_enabled": True,
            "webhook_url": "https://hooks.example.com/endpoint",
            "webhook_auth_type": "bearer",
            "webhook_auth_token": "token-123",
        }
        patch_resp = client.patch(
            "/api/v1/nodes/out-configured/webhook", json=patch_payload
        )
        assert patch_resp.status_code == 200

        # Now GET should return the configured values
        get_resp = client.get("/api/v1/nodes/out-configured/webhook")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["webhook_enabled"] is True
        assert data["webhook_url"] == "https://hooks.example.com/endpoint"
        assert data["webhook_auth_type"] == "bearer"
        assert data["webhook_auth_token"] == "token-123"


# ---------------------------------------------------------------------------
# B6.3 — PATCH /nodes/{node_id}/webhook
# ---------------------------------------------------------------------------

class TestPatchWebhookConfig:
    """Tests for PATCH /api/v1/nodes/{node_id}/webhook."""

    def test_patch_webhook_config_returns_200(self, client):
        """Successful PATCH returns HTTP 200."""
        _create_output_node(client, "out-patch-200")

        payload = {
            "webhook_enabled": True,
            "webhook_url": "https://api.example.com/webhook",
            "webhook_auth_type": "none",
        }
        resp = client.patch("/api/v1/nodes/out-patch-200/webhook", json=payload)
        assert resp.status_code == 200

    def test_patch_webhook_config_response_body(self, client):
        """PATCH response contains status='ok' and correct node_id."""
        _create_output_node(client, "out-patch-body")

        payload = {
            "webhook_enabled": False,
            "webhook_url": None,
            "webhook_auth_type": "none",
        }
        resp = client.patch("/api/v1/nodes/out-patch-body/webhook", json=payload)
        data = resp.json()
        assert data["status"] == "ok"
        assert data["node_id"] == "out-patch-body"

    def test_patch_webhook_config_persists(self, client):
        """PATCH config is retrievable via GET."""
        _create_output_node(client, "out-persist")

        patch_payload = {
            "webhook_enabled": True,
            "webhook_url": "https://hooks.example.com/my-endpoint",
            "webhook_auth_type": "api_key",
            "webhook_auth_key_name": "X-My-Key",
            "webhook_auth_key_value": "abc-def",
        }
        client.patch("/api/v1/nodes/out-persist/webhook", json=patch_payload)

        get_resp = client.get("/api/v1/nodes/out-persist/webhook")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["webhook_enabled"] is True
        assert data["webhook_url"] == "https://hooks.example.com/my-endpoint"
        assert data["webhook_auth_type"] == "api_key"
        assert data["webhook_auth_key_name"] == "X-My-Key"
        assert data["webhook_auth_key_value"] == "abc-def"

    def test_patch_webhook_config_invalid_url_returns_422(self, client):
        """webhook_enabled=True with invalid URL returns 422 from Pydantic validation."""
        _create_output_node(client, "out-invalid-url")

        payload = {
            "webhook_enabled": True,
            "webhook_url": "not-a-valid-url",
            "webhook_auth_type": "none",
        }
        resp = client.patch("/api/v1/nodes/out-invalid-url/webhook", json=payload)
        # Pydantic model_validator raises ValueError → FastAPI returns 422
        assert resp.status_code == 422

    def test_patch_webhook_config_enabled_empty_url_returns_422(self, client):
        """webhook_enabled=True with empty URL returns 422 from Pydantic validation."""
        _create_output_node(client, "out-empty-url")

        payload = {
            "webhook_enabled": True,
            "webhook_url": "",
            "webhook_auth_type": "none",
        }
        resp = client.patch("/api/v1/nodes/out-empty-url/webhook", json=payload)
        assert resp.status_code == 422

    def test_patch_webhook_config_unknown_node_returns_404(self, client):
        """PATCH on non-existent node returns HTTP 404."""
        payload = {
            "webhook_enabled": False,
            "webhook_url": None,
            "webhook_auth_type": "none",
        }
        resp = client.patch("/api/v1/nodes/ghost-node-id/webhook", json=payload)
        assert resp.status_code == 404

    def test_patch_webhook_config_wrong_node_type_returns_400(self, client):
        """PATCH on non-output_node type returns HTTP 400."""
        _create_non_output_node(client, "sensor-wrong-patch")

        payload = {
            "webhook_enabled": False,
            "webhook_url": None,
            "webhook_auth_type": "none",
        }
        resp = client.patch("/api/v1/nodes/sensor-wrong-patch/webhook", json=payload)
        assert resp.status_code == 400
        assert "output_node" in resp.json()["detail"]

    def test_patch_webhook_config_disabled_does_not_require_url(self, client):
        """webhook_enabled=False with no URL is valid."""
        _create_output_node(client, "out-disabled-no-url")

        payload = {
            "webhook_enabled": False,
            "webhook_url": None,
            "webhook_auth_type": "none",
        }
        resp = client.patch("/api/v1/nodes/out-disabled-no-url/webhook", json=payload)
        assert resp.status_code == 200

    def test_patch_preserves_non_webhook_config_fields(self, client):
        """PATCH only merges webhook fields; other config fields are preserved."""
        # Create node with some custom config fields
        payload = {
            "base_version": 0,
            "nodes": [
                {
                    "id": "out-preserve-config",
                    "name": "My Output",
                    "type": "output_node",
                    "category": "flow_control",
                    "enabled": True,
                    "visible": False,
                    "config": {"some_other_field": "should_remain"},
                    "x": 100.0,
                    "y": 100.0,
                }
            ],
            "edges": [],
        }
        client.put("/api/v1/dag/config", json=payload)

        # PATCH webhook config
        client.patch(
            "/api/v1/nodes/out-preserve-config/webhook",
            json={"webhook_enabled": False, "webhook_auth_type": "none"},
        )

        # Verify other config field is still present
        from app.repositories import NodeRepository
        repo = NodeRepository()
        node = repo.get_by_id("out-preserve-config")
        assert node is not None
        assert node["config"].get("some_other_field") == "should_remain"

    def test_patch_webhook_config_hot_reloads_running_node(self, client):
        """PATCH calls _rebuild_webhook on a running node instance."""
        _create_output_node(client, "out-hot-reload")

        mock_node = Mock()
        mock_node._rebuild_webhook = Mock()

        patch_payload = {
            "webhook_enabled": True,
            "webhook_url": "https://example.com/hook",
            "webhook_auth_type": "none",
        }

        with patch("app.api.v1.output.service.node_manager") as mock_nm:
            mock_nm.nodes.get.return_value = mock_node
            resp = client.patch(
                "/api/v1/nodes/out-hot-reload/webhook", json=patch_payload
            )

        assert resp.status_code == 200
        mock_node._rebuild_webhook.assert_called_once()

    def test_patch_webhook_config_bearer_auth(self, client):
        """PATCH with bearer auth type persists correctly."""
        _create_output_node(client, "out-bearer")

        payload = {
            "webhook_enabled": True,
            "webhook_url": "https://api.example.com/webhook",
            "webhook_auth_type": "bearer",
            "webhook_auth_token": "my-secret-token",
        }
        resp = client.patch("/api/v1/nodes/out-bearer/webhook", json=payload)
        assert resp.status_code == 200

        get_resp = client.get("/api/v1/nodes/out-bearer/webhook")
        data = get_resp.json()
        assert data["webhook_auth_type"] == "bearer"
        assert data["webhook_auth_token"] == "my-secret-token"

    def test_patch_webhook_config_basic_auth(self, client):
        """PATCH with basic auth type persists correctly."""
        _create_output_node(client, "out-basic")

        payload = {
            "webhook_enabled": True,
            "webhook_url": "https://api.example.com/webhook",
            "webhook_auth_type": "basic",
            "webhook_auth_username": "user",
            "webhook_auth_password": "pass",
        }
        resp = client.patch("/api/v1/nodes/out-basic/webhook", json=payload)
        assert resp.status_code == 200

        get_resp = client.get("/api/v1/nodes/out-basic/webhook")
        data = get_resp.json()
        assert data["webhook_auth_type"] == "basic"
        assert data["webhook_auth_username"] == "user"
        assert data["webhook_auth_password"] == "pass"

    def test_patch_invalid_auth_type_returns_422(self, client):
        """Unknown auth_type value returns 422 (Pydantic Literal validation)."""
        _create_output_node(client, "out-bad-auth")

        payload = {
            "webhook_enabled": True,
            "webhook_url": "https://api.example.com/webhook",
            "webhook_auth_type": "oauth2",  # Not in Literal enum
        }
        resp = client.patch("/api/v1/nodes/out-bad-auth/webhook", json=payload)
        assert resp.status_code == 422
