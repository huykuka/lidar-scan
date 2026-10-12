"""End-to-end tests for offline replay: real recording -> isolated DAG -> compare."""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest

from app.db.models import ApplicationResultModel
from app.db.session import SessionLocal, get_engine
from app.repositories import EdgeRepository, NodeRepository, RecordingRepository

from .conftest import N_FRAMES, N_POINTS
from .helpers import start_run as _start, wait_run as _wait


def test_replay_runs_all_frames_fast_and_captures_outputs(dag):
    started = time.time()
    run = _wait(dag, _start(dag))
    assert run["status"] == "completed", run
    assert run["frames_processed"] == N_FRAMES
    # 12 frames at 1 fps would be ~11 s in real time
    assert time.time() - started < 8

    out = dag.get(f"/api/v1/replays/{run['id']}/outputs").json()
    assert len(out["nodes"]["pb"]["frames"]) == N_FRAMES
    ds_frames = out["nodes"]["ds"]["frames"]
    assert len(ds_frames) == N_FRAMES
    assert all(f["points"] == N_POINTS // 5 for f in ds_frames)
    assert [f["frame"] for f in out["nodes"]["pb"]["frames"]] == list(range(N_FRAMES))
    assert len(out["saved_results"]) == N_FRAMES
    assert out["errors"] == []


def test_replay_does_not_write_live_results(dag, tmp_path):
    _wait(dag, _start(dag))
    with SessionLocal() as db:
        assert db.query(ApplicationResultModel).count() == 0
    assert not (tmp_path / "data" / "results").exists()


def test_override_changes_output_and_compare_reports_diff(dag):
    a = _wait(dag, _start(dag, label="baseline"))
    b = _wait(dag, _start(dag, label="k10", overrides={"ds": {"every_k_points": 10}}))
    assert a["config_hash"] != b["config_hash"]

    # The saved DAG config must be untouched by the override.
    assert NodeRepository().get_by_id("ds")["config"]["every_k_points"] == 5

    cmp = dag.get("/api/v1/replays/compare", params={"a": a["id"], "b": b["id"]}).json()
    assert cmp["same_recording"] is True
    assert cmp["summary"]["identical"] is False
    ds = cmp["nodes"]["ds"]
    assert ds["frames_compared"] == N_FRAMES
    assert ds["points_differing_frames"] == N_FRAMES
    assert ds["points_mean_delta"] == pytest.approx(N_POINTS // 10 - N_POINTS // 5)


def test_identical_runs_compare_identical(dag):
    a = _wait(dag, _start(dag))
    b = _wait(dag, _start(dag))
    cmp = dag.get("/api/v1/replays/compare", params={"a": a["id"], "b": b["id"]}).json()
    assert cmp["summary"]["identical"] is True


def test_validation_errors(dag):
    assert dag.post("/api/v1/replays", json={"recording_id": "nope", "playback_node_id": "pb"}).status_code == 404
    assert dag.post("/api/v1/replays", json={"recording_id": "rec1", "playback_node_id": "ds"}).status_code == 400
    bad = dag.post("/api/v1/replays", json={
        "recording_id": "rec1", "playback_node_id": "pb", "overrides": {"ghost": {"a": 1}},
    })
    assert bad.status_code == 400
    assert dag.get("/api/v1/replays/compare", params={"a": "x", "b": "y"}).status_code == 404


def test_list_and_delete(dag):
    run = _wait(dag, _start(dag))
    listed = dag.get("/api/v1/replays", params={"recording_id": "rec1"}).json()
    assert listed["total"] == 1
    assert dag.delete(f"/api/v1/replays/{run['id']}").status_code == 204
    assert dag.get(f"/api/v1/replays/{run['id']}").status_code == 404


# ── visual diff ────────────────────────────────────────────────────────────────

def test_default_capture_includes_final_nodes_parents_and_serves_diff(dag):
    a = _wait(dag, _start(dag, label="a"))
    b = _wait(dag, _start(dag, label="b", overrides={"ds": {"every_k_points": 10}}))

    # result_storage is the sink; the downsample node feeding it is captured by default.
    assert set(a["summary"]["clouds"]) == {"ds"}
    assert a["summary"]["clouds"]["ds"]["frames"] == list(range(N_FRAMES))

    cmp = dag.get("/api/v1/replays/compare", params={"a": a["id"], "b": b["id"]}).json()
    assert [n["node_id"] for n in cmp["cloud_nodes"]] == ["ds"]

    res = dag.get("/api/v1/replays/compare/cloud",
                  params={"a": a["id"], "b": b["id"], "node_id": "ds", "frame": 3, "tol": 0.001})
    assert res.status_code == 200
    import struct
    n_a, n_b, only_a, only_b, *_ = struct.unpack_from("<IIIIff", res.content, 0)
    assert (n_a, n_b) == (N_POINTS // 5, N_POINTS // 10)
    assert only_a > 0 and only_b == 0     # B is a subset of A's points


def test_identical_runs_have_no_visual_differences(dag):
    import struct
    a = _wait(dag, _start(dag))
    b = _wait(dag, _start(dag))
    res = dag.get("/api/v1/replays/compare/cloud",
                  params={"a": a["id"], "b": b["id"], "node_id": "ds", "frame": 0})
    n_a, n_b, only_a, only_b, *_ = struct.unpack_from("<IIIIff", res.content, 0)
    assert n_a == n_b and only_a == 0 and only_b == 0


def test_capture_nodes_can_be_disabled_or_validated(dag, tmp_path):
    run = _wait(dag, _start(dag, capture_nodes=[]))
    assert run["summary"]["clouds"] == {}
    assert not (tmp_path / "data" / "replays" / run["id"] / "clouds").exists()

    bad = dag.post("/api/v1/replays", json={
        "recording_id": "rec1", "playback_node_id": "pb", "capture_nodes": ["ghost"],
    })
    assert bad.status_code == 400

    other = _wait(dag, _start(dag))
    missing = dag.get("/api/v1/replays/compare/cloud",
                      params={"a": run["id"], "b": other["id"], "node_id": "ds", "frame": 0})
    assert missing.status_code == 404


def test_delete_removes_captured_clouds(dag, tmp_path):
    run = _wait(dag, _start(dag))
    folder = tmp_path / "data" / "replays" / run["id"]
    assert folder.exists()
    assert dag.delete(f"/api/v1/replays/{run['id']}").status_code == 204
    assert not folder.exists()
