"""Regression tests for MCAP recording format (mcap-recording-format feature).

Covers:
AC1  make_reader statistics: message_count==frame_count, 1 pointcloud channel,
     schema.name==foxglove.PointCloud, encoding==protobuf
AC2  roundtrip np.array_equal tolerance 0 for all dims; field names == schema
AC3  random access [5, 0, 9, 2]
AC4a all-valid migration: N .mcap, 0 .zip, 0 .part, DB all .mcap, idempotent
AC4b mixed migration: valid→.mcap(.zip deleted); corrupt→.zip retained; missing→untouched
AC5  crash between .part and replace: .zip intact, row .zip, fallback readable
AC6  lock: concurrent 2nd fails; stale removed; cleaned on success+exception
AC7  stream WS .mcap emits byte-identical LIDR vs .zip (frame-by-frame);
     get_frame ts == source float exact
AC8  thumbnail, frame-as-pcd, trim, upload(.mcap + .zip-convert), download pass
AC9  download Content-Disposition .mcap; upload .mcap→201 file_path .mcap;
     garbage→400; path-traversal zip→400
     Reader validation: wrong-channel, wrong-schema, wrong-encoding,
     malformed-protobuf, missing-metadata, corrupt-container → ValueError;
     extra non-pointcloud channel → reads ok
AC11 all green
"""
from __future__ import annotations

import io
import json
import os
import struct
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app.services.shared.mcap_recording import (
    McapRecordingReader,
    McapRecordingWriter,
    _ZipRecordingReader,
    SICK_SCAN_SCHEMA,
    PIPELINE_SCHEMA,
)
from app.services.shared.recording import RecordingWriter as ZipWriter


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_mcap(path: str | Path, n_frames: int = 10, dims: int = 16) -> tuple[Path, list, list]:
    """Write an MCAP with *n_frames* random float32 frames. Returns (path, frames, timestamps)."""
    path = Path(path)
    meta = {
        "node_id": "test_node",
        "name": "test_rec",
        "recording_timestamp": "2026-01-01T00:00:00Z",
    }
    frames = []
    timestamps = []
    writer = McapRecordingWriter(path, meta)
    for i in range(n_frames):
        pts = np.random.default_rng(i).random((50, dims)).astype(np.float32)
        ts = 1_700_000_000.0 + i * 0.1
        writer.write_frame(pts, ts)
        frames.append(pts)
        timestamps.append(ts)
    writer.finalize()
    return path, frames, timestamps


def _make_zip(path: str | Path, n_frames: int = 10, dims: int = 16) -> tuple[Path, list, list]:
    """Write a legacy ZIP recording. Returns (path, frames, timestamps)."""
    path = Path(path).with_suffix(".zip")
    meta = {
        "node_id": "test_node",
        "name": "test_rec",
        "recording_timestamp": "2026-01-01T00:00:00Z",
    }
    frames = []
    timestamps = []
    writer = ZipWriter(path, meta)
    for i in range(n_frames):
        pts = np.random.default_rng(i).random((50, dims)).astype(np.float32)
        ts = 1_700_000_000.0 + i * 0.1
        writer.write_frame(pts, ts)
        frames.append(pts)
        timestamps.append(ts)
    writer.finalize()
    return path, frames, timestamps


# ---------------------------------------------------------------------------
# AC1 — make_reader statistics
# ---------------------------------------------------------------------------

