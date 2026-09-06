import asyncio
import json
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# Save real asyncio.sleep BEFORE any patching — used by fake_sleep helpers
# to yield control without recursing into the patched version.
_real_sleep = asyncio.sleep

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
async def test_produce_pacing_sleeps_correct_deltas():
    """produce() must call asyncio.sleep using even-spacing (duration / (frame_count-1))."""
    from app.api.v1.recordings.service import stream_recording

    # 3 frames, duration = 1.2s → interval = 1.2 / 2 = 0.6s
    frames = [
        (np.zeros((1, 16), dtype=np.float32), 100.0),
        (np.zeros((1, 16), dtype=np.float32), 100.5),
        (np.zeros((1, 16), dtype=np.float32), 101.2),
    ]

    mock_reader = MagicMock()
    mock_reader.frame_count = 3
    mock_reader.duration = 1.2  # even-spacing uses this
    mock_reader.get_frame = MagicMock(side_effect=lambda i: frames[i])

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_bytes = AsyncMock()

    commands = [
        {"type": "websocket.receive", "text": json.dumps({"type": "start", "frameIndex": 0})},
        # Disconnect after producer runs
        {"type": "websocket.disconnect"},
    ]
    cmd_iter = iter(commands)

    async def fake_receive():
        return next(cmd_iter)

    ws.receive = fake_receive
    ws.client_state = MagicMock()
    ws.client_state.name = "CONNECTED"

    sleep_calls: list[float] = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    fake_loop = MagicMock()
    fake_loop.time = MagicMock(return_value=0.0)

    send_json_responses: list[dict] = []

    async def fake_send_json(data):
        send_json_responses.append(data)

    ws.send_json = fake_send_json

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("app.api.v1.recordings.service.RecordingReader", return_value=mock_reader),
        patch("app.api.v1.recordings.service.asyncio.to_thread", side_effect=fake_to_thread),
        patch("app.api.v1.recordings.service.asyncio.sleep", side_effect=fake_sleep),
        patch("app.api.v1.recordings.service.asyncio.get_event_loop", return_value=fake_loop),
    ):
        await stream_recording(ws, {"id": "rec-1", "file_path": "/fake.zip"})

    # Even-spacing: interval = 1.2 / 2 = 0.6s
    # Frame 0: no sleep (anchor set).
    # Frame 1: offset=1, target = 0 + 0.6 = 0.6, clock frozen at 0 → sleep 0.6
    # Frame 2: offset=2, target = 0 + 1.2 = 1.2, clock frozen at 0 → sleep 1.2
    assert len(sleep_calls) == 2
    assert abs(sleep_calls[0] - 0.6) < 0.01, f"Expected 0.6, got {sleep_calls[0]}"
    assert abs(sleep_calls[1] - 1.2) < 0.01, f"Expected 1.2, got {sleep_calls[1]}"
    # All sleeps non-negative
    assert all(d >= 0 for d in sleep_calls)


