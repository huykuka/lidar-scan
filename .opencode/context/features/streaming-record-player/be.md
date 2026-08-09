# streaming-record-player

## Tasks
- Add public recording WebSocket stream endpoint.
- Stream bounded decoded frames with strict commands and LIDR v2 binary output.
- Add service/handler tests.

## Findings
- Recording routes live in `app/api/v1/recordings/handler.py`; package exports router.
- `RecordingReader` lives in `app/services/shared/recording.py`.
- No ORM/schema changes required.
- Added public `/api/v1/recordings/{recording_id}/stream` WebSocket.
- Relevant tests: 24 passed. Full suite blocked by pre-existing missing `app.modules.application.*` imports in seven tests.
- Ruff passes changed backend/test paths.
- GitNexus detect_changes reports high due to unrelated concurrent frontend changes; backend stream files are intended scope.
- Bug root cause: stream loop discarded received command when producer task and receive task completed in same asyncio.wait cycle. This dropped seek/start at archive boundary; command-first handling preserves control messages.
- Regression coverage: `tests/api/v1/recordings/test_streaming_websocket.py` proves ready → start → LIDR v2 bytes and seek frame emission without archive buffering.