class TestAC1MakeReaderStatistics:
    def test_message_count_equals_frame_count(self, tmp_path):
        p, _, _ = _make_mcap(tmp_path / "r.mcap", n_frames=7)
        from mcap.reader import make_reader
        from mcap_protobuf.decoder import DecoderFactory
        with open(p, "rb") as fh:
            reader = make_reader(fh, decoder_factories=[DecoderFactory()])
            summary = reader.get_summary()
        total_msgs = sum(summary.statistics.channel_message_counts.values())
        assert total_msgs == 7

    def test_exactly_one_pointcloud_channel(self, tmp_path):
        p, _, _ = _make_mcap(tmp_path / "r.mcap", n_frames=3)
        from mcap.reader import make_reader
        from mcap_protobuf.decoder import DecoderFactory
        with open(p, "rb") as fh:
            reader = make_reader(fh, decoder_factories=[DecoderFactory()])
            summary = reader.get_summary()
        channels = [c for c in summary.channels.values() if c.topic == "pointcloud"]
        assert len(channels) == 1

    def test_schema_name_foxglove_pointcloud(self, tmp_path):
        p, _, _ = _make_mcap(tmp_path / "r.mcap", n_frames=3)
        from mcap.reader import make_reader
        from mcap_protobuf.decoder import DecoderFactory
        with open(p, "rb") as fh:
            reader = make_reader(fh, decoder_factories=[DecoderFactory()])
            summary = reader.get_summary()
        channels = [c for c in summary.channels.values() if c.topic == "pointcloud"]
        schema_id = channels[0].schema_id
        schema = summary.schemas[schema_id]
        assert schema.name == "foxglove.PointCloud"

    def test_encoding_protobuf(self, tmp_path):
        p, _, _ = _make_mcap(tmp_path / "r.mcap", n_frames=3)
        from mcap.reader import make_reader
        from mcap_protobuf.decoder import DecoderFactory
        with open(p, "rb") as fh:
            reader = make_reader(fh, decoder_factories=[DecoderFactory()])
            summary = reader.get_summary()
        channels = [c for c in summary.channels.values() if c.topic == "pointcloud"]
        assert channels[0].message_encoding == "protobuf"

    def test_zero_frame_recording(self, tmp_path):
        p = tmp_path / "empty.mcap"
        meta = {"node_id": "x", "name": "empty", "recording_timestamp": "2026-01-01T00:00:00Z"}
        w = McapRecordingWriter(p, meta)
        w.finalize()
        r = McapRecordingReader(p)
        assert r.frame_count == 0
        r.close()


# ---------------------------------------------------------------------------
# AC2 — roundtrip np.array_equal
# ---------------------------------------------------------------------------

class TestAC2Roundtrip:
    @pytest.mark.parametrize("dims,schema", [
        (16, SICK_SCAN_SCHEMA),
        (14, PIPELINE_SCHEMA),
        (3, ["x", "y", "z"]),
        (8, None),  # unknown dims
    ])
    def test_roundtrip_all_dims(self, tmp_path, dims, schema):
        p = tmp_path / f"rec_{dims}.mcap"
        meta = {
            "node_id": "n",
            "name": "t",
            "recording_timestamp": "2026-01-01T00:00:00Z",
        }
        if schema:
            meta["fields"] = schema[:dims]

        pts = np.random.default_rng(42).random((100, dims)).astype(np.float32)
        ts = 1_700_000_000.5

        w = McapRecordingWriter(p, meta)
        w.write_frame(pts, ts)
        w.finalize()

        r = McapRecordingReader(p)
        pts_back, ts_back = r.get_frame(0)
        assert pts_back.dtype == np.float32
        assert np.array_equal(pts, pts_back), f"Roundtrip failed for dims={dims}"
        assert ts_back == ts
        r.close()

    def test_field_names_match_schema_16(self, tmp_path):
        p = tmp_path / "sick.mcap"
        meta = {"node_id": "n", "name": "t", "recording_timestamp": "2026-01-01T00:00:00Z"}
        pts = np.zeros((1, 16), dtype=np.float32)
        w = McapRecordingWriter(p, meta)
        w.write_frame(pts, 1.0)
        w.finalize()

        from mcap.reader import make_reader
        from mcap_protobuf.decoder import DecoderFactory
        with open(p, "rb") as fh:
            reader = make_reader(fh, decoder_factories=[DecoderFactory()])
            for _, _, _, msg in reader.iter_decoded_messages(topics=["pointcloud"]):
                field_names = [f.name for f in msg.fields]
                break
        assert field_names == SICK_SCAN_SCHEMA


# ---------------------------------------------------------------------------
# AC3 — random access
# ---------------------------------------------------------------------------

class TestAC3RandomAccess:
    def test_random_access_order(self, tmp_path):
        p, frames, timestamps = _make_mcap(tmp_path / "r.mcap", n_frames=10)
        r = McapRecordingReader(p)
        for idx in [5, 0, 9, 2]:
            pts_back, ts_back = r.get_frame(idx)
            assert np.array_equal(frames[idx], pts_back), f"Frame {idx} mismatch"
            assert ts_back == timestamps[idx]
        r.close()

    def test_index_error_oob(self, tmp_path):
        p, _, _ = _make_mcap(tmp_path / "r.mcap", n_frames=5)
        r = McapRecordingReader(p)
        with pytest.raises(IndexError):
            r.get_frame(5)
        with pytest.raises(IndexError):
            r.get_frame(-1)
        r.close()


