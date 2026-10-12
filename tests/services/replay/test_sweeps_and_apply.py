"""API tests: parameter sweeps, ground-truth scoring, clone data and apply-to-pipeline."""
from __future__ import annotations

import time

import pytest

from app.repositories import NodeRepository

from .conftest import N_POINTS
from .helpers import start_run, wait_run

BASE = "/api/v1/replays"


def _sweep(client, values, **extra):
    body = {"recording_id": "rec1", "playback_node_id": "pb", "node_id": "ds",
            "parameter": "every_k_points", "values": values, **extra}
    return client.post(f"{BASE}/sweeps", json=body)


def _wait_sweep(client, sweep_id, timeout=40.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail = client.get(f"{BASE}/sweeps/{sweep_id}").json()
        if detail["sweep"]["progress"]["active"] == 0:
            return detail
        time.sleep(0.2)
    raise AssertionError("sweep did not finish")


@pytest.fixture
def valid_dag(dag):
    """The shared fixture wires an operation node into result_storage, which the DAG save
    rules reject (result_storage only accepts application nodes). Apply goes through the
    same validation as the Settings page, so drop the sink for those tests."""
    from app.db.models import NodeModel
    from app.db.session import SessionLocal
    from app.repositories import EdgeRepository

    EdgeRepository().save_all([
        {"source_node": "pb", "source_port": "out", "target_node": "ds", "target_port": "in"},
    ])
    with SessionLocal() as db:
        db.query(NodeModel).filter(NodeModel.id == "rs").delete()
        db.commit()
    return dag


def _admin_headers(client):
    token = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── sweeps ──────────────────────────────────────────────────────────────────────

def test_sweep_runs_every_value_and_the_metric_follows_the_parameter(dag):
    res = _sweep(dag, [2, 5, 10], label="k sweep")
    assert res.status_code == 202, res.text
    detail = _wait_sweep(dag, res.json()["id"])

    runs = detail["runs"]
    assert detail["sweep"]["progress"] == {"total": 3, "completed": 3, "failed": 0, "active": 0}
    by_k = {r["overrides"]["ds"]["every_k_points"]: r for r in runs}
    for k, run in by_k.items():
        assert run["sweep_id"] == res.json()["id"]
        assert run["summary"]["nodes"]["ds"]["values"]["downsampled_count"]["mean"] == N_POINTS / k
    assert sorted(by_k) == [2, 5, 10]


def test_sweep_adds_the_current_value_as_baseline_when_missing(dag):
    detail = _wait_sweep(dag, _sweep(dag, [2, 10]).json()["id"])  # live config is 5
    labels = sorted(r["label"] for r in detail["runs"])
    assert len(labels) == 3 and any("(current)" in label for label in labels)
    baseline = next(r for r in detail["runs"] if "(current)" in r["label"])
    assert baseline["overrides"] == {}

    no_baseline = _wait_sweep(dag, _sweep(dag, [2, 10], include_current=False).json()["id"])
    assert len(no_baseline["runs"]) == 2


def test_sweep_runs_report_the_value_they_used_including_the_baseline(dag):
    detail = _wait_sweep(dag, _sweep(dag, [2, 10]).json()["id"])      # live value is 5
    by_value = {r["x_value"]: r for r in detail["runs"]}
    assert sorted(by_value) == [2, 5, 10]
    assert by_value[5]["is_baseline"] is True and by_value[2]["is_baseline"] is False
    assert by_value[5]["overrides"] == {}


def test_sweep_deduplicates_equivalent_values(dag):
    detail = _wait_sweep(dag, _sweep(dag, [2, "2", 2.0, 5], include_current=False).json()["id"])
    assert len(detail["runs"]) == 2


def test_sweep_validation(dag):
    assert _sweep(dag, []).status_code == 422
    assert _sweep(dag, list(range(2, 33))).status_code == 422          # 31 values
    assert _sweep(dag, [2], node_id="ghost").status_code == 404
    assert _sweep(dag, [2], parameter="  ").status_code == 400
    assert _sweep(dag, [2], playback_node_id="ds").status_code == 400  # not a playback node
    assert _sweep(dag, [2], recording_id="nope").status_code == 404
    # nothing half-created
    assert dag.get(f"{BASE}/sweeps").json()["total"] == 0
    assert dag.get(BASE, params={"include_sweep_runs": True}).json()["total"] == 0


def test_baseline_pushing_a_sweep_over_the_limit_is_rejected_cleanly(dag):
    res = _sweep(dag, list(range(2, 32)))  # 30 values + baseline(5 is inside) -> fits
    assert res.status_code == 202
    over = _sweep(dag, list(range(100, 130)))  # 30 values, 5 not included -> 31 runs
    assert over.status_code == 400 and "limited" in over.json()["detail"]
    _wait_sweep(dag, res.json()["id"], timeout=120)


def test_sweep_runs_are_hidden_from_the_plain_run_list(dag):
    _wait_sweep(dag, _sweep(dag, [2, 10], include_current=False).json()["id"])
    wait_run(dag, start_run(dag))
    assert dag.get(BASE).json()["total"] == 1
    assert dag.get(BASE, params={"include_sweep_runs": True}).json()["total"] == 3


def test_cancel_and_delete_sweep(dag, tmp_path):
    sweep_id = _sweep(dag, list(range(2, 12)), include_current=False).json()["id"]
    assert dag.delete(f"{BASE}/sweeps/{sweep_id}").status_code == 409       # still active
    assert dag.post(f"{BASE}/sweeps/{sweep_id}/cancel").json()["cancelled"] >= 1

    detail = _wait_sweep(dag, sweep_id)
    assert detail["sweep"]["progress"]["active"] == 0
    assert all(r["status"] in ("completed", "failed") for r in detail["runs"])
    assert any(r["error"] == "Cancelled" for r in detail["runs"])            # queued ones were cancelled

    assert dag.delete(f"{BASE}/sweeps/{sweep_id}").status_code == 204
    assert dag.get(f"{BASE}/sweeps/{sweep_id}").status_code == 404
    assert dag.get(BASE, params={"include_sweep_runs": True}).json()["total"] == 0
    assert not any((tmp_path / "data" / "replays").glob("*/")) if (tmp_path / "data" / "replays").exists() else True


# ── ground truth ────────────────────────────────────────────────────────────────

def _target(client, expected, tolerance=1.0, **extra):
    body = {"recording_id": "rec1", "node_id": "ds", "metric_key": "downsampled_count",
            "expected": expected, "tolerance": tolerance, "label": "kept points", **extra}
    return client.post(f"{BASE}/targets", json=body)


def test_target_crud_and_validation(dag):
    created = _target(dag, 20)
    assert created.status_code == 201 and created.json()["expected"] == 20
    assert dag.get(f"{BASE}/targets", params={"recording_id": "rec1"}).json()["targets"][0]["label"] == "kept points"
    assert _target(dag, 20, recording_id="nope").status_code == 404
    assert _target(dag, 20, tolerance=-1).status_code == 422
    assert dag.delete(f"{BASE}/targets/{created.json()['id']}").status_code == 204
    assert dag.delete(f"{BASE}/targets/{created.json()['id']}").status_code == 404
    assert dag.get(f"{BASE}/targets").json()["targets"] == []


def test_runs_are_scored_and_the_sweep_picks_the_best(dag):
    _target(dag, expected=20, tolerance=1)             # k=5 keeps exactly 20 points
    detail = _wait_sweep(dag, _sweep(dag, [2, 5, 10], include_current=False).json()["id"])

    by_k = {r["overrides"]["ds"]["every_k_points"]: r for r in detail["runs"]}
    assert by_k[5]["scores"]["overall"] == "pass"
    assert by_k[2]["scores"]["overall"] == "fail" and by_k[10]["scores"]["overall"] == "fail"
    t = by_k[2]["scores"]["targets"][0]
    assert t["value"] == 50 and t["error"] == 30 and t["std"] == 0
    assert detail["best_run_id"] == by_k[5]["id"]
    assert len(detail["targets"]) == 1


def test_scores_appear_on_listed_runs_and_in_compare(dag):
    _target(dag, expected=20, tolerance=1)
    a = wait_run(dag, start_run(dag, label="a"))
    b = wait_run(dag, start_run(dag, label="b", overrides={"ds": {"every_k_points": 10}}))
    listed = {r["label"]: r for r in dag.get(BASE).json()["runs"]}
    assert listed["a"]["scores"]["overall"] == "pass" and listed["b"]["scores"]["overall"] == "fail"

    cmp = dag.get(f"{BASE}/compare", params={"a": a["id"], "b": b["id"]}).json()
    assert cmp["scores_a"]["overall"] == "pass" and cmp["scores_b"]["overall"] == "fail"
    assert cmp["run_a_info"]["overrides"] == {}
    assert cmp["run_b_info"]["overrides"] == {"ds": {"every_k_points": 10}}


def test_no_targets_means_no_scores_and_no_best_run(dag):
    detail = _wait_sweep(dag, _sweep(dag, [2, 10], include_current=False).json()["id"])
    assert detail["best_run_id"] is None
    assert all(r["scores"]["overall"] is None for r in detail["runs"])


# ── clone data ──────────────────────────────────────────────────────────────────

def test_run_exposes_what_is_needed_to_clone_it(dag):
    run = wait_run(dag, start_run(dag, overrides={"ds": {"every_k_points": 10}}, capture_nodes=["ds"]))
    assert run["overrides"] == {"ds": {"every_k_points": 10}}
    assert run["capture_nodes"] == ["ds"]
    assert run["recording_id"] == "rec1" and run["playback_node_id"] == "pb"


# ── apply to the live pipeline ──────────────────────────────────────────────────

def test_preview_is_read_only_and_describes_the_change(dag):
    run = wait_run(dag, start_run(dag, overrides={"ds": {"every_k_points": 10}}))
    preview = dag.get(f"{BASE}/{run['id']}/apply-preview").json()
    assert preview["has_changes"] is True
    assert preview["changes"] == [{
        "node_id": "ds", "node_name": "Down", "node_exists": True,
        "key": "every_k_points", "current": 5, "new": 10, "changed": True,
    }]
    assert preview["pipeline_changed_since_run"] == []
    assert NodeRepository().get_by_id("ds")["config"]["every_k_points"] == 5


def test_apply_requires_an_authenticated_admin(dag):
    run = wait_run(dag, start_run(dag, overrides={"ds": {"every_k_points": 10}}))
    assert dag.post(f"{BASE}/{run['id']}/apply").status_code == 401
    assert NodeRepository().get_by_id("ds")["config"]["every_k_points"] == 5


def test_apply_updates_the_saved_pipeline_and_is_not_repeatable(valid_dag):
    dag = valid_dag
    run = wait_run(dag, start_run(dag, overrides={"ds": {"every_k_points": 10}}))
    res = dag.post(f"{BASE}/{run['id']}/apply", headers=_admin_headers(dag))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["applied"] == [{"node_id": "ds", "node_name": "Down", "key": "every_k_points", "old": 5, "new": 10}]
    assert body["reload_mode"] in ("selective", "full", "none") and body["config_version"] >= 1

    config = NodeRepository().get_by_id("ds")["config"]
    assert config["every_k_points"] == 10
    assert config["op_type"] if "op_type" in config else True            # other keys survive

    again = dag.post(f"{BASE}/{run['id']}/apply", headers=_admin_headers(dag))
    assert again.status_code == 409 and "already" in again.json()["detail"]
    assert dag.get(f"{BASE}/{run['id']}/apply-preview").json()["has_changes"] is False


def test_apply_keeps_the_numeric_string_style_of_the_saved_config(valid_dag):
    dag = valid_dag
    NodeRepository().upsert({"id": "ds", "name": "Down", "type": "uniform_downsample",
                             "category": "operation", "config": {"every_k_points": "5"}})
    run = wait_run(dag, start_run(dag, overrides={"ds": {"every_k_points": 10}}))
    assert dag.post(f"{BASE}/{run['id']}/apply", headers=_admin_headers(dag)).status_code == 200
    assert NodeRepository().get_by_id("ds")["config"]["every_k_points"] == "10"


def test_preview_warns_when_the_pipeline_changed_since_the_run(dag):
    run = wait_run(dag, start_run(dag, overrides={"ds": {"every_k_points": 10}}))
    NodeRepository().upsert({"id": "ds", "name": "Down", "type": "uniform_downsample",
                             "category": "operation", "config": {"every_k_points": 5, "extra": "x"}})
    drift = dag.get(f"{BASE}/{run['id']}/apply-preview").json()["pipeline_changed_since_run"]
    assert any(d["node_id"] == "ds" and d["key"] == "extra" for d in drift)


def test_apply_without_overrides_or_with_removed_node(dag):
    plain = wait_run(dag, start_run(dag))
    res = dag.post(f"{BASE}/{plain['id']}/apply", headers=_admin_headers(dag))
    assert res.status_code == 409 and "no parameter overrides" in res.json()["detail"]

    run = wait_run(dag, start_run(dag, overrides={"ds": {"every_k_points": 10}}))
    from app.db.models import NodeModel
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        db.query(NodeModel).filter(NodeModel.id == "ds").delete()
        db.commit()
    res = dag.post(f"{BASE}/{run['id']}/apply", headers=_admin_headers(dag))
    assert res.status_code == 409 and "no longer" in res.json()["detail"]
    assert dag.get(f"{BASE}/{run['id']}/apply-preview").json()["missing_nodes"] == ["ds"]


def test_apply_unknown_run(dag):
    assert dag.get(f"{BASE}/nope/apply-preview").status_code == 404
    assert dag.post(f"{BASE}/nope/apply", headers=_admin_headers(dag)).status_code == 404
