"""Shared fixtures for the replay tests: a recording and a playback -> downsample -> store DAG."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from app.db.session import SessionLocal, get_engine
from app.repositories import EdgeRepository, NodeRepository, RecordingRepository

N_FRAMES = 12
N_POINTS = 100


def _write_recording(path: Path) -> None:
    pts = np.random.default_rng(0).random((N_POINTS, 3)).astype(np.float32)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.json", json.dumps({
            "frame_count": N_FRAMES,
            "timestamps": [float(i) for i in range(N_FRAMES)],
            "start_timestamp": 0.0,
            "end_timestamp": float(N_FRAMES - 1),
            "fields": ["x", "y", "z"],
        }))
        header = (
            "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\n"
            f"WIDTH {N_POINTS}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {N_POINTS}\nDATA binary\n"
        ).encode("ascii")
        for i in range(N_FRAMES):
            zf.writestr(f"frame_{i:05d}.pcd", header + pts.tobytes())


@pytest.fixture
def dag(client, tmp_path, monkeypatch):
    """playback -> uniform_downsample -> result_storage, plus a recording."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "recordings").mkdir(parents=True)
    rec_path = tmp_path / "data" / "recordings" / "rec1.zip"
    _write_recording(rec_path)

    get_engine()
    with SessionLocal() as db:
        RecordingRepository(db).create({
            "id": "rec1", "name": "rec1", "node_id": "src", "sensor_id": None,
            "file_path": str(rec_path), "file_size_bytes": rec_path.stat().st_size,
            "frame_count": N_FRAMES, "duration_seconds": float(N_FRAMES - 1),
            "recording_timestamp": "2026-01-01T00:00:00+00:00", "metadata": {}, "status": "ready",
        })

    repo = NodeRepository()
    repo.upsert({"id": "pb", "name": "Playback", "type": "playback", "category": "sensor",
                 "config": {"recording_id": "rec1", "playback_speed": 1.0}})
    repo.upsert({"id": "ds", "name": "Down", "type": "uniform_downsample", "category": "operation",
                 "config": {"every_k_points": 5}})
    repo.upsert({"id": "rs", "name": "Store", "type": "result_storage", "category": "flow_control",
                 "config": {}})
    EdgeRepository().save_all([
        {"source_node": "pb", "source_port": "out", "target_node": "ds", "target_port": "in"},
        {"source_node": "ds", "source_port": "out", "target_node": "rs", "target_port": "in"},
    ])
    return client