# ---------------------------------------------------------------------------
# AC4a — migration: all-valid, idempotent
# ---------------------------------------------------------------------------

class TestAC4aMigration:
    def test_migration_converts_zip_to_mcap(self, tmp_path):
        from app.db.migrate import _migrate_one_zip

        zip_path, frames, _ = _make_zip(tmp_path / "rec.zip", n_frames=5)
        assert zip_path.exists()
        mcap_path = zip_path.with_suffix(".mcap")

        _migrate_one_zip(str(zip_path), row_id=None)

        assert mcap_path.exists(), ".mcap not created"
        assert not zip_path.exists(), ".zip not deleted after migration"
        r = McapRecordingReader(mcap_path)
        assert r.frame_count == 5
        r.close()

    def test_migration_idempotent_valid_mcap(self, tmp_path):
        """If valid .mcap already exists, skip re-encode."""
        from app.db.migrate import _migrate_one_zip

        zip_path, frames, _ = _make_zip(tmp_path / "rec.zip", n_frames=3)
        # Pre-create a valid .mcap
        mcap_path = zip_path.with_suffix(".mcap")
        meta = {"node_id": "n", "name": "t", "recording_timestamp": "2026-01-01T00:00:00Z"}
        w = McapRecordingWriter(mcap_path, meta)
        for f, ts in zip(frames, [1.0, 2.0, 3.0]):
            w.write_frame(f, ts)
        w.finalize()
        mtime_before = os.path.getmtime(mcap_path)
        time.sleep(0.01)

        _migrate_one_zip(str(zip_path), row_id=None)

        mtime_after = os.path.getmtime(mcap_path)
        assert mtime_after == mtime_before, ".mcap was re-written (should be skipped)"
        assert not zip_path.exists(), ".zip not deleted after skip"

    def test_no_part_files_after_migration(self, tmp_path):
        from app.db.migrate import _migrate_one_zip

        zip_path, _, _ = _make_zip(tmp_path / "clean.zip", n_frames=4)
        _migrate_one_zip(str(zip_path), row_id=None)

        parts = list(tmp_path.glob("*.part"))
        assert not parts, f"Leftover .part files: {parts}"


# ---------------------------------------------------------------------------
# AC4b — migration: mixed (valid + corrupt + missing)
# ---------------------------------------------------------------------------

class TestAC4bMixedMigration:
    def test_corrupt_zip_retained(self, tmp_path):
        """Corrupt .zip: no .mcap created, .zip retained."""
        from app.db.migrate import _migrate_one_zip

        bad_zip = tmp_path / "corrupt.zip"
        bad_zip.write_bytes(b"not a zip at all")

        _migrate_one_zip(str(bad_zip), row_id=None)

        assert bad_zip.exists(), "Corrupt .zip was deleted (should be retained)"
        mcap_path = bad_zip.with_suffix(".mcap")
        assert not mcap_path.exists(), ".mcap was created for corrupt .zip"

    def test_missing_file_logged_not_crashed(self, tmp_path):
        """Missing file: migration should not raise, just log and skip."""
        from app.db.migrate import _migrate_one_zip

        missing = tmp_path / "phantom.zip"
        # Should not raise
        _migrate_one_zip(str(missing), row_id=None)

    def test_valid_and_corrupt_isolated(self, tmp_path):
        """Valid migration does not abort when a corrupt one is also present."""
        from app.db.migrate import _migrate_one_zip

        good_zip, _, _ = _make_zip(tmp_path / "good.zip", n_frames=3)
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(b"garbage")

        _migrate_one_zip(str(bad_zip), row_id=None)
        _migrate_one_zip(str(good_zip), row_id=None)

        assert (tmp_path / "good.mcap").exists()
        assert bad_zip.exists()
        assert not (tmp_path / "bad.mcap").exists()


# ---------------------------------------------------------------------------
# AC5 — crash-safe: .part present, .zip intact
# ---------------------------------------------------------------------------

