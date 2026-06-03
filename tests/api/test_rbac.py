"""Tests for @roles_required decorator — 3-tier role hierarchy.

Role hierarchy: service (2) > admin (1) > user (0)
- @roles_required("admin"): allows admin + service (level >= 1)
- @roles_required("service"): allows service only (level == 2)
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
# @roles_required("admin") — DAG config save (PUT /dag/config)
# ---------------------------------------------------------------------------

class TestRolesRequiredAdmin:
    """Endpoints with @roles_required("admin") allow admin + service, block user."""

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
# @roles_required("admin") — node reload (POST /nodes/reload)
# ---------------------------------------------------------------------------

class TestRolesRequiredAdminReload:
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
# @roles_required("service") — node definitions registry
# ---------------------------------------------------------------------------

class TestRolesRequiredService:
    """GET /nodes/definitions/registry uses @roles_required("service")."""

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
# @roles_required("service") — node type toggle
# ---------------------------------------------------------------------------

class TestRolesRequiredServiceToggle:
    """PUT /nodes/definitions/{type}/enabled uses @roles_required("service")."""

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
# Decorator & role hierarchy unit tests
# ---------------------------------------------------------------------------

class TestRolesRequiredDecorator:
    """Verify the decorator itself and role level logic."""

    def test_role_levels_are_ordered(self):
        from app.api.v1.auth.dependencies import ROLE_LEVELS

        assert ROLE_LEVELS["user"] < ROLE_LEVELS["admin"] < ROLE_LEVELS["service"]

    def test_three_default_users_seeded(self, rbac_client):
        token = _get_token(rbac_client, "service")
        resp = rbac_client.get("/api/v1/auth/users", headers=_auth(token))
        assert resp.status_code == 200
        roles = {u["role"] for u in resp.json()}
        assert roles == {"user", "admin", "service"}

    def test_unknown_role_raises_value_error(self):
        from app.api.v1.auth.dependencies import roles_required
        with pytest.raises(ValueError, match="Unknown role"):
            roles_required("superuser")

    def test_empty_roles_raises_value_error(self):
        from app.api.v1.auth.dependencies import roles_required
        with pytest.raises(ValueError, match="at least one role"):
            roles_required()
