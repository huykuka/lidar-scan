"""Tests for the recording-upload storage strategies and their facade."""

import asyncio
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import blob_storage
from app.services.blob_storage import registry
from app.services.blob_storage.base import StorageStatus, StorageStrategy
from app.services.blob_storage.s3 import S3Strategy


class FakeStrategy(StorageStrategy):
    name = "fake"

    def __init__(self, existing=(), ok=True):
        self.existing = set(existing)
        self.ok = ok
        self.uploaded: list[tuple[Path, str]] = []

    @property
    def key_prefix(self):
        return "recordings"

    @property
    def location(self):
        return "fake-bucket"

    def is_configured(self):
        return True

    def check(self):
        return StorageStatus(True, self.ok, self.name, self.location)

    def exists(self, key):
        return key in self.existing

    def upload(self, file_path, key, on_progress=None):
        if on_progress:
            on_progress(5, 10)
            on_progress(10, 10)
        self.uploaded.append((file_path, key))


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    blob_storage._cached = None
    registry._instances.clear()
    yield
    blob_storage._cached = None
    registry._instances.clear()


def _use(monkeypatch, strategy):
    monkeypatch.setattr(blob_storage, "get_strategy", lambda: strategy)


REC = {"id": "abcdef1234", "name": "My scan/1", "created_at": "2026-10-17T10:00:00+00:00",
       "file_path": "/data/uuid-123.mcap"}


def test_unknown_backend(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "nope")
    status = asyncio.run(blob_storage.get_status(force=True))
    assert not status.configured and "Unknown" in status.reason


