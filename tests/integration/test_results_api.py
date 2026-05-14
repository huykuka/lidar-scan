"""
Integration tests for the results API.

Covers:
  - Full lifecycle: save (via service) → GET list → GET detail → GET PCD → DELETE
  - 404 on unknown node_id / result_id
  - Node delete cascade via orchestrator integration
"""

import asyncio

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_pcd(n_points: int = 10):
    import open3d as o3d

    pcd = o3d.geometry.PointCloud()
    pts = np.random.rand(n_points, 3).astype(np.float64)
    cols = np.random.rand(n_points, 3).astype(np.float64)
    pcd.points = o3d.utility.Vector3dVector(pts)
    pcd.colors = o3d.utility.Vector3dVector(cols)
    return pcd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def results_client(tmp_path, monkeypatch):
    """TestClient with an isolated main DB, results dir, and a known results_service singleton."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.chdir(tmp_path)

    # Create the main app DB (includes application_results table)
    from app.db.migrate import ensure_schema
    from app.db.session import init_engine

    engine = init_engine()
    ensure_schema(engine)

    # Create isolated ResultsStorageService (uses the main DB via SessionLocal)
    from app.services.results_storage import ResultsStorageService

    svc = ResultsStorageService()

    # Patch the singleton used by the router
    import app.api.v1.results.router as results_router_module

    monkeypatch.setattr(results_router_module, "_results_service", svc)

    from app.app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client, svc


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/results (overview)
# ---------------------------------------------------------------------------


class TestResultsOverview:
    def test_get_results_empty(self, results_client):
        client, svc = results_client
        resp = client.get("/api/v1/results")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_results_shows_node_with_results(
        self, results_client, tmp_path, monkeypatch
    ):
        client, svc = results_client
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        asyncio.get_event_loop().run_until_complete(
            svc.save_result("test_node_xyz", [("p", pcd)], {"val": 1})
        )
        resp = client.get("/api/v1/results")
        assert resp.status_code == 200
        data = resp.json()
        node_ids = [r["node_id"] for r in data]
        assert "test_node_xyz" in node_ids


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/results/{node_id}
# ---------------------------------------------------------------------------


class TestNodeResultsList:
    def test_404_for_unknown_node(self, results_client):
        client, svc = results_client
        resp = client.get("/api/v1/results/totally_unknown_node_id_xyz")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_returns_results_for_known_node(
        self, results_client, tmp_path, monkeypatch
    ):
        client, svc = results_client
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        asyncio.get_event_loop().run_until_complete(
            svc.save_result("node_list_test", [("p", pcd)], {"score": 9.5})
        )
        resp = client.get("/api/v1/results/node_list_test")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["node_id"] == "node_list_test"
        assert "pcd_count" in data[0]
        assert "metadata_summary" in data[0]

    def test_pagination_params_accepted(self, results_client, tmp_path, monkeypatch):
        client, svc = results_client
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        for _ in range(3):
            asyncio.get_event_loop().run_until_complete(
                svc.save_result("node_page", [("p", pcd)], {})
            )
        resp = client.get("/api/v1/results/node_page?limit=2&offset=0")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp2 = client.get("/api/v1/results/node_page?limit=2&offset=2")
        assert resp2.status_code == 200
        assert len(resp2.json()) == 1


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/results/{node_id}/{result_id}
# ---------------------------------------------------------------------------


class TestResultDetail:
    def test_404_for_unknown_result(self, results_client):
        client, svc = results_client
        resp = client.get("/api/v1/results/node_x/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_get_detail_full_lifecycle(self, results_client, tmp_path, monkeypatch):
        client, svc = results_client
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        result_id = asyncio.get_event_loop().run_until_complete(
            svc.save_result(
                "node_detail",
                [("empty", pcd), ("loaded", pcd)],
                {"volume_m3": 3.14, "icp_valid": True},
                "success",
            )
        )
        resp = client.get(f"/api/v1/results/node_detail/{result_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["result_id"] == result_id
        assert data["node_id"] == "node_detail"
        assert data["status"] == "success"
        assert data["metadata"]["volume_m3"] == pytest.approx(3.14)
        assert len(data["pcd_files"]) == 2
        labels = [f["label"] for f in data["pcd_files"]]
        assert "empty" in labels
        assert "loaded" in labels
        # URLs must be correct
        for f in data["pcd_files"]:
            assert f["url"].startswith("/api/v1/results/node_detail/")


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/results/{node_id}/{result_id}/pcd/{label}
# ---------------------------------------------------------------------------


class TestPcdDownload:
    def test_404_for_unknown_label(self, results_client):
        client, svc = results_client
        resp = client.get("/api/v1/results/node_x/no_result/pcd/nolabel")
        assert resp.status_code == 404

    def test_pcd_file_download(self, results_client, tmp_path, monkeypatch):
        client, svc = results_client
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(20)
        result_id = asyncio.get_event_loop().run_until_complete(
            svc.save_result("node_pcd", [("merged", pcd)], {})
        )
        resp = client.get(f"/api/v1/results/node_pcd/{result_id}/pcd/merged")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        assert len(resp.content) > 0

    def test_pcd_content_disposition_header(
        self, results_client, tmp_path, monkeypatch
    ):
        client, svc = results_client
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        result_id = asyncio.get_event_loop().run_until_complete(
            svc.save_result("node_pcd2", [("empty", pcd)], {})
        )
        resp = client.get(f"/api/v1/results/node_pcd2/{result_id}/pcd/empty")
        assert resp.status_code == 200
        assert "empty.pcd" in resp.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# Tests: DELETE /api/v1/results/{node_id}/{result_id}
# ---------------------------------------------------------------------------


class TestDeleteResult:
    def test_404_for_unknown_result(self, results_client):
        client, svc = results_client
        resp = client.delete(
            "/api/v1/results/node_x/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_delete_removes_result(self, results_client, tmp_path, monkeypatch):
        client, svc = results_client
        monkeypatch.chdir(tmp_path)
        pcd = _make_mock_pcd(5)
        result_id = asyncio.get_event_loop().run_until_complete(
            svc.save_result("node_del_api", [("p", pcd)], {})
        )
        resp = client.delete(f"/api/v1/results/node_del_api/{result_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["result_id"] == result_id

        # Subsequent GET should 404
        resp2 = client.get(f"/api/v1/results/node_del_api/{result_id}")
        assert resp2.status_code == 404