@pytest.mark.asyncio
async def test_produce_pacing_no_stall_for_gapped_timestamps():
    """produce() must NOT stall when per-frame timestamps have large gaps.

    Even-spacing completely ignores per-frame timestamps; any gap in the
    timestamp data must NOT translate into a sleep > interval.

    Setup: 3 frames where frame[1] has a 5s gap in recording time.
    Old clamp-based pacing would sleep ~1s at frame[1] (visible stall).
    Even-spacing must sleep only interval = duration/(N-1) each frame.
    """
    from app.api.v1.recordings.service import stream_recording

    # Gap between frame 0 and 1 is 5s in recording time
    frames = [
        (np.zeros((1, 16), dtype=np.float32), 100.0),
        (np.zeros((1, 16), dtype=np.float32), 105.0),  # 5s gap — must NOT cause 5s or 1s stall
        (np.zeros((1, 16), dtype=np.float32), 105.1),
    ]

    mock_reader = MagicMock()
    mock_reader.frame_count = 3
    mock_reader.duration = 0.2  # total recording = 200ms → interval = 0.1s
    mock_reader.get_frame = MagicMock(side_effect=lambda i: frames[i])

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_bytes = AsyncMock()

    commands = [
        {"type": "websocket.receive", "text": json.dumps({"type": "start", "frameIndex": 0})},
        {"type": "websocket.disconnect"},
    ]
    cmd_iter = iter(commands)

    async def fake_receive():
        return next(cmd_iter)

    ws.receive = fake_receive
    ws.client_state = MagicMock()
    ws.client_state.name = "CONNECTED"

    sleep_calls: list[float] = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    fake_loop = MagicMock()
    fake_loop.time = MagicMock(return_value=0.0)

    send_json_responses: list[dict] = []

    async def fake_send_json(data):
        send_json_responses.append(data)

    ws.send_json = fake_send_json

    async def fake_to_thread_gap(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("app.api.v1.recordings.service.RecordingReader", return_value=mock_reader),
        patch("app.api.v1.recordings.service.asyncio.to_thread", side_effect=fake_to_thread_gap),
        patch("app.api.v1.recordings.service.asyncio.sleep", side_effect=fake_sleep),
        patch("app.api.v1.recordings.service.asyncio.get_event_loop", return_value=fake_loop),
    ):
        await stream_recording(ws, {"id": "rec-1", "file_path": "/fake.zip"})

    # Even-spacing: interval = 0.2 / 2 = 0.1s
    # Frame 0: no sleep.
    # Frame 1: sleep = 0.1 (NOT 1.0 or 5.0 — gap in timestamps must be ignored)
    # Frame 2: sleep = 0.2
    assert len(sleep_calls) == 2
    # No sleep may exceed interval significantly — the 5s timestamp gap must NOT stall
    assert all(s <= 0.25 for s in sleep_calls), (
        f"Stall detected: {sleep_calls}. Large timestamp gap (5s) leaked into sleep. "
        "Even-spacing must ignore per-frame timestamps."
    )
    assert abs(sleep_calls[0] - 0.1) < 0.01, f"Frame 1 expected 0.1s, got {sleep_calls[0]}"
    assert abs(sleep_calls[1] - 0.2) < 0.01, f"Frame 2 expected 0.2s, got {sleep_calls[1]}"


@pytest.mark.asyncio
async def test_produce_pacing_no_negative_sleep():
    """produce() must never call asyncio.sleep with a negative value.

    Even-spacing targets are always non-negative with a frozen clock starting at 0.
    With an advancing clock the sleep_delta guard (> 0 check) prevents negative calls.
    """
    from app.api.v1.recordings.service import stream_recording

    # Non-monotonic timestamps are irrelevant for even-spacing — the pacing ignores them.
    # Verify no negative sleep occurs when clock is frozen at 0.
    frames = [
        (np.zeros((1, 16), dtype=np.float32), 100.0),
        (np.zeros((1, 16), dtype=np.float32), 99.5),  # backwards — irrelevant with even-spacing
        (np.zeros((1, 16), dtype=np.float32), 100.2),
    ]

    mock_reader = MagicMock()
    mock_reader.frame_count = 3
    mock_reader.duration = 0.4  # 400ms → interval = 0.2s
    mock_reader.get_frame = MagicMock(side_effect=lambda i: frames[i])

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_bytes = AsyncMock()

    commands = [
        {"type": "websocket.receive", "text": json.dumps({"type": "start", "frameIndex": 0})},
        {"type": "websocket.disconnect"},
    ]
    cmd_iter = iter(commands)

    async def fake_receive():
        return next(cmd_iter)

    ws.receive = fake_receive
    ws.client_state = MagicMock()
    ws.client_state.name = "CONNECTED"

    sleep_calls: list[float] = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    fake_loop = MagicMock()
    fake_loop.time = MagicMock(return_value=0.0)

    send_json_responses: list[dict] = []

    async def fake_send_json(data):
        send_json_responses.append(data)

    ws.send_json = fake_send_json

    async def fake_to_thread_3(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("app.api.v1.recordings.service.RecordingReader", return_value=mock_reader),
        patch("app.api.v1.recordings.service.asyncio.to_thread", side_effect=fake_to_thread_3),
        patch("app.api.v1.recordings.service.asyncio.sleep", side_effect=fake_sleep),
        patch("app.api.v1.recordings.service.asyncio.get_event_loop", return_value=fake_loop),
    ):
        await stream_recording(ws, {"id": "rec-1", "file_path": "/fake.zip"})

    # All sleeps must be non-negative
    assert all(d >= 0 for d in sleep_calls), f"Negative sleep detected: {sleep_calls}"
    # Even-spacing: interval=0.2. Frame 1: sleep=0.2, Frame 2: sleep=0.4 (clock frozen at 0)
    assert len(sleep_calls) == 2
    assert abs(sleep_calls[0] - 0.2) < 0.01
    assert abs(sleep_calls[1] - 0.4) < 0.01


