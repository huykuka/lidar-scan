"""Small helpers shared by the replay API tests."""
from __future__ import annotations

import time

from .conftest import N_FRAMES, N_POINTS  # noqa: F401  (re-exported for convenience)

def wait_run(client, run_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/v1/replays/{run_id}").json()
        if run["status"] in ("completed", "failed"):
            return run
        time.sleep(0.1)
    raise AssertionError("replay did not finish")


def start_run(client, **overrides):
    body = {"recording_id": "rec1", "playback_node_id": "pb", "label": "x"}
    body.update(overrides)
    res = client.post("/api/v1/replays", json=body)
    assert res.status_code == 202, res.text
    return res.json()["id"]


