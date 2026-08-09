import asyncio
import json
import struct
from unittest.mock import AsyncMock, MagicMock, patch, call

import numpy as np
import pytest

from app.db.models import RecordingModel
from app.services.shared.recording import RecordingWriter


def _receive_json_after_streamed_frames(websocket):
    while True:
        message = websocket.receive()
        if message.get("text") is not None:
            return json.loads(message["text"])


def _recording(tmp_path, db_session):
    archive = tmp_path / "playback.zip"
    with RecordingWriter(archive, {"name": "playback"}) as writer:
        writer.write_frame(np.array([[1.0, 2.0, 3.0] + list(range(4, 17))], dtype=np.float32), 10.0)
        writer.write_frame(np.array([[4.0, 5.0, 6.0] + list(range(7, 20))], dtype=np.float32), 11.0)
    db_session.add(RecordingModel(
        id="recording-1", name="playback", node_id="node-1",
        file_path=str(archive), file_size_bytes=archive.stat().st_size,
        frame_count=2, duration_seconds=1.0,
        recording_timestamp="2026-01-01T00:00:00Z", metadata_json="{}",
    ))
    db_session.commit()


def test_recording_stream_auto_start_emits_lidr_frame(client, tmp_path):
    from app.db.models import get_db

    db = next(get_db())
    try:
        _recording(tmp_path, db)
    finally:
        db.close()

    with client.websocket_connect("/api/v1/recordings/recording-1/stream") as websocket:
        assert websocket.receive_json() == {
            "type": "ready", "frameCount": 2, "startFrameIndex": 0, "generation": 0,
        }
        websocket.send_text(json.dumps({"type": "start", "frameIndex": 0}))
        assert websocket.receive_json() == {"type": "seeked", "frameIndex": 0, "generation": 1}

        frame = websocket.receive_bytes()
        magic, version, generation, frame_index, timestamp, point_count = struct.unpack(
            "<4sIIIdI", frame[:28]
        )
        assert (magic, version, generation, frame_index, timestamp, point_count) == (
            b"LIDR", 2, 1, 0, 10.0, 1,
        )
        assert np.frombuffer(frame, dtype=np.float32, offset=28).tolist() == [1.0, 2.0, 3.0]


def test_recording_stream_seek_emits_requested_frame(client, tmp_path):
    from app.db.models import get_db

    db = next(get_db())
    try:
        _recording(tmp_path, db)
    finally:
        db.close()

    with client.websocket_connect("/api/v1/recordings/recording-1/stream") as websocket:
        websocket.receive_json()
        websocket.send_text('{"type":"start","frameIndex":0}')
        websocket.receive_json()
        websocket.receive_bytes()

        websocket.send_text('{"type":"seek","frameIndex":1}')
        message = websocket.receive()
        while message.get("bytes") is not None:
            message = websocket.receive()
        assert json.loads(message["text"]) == {
            "type": "seeked", "frameIndex": 1, "generation": 2,
        }
        frame = websocket.receive_bytes()
        assert struct.unpack("<4sIIIdI", frame[:28])[3] == 1


def test_recording_stream_pause_start_resumes_from_next_frame(client, tmp_path):
    from app.db.models import get_db

    db = next(get_db())
    try:
        _recording(tmp_path, db)
    finally:
        db.close()

    with client.websocket_connect("/api/v1/recordings/recording-1/stream") as websocket:
        websocket.receive_json()
        websocket.send_text('{"type":"start","frameIndex":0}')
        websocket.receive_json()
        assert struct.unpack("<4sIIIdI", websocket.receive_bytes()[:28])[3] == 0
        websocket.send_text('{"type":"pause"}')
        paused = _receive_json_after_streamed_frames(websocket)
        assert paused["type"] == "paused"
        assert paused["frameIndex"] in {1, 2}
        websocket.send_text('{"type":"start"}')
        assert websocket.receive_json() == {"type": "seeked", "frameIndex": paused["frameIndex"], "generation": 2}
        if paused["frameIndex"] < 2:
            assert struct.unpack("<4sIIIdI", websocket.receive_bytes()[:28])[3] == 1
        else:
            assert websocket.receive_json() == {"type": "eof", "frameIndex": 2, "generation": 2}