@pytest.mark.asyncio
async def test_produce_pacing_even_spacing_independent_of_timestamps():
    """Even-spacing sleep must depend only on duration/frame_count, not per-frame timestamps.

    Two setups with identical duration and frame_count but very different per-frame
    timestamps (one smooth, one with a huge gap) must produce identical sleep schedules.
    """
    from app.api.v1.recordings.service import stream_recording

    async def _run_with_frames(frames_list):
        mock_reader = MagicMock()
        mock_reader.frame_count = 3
        mock_reader.duration = 0.2  # interval = 0.1s
        mock_reader.get_frame = MagicMock(side_effect=lambda i: frames_list[i])

        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_bytes = AsyncMock()

        commands = [
            {"type": "websocket.receive", "text": json.dumps({"type": "start", "frameIndex": 0})},
            {"type": "websocket.disconnect"},
        ]
        cmd_iter = iter(commands)

        async def fake_receive():
            return next(cmd_iter)

        ws.receive = fake_receive
        ws.client_state = MagicMock()
        ws.client_state.name = "CONNECTED"

        sleep_calls: list[float] = []

        async def fake_sleep(delay):
            sleep_calls.append(delay)

        fake_loop = MagicMock()
        fake_loop.time = MagicMock(return_value=0.0)

        async def fake_send_json(data):
            pass

        ws.send_json = fake_send_json

        async def fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with (
            patch("app.api.v1.recordings.service.RecordingReader", return_value=mock_reader),
            patch("app.api.v1.recordings.service.asyncio.to_thread", side_effect=fake_to_thread),
            patch("app.api.v1.recordings.service.asyncio.sleep", side_effect=fake_sleep),
            patch("app.api.v1.recordings.service.asyncio.get_event_loop", return_value=fake_loop),
        ):
            await stream_recording(ws, {"id": "rec-1", "file_path": "/fake.zip"})

        return sleep_calls

    # Smooth 0.1s spacing
    smooth_frames = [
        (np.zeros((1, 16), dtype=np.float32), 100.0),
        (np.zeros((1, 16), dtype=np.float32), 100.1),
        (np.zeros((1, 16), dtype=np.float32), 100.2),
    ]
    # 5s gap between frames 0 and 1 (Root Cause B scenario)
    gapped_frames = [
        (np.zeros((1, 16), dtype=np.float32), 100.0),
        (np.zeros((1, 16), dtype=np.float32), 105.0),  # 5s gap
        (np.zeros((1, 16), dtype=np.float32), 105.1),
    ]

    smooth_sleeps = await _run_with_frames(smooth_frames)
    gapped_sleeps = await _run_with_frames(gapped_frames)

    # Both must produce identical sleep schedules: [0.1, 0.2]
    assert smooth_sleeps == gapped_sleeps, (
        f"Sleep schedules differ: smooth={smooth_sleeps}, gapped={gapped_sleeps}. "
        "Even-spacing must ignore per-frame timestamps."
    )
    assert len(gapped_sleeps) == 2
    assert abs(gapped_sleeps[0] - 0.1) < 0.01
    assert abs(gapped_sleeps[1] - 0.2) < 0.01


