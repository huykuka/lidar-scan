"""Tests for POST /recordings/{recording_id}/trim endpoint.

Endpoint now returns 202 immediately with status='processing'.
Background task runs synchronously inside TestClient (starlette runs
background tasks after the response in the same thread), so after the
POST returns we can immediately query the row and observe status='ready'.
"""

import asyncio
import hashlib
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from app.services.shared.recording import RecordingReader, RecordingWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recording_zip(tmp_path: Path, n_frames: int, name: str) -> tuple[Path, list]:
    """Return (zip_path, list_of_(points, timestamp)) for a recording."""
    dest = tmp_path / f"{name}.zip"
    metadata = {"node_id": "testnode", "sensor_id": "sensor1", "name": name}
    frames = []
    writer = RecordingWriter(dest, metadata)
    for i in range(n_frames):
        pts = np.array([[float(i), float(i), float(i)]], dtype=np.float32)
        ts = float(1000 + i)
        writer.write_frame(pts, ts)
        frames.append((pts, ts))
    writer.finalize()
    return dest, frames


def _register_recording(client, zip_path: Path, name: str = "src") -> dict:
    """Upload a recording ZIP via the API and return the RecordingResponse dict."""
    with open(zip_path, "rb") as fh:
        resp = client.post(
            "/api/v1/recordings/upload",
            files={"file": (zip_path.name, fh, "application/zip")},
            data={"name": name},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _trim(client, src_id: str, body: dict) -> dict:
    """POST trim and return response JSON."""
    resp = client.post(f"/api/v1/recordings/{src_id}/trim", json=body)
    return resp


# ---------------------------------------------------------------------------
# Route registration smoke test
# ---------------------------------------------------------------------------

def test_trim_route_registered():
    from app.api.v1.recordings.handler import router
    paths = {route.path for route in router.routes if hasattr(route, "path")}
    assert "/recordings/{recording_id}/trim" in paths


# ---------------------------------------------------------------------------
# 202 + status='processing' → 'ready' happy path
# ---------------------------------------------------------------------------

def test_trim_returns_202_immediately(client, tmp_path):
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=10, name="full")
    src = _register_recording(client, zip_path, "full")

    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 2, "end_frame": 7},
    )
    assert resp.status_code == 202, resp.text


def test_trim_happy_path_returns_recording_response(client, tmp_path):
    """After TestClient runs the background task, status flips to 'ready' with correct data."""
    zip_path, frames = _make_recording_zip(tmp_path, n_frames=10, name="full")
    src = _register_recording(client, zip_path, "full")

    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 2, "end_frame": 7},
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()

    # Shape check — includes new status field
    for field in ("id", "name", "node_id", "file_path", "file_size_bytes",
                  "frame_count", "duration_seconds", "recording_timestamp",
                  "metadata", "created_at", "status"):
        assert field in data, f"Missing field: {field}"

    assert data["id"] != src["id"]
    assert data["name"] == "full (trim)"

    # TestClient runs background tasks before returning from client.post(),
    # so the row should already be 'ready' by the time we check.
    get_resp = client.get(f"/api/v1/recordings/{data['id']}")
    assert get_resp.status_code == 200
    final = get_resp.json()
    assert final["status"] == "ready"
    assert final["frame_count"] == 5  # [2,7) = 5 frames
    assert final["file_size_bytes"] > 0


def test_trim_processing_row_created_before_background(client, tmp_path):
    """Initial 202 response body shows status='processing'."""
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="proc")
    src = _register_recording(client, zip_path, "proc")

    # Intercept before bg runs — patch _perform_trim_copy to block briefly
    # We can't easily pause bg tasks in TestClient (they run in-process),
    # so we verify the *response body* status field is 'processing' since that
    # is the value inserted into DB before the background task starts.
    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 0, "end_frame": 3},
    )
    assert resp.status_code == 202
    # The response body is the just-created row (status='processing' at insert time)
    assert resp.json()["status"] == "processing"


def test_trim_custom_name(client, tmp_path):
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="orig")
    src = _register_recording(client, zip_path, "orig")

    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 0, "end_frame": 3, "name": "custom"},
    )
    assert resp.status_code == 202
    assert resp.json()["name"] == "custom"


