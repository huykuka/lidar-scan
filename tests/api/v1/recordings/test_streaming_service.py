import struct

import numpy as np
from app.api.v1.recordings.schemas import StreamStartCommand
from app.api.v1.recordings.service import (
    _encode_stream_frame,
    _next_generation,
    _parse_stream_command,
)


def test_commands_require_strict_integer_frame_index():
    command, error = _parse_stream_command('{"type":"start","frameIndex":true}')
    assert command is None
    assert error["code"] == "invalid_frame_index"

    command, error = _parse_stream_command('{"type":"start","frameIndex":1}')
    assert isinstance(command, StreamStartCommand)
    assert error is None


def test_invalid_json_and_unknown_command_stay_classified():
    _, error = _parse_stream_command("not-json")
    assert error["code"] == "invalid_json"
    _, error = _parse_stream_command('{"type":"pause","frameIndex":0}')
    assert error["code"] == "unknown_command"


def test_generation_wrap_reserves_zero():
    assert _next_generation(0) == 1
    assert _next_generation(0xFFFFFFFF) == 1


def test_binary_frame_layout():
    payload = _encode_stream_frame(np.array([[1, 2, 3]], dtype=np.float32), 4.5, 7, 9)
    magic, version, generation, index, timestamp, count = struct.unpack("<4sIIIdI", payload[:28])
    assert (magic, version, generation, index, timestamp, count) == (b"LIDR", 2, 9, 7, 4.5, 1)
    assert len(payload) == 28 + 12