def test_recording_stream_pause_before_start_and_repeated_pause(client, tmp_path):
    from app.db.models import get_db

    db = next(get_db())
    try:
        _recording(tmp_path, db)
    finally:
        db.close()

    with client.websocket_connect("/api/v1/recordings/recording-1/stream") as websocket:
        websocket.receive_json()
        websocket.send_text('{"type":"pause"}')
        assert websocket.receive_json()["code"] == "not_started"
        websocket.send_text('{"type":"start","frameIndex":0}')
        websocket.receive_json()
        websocket.receive_bytes()
        websocket.send_text('{"type":"pause"}')
        first = _receive_json_after_streamed_frames(websocket)
        websocket.send_text('{"type":"pause"}')
        assert _receive_json_after_streamed_frames(websocket) == first


def test_recording_stream_paused_seek_emits_only_target_until_start(client, tmp_path):
    from app.db.models import get_db

    db = next(get_db())
    try:
        _recording(tmp_path, db)
    finally:
        db.close()

    with client.websocket_connect("/api/v1/recordings/recording-1/stream") as websocket:
        websocket.receive_json()
        websocket.send_text('{"type":"seek","frameIndex":1}')
        assert websocket.receive_json() == {"type": "seeked", "frameIndex": 1, "generation": 1}
        frame = websocket.receive_bytes()
        assert struct.unpack("<4sIIIdI", frame[:28])[3] == 1
        websocket.send_text('{"type":"start"}')
        assert websocket.receive_json() == {"type": "seeked", "frameIndex": 2, "generation": 2}
        assert websocket.receive_json() == {"type": "eof", "frameIndex": 2, "generation": 2}


# ---------------------------------------------------------------------------
# Regression tests: accept-before-DB ordering (prevents docker-only 403)
# ---------------------------------------------------------------------------

def test_recording_stream_not_found_closes_after_accept(client):
    """Not-found path: endpoint must accept() then close(1008), not 403."""
    with client.websocket_connect("/api/v1/recordings/does-not-exist/stream") as ws:
        msg = ws.receive()
        # After accept, server sends a close frame with code 1008
        assert msg.get("type") == "websocket.close"
        assert msg.get("code") == 1008


@pytest.mark.asyncio
async def test_accept_called_before_db_lookup():
    """accept() must be the FIRST awaited call — before any DB work.

    Patch asyncio.to_thread (DB lookup) and websocket.accept. Verify accept
    is awaited first, then to_thread is called for the DB work.
    """
    from app.api.v1.recordings.handler import recordings_stream_endpoint

    call_order: list[str] = []

    ws = MagicMock()

    async def fake_accept():
        call_order.append("accept")

    async def fake_close(**kwargs):
        call_order.append("close")

    ws.accept = fake_accept
    ws.close = fake_close

    # to_thread returns None → recording not found path (simpler to test ordering)
    original_to_thread = asyncio.to_thread

    async def fake_to_thread(fn, *args, **kwargs):
        call_order.append("to_thread")
        return None  # simulate not-found

    with patch("app.api.v1.recordings.handler.asyncio.to_thread", side_effect=fake_to_thread):
        await recordings_stream_endpoint(ws, "any-id")

    assert call_order[0] == "accept", "accept() must be called before DB lookup"
    assert "to_thread" in call_order, "DB lookup must run via asyncio.to_thread"
    assert call_order.index("accept") < call_order.index("to_thread")


@pytest.mark.asyncio
async def test_stream_recording_does_not_call_accept():
    """stream_recording must NOT call websocket.accept() — endpoint owns accept now."""
    from app.api.v1.recordings.service import stream_recording

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()
    ws.receive = AsyncMock(return_value={"type": "websocket.disconnect"})
    ws.client_state = MagicMock()
    ws.client_state.name = "CONNECTED"

    fake_recording = {
        "id": "rec-1",
        "file_path": "/nonexistent/path.zip",
    }

    # RecordingReader init will fail → stream_recording sends error + closes
    await stream_recording(ws, fake_recording)

    ws.accept.assert_not_called()

