"""TDD Tests for new selective-reload endpoints (Phase 5).

Tests are written BEFORE the implementation (TDD).
All tests must pass once Phase 5 is implemented.

Endpoints under test:
  POST /api/v1/nodes/{node_id}/reload  → NodeReloadResponse
  GET  /api/v1/nodes/reload/status     → ReloadStatusResponse

Spec: .opencode/plans/node-reload-improvement/api-spec.md §§ 2, 3
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# POST /api/v1/nodes/{node_id}/reload
# ---------------------------------------------------------------------------


class TestPostNodeReload:
    """Tests for POST /api/v1/nodes/{node_id}/reload."""

    def _mock_result(self, node_id="abc123", status="reloaded", duration_ms=73.0, ws_topic="sensor_abc123"):
        """Build a mock SelectiveReloadResult-like object."""
        result = MagicMock()
        result.node_id = node_id
        result.status = status
        result.duration_ms = duration_ms
        result.ws_topic = ws_topic
        result.error_message = None
        result.rolled_back = False
        return result

    def test_post_node_reload_success_200(self, client):
        """POST /nodes/{node_id}/reload must return 200 with NodeReloadResponse when node exists."""
        mock_result = self._mock_result("abc123")

        with patch(
            "app.api.v1.nodes.service.node_manager.nodes",
            {"abc123": MagicMock()},
        ), patch(
            "app.api.v1.nodes.service.node_manager._reload_lock",
        ) as mock_lock, patch(
            "app.api.v1.nodes.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            mock_lock.locked.return_value = False
            resp = client.post("/api/v1/nodes/abc123/reload")

        assert resp.status_code == 200
        data = resp.json()
        assert data["node_id"] == "abc123"
        assert data["status"] == "reloaded"
        assert "duration_ms" in data
        assert "ws_topic" in data

    def test_post_node_reload_404_unknown_node(self, client):
        """POST /nodes/{node_id}/reload must return 404 when node is not in running DAG."""
        with patch(
            "app.api.v1.nodes.service.node_manager.nodes",
            {},  # empty — node not running
        ), patch(
            "app.api.v1.nodes.service.node_manager._reload_lock",
        ) as mock_lock:
            mock_lock.locked.return_value = False
            resp = client.post("/api/v1/nodes/unknown_node/reload")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_post_node_reload_409_lock_held(self, client):
        """POST /nodes/{node_id}/reload must return 409 when reload lock is already held."""
        with patch(
            "app.api.v1.nodes.service.node_manager.nodes",
            {"abc123": MagicMock()},
        ), patch(
            "app.api.v1.nodes.service.node_manager._reload_lock",
        ) as mock_lock:
            mock_lock.locked.return_value = True
            resp = client.post("/api/v1/nodes/abc123/reload")

        assert resp.status_code == 409
        assert "progress" in resp.json()["detail"].lower()

    def test_post_node_reload_500_on_failure_with_rollback(self, client):
        """POST /nodes/{node_id}/reload must return 500 when reload fails and was rolled back."""
        mock_result = self._mock_result(status="error")
        mock_result.error_message = "Address already in use"
        mock_result.rolled_back = True

        with patch(
            "app.api.v1.nodes.service.node_manager.nodes",
            {"abc123": MagicMock()},
        ), patch(
            "app.api.v1.nodes.service.node_manager._reload_lock",
        ) as mock_lock, patch(
            "app.api.v1.nodes.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            mock_lock.locked.return_value = False
            resp = client.post("/api/v1/nodes/abc123/reload")

        assert resp.status_code == 500
        assert "abc123" in resp.json()["detail"]

    def test_post_node_reload_calls_selective_reload_node(self, client):
        """POST /nodes/{node_id}/reload must call node_manager.selective_reload_node with correct ID."""
        mock_result = self._mock_result("mynode")

        with patch(
            "app.api.v1.nodes.service.node_manager.nodes",
            {"mynode": MagicMock()},
        ), patch(
            "app.api.v1.nodes.service.node_manager._reload_lock",
        ) as mock_lock, patch(
            "app.api.v1.nodes.service.node_manager.selective_reload_node",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_reload:
            mock_lock.locked.return_value = False
            client.post("/api/v1/nodes/mynode/reload")

        mock_reload.assert_called_once_with("mynode")


# ---------------------------------------------------------------------------
# GET /api/v1/nodes/reload/status
# ---------------------------------------------------------------------------


class TestGetReloadStatus:
    """Tests for GET /api/v1/nodes/reload/status."""

    def test_get_reload_status_idle(self, client):
        """When no reload is in progress, status must show locked=False and nulls."""
        with patch(
            "app.api.v1.nodes.service.node_manager._reload_lock",
        ) as mock_lock, patch(
            "app.api.v1.nodes.service.node_manager._active_reload_node_id",
            None,
        ):
            mock_lock.locked.return_value = False
            resp = client.get("/api/v1/nodes/reload/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["locked"] is False
        assert data["reload_in_progress"] is False
        assert data["active_reload_node_id"] is None
        assert data["estimated_completion_ms"] is None

    def test_get_reload_status_during_selective_reload(self, client):
        """During selective reload, status must show locked=True and the active node ID."""
        with patch(
            "app.api.v1.nodes.service.node_manager._reload_lock",
        ) as mock_lock, patch(
            "app.api.v1.nodes.service.node_manager",
        ) as mock_mgr:
            mock_lock.locked.return_value = True
            mock_mgr._reload_lock = mock_lock
            mock_mgr._active_reload_node_id = "active_node_123"

            resp = client.get("/api/v1/nodes/reload/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["locked"] is True
        assert data["reload_in_progress"] is True
        assert data["active_reload_node_id"] == "active_node_123"
        assert data["estimated_completion_ms"] == 150  # selective estimate

    def test_get_reload_status_during_full_reload(self, client):
        """During full reload (active_reload_node_id=None), estimated_completion_ms must be 3000."""
        with patch(
            "app.api.v1.nodes.service.node_manager",
        ) as mock_mgr:
            mock_lock = MagicMock()
            mock_lock.locked.return_value = True
            mock_mgr._reload_lock = mock_lock
            mock_mgr._active_reload_node_id = None

            resp = client.get("/api/v1/nodes/reload/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["locked"] is True
        assert data["reload_in_progress"] is True
        assert data["active_reload_node_id"] is None
        assert data["estimated_completion_ms"] == 3000  # full reload estimate

    def test_get_reload_status_response_schema(self, client):
        """Response must always include all required ReloadStatusResponse fields."""
        with patch(
            "app.api.v1.nodes.service.node_manager._reload_lock",
        ) as mock_lock, patch(
            "app.api.v1.nodes.service.node_manager._active_reload_node_id",
            None,
        ):
            mock_lock.locked.return_value = False
            resp = client.get("/api/v1/nodes/reload/status")

        assert resp.status_code == 200
        data = resp.json()
        for field in ("locked", "reload_in_progress", "active_reload_node_id", "estimated_completion_ms"):
            assert field in data, f"Missing field: {field}"