@pytest.mark.asyncio
async def test_produce_seek_resume_reanchors_per_run():
    """Second produce() call (seek-resume) anchors to ITS first frame, not run-0 timestamps.

    Setup: 7-frame recording.
      frames[0..4]: t=100.0..100.4 (0.1s spacing)
      frames[5]:   t=5000.0  (far ahead — simulates recording with large timestamp skip)
      frames[6]:   t=5000.1

    stream_recording receives:
      1. start at frame 0  → produce(0) runs frames 0..4, then EOF
         (frame_count set to 5 initially — replaced by separate mock below)

    Simpler approach: drive stream_recording with a seek command that triggers
    produce(frame_index+1) starting at frame 5. We verify frame 6's sleep is ~0.1
    (re-anchored to frame 5's timestamp), NOT ~4900s (leaked from frame-0 anchor).

    Recording: frames 0-4 at t=100+i*0.1, frames 5-6 at t=5000.0, 5000.1
    Commands: start@0 (produce runs all; we stop early via EOF), seek@5 (paused run)
    After seek@5: send_frame(5) emitted, was_paused=False so produce(6) starts.
    Frame 6 sleep should be ~0.1 (delta from anchor set at frame 5, t=5000.0).
    """
    from app.api.v1.recordings.service import stream_recording

    # 8-frame recording:
    #   frames 0-4:  t=100.0..100.4 (0.1s spacing) — run 0 starts here
    #   frame  5:    t=5000.0  (far-ahead anchor frame for seek target)
    #   frame  6:    t=5000.0  (anchor frame for produce(6); no sleep — first frame)
    #   frame  7:    t=5000.1  (second frame of produce(6); sleep ~0.1 expected)
    #
    # Commands:
    #   start@0  → produce(0) begins; first sleep (frame 1) → fake_sleep blocks → seek arrives
    #   seek@5   → produce(0) cancelled; send_frame(5) emitted; was_paused=False → produce(6) starts
    #              produce(6) frame 6 → anchor set; frame 7 → sleep(~0.1)
    #   disconnect
    #
    # Anchor leak check: if anchor_timestamp leaked from produce(0) (=100.0),
    #   frame 7 raw_delta = 5000.1 - 100.0 = 4900.1 → burst sleep detected.
    # With correct re-anchor: frame 7 raw_delta = 5000.1 - 5000.0 = 0.1 → sleep ~0.1.

    frames = [
                 (np.zeros((1, 16), dtype=np.float32), 100.0 + i * 0.1) for i in range(5)
             ] + [
                 (np.zeros((1, 16), dtype=np.float32), 5000.0),  # frame 5 — seek target, send_frame only
                 (np.zeros((1, 16), dtype=np.float32), 5000.0),  # frame 6 — anchor of produce(6)
                 (np.zeros((1, 16), dtype=np.float32), 5000.1),  # frame 7 — first paced sleep of produce(6)
             ]

    mock_reader = MagicMock()
    mock_reader.frame_count = 8
    # duration = 0.7 → interval = 0.7 / (8-1) = 0.1s
    # Even-spacing: produce(start_index=6) frame 7 → offset=1 → sleep = 0.1s
    mock_reader.duration = 0.7
    mock_reader.get_frame = MagicMock(side_effect=lambda i: frames[i])

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_bytes = AsyncMock()

    # Command sequence:
    #   1. start@0 → produce(0..6) starts running
    #   2. seek@5  → producer cancelled, send_frame(5), produce(6) starts
    #   3. disconnect
    # We need seek to arrive while produce(0) is running (sleeping).
    # Use an event: fake_sleep blocks until seek has been queued, then unblocks.
    seek_event = asyncio.Event()
    first_sleep_reached = asyncio.Event()

    commands = [
        {"type": "websocket.receive", "text": json.dumps({"type": "start", "frameIndex": 0})},
        {"type": "websocket.receive", "text": json.dumps({"type": "seek", "frameIndex": 5})},
        {"type": "websocket.disconnect"},
    ]
    cmd_index = 0
    cmd_lock = asyncio.Lock()

    async def fake_receive():
        nonlocal cmd_index
        # Stall second receive until first sleep fires (producer is running)
        if cmd_index == 1:
            await first_sleep_reached.wait()
        async with cmd_lock:
            msg = commands[cmd_index]
            cmd_index += 1
        return msg

    ws.receive = fake_receive
    ws.client_state = MagicMock()
    ws.client_state.name = "CONNECTED"

    # Per-run sleep tracking: run_id increments when second produce() starts.
    # Strategy: detect run boundary via send_json "seeked" gen==2 (seek@5 acknowledgement).
    # Note: current_run_id must be nonlocal so fake_sleep sees the update.
    sleep_calls: list[tuple[int, float]] = []  # (call_number, delay)
    sleep_run_ids: list[int] = []  # run_id for each sleep call (0=first produce, 1=second)
    call_counter = 0
    current_run_id = 0  # bumped to 1 when second produce() starts

    async def fake_sleep(delay):
        nonlocal call_counter
        n = call_counter
        call_counter += 1
        sleep_calls.append((n, delay))
        sleep_run_ids.append(current_run_id)
        if n == 0:
            # Signal that producer(0) is sleeping — let seek command through.
            first_sleep_reached.set()
            # Block here so the event loop can process the seek command and cancel
            # this producer task.  We wait on an asyncio.Event that will never fire
            # — the CancelledError from task.cancel() will interrupt this await,
            # which is exactly the behaviour we want to test (cancellation propagates).
            # Use _real_sleep with a long timeout as a cancellable blocker; CancelledError
            # raised here will propagate out of fake_sleep and cancel produce(0).
            await _real_sleep(3600)

    # Monotonic time: stays 0.0 so sleep_delta = raw_delta exactly
    fake_loop = MagicMock()
    fake_loop.time = MagicMock(return_value=0.0)

    send_json_responses: list[dict] = []

    async def fake_send_json(data):
        nonlocal current_run_id
        send_json_responses.append(data)
        # When seek@5 acknowledgement arrives (seeked, generation==2), second produce() is
        # about to start — bump run_id so subsequent sleeps are tagged as run 1.
        if data.get("type") == "seeked" and data.get("generation") == 2:
            current_run_id = 1

    ws.send_json = fake_send_json

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("app.api.v1.recordings.service.RecordingReader", return_value=mock_reader),
        patch("app.api.v1.recordings.service.asyncio.to_thread", side_effect=fake_to_thread),
        patch("app.api.v1.recordings.service.asyncio.sleep", side_effect=fake_sleep),
        patch("app.api.v1.recordings.service.asyncio.get_event_loop", return_value=fake_loop),
    ):
        await stream_recording(ws, {"id": "rec-1", "file_path": "/fake.zip"})

    # Partition sleeps by run_id — run 0 = first produce(), run 1 = second produce()
    # sleep_calls: list[(call_number, delay)], sleep_run_ids: list[run_id] aligned by index
    run0_sleeps = [sleep_calls[i][1] for i in range(len(sleep_calls)) if sleep_run_ids[i] == 0]
    run1_sleeps = [sleep_calls[i][1] for i in range(len(sleep_calls)) if sleep_run_ids[i] == 1]

    # Run 1 (second produce, starts at frame 6) must contain exactly one sleep:
    #   Even-spacing: interval = 0.7 / (8-1) = 0.1s
    #   frame 7 → offset = 7 - 6 = 1 → target = anchor + 0.1 → sleep = 0.1
    # Old per-timestamp anchor-leak: if anchor_ts=100.0 leaked, frame 7 delta=4900.1 → burst detected
    assert run1_sleeps, (
        f"No sleeps in second produce() run (run_id=1). "
        f"All sleeps: {list(zip(sleep_run_ids, [d for _, d in sleep_calls]))}. "
        "produce() must run frame 7 with a re-anchored sleep from frame 6 (t=5000.0)."
    )

    burst_in_run1 = [d for d in run1_sleeps if d > 100.0]
    assert not burst_in_run1, (
        f"Burst sleep in second produce() run: {burst_in_run1}. "
        "anchor leaked from run 0 — anchor_timestamp must reset per produce() call."
    )

    assert abs(run1_sleeps[0] - 0.1) < 0.02, (
        f"Second produce() first sleep expected ~0.1s (even-spacing: duration=0.7, N=8, interval=0.1), "
        f"got {run1_sleeps[0]}. run0_sleeps={run0_sleeps}, run1_sleeps={run1_sleeps}"
    )