def test_trim_new_recording_visible_in_list(client, tmp_path):
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="r")
    src = _register_recording(client, zip_path, "r")

    trim_resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 1, "end_frame": 4},
    )
    new_id = trim_resp.json()["id"]

    get_resp = client.get(f"/api/v1/recordings/{new_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == new_id


# ---------------------------------------------------------------------------
# Frame content / reindexing — wait for 'ready' via GET
# ---------------------------------------------------------------------------

def test_trim_output_frames_match_source_slice(client, tmp_path):
    zip_path, frames = _make_recording_zip(tmp_path, n_frames=8, name="s")
    src = _register_recording(client, zip_path, "s")

    start, end = 2, 6
    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": start, "end_frame": end},
    )
    assert resp.status_code == 202
    data_id = resp.json()["id"]

    # BG task ran; get finalized row
    final = client.get(f"/api/v1/recordings/{data_id}").json()
    assert final["status"] == "ready"

    reader = RecordingReader(final["file_path"])
    assert reader.frame_count == end - start

    for out_idx, src_idx in enumerate(range(start, end)):
        out_pts, out_ts = reader.get_frame(out_idx)
        src_pts, src_ts = frames[src_idx]
        np.testing.assert_array_almost_equal(out_pts[:, :3], src_pts[:, :3])
        assert out_ts == src_ts

    reader.close()


def test_trim_output_frames_reindexed_from_zero(client, tmp_path):
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="ri")
    src = _register_recording(client, zip_path, "ri")

    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 3, "end_frame": 5},
    )
    assert resp.status_code == 202
    data_id = resp.json()["id"]
    final = client.get(f"/api/v1/recordings/{data_id}").json()

    with zipfile.ZipFile(final["file_path"]) as zf:
        names = zf.namelist()
    assert "frame_00000.pcd" in names
    assert "frame_00001.pcd" in names
    assert "frame_00003.pcd" not in names


def test_trim_metadata_timestamps_recomputed(client, tmp_path):
    zip_path, frames = _make_recording_zip(tmp_path, n_frames=6, name="ts")
    src = _register_recording(client, zip_path, "ts")

    start, end = 1, 4
    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": start, "end_frame": end},
    )
    assert resp.status_code == 202
    data_id = resp.json()["id"]
    final = client.get(f"/api/v1/recordings/{data_id}").json()

    reader = RecordingReader(final["file_path"])
    assert reader.start_timestamp == frames[start][1]
    assert reader.end_timestamp == frames[end - 1][1]
    reader.close()


# ---------------------------------------------------------------------------
# Boundary cases
# ---------------------------------------------------------------------------

def test_trim_single_first_frame(client, tmp_path):
    zip_path, frames = _make_recording_zip(tmp_path, n_frames=5, name="b1")
    src = _register_recording(client, zip_path, "b1")

    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 0, "end_frame": 1},
    )
    assert resp.status_code == 202
    data_id = resp.json()["id"]
    final = client.get(f"/api/v1/recordings/{data_id}").json()
    assert final["frame_count"] == 1

    reader = RecordingReader(final["file_path"])
    pts, ts = reader.get_frame(0)
    np.testing.assert_array_almost_equal(pts[:, :3], frames[0][0][:, :3])
    reader.close()


def test_trim_single_last_frame(client, tmp_path):
    n = 5
    zip_path, frames = _make_recording_zip(tmp_path, n_frames=n, name="b2")
    src = _register_recording(client, zip_path, "b2")

    resp = client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": n - 1, "end_frame": n},
    )
    assert resp.status_code == 202
    data_id = resp.json()["id"]
    final = client.get(f"/api/v1/recordings/{data_id}").json()
    assert final["frame_count"] == 1

    reader = RecordingReader(final["file_path"])
    pts, ts = reader.get_frame(0)
    np.testing.assert_array_almost_equal(pts[:, :3], frames[n - 1][0][:, :3])
    reader.close()


# ---------------------------------------------------------------------------
# 400 validation — no row created on invalid range
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body,detail_substr", [
    ({"start_frame": 5, "end_frame": 5}, "Invalid frame range"),
    ({"start_frame": 6, "end_frame": 5}, "Invalid frame range"),
    ({"start_frame": -1, "end_frame": 3}, "Invalid frame range"),
    ({"start_frame": 0, "end_frame": 100}, "Invalid frame range"),
])
def test_trim_400_invalid_range(client, tmp_path, body, detail_substr):
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="val")
    src = _register_recording(client, zip_path, "val")

    before_list = client.get("/api/v1/recordings").json()["recordings"]
    before_ids = {r["id"] for r in before_list}

    resp = client.post(f"/api/v1/recordings/{src['id']}/trim", json=body)
    assert resp.status_code == 400, resp.text
    assert "detail" in resp.json()
    assert detail_substr in resp.json()["detail"]

    # No new row created
    after_list = client.get("/api/v1/recordings").json()["recordings"]
    after_ids = {r["id"] for r in after_list}
    assert after_ids == before_ids, "A DB row was created for an invalid trim range"


