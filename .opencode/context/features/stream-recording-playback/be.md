# stream-recording-playback

- Added recording WebSocket transport in `app/api/v1/websocket`.
- Reused `RecordingReader`; playback output uses 24-byte LIDR header.