@pytest.mark.asyncio
async def test_produce_cancellation_propagates():
    """CancelledError from asyncio.sleep must propagate out of produce(), not be swallowed.

    Method: drive stream_recording with start@0, then pause while producer sleeps.
    The service cancels the producer task. We verify the producer task ends as cancelled
    (CancelledError not swallowed inside produce()).

    If produce() catches CancelledError and suppresses it, the task would finish
    with result=None instead of being cancelled — detected via task.cancelled().
    """
    from app.api.v1.recordings.service import stream_recording

    # Two frames with a large gap so frame 1 sleeps long enough to be caught mid-sleep
    frames = [
        (np.zeros((1, 16), dtype=np.float32), 100.0),
        (np.zeros((1, 16), dtype=np.float32), 101.0),  # 1.0s gap
    ]

    mock_reader = MagicMock()
    mock_reader.frame_count = 2
    mock_reader.get_frame = MagicMock(side_effect=lambda i: frames[i])

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_bytes = AsyncMock()

    producer_task_ref: list[asyncio.Task] = []
    sleep_entered = asyncio.Event()
    sleep_unblock = asyncio.Event()

    async def fake_sleep(delay):
        sleep_entered.set()
        # Block until cancelled — real CancelledError will be raised here
        await sleep_unblock.wait()

    fake_loop = MagicMock()
    fake_loop.time = MagicMock(return_value=0.0)

    send_json_responses: list[dict] = []

    async def fake_send_json(data):
        send_json_responses.append(data)
        # After "seeked" (start@0 generates seeked), stash the producer task handle
        # We can't directly get it here; instead we drive via pause command.

    ws.send_json = fake_send_json

    # Commands: start@0, then pause once producer is sleeping
    pause_sent = asyncio.Event()
    commands = [
        {"type": "websocket.receive", "text": json.dumps({"type": "start", "frameIndex": 0})},
        {"type": "websocket.receive", "text": json.dumps({"type": "pause"})},
        {"type": "websocket.disconnect"},
    ]
    cmd_index = 0

    async def fake_receive():
        nonlocal cmd_index
        if cmd_index == 1:
            # Wait until producer is mid-sleep before sending pause
            await sleep_entered.wait()
        msg = commands[cmd_index]
        cmd_index += 1
        return msg

    ws.receive = fake_receive
    ws.client_state = MagicMock()
    ws.client_state.name = "CONNECTED"

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    # Intercept asyncio.create_task to capture the producer task
    real_create_task = asyncio.create_task
    captured_producer: list[asyncio.Task] = []

    def patched_create_task(coro, **kwargs):
        task = real_create_task(coro, **kwargs)
        # Capture only produce() tasks (nested inside stream_recording)
        qualname = getattr(coro, '__qualname__', '') or ''
        if 'produce' in qualname and 'receive' not in qualname:
            captured_producer.append(task)
        return task

    with (
        patch("app.api.v1.recordings.service.RecordingReader", return_value=mock_reader),
        patch("app.api.v1.recordings.service.asyncio.to_thread", side_effect=fake_to_thread),
        patch("app.api.v1.recordings.service.asyncio.sleep", side_effect=fake_sleep),
        patch("app.api.v1.recordings.service.asyncio.get_event_loop", return_value=fake_loop),
        patch("app.api.v1.recordings.service.asyncio.create_task", side_effect=patched_create_task),
    ):
        await stream_recording(ws, {"id": "rec-1", "file_path": "/fake.zip"})

    # Producer task must exist and be done
    assert captured_producer, "No producer task was created — start command did not trigger produce()"
    producer_task = captured_producer[0]
    assert producer_task.done(), "Producer task must be done after session ends"

    # CancelledError must have propagated: task.cancelled() == True
    # If produce() swallowed CancelledError, task.cancelled() == False and task.result() == None
    assert producer_task.cancelled(), (
        "Producer task not cancelled — CancelledError was swallowed inside produce(). "
        "produce() must not catch asyncio.CancelledError."
    )


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


