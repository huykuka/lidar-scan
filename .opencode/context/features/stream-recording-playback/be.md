# stream-recording-playback

- Added recording WebSocket transport in `app/api/v1/websocket`.
- Reused `RecordingReader`; playback output uses 24-byte LIDR header.
- Root cause: `RecordingReader` returns recorded point clouds with all columns (commonly 16), while `_encode_stream_frame` required exactly 3 columns; producer raised before first binary frame. Encoder now validates at least XYZ and emits contiguous XYZ float32 payload.
- Stream now logs reader/producer failures with recording path, frame index, generation, and stack trace while preserving safe `recording_stream_failed` client response. Receive task retained/cancelled across producer completion so seek commands are not lost.
- Regression: `tests/api/v1/recordings/test_streaming_websocket.py` writes 16-column frames and verifies real reader→LIDR payload plus seek.
