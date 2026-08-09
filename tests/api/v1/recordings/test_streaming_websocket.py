import json
import struct

import numpy as np

from app.db.models import RecordingModel
from app.services.shared.recording import RecordingWriter


def _recording(tmp_path, db_session):
    archive = tmp_path / "playback.zip"
    with RecordingWriter(archive, {"name": "playback"}) as writer:
        writer.write_frame(np.array([[1.0, 2.0, 3.0]], dtype=np.float32), 10.0)
        writer.write_frame(np.array([[4.0, 5.0, 6.0]], dtype=np.float32), 11.0)
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
