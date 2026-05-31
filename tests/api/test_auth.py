"""Tests for auth endpoints — login, token validation, and /me."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """TestClient with a fresh DB that seeds default users."""
    db_file = tmp_path / "test_auth.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    from app.db.session import init_engine
    from app.db.migrate import ensure_schema

    engine = init_engine()
    ensure_schema(engine)

    from app.app import app

    return TestClient(app)


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Login endpoint
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_valid_user(self, auth_client):
        resp = _login(auth_client, "user", "user")
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["user"]["username"] == "user"
        assert body["user"]["role"] == "user"

    def test_login_valid_admin(self, auth_client):
        resp = _login(auth_client, "admin", "admin")
        assert resp.status_code == 200
        assert resp.json()["user"]["role"] == "admin"

    def test_login_valid_service(self, auth_client):
        resp = _login(auth_client, "service", "service")
        assert resp.status_code == 200
        assert resp.json()["user"]["role"] == "service"

    def test_login_wrong_password(self, auth_client):
        resp = _login(auth_client, "admin", "wrong")
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]

    def test_login_nonexistent_user(self, auth_client):
        resp = _login(auth_client, "nobody", "pass")
        assert resp.status_code == 401

    def test_login_empty_body(self, auth_client):
        resp = auth_client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422

    def test_login_returns_bearer_token_type(self, auth_client):
        resp = _login(auth_client, "user", "user")
        assert resp.json()["token_type"] == "bearer"


# ---------------------------------------------------------------------------
# /auth/me endpoint
# ---------------------------------------------------------------------------

class TestMe:
    def test_me_without_token(self, auth_client):
        resp = auth_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self, auth_client):
        resp = auth_client.get("/api/v1/auth/me", headers=_auth_header("garbage"))
        assert resp.status_code == 401

    def test_me_with_valid_token(self, auth_client):
        token = _login(auth_client, "admin", "admin").json()["access_token"]
        resp = auth_client.get("/api/v1/auth/me", headers=_auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "admin"
        assert body["role"] == "admin"

    def test_me_returns_correct_role_for_each_user(self, auth_client):
        for username, role in [("user", "user"), ("admin", "admin"), ("service", "service")]:
            token = _login(auth_client, username, username).json()["access_token"]
            resp = auth_client.get("/api/v1/auth/me", headers=_auth_header(token))
            assert resp.json()["role"] == role, f"Expected role '{role}' for user '{username}'"


# ---------------------------------------------------------------------------
# User management endpoints (admin-only)
# ---------------------------------------------------------------------------

class TestUserManagement:
    def test_list_users_requires_auth(self, auth_client):
        resp = auth_client.get("/api/v1/auth/users")
        assert resp.status_code == 401

    def test_list_users_as_admin(self, auth_client):
        token = _login(auth_client, "admin", "admin").json()["access_token"]
        resp = auth_client.get("/api/v1/auth/users", headers=_auth_header(token))
        assert resp.status_code == 200
        users = resp.json()
        usernames = {u["username"] for u in users}
        assert {"user", "admin", "service"} <= usernames

    def test_list_users_blocked_for_user_role(self, auth_client):
        token = _login(auth_client, "user", "user").json()["access_token"]
        resp = auth_client.get("/api/v1/auth/users", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_create_user_as_admin(self, auth_client):
        token = _login(auth_client, "admin", "admin").json()["access_token"]
        resp = auth_client.post(
            "/api/v1/auth/users",
            json={"username": "newuser", "password": "pass123", "role": "user"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 201
        assert resp.json()["username"] == "newuser"

    def test_create_duplicate_user_returns_409(self, auth_client):
        token = _login(auth_client, "admin", "admin").json()["access_token"]
        auth_client.post(
            "/api/v1/auth/users",
            json={"username": "dup", "password": "pass", "role": "user"},
            headers=_auth_header(token),
        )
        resp = auth_client.post(
            "/api/v1/auth/users",
            json={"username": "dup", "password": "pass", "role": "user"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 409

    def test_delete_own_account_returns_400(self, auth_client):
        token = _login(auth_client, "admin", "admin").json()["access_token"]
        me = auth_client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
        resp = auth_client.delete(f"/api/v1/auth/users/{me['id']}", headers=_auth_header(token))
        assert resp.status_code == 400
