"""Tests for role-based access control — 3-tier role hierarchy.

Role hierarchy: service (2) > admin (1) > user (0)
- require_admin: allows admin + service (level >= 1)
- require_service: allows service only (exact match)
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def rbac_client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_rbac.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    from app.db.session import init_engine
    from app.db.migrate import ensure_schema

    engine = init_engine()
    ensure_schema(engine)

    from app.app import app

    return TestClient(app)


def _get_token(client: TestClient, username: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": username})
    assert resp.status_code == 200, f"Login failed for {username}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _put_dag(client, base_version: int, nodes: list, headers: dict):
    body = {"base_version": base_version, "nodes": nodes, "edges": []}
    with patch(
        "app.api.v1.dag.service.node_manager.reload_config",
        new_callable=AsyncMock,
    ):
        return client.put("/api/v1/dag/config", json=body, headers=headers)


# ---------------------------------------------------------------------------
# require_admin guard — DAG config save (PUT /dag/config)
# ---------------------------------------------------------------------------

class TestRequireAdmin:
    """Endpoints guarded by require_admin should allow admin + service, block user."""

    def test_unauthenticated_blocked(self, rbac_client):
        resp = rbac_client.put("/api/v1/dag/config", json={"base_version": 0, "nodes": [], "edges": []})
        assert resp.status_code == 401

    def test_user_role_blocked(self, rbac_client):
        token = _get_token(rbac_client, "user")
        resp = rbac_client.put(
            "/api/v1/dag/config",
            json={"base_version": 0, "nodes": [], "edges": []},
            headers=_auth(token),
        )
        assert resp.status_code == 403
        assert "Admin access required" in resp.json()["detail"]

    def test_admin_role_allowed(self, rbac_client):
        token = _get_token(rbac_client, "admin")
        resp = _put_dag(rbac_client, 0, [], _auth(token))
        assert resp.status_code == 200

    def test_service_role_allowed(self, rbac_client):
        token = _get_token(rbac_client, "service")
        resp = _put_dag(rbac_client, 0, [], _auth(token))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# require_admin guard — node reload (POST /nodes/reload)
# ---------------------------------------------------------------------------

class TestRequireAdminReload:
    def test_reload_blocked_for_user(self, rbac_client):
        token = _get_token(rbac_client, "user")
        resp = rbac_client.post("/api/v1/nodes/reload", headers=_auth(token))
        assert resp.status_code == 403

    def test_reload_allowed_for_admin(self, rbac_client):
        token = _get_token(rbac_client, "admin")
        with patch(
            "app.api.v1.nodes.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = rbac_client.post("/api/v1/nodes/reload", headers=_auth(token))
        assert resp.status_code == 200

    def test_reload_allowed_for_service(self, rbac_client):
        token = _get_token(rbac_client, "service")
        with patch(
            "app.api.v1.nodes.service.node_manager.reload_config",
            new_callable=AsyncMock,
        ):
            resp = rbac_client.post("/api/v1/nodes/reload", headers=_auth(token))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# require_service guard — node definitions registry
# ---------------------------------------------------------------------------

class TestRequireService:
    """GET /nodes/definitions/registry is service-only."""

    def test_registry_blocked_for_unauthenticated(self, rbac_client):
        resp = rbac_client.get("/api/v1/nodes/definitions/registry")
        assert resp.status_code == 401

    def test_registry_blocked_for_user(self, rbac_client):
        token = _get_token(rbac_client, "user")
        resp = rbac_client.get("/api/v1/nodes/definitions/registry", headers=_auth(token))
        assert resp.status_code == 403
        assert "Service access required" in resp.json()["detail"]

    def test_registry_blocked_for_admin(self, rbac_client):
        token = _get_token(rbac_client, "admin")
        resp = rbac_client.get("/api/v1/nodes/definitions/registry", headers=_auth(token))
        assert resp.status_code == 403
        assert "Service access required" in resp.json()["detail"]

    def test_registry_allowed_for_service(self, rbac_client):
        token = _get_token(rbac_client, "service")
        resp = rbac_client.get("/api/v1/nodes/definitions/registry", headers=_auth(token))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# require_service guard — node type toggle
# ---------------------------------------------------------------------------

class TestRequireServiceToggle:
    """PUT /nodes/definitions/{type}/enabled is service-only."""

    def test_toggle_blocked_for_admin(self, rbac_client):
        token = _get_token(rbac_client, "admin")
        resp = rbac_client.put(
            "/api/v1/nodes/definitions/SomeType/enabled",
            json={"enabled": False},
            headers=_auth(token),
        )
        assert resp.status_code == 403

    def test_toggle_blocked_for_user(self, rbac_client):
        token = _get_token(rbac_client, "user")
        resp = rbac_client.put(
            "/api/v1/nodes/definitions/SomeType/enabled",
            json={"enabled": False},
            headers=_auth(token),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Role hierarchy correctness
# ---------------------------------------------------------------------------

class TestRoleHierarchy:
    """Verify the numeric role level logic."""

    def test_role_levels_are_ordered(self):
        from app.api.v1.auth.dependencies import ROLE_LEVELS

        assert ROLE_LEVELS["user"] < ROLE_LEVELS["admin"] < ROLE_LEVELS["service"]

    def test_three_default_users_seeded(self, rbac_client):
        token = _get_token(rbac_client, "service")
        resp = rbac_client.get("/api/v1/auth/users", headers=_auth(token))
        assert resp.status_code == 200
        roles = {u["role"] for u in resp.json()}
        assert roles == {"user", "admin", "service"}