# ---------------------------------------------------------------------------
# 404
# ---------------------------------------------------------------------------

def test_trim_404_unknown_recording(client):
    resp = client.post(
        "/api/v1/recordings/doesnotexist1234/trim",
        json={"start_frame": 0, "end_frame": 1},
    )
    assert resp.status_code == 404
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# Original intact after trim
# ---------------------------------------------------------------------------

def test_trim_original_db_row_unchanged(client, tmp_path):
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="orig2")
    src = _register_recording(client, zip_path, "orig2")

    orig_frame_count = src["frame_count"]
    orig_file_path = src["file_path"]

    client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 1, "end_frame": 3},
    )

    get_resp = client.get(f"/api/v1/recordings/{src['id']}")
    assert get_resp.status_code == 200
    after = get_resp.json()
    assert after["frame_count"] == orig_frame_count
    assert after["file_path"] == orig_file_path


def test_trim_original_file_bytes_unchanged(client, tmp_path):
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="orig3")
    src = _register_recording(client, zip_path, "orig3")

    orig_path = Path(src["file_path"])
    orig_hash = hashlib.sha256(orig_path.read_bytes()).hexdigest()
    orig_size = orig_path.stat().st_size

    client.post(
        f"/api/v1/recordings/{src['id']}/trim",
        json={"start_frame": 0, "end_frame": 2},
    )

    assert orig_path.stat().st_size == orig_size
    assert hashlib.sha256(orig_path.read_bytes()).hexdigest() == orig_hash


# ---------------------------------------------------------------------------
# Failure path: _perform_trim_copy raises → status='failed', no partial file
# ---------------------------------------------------------------------------

def test_trim_failure_sets_status_failed(client, tmp_path):
    """If the copy raises, the bg task sets status='failed' and removes partial file."""
    import app.api.v1.recordings.service as svc

    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="fail")
    src = _register_recording(client, zip_path, "fail")

    with patch.object(svc, "_perform_trim_copy", side_effect=RuntimeError("disk full")):
        resp = client.post(
            f"/api/v1/recordings/{src['id']}/trim",
            json={"start_frame": 0, "end_frame": 3},
        )

    assert resp.status_code == 202
    new_id = resp.json()["id"]

    # After BG task: status should be 'failed'
    get_resp = client.get(f"/api/v1/recordings/{new_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "failed"

    # Partial dest file should not exist
    dest = Path(resp.json()["file_path"])
    assert not dest.exists(), f"Partial file still exists: {dest}"


# ---------------------------------------------------------------------------
# Regression: _perform_trim_copy must be offloaded to a thread (not inline)
# ---------------------------------------------------------------------------

def test_trim_copy_offloaded_to_thread(client, tmp_path):
    """Assert _perform_trim_copy runs via asyncio.to_thread, not inline on the event loop."""
    import app.api.v1.recordings.service as svc

    zip_path, _ = _make_recording_zip(tmp_path, n_frames=5, name="offload")
    src = _register_recording(client, zip_path, "offload")

    calls = []
    original_to_thread = asyncio.to_thread

    async def _spy_to_thread(func, *args, **kwargs):
        calls.append(func)
        return await original_to_thread(func, *args, **kwargs)

    with patch.object(svc.asyncio, "to_thread", side_effect=_spy_to_thread):
        resp = client.post(
            f"/api/v1/recordings/{src['id']}/trim",
            json={"start_frame": 1, "end_frame": 4},
        )

    assert resp.status_code == 202, resp.text
    # _perform_trim_copy must appear among the functions offloaded to threads
    assert any(getattr(fn, "__name__", "") == "_perform_trim_copy" for fn in calls), (
        f"_perform_trim_copy not offloaded via asyncio.to_thread. Calls: {calls}"
    )


# ---------------------------------------------------------------------------
# Migration: status column exists and defaults to 'ready' for existing rows
# ---------------------------------------------------------------------------

def test_migration_recordings_status_column_exists(client):
    """recordings table must have a 'status' column defaulting to 'ready'."""
    from sqlalchemy import text
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        cols = {
            row[1]
            for row in db.execute(text("PRAGMA table_info(recordings)")).fetchall()
        }
        assert "status" in cols, "recordings table missing 'status' column after migration"
    finally:
        db.close()


def test_existing_recordings_have_status_ready(client, tmp_path):
    """Rows inserted without explicit status (simulating old rows) default to 'ready'."""
    zip_path, _ = _make_recording_zip(tmp_path, n_frames=3, name="legacy")
    src = _register_recording(client, zip_path, "legacy")

    # Uploaded rows don't set status explicitly — they should default to 'ready'
    get_resp = client.get(f"/api/v1/recordings/{src['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "ready"