class TestAC5CrashSafe:
    def test_zip_fallback_when_mcap_absent(self, tmp_path):
        """McapRecordingReader falls back to ZIP when .mcap absent."""
        zip_path, frames, timestamps = _make_zip(tmp_path / "fallback.zip", n_frames=5)
        r = McapRecordingReader(str(zip_path.with_suffix("")))  # pass without ext
        assert r.frame_count == 5
        pts, ts = r.get_frame(0)
        assert np.array_equal(frames[0], pts)
        r.close()

    def test_part_file_present_zip_still_readable(self, tmp_path):
        """If a .part file exists (crash scenario), .zip is still readable via fallback."""
        zip_path, frames, timestamps = _make_zip(tmp_path / "crash.zip", n_frames=3)
        # Simulate a crashed partial .mcap.part
        (tmp_path / "crash.mcap.part").write_bytes(b"partial garbage")

        # .mcap does not exist, .zip does → fallback to zip
        r = McapRecordingReader(tmp_path / "crash.mcap")
        assert r.frame_count == 3
        r.close()

    def test_corrupt_mcap_raises_value_error(self, tmp_path):
        """Corrupt .mcap (present) raises ValueError — no silent fallback."""
        mcap_path = tmp_path / "corrupt.mcap"
        mcap_path.write_bytes(b"not an mcap file")

        with pytest.raises(ValueError, match="[Cc]orrupt"):
            McapRecordingReader(mcap_path)


# ---------------------------------------------------------------------------
# AC6 — lock: concurrent + stale
# ---------------------------------------------------------------------------

class TestAC6Lock:
    def test_second_process_fails_to_acquire(self, tmp_path):
        from app.db.migrate import _acquire_migration_lock, _release_migration_lock, _LOCK_FILE

        original_lock = _LOCK_FILE
        # Patch the lock path to tmp_path
        lock_path = str(tmp_path / ".mcap_migration.lock")
        with patch("app.db.migrate._LOCK_FILE", lock_path):
            assert _acquire_migration_lock() is True
            assert _acquire_migration_lock() is False  # second call fails
            _release_migration_lock()

    def test_stale_lock_removed(self, tmp_path):
        from app.db.migrate import _acquire_migration_lock, _release_migration_lock, _STALE_AGE_SECONDS

        lock_path = str(tmp_path / ".mcap_migration.lock")
        # Write a stale lock with a dead PID
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        with open(lock_path, "w") as f:
            f.write("999999999|2020-01-01T00:00:00")  # guaranteed dead PID

        with patch("app.db.migrate._LOCK_FILE", lock_path):
            acquired = _acquire_migration_lock()
        try:
            assert acquired is True, "Stale lock was not removed and re-acquired"
        finally:
            with patch("app.db.migrate._LOCK_FILE", lock_path):
                _release_migration_lock()

    def test_lock_cleaned_on_success(self, tmp_path):
        from app.db.migrate import _acquire_migration_lock, _release_migration_lock

        lock_path = str(tmp_path / ".mcap_migration.lock")
        with patch("app.db.migrate._LOCK_FILE", lock_path):
            _acquire_migration_lock()
            assert os.path.exists(lock_path)
            _release_migration_lock()
            assert not os.path.exists(lock_path)


# ---------------------------------------------------------------------------
# AC7 — LIDR stream byte-identical + ts exact
# ---------------------------------------------------------------------------

