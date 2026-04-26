"""Tests for the detection model upload API endpoints."""
import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with isolated DB and model store directory."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    from app.db.migrate import ensure_schema
    from app.db.session import init_engine

    engine = init_engine()
    ensure_schema(engine)

    # Patch model store to use tmp_path
    import app.modules.detection.model_store as ms

    monkeypatch.setattr(ms, "_store", None)
    monkeypatch.setattr(ms, "_MODELS_DIR", tmp_path / "models")

    from app.app import app

    with TestClient(app) as tc:
        yield tc


class TestDetectionModelsAPI:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/v1/detection/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["models"] == []

    def test_upload_model(self, client: TestClient) -> None:
        fake_weights = b"fake model weights data"
        resp = client.post(
            "/api/v1/detection/models/upload",
            files={"file": ("kitti_weights.pth", io.BytesIO(fake_weights), "application/octet-stream")},
            data={"display_name": "KITTI PointPillars", "model_type": "pointpillars"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"]["display_name"] == "KITTI PointPillars"
        assert data["model"]["model_type"] == "pointpillars"
        assert data["model"]["file_size"] == len(fake_weights)
        assert data["model"]["id"]

    def test_upload_then_list(self, client: TestClient) -> None:
        client.post(
            "/api/v1/detection/models/upload",
            files={"file": ("w1.pth", io.BytesIO(b"aaa"), "application/octet-stream")},
            data={"display_name": "Model A"},
        )
        client.post(
            "/api/v1/detection/models/upload",
            files={"file": ("w2.pt", io.BytesIO(b"bbb"), "application/octet-stream")},
            data={"display_name": "Model B"},
        )
        resp = client.get("/api/v1/detection/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_get_model(self, client: TestClient) -> None:
        upload = client.post(
            "/api/v1/detection/models/upload",
            files={"file": ("w.pth", io.BytesIO(b"data"), "application/octet-stream")},
            data={"display_name": "Test"},
        )
        model_id = upload.json()["model"]["id"]
        resp = client.get(f"/api/v1/detection/models/{model_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == model_id

    def test_get_model_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/detection/models/nonexistent")
        assert resp.status_code == 404

    def test_delete_model(self, client: TestClient) -> None:
        upload = client.post(
            "/api/v1/detection/models/upload",
            files={"file": ("w.pth", io.BytesIO(b"data"), "application/octet-stream")},
            data={"display_name": "To Delete"},
        )
        model_id = upload.json()["model"]["id"]

        resp = client.delete(f"/api/v1/detection/models/{model_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify gone
        resp = client.get(f"/api/v1/detection/models/{model_id}")
        assert resp.status_code == 404

    def test_delete_model_not_found(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/detection/models/nonexistent")
        assert resp.status_code == 404

    def test_upload_invalid_extension(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/detection/models/upload",
            files={"file": ("evil.exe", io.BytesIO(b"bad"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_upload_empty_file(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/detection/models/upload",
            files={"file": ("empty.pth", io.BytesIO(b""), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Empty" in resp.json()["detail"]