def test_registry_selects_s3_by_default(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
    assert isinstance(registry.get_strategy(), S3Strategy)


def test_s3_not_configured(monkeypatch):
    for name in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        monkeypatch.setattr(settings, name, "")
    status = S3Strategy().check()
    assert not status.configured and not status.authenticated


def test_s3_bad_credentials(monkeypatch):
    for name, value in (("S3_BUCKET", "b"), ("S3_ACCESS_KEY_ID", "i"), ("S3_SECRET_ACCESS_KEY", "s")):
        monkeypatch.setattr(settings, name, value)
    strategy = S3Strategy()
    monkeypatch.setattr(strategy, "_client", lambda: (_ for _ in ()).throw(Exception("403")))
    status = strategy.check()
    assert status.configured and not status.authenticated


def test_status_goes_through_strategy(monkeypatch):
    _use(monkeypatch, FakeStrategy(ok=True))
    status = asyncio.run(blob_storage.get_status(force=True))
    assert status.authenticated and status.bucket == "fake-bucket"


def test_build_key_is_readable_and_avoids_collisions(monkeypatch):
    _use(monkeypatch, FakeStrategy())
    assert asyncio.run(blob_storage.build_key(REC)) == "recordings/My_scan_1_2026-10-17.mcap"

    _use(monkeypatch, FakeStrategy(existing={"recordings/My_scan_1_2026-10-17.mcap"}))
    assert asyncio.run(blob_storage.build_key(REC)) == "recordings/My_scan_1_2026-10-17_abcdef12.mcap"


def test_upload_recording_uses_strategy(monkeypatch):
    fake = FakeStrategy()
    _use(monkeypatch, fake)
    bucket, key = asyncio.run(blob_storage.upload_recording(REC))
    assert (bucket, key) == ("fake-bucket", "recordings/My_scan_1_2026-10-17.mcap")
    assert fake.uploaded == [(Path("/data/uuid-123.mcap"), key)]


def test_job_records_uploaded_then_failed(monkeypatch):
    states = []
    events = []
    monkeypatch.setattr(blob_storage, "_set_upload_state_sync", lambda rid, st: states.append(st))

    async def fake_broadcast(topic, message, reliable=False):
        events.append((topic, message, reliable))

    from app.services.websocket import manager as ws_manager
    monkeypatch.setattr(ws_manager.manager, "broadcast", fake_broadcast)
    _use(monkeypatch, FakeStrategy())
    asyncio.run(blob_storage.run_upload_job(REC))
    assert states[-1]["status"] == "uploaded" and states[-1]["key"].endswith(".mcap")
    assert any(e[1]["recording_upload"]["blob_upload"].get("progress") == 100 for e in events)
    topic, msg, reliable = events[-1]
    assert topic == "system_status" and reliable
    assert msg["recording_upload"]["recording_id"] == REC["id"]
    assert msg["recording_upload"]["blob_upload"]["status"] == "uploaded"

    class Boom(FakeStrategy):
        def upload(self, file_path, key, on_progress=None):
            raise OSError("nope")

    _use(monkeypatch, Boom())
    asyncio.run(blob_storage.run_upload_job(REC))
    assert states[-1]["status"] == "failed" and "nope" in states[-1]["error"]


def test_in_progress_detection():
    from datetime import datetime, timedelta, timezone

    fresh = datetime.now(timezone.utc).isoformat()
    stale = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    mk = lambda st, t: {"metadata": {"blob_upload": {"status": st, "started_at": t}}}
    assert blob_storage.is_upload_in_progress(mk("uploading", fresh))
    assert not blob_storage.is_upload_in_progress(mk("uploading", stale))
    assert not blob_storage.is_upload_in_progress(mk("uploaded", fresh))


def test_auto_upload_disabled_does_nothing(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_AUTO_UPLOAD", False)
    fake = FakeStrategy()
    _use(monkeypatch, fake)
    asyncio.run(blob_storage.auto_upload_recording(REC))
    assert fake.uploaded == []


def test_auto_upload_skipped_when_unauthenticated(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_AUTO_UPLOAD", True)
    fake = FakeStrategy(ok=False)
    _use(monkeypatch, fake)
    asyncio.run(blob_storage.auto_upload_recording(REC))
    assert fake.uploaded == []


def test_concurrency_limit(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_MAX_CONCURRENT_UPLOADS", 2)
    monkeypatch.setattr(blob_storage, "_slots", None)
    running = peak = 0

    async def fake_run(recording, cancel=None):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1

    monkeypatch.setattr(blob_storage, "_run_upload", fake_run)

    async def go():
        await asyncio.gather(*(blob_storage.run_upload_job({"id": str(i)}) for i in range(6)))

    asyncio.run(go())
    assert peak == 2


def test_cancel_while_queued_skips_upload(monkeypatch):
    import threading

    monkeypatch.setattr(blob_storage, "_slots", None)
    states = []

    async def fake_persist(rid, st):
        states.append(st)

    monkeypatch.setattr(blob_storage, "_persist_and_emit", fake_persist)
    fake = FakeStrategy()
    _use(monkeypatch, fake)

    async def go():
        cancel = threading.Event()
        cancel.set()
        await blob_storage.run_upload_job(REC, cancel)

    asyncio.run(go())
    assert fake.uploaded == [] and states == []


def test_cancel_during_transfer_clears_state(monkeypatch):
    import threading

    monkeypatch.setattr(blob_storage, "_slots", None)
    states = []

    async def fake_persist(rid, st):
        states.append(st)

    async def fake_emit(*a, **k):
        pass

    monkeypatch.setattr(blob_storage, "_persist_and_emit", fake_persist)
    monkeypatch.setattr(blob_storage, "_emit", fake_emit)
    cancel = threading.Event()

    class Slow(FakeStrategy):
        def upload(self, file_path, key, on_progress=None):
            cancel.set()  # user cancels mid-transfer
            on_progress(1, 10)  # next progress tick must abort

    _use(monkeypatch, Slow())
    asyncio.run(blob_storage.run_upload_job(REC, cancel))
    # only the initial 'uploading' state was written; no 'uploaded'/'failed' afterwards
    assert [s["status"] for s in states if s] == ["uploading"]