@pytest.mark.asyncio
async def test_produce_no_stall_quantized_second_timestamps():
    """produce() must NOT stall when timestamps are quantized to whole seconds.

    Regression test for Root Cause B: old clamp-based pacing tripped the
    large-gap clamp on every 1s boundary → visible ~1s stall per boundary.
    Even-spacing completely ignores per-frame timestamps; boundary crossings
    must NOT produce any sleep > interval.

    Setup: 11 frames at integer-second timestamps (0s, 1s, 2s, ..., 10s).
    Recording duration = 2.0s (desired playback). 10 boundaries → old code
    would stall at each boundary. Even-spacing: interval = 2.0/10 = 0.2s.
    All sleeps must be ≤ 0.2s (+ small epsilon) and never approach 1s.
    """
    from app.api.v1.recordings.service import stream_recording

    # 11 frames at integer-second epoch timestamps
    frames = [
        (np.zeros((1, 3), dtype=np.float32), float(1_000_000 + i))
        for i in range(11)
    ]

    mock_reader = MagicMock()
    mock_reader.frame_count = 11
    mock_reader.duration = 2.0  # desired playback = 2s → interval = 0.2s
    mock_reader.get_frame = MagicMock(side_effect=lambda i: frames[i])

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_bytes = AsyncMock()

    commands = [
        {"type": "websocket.receive", "text": json.dumps({"type": "start", "frameIndex": 0})},
        {"type": "websocket.disconnect"},
    ]
    cmd_iter = iter(commands)

    async def fake_receive():
        return next(cmd_iter)

    ws.receive = fake_receive
    ws.client_state = MagicMock()
    ws.client_state.name = "CONNECTED"

    sleep_calls: list[float] = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    fake_loop = MagicMock()
    fake_loop.time = MagicMock(return_value=0.0)

    async def fake_send_json(data):
        pass

    ws.send_json = fake_send_json

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("app.api.v1.recordings.service.RecordingReader", return_value=mock_reader),
        patch("app.api.v1.recordings.service.asyncio.to_thread", side_effect=fake_to_thread),
        patch("app.api.v1.recordings.service.asyncio.sleep", side_effect=fake_sleep),
        patch("app.api.v1.recordings.service.asyncio.get_event_loop", return_value=fake_loop),
    ):
        await stream_recording(ws, {"id": "rec-1", "file_path": "/fake.zip"})

    # Even-spacing: interval = 2.0 / 10 = 0.2s
    # 10 frames after anchor → 10 sleeps: 0.2, 0.4, 0.6, ..., 2.0
    assert len(sleep_calls) == 10, f"Expected 10 sleeps, got {len(sleep_calls)}: {sleep_calls}"

    # With clock frozen at 0, each sleep = offset * interval = cumulative.
    # Key property: consecutive sleep DIFFERENCES must equal interval (0.2s),
    # not ~1s (old stall). A sleep[i+1] - sleep[i] > 2*interval means a stall.
    interval = 2.0 / 10  # 0.2s
    for i in range(1, len(sleep_calls)):
        jump = sleep_calls[i] - sleep_calls[i - 1]
        assert jump <= interval * 1.5, (
            f"Stall between frames {i} and {i + 1}: sleep jumped {jump:.3f}s "
            f"(max allowed {interval * 1.5:.3f}s). "
            "Quantized-second timestamps must NOT cause ~1s stalls."
        )

    # All sleeps are uniform multiples of interval=0.2 (clock frozen at 0)
    for i, s in enumerate(sleep_calls):
        expected = (i + 1) * interval
        assert abs(s - expected) < 0.001, f"sleep_calls[{i}]={s}, expected={expected}"