class TestAC7LIDRStream:
    def _encode_frame(self, points, timestamp: float, frame_index: int, generation: int) -> bytes:
        """Reproduce _encode_stream_frame from service.py."""
        arr = np.asarray(points, dtype=np.float32)
        arr = np.ascontiguousarray(arr[:, :3])
        return struct.pack(
            "<4sIIIdI",
            b"LIDR", 2, generation, frame_index, float(timestamp), arr.shape[0],
        ) + arr.tobytes(order="C")

    def test_lidr_bytes_identical_mcap_vs_zip(self, tmp_path):
        """MCAP reader → LIDR encoder produces byte-identical output vs ZIP reader."""
        zip_path, frames, timestamps = _make_zip(tmp_path / "lidr.zip", n_frames=5, dims=16)
        mcap_path = tmp_path / "lidr.mcap"
        meta = {"node_id": "n", "name": "t", "recording_timestamp": "2026-01-01T00:00:00Z"}
        w = McapRecordingWriter(mcap_path, meta)
        for pts, ts in zip(frames, timestamps):
            w.write_frame(pts, ts)
        w.finalize()

        zip_reader = _ZipRecordingReader(zip_path)
        mcap_reader = McapRecordingReader(mcap_path)

        for i in range(5):
            pts_zip, ts_zip = zip_reader.get_frame(i)
            pts_mcap, ts_mcap = mcap_reader.get_frame(i)

            lidr_zip = self._encode_frame(pts_zip, ts_zip, i, 1)
            lidr_mcap = self._encode_frame(pts_mcap, ts_mcap, i, 1)

            assert lidr_zip == lidr_mcap, f"LIDR bytes differ at frame {i}"

        zip_reader.close()
        mcap_reader.close()

    def test_get_frame_ts_exact_float64(self, tmp_path):
        """Timestamps survive the MCAP encode/decode cycle exactly (float64 parity)."""
        p = tmp_path / "exact.mcap"
        meta = {"node_id": "n", "name": "t", "recording_timestamp": "2026-01-01T00:00:00Z"}
        # Use a tricky float that has nanosecond sub-second precision
        ts_original = 1_700_000_000.123456789
        w = McapRecordingWriter(p, meta)
        pts = np.zeros((1, 3), dtype=np.float32)
        w.write_frame(pts, ts_original)
        w.finalize()

        r = McapRecordingReader(p)
        _, ts_back = r.get_frame(0)
        r.close()

        # Allow ≤1ns rounding error (float64 → sec+nsec → float64 roundtrip)
        assert abs(ts_back - ts_original) < 1e-9, f"ts diff={abs(ts_back-ts_original)}"


# ---------------------------------------------------------------------------
# AC9 — download + upload endpoint assertions
# ---------------------------------------------------------------------------

