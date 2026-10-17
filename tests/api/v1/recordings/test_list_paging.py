"""Paging + search for GET /recordings."""

import pytest

from app.db.models import RecordingModel
from app.repositories.recordings_orm import RecordingRepository


@pytest.fixture
def repo(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    r = RecordingRepository(session)
    for i in range(25):
        r.create({
            "id": f"id{i:02d}", "name": f"Scan {i:02d}" if i % 5 else f"Truck {i:02d}", "node_id": "n1",
            "file_path": f"/x/{i}.mcap", "file_size_bytes": 1, "frame_count": 1, "duration_seconds": 1.0,
            "recording_timestamp": "t", "metadata": {"sensor_name": "picoscan"},
            "created_at": f"2026-10-{i + 1:02d}T00:00:00+00:00",
        })
    yield r
    session.close()


def test_all_when_no_limit(repo):
    rows, total = repo.list_page()
    assert len(rows) == total == 25


def test_pages_are_newest_first_and_disjoint(repo):
    p1, total = repo.list_page(limit=10, offset=0)
    p2, _ = repo.list_page(limit=10, offset=10)
    p3, _ = repo.list_page(limit=10, offset=20)
    assert total == 25 and [len(p) for p in (p1, p2, p3)] == [10, 10, 5]
    ids = [r["id"] for r in p1 + p2 + p3]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == 25


def test_search_total_counts_matches_not_page(repo):
    rows, total = repo.list_page(q="truck", limit=2)
    assert total == 5 and len(rows) == 2
    _, by_sensor = repo.list_page(q="PICOSCAN")
    assert by_sensor == 25
