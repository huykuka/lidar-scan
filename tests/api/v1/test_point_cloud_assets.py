import io

import numpy as np
import pytest

from app.modules.matching.store import ReferenceStore, reference_store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(reference_store, "root", tmp_path / "assets")


def _npy(n=500):
    buf = io.BytesIO()
    np.save(buf, np.random.default_rng(0).random((n, 3)).astype(np.float32))
    return buf.getvalue()


def _upload(client, name="part", filename="part.npy", data=None):
    return client.post(
        "/api/v1/point-cloud-assets",
        files={"file": (filename, data if data is not None else _npy(), "application/octet-stream")},
        data={"name": name},
    )


def test_upload_list_get_delete(client):
    r = _upload(client)
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["name"] == "part" and asset["point_count"] == 500 and asset["format"] == "npy"

    listing = client.get("/api/v1/point-cloud-assets").json()
    assert listing["count"] == 1 and listing["assets"][0]["id"] == asset["id"]
    assert client.get(f"/api/v1/point-cloud-assets/{asset['id']}").json()["id"] == asset["id"]

    prev = client.get(f"/api/v1/point-cloud-assets/{asset['id']}/preview?max_points=200").json()
    assert prev["total_points"] == 500 and prev["returned_points"] == 200 and len(prev["points"][0]) == 3

    renamed = client.patch(f"/api/v1/point-cloud-assets/{asset['id']}", json={"name": "renamed"})
    assert renamed.json()["name"] == "renamed"

    assert client.delete(f"/api/v1/point-cloud-assets/{asset['id']}").status_code == 204
    assert client.get(f"/api/v1/point-cloud-assets/{asset['id']}").status_code == 404
    assert client.delete(f"/api/v1/point-cloud-assets/{asset['id']}").status_code == 404


def test_name_defaults_to_filename_stem(client):
    r = client.post(
        "/api/v1/point-cloud-assets",
        files={"file": ("bracket.npy", _npy(), "application/octet-stream")},
    )
    assert r.json()["name"] == "bracket"


def test_rejects_bad_files(client):
    assert _upload(client, filename="x.txt", data=b"hello").status_code == 400
    assert _upload(client, filename="x.pcd", data=b"not a pcd").status_code == 400
    assert _upload(client, filename="x.npy", data=b"").status_code == 400


def test_unknown_and_malformed_ids_404(client):
    assert client.get("/api/v1/point-cloud-assets/" + "0" * 32).status_code == 404
    assert client.get("/api/v1/point-cloud-assets/not-an-id").status_code == 404
    assert client.patch("/api/v1/point-cloud-assets/" + "0" * 32, json={"name": "a"}).status_code == 404