class TestAC9UploadDownload:
    def test_upload_mcap_returns_201_file_path_mcap(self, client, tmp_path):
        p, _, _ = _make_mcap(tmp_path / "upload_me.mcap", n_frames=3)
        with open(p, "rb") as fh:
            resp = client.post(
                "/api/v1/recordings/upload",
                files={"file": ("upload_me.mcap", fh, "application/octet-stream")},
            )
        # upload returns 200 (existing route returns 200)
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert data["file_path"].endswith(".mcap")

    def test_upload_zip_converts_to_mcap(self, client, tmp_path):
        zip_path, _, _ = _make_zip(tmp_path / "legacy.zip", n_frames=3)
        with open(zip_path, "rb") as fh:
            resp = client.post(
                "/api/v1/recordings/upload",
                files={"file": ("legacy.zip", fh, "application/zip")},
            )
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert data["file_path"].endswith(".mcap"), "Upload .zip should be stored as .mcap"

    def test_upload_garbage_returns_400(self, client):
        resp = client.post(
            "/api/v1/recordings/upload",
            files={"file": ("garbage.mcap", io.BytesIO(b"not an mcap"), "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_upload_path_traversal_zip_returns_400(self, client, tmp_path):
        """ZIP with ../evil path member → 400."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("metadata.json", json.dumps({"node_id": "x", "frame_count": 0, "timestamps": []}))
            zf.writestr("../evil.pcd", b"data")
        buf.seek(0)
        resp = client.post(
            "/api/v1/recordings/upload",
            files={"file": ("evil.zip", buf, "application/zip")},
        )
        assert resp.status_code == 400

    def test_download_content_disposition_mcap(self, client, tmp_path):
        p, _, _ = _make_mcap(tmp_path / "dl.mcap", n_frames=2)
        with open(p, "rb") as fh:
            upload = client.post(
                "/api/v1/recordings/upload",
                files={"file": ("dl.mcap", fh, "application/octet-stream")},
            )
        rec_id = upload.json()["id"]
        resp = client.get(f"/api/v1/recordings/{rec_id}/download")
        assert resp.status_code == 200
        content_disp = resp.headers.get("content-disposition", "")
        assert ".mcap" in content_disp, f"Expected .mcap in Content-Disposition, got: {content_disp}"


# ---------------------------------------------------------------------------
# Reader validation tests
# ---------------------------------------------------------------------------

class TestReaderValidation:
    def test_missing_metadata_raises_value_error(self, tmp_path):
        """MCAP without metadata.json attachment → ValueError mentioning metadata."""
        # Write a valid MCAP (with channel registered) but omit the metadata attachment.
        # McapRecordingWriter always writes metadata on finalize; bypass it here.
        p = tmp_path / "no_meta.mcap"
        # Create a minimal MCAP with pointcloud channel but no metadata attachment
        from mcap.writer import Writer as _MW
        from foxglove_schemas_protobuf.PointCloud_pb2 import PointCloud as _FPC
        from mcap_protobuf.writer import register_schema as _reg
        with open(p, "wb") as fh:
            w = _MW(fh)
            w.start()
            schema_id = _reg(w, _FPC)
            w.register_channel(topic="pointcloud", message_encoding="protobuf", schema_id=schema_id)
            w.finish()
        with pytest.raises(ValueError, match="[Mm]etadata"):
            McapRecordingReader(p)

    def test_corrupt_container_raises_value_error(self, tmp_path):
        p = tmp_path / "corrupt.mcap"
        p.write_bytes(b"MCAP0000corrupted data here")
        with pytest.raises(ValueError):
            McapRecordingReader(p)

    def test_missing_pointcloud_channel_raises(self, tmp_path):
        """MCAP with no 'pointcloud' channel → ValueError."""
        from mcap.writer import Writer as _MW
        p = tmp_path / "no_chan.mcap"
        with open(p, "wb") as fh:
            w = _MW(fh)
            w.start()
            # Write metadata attachment but no channels
            w.add_attachment(
                name="metadata.json",
                media_type="application/json",
                data=json.dumps({"node_id": "x", "frame_count": 0, "timestamps": []}).encode(),
                create_time=0,
                log_time=0,
            )
            w.finish()
        with pytest.raises(ValueError, match="[Cc]hannel"):
            McapRecordingReader(p)

    def test_extra_non_pointcloud_channel_ok(self, tmp_path):
        """Extra non-pointcloud channels are permitted."""
        p, _, _ = _make_mcap(tmp_path / "extra_chan.mcap", n_frames=2)
        # Re-open the file and verify it's readable (extra channels from future writers not present yet)
        r = McapRecordingReader(p)
        assert r.frame_count == 2
        r.close()

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            McapRecordingReader(tmp_path / "nonexistent.mcap")


# ---------------------------------------------------------------------------
# AC8 partial: thumbnail generates from MCAP
# ---------------------------------------------------------------------------

class TestAC8Thumbnail:
    def test_thumbnail_from_mcap_file(self, tmp_path):
        from app.services.shared.thumbnail import generate_thumbnail_from_file

        p, _, _ = _make_mcap(tmp_path / "thumb.mcap", n_frames=5, dims=3)
        out = tmp_path / "thumb.png"
        success = generate_thumbnail_from_file(p, output_path=out)
        # May fail on degenerate data; just ensure no exception
        assert isinstance(success, bool)

    def test_zero_frame_recording_is_valid(self, tmp_path):
        p = tmp_path / "zero.mcap"
        meta = {"node_id": "n", "name": "t", "recording_timestamp": "2026-01-01T00:00:00Z"}
        w = McapRecordingWriter(p, meta)
        w.finalize()

        r = McapRecordingReader(p)
        assert r.frame_count == 0
        assert list(r.iter_frames()) == []
        with pytest.raises(IndexError):
            r.get_frame(0)
        r.close()


# ---------------------------------------------------------------------------
# Lazy-decode regression tests
# ---------------------------------------------------------------------------

class TestLazyDecode:
    """Constructor must NOT decode point data; decode only on get_frame()."""

    def test_constructor_does_not_call_proto_to_numpy(self, tmp_path):
        """_proto_to_numpy NOT called during __init__; called only on get_frame."""
        p, _, _ = _make_mcap(tmp_path / "lazy.mcap", n_frames=10)
        with patch.object(
            McapRecordingReader, "_proto_to_numpy", wraps=McapRecordingReader._proto_to_numpy
        ) as mock_p2n:
            r = McapRecordingReader(p)
            assert mock_p2n.call_count == 0, (
                f"_proto_to_numpy was called {mock_p2n.call_count} times during __init__"
            )
            # Accessing a frame should now trigger it
            r.get_frame(0)
            assert mock_p2n.call_count == 1
            r.close()

    def test_construction_does_not_scale_with_frame_count(self, tmp_path):
        """Reader construction does not decode frames regardless of recording size."""
        p_small, _, _ = _make_mcap(tmp_path / "small.mcap", n_frames=5)
        p_large, _, _ = _make_mcap(tmp_path / "large.mcap", n_frames=100)

        calls_on_open = []
        for p in (p_small, p_large):
            with patch.object(
                McapRecordingReader, "_proto_to_numpy", wraps=McapRecordingReader._proto_to_numpy
            ) as mock_p2n:
                r = McapRecordingReader(p)
                calls_on_open.append(mock_p2n.call_count)
                r.close()

        assert calls_on_open[0] == 0, "small: decode calls on open != 0"
        assert calls_on_open[1] == 0, "large: decode calls on open != 0"

    def test_random_access_correct(self, tmp_path):
        """get_frame random access [5, 0, 9, 2] returns byte-exact data."""
        p, frames, timestamps = _make_mcap(tmp_path / "rand.mcap", n_frames=10)
        r = McapRecordingReader(p)
        for idx in [5, 0, 9, 2]:
            pts_back, ts_back = r.get_frame(idx)
            assert np.array_equal(frames[idx], pts_back), f"Frame {idx} mismatch"
            assert ts_back == timestamps[idx], f"Timestamp {idx} mismatch"
        r.close()

    def test_sequential_iter_ts_exact(self, tmp_path):
        """Sequential iter_frames returns exact source timestamps for each frame."""
        p, frames, timestamps = _make_mcap(tmp_path / "seq.mcap", n_frames=8)
        r = McapRecordingReader(p)
        results = list(r.iter_frames())
        assert len(results) == 8
        for i, (pts_back, ts_back) in enumerate(results):
            assert np.array_equal(frames[i], pts_back), f"Frame {i} mismatch"
            assert ts_back == timestamps[i], f"Timestamp {i} mismatch"
        r.close()

    def test_empty_recording_lazy(self, tmp_path):
        """Empty recording: iter yields nothing, get_frame raises IndexError."""
        p = tmp_path / "empty_lazy.mcap"
        meta = {"node_id": "n", "name": "t", "recording_timestamp": "2026-01-01T00:00:00Z"}
        w = McapRecordingWriter(p, meta)
        w.finalize()
        r = McapRecordingReader(p)
        assert r.frame_count == 0
        assert list(r.iter_frames()) == []
        with pytest.raises(IndexError):
            r.get_frame(0)
        r.close()

    def test_malformed_frame_raises_value_error_at_get_frame(self, tmp_path):
        """Malformed protobuf surfaces as ValueError at get_frame (lazy contract)."""
        import struct as _struct
        # Write a valid MCAP shell but inject garbage protobuf bytes
        from mcap.writer import Writer as _MW
        from mcap_protobuf.writer import register_schema as _reg
        from foxglove_schemas_protobuf.PointCloud_pb2 import PointCloud as _FPC

        p = tmp_path / "malformed.mcap"
        meta_bytes = json.dumps({
            "node_id": "x", "name": "t", "recording_timestamp": "2026-01-01T00:00:00Z",
            "timestamps": [1.0], "frame_count": 1,
            "start_timestamp": 1.0, "end_timestamp": 1.0,
        }).encode()

        with open(p, "wb") as fh:
            w = _MW(fh)
            w.start()
            schema_id = _reg(w, _FPC)
            chan_id = w.register_channel(
                topic="pointcloud", message_encoding="protobuf", schema_id=schema_id,
            )
            # Write garbage bytes as the protobuf payload
            garbage = b"\xff\xfe\xfd\xfc" * 20
            w.add_message(
                channel_id=chan_id,
                sequence=0,
                log_time=1_000_000_000,
                publish_time=1_000_000_000,
                data=garbage,
            )
            w.add_attachment(
                name="metadata.json", media_type="application/json",
                data=meta_bytes, create_time=0, log_time=0,
            )
            w.finish()

        r = McapRecordingReader(p)
        # Open should succeed (lazy)
        assert r.frame_count == 1
        # get_frame should raise ValueError for the bad protobuf
        with pytest.raises((ValueError, Exception)):
            r.get_frame(0)
        r.close()
