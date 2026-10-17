"""App settings API: persistence, validation, secrets, and retention sweep."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.db.migrate import _seed_default_users


@pytest.fixture
def admin(client):
    _seed_default_users()
    res = client.post("/api/v1/auth/login", json={"username": "service", "password": "service"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY", "simple passphrase")


@pytest.fixture(autouse=True)
def restore_settings():
    snapshot = {k: getattr(settings, k) for k in (
        "STORAGE_AUTO_UPLOAD", "S3_BUCKET", "S3_SECRET_ACCESS_KEY", "S3_ACCESS_KEY_ID", "RECORDINGS_RETENTION_DAYS")}
    yield
    for k, v in snapshot.items():
        setattr(settings, k, v)


def _find(data, key):
    return next(s for c in data["categories"] for s in c["settings"] if s["key"] == key)


def test_requires_service_role(client, admin):
    assert client.get("/api/v1/app-settings").status_code == 401
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/api/v1/app-settings", headers=headers).status_code == 403
    assert client.put("/api/v1/app-settings", headers=headers, json={}).status_code == 403


def test_update_persists_and_applies(client, admin):
    res = client.put("/api/v1/app-settings", headers=admin,
                     json={"values": {"S3_BUCKET": " my-bucket ", "STORAGE_AUTO_UPLOAD": True}})
    assert res.status_code == 200
    assert settings.S3_BUCKET == "my-bucket"
    assert settings.STORAGE_AUTO_UPLOAD is True
    assert _find(res.json(), "S3_BUCKET")["modified"] is True


def test_validation_errors(client, admin):
    res = client.put("/api/v1/app-settings", headers=admin, json={"values": {
        "RECORDINGS_RETENTION_DAYS": -1, "STORAGE_BACKEND": "ftp", "NOPE": 1}})
    assert res.status_code == 422
    assert set(res.json()["detail"]) == {"RECORDINGS_RETENTION_DAYS", "STORAGE_BACKEND", "NOPE"}


def test_secret_never_returned_and_kept_when_omitted(client, admin):
    client.put("/api/v1/app-settings", headers=admin, json={"values": {"S3_SECRET_ACCESS_KEY": "s3cr3t"}})
    body = client.put("/api/v1/app-settings", headers=admin, json={"values": {"S3_BUCKET": "b"}}).json()
    item = _find(body, "S3_SECRET_ACCESS_KEY")
    assert item["value"] is None and item["is_set"] is True
    assert settings.S3_SECRET_ACCESS_KEY == "s3cr3t"
    assert "s3cr3t" not in client.get("/api/v1/app-settings", headers=admin).text


def test_reset_restores_default(client, admin):
    default = settings.RECORDINGS_RETENTION_DAYS
    client.put("/api/v1/app-settings", headers=admin, json={"values": {"RECORDINGS_RETENTION_DAYS": 30}})
    assert settings.RECORDINGS_RETENTION_DAYS == 30
    client.put("/api/v1/app-settings", headers=admin, json={"reset": ["RECORDINGS_RETENTION_DAYS"]})
    assert settings.RECORDINGS_RETENTION_DAYS == default


def test_retention_sweep(client, tmp_path, monkeypatch):
    from app.db.models import get_db
    from app.repositories.recordings_orm import RecordingRepository
    from app.services.retention import sweep_recordings_sync

    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    db = next(get_db())
    repo = RecordingRepository(db)
    files = {}
    for rid, meta in (("uploaded", {"blob_upload": {"key": "k"}}), ("local", {})):
        f = tmp_path / f"{rid}.mcap"
        f.write_bytes(b"x")
        files[rid] = f
        repo.create({"id": rid, "name": rid, "node_id": "n", "sensor_id": None, "file_path": str(f),
                     "file_size_bytes": 1, "frame_count": 1, "duration_seconds": 1.0,
                     "recording_timestamp": old, "metadata": meta, "created_at": old})

    monkeypatch.setattr(settings, "RECORDINGS_RETENTION_DAYS", 0)
    assert sweep_recordings_sync() == 0

    monkeypatch.setattr(settings, "RECORDINGS_RETENTION_DAYS", 30)
    monkeypatch.setattr(settings, "RETENTION_ONLY_UPLOADED", True)
    assert sweep_recordings_sync() == 1
    assert not files["uploaded"].exists() and files["local"].exists()

    monkeypatch.setattr(settings, "RETENTION_ONLY_UPLOADED", False)
    assert sweep_recordings_sync() == 1
    assert not files["local"].exists()
    db.close()


def test_secret_encrypted_at_rest_and_restored_on_load(client, admin):
    from app.db.models import AppSettingModel
    from app.db.session import SessionLocal
    from app.services.app_settings import load_overrides

    client.put("/api/v1/app-settings", headers=admin, json={"values": {"S3_SECRET_ACCESS_KEY": "s3cr3t"}})
    db = SessionLocal()
    stored = db.get(AppSettingModel, "S3_SECRET_ACCESS_KEY").value_json
    db.close()
    assert "s3cr3t" not in stored and "enc:v1:" in stored

    settings.S3_SECRET_ACCESS_KEY = ""
    load_overrides()
    assert settings.S3_SECRET_ACCESS_KEY == "s3cr3t"


def test_wrong_key_does_not_crash_or_leak(client, admin, monkeypatch):
    from app.services.app_settings import load_overrides

    client.put("/api/v1/app-settings", headers=admin, json={"values": {"S3_SECRET_ACCESS_KEY": "s3cr3t"}})
    settings.S3_SECRET_ACCESS_KEY = ""
    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY", "a different passphrase")
    load_overrides()
    assert settings.S3_SECRET_ACCESS_KEY == ""


def test_secret_rejected_without_encryption_key(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY", "")
    res = client.put("/api/v1/app-settings", headers=admin, json={"values": {"S3_SECRET_ACCESS_KEY": "x"}})
    assert res.status_code == 422
    assert "S3_SECRET_ACCESS_KEY" in res.json()["detail"]
    assert client.get("/api/v1/app-settings", headers=admin).json()["encryption_available"] is False


def test_database_not_served_statically(client):
    assert client.get("/data/config/data.db").status_code == 404
    assert client.get("/data/data.db").status_code == 404


def test_access_key_id_is_secret_and_encrypted(client, admin):
    from app.db.models import AppSettingModel
    from app.db.session import SessionLocal

    body = client.put("/api/v1/app-settings", headers=admin,
                      json={"values": {"S3_ACCESS_KEY_ID": "AKIAEXAMPLE"}}).json()
    item = _find(body, "S3_ACCESS_KEY_ID")
    assert item["value"] is None and item["is_set"] is True
    assert "AKIAEXAMPLE" not in client.get("/api/v1/app-settings", headers=admin).text
    db = SessionLocal()
    assert "AKIAEXAMPLE" not in db.get(AppSettingModel, "S3_ACCESS_KEY_ID").value_json
    db.close()
    settings.S3_ACCESS_KEY_ID = ""


def test_any_string_works_as_key(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY", "x")
    res = client.put("/api/v1/app-settings", headers=admin, json={"values": {"S3_SECRET_ACCESS_KEY": "v"}})
    assert res.status_code == 200
    assert res.json()["encryption_available"] is True
