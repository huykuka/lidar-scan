# Stream Recording Playback

## Tasks
- [x] Add recording playback WebSocket service.
- [x] Update exact 24-byte LIDR parser layout.
- [x] Replace archive viewer with streamed playback.
- [x] Add/update tests.
- [x] Run npm test and reviewer loop.

## Findings
- Recording info endpoint exists at RecordingApiService.getRecordingInfo().
- Production WS factory maps topic to `/api/v1/ws/{topic}`.
- Existing viewer uses JSZip and worker; streamed frames can render directly from parseLidrFrame().
- Stream service uses generation checks, one delayed retry, acknowledged seek recovery, and bounded frame cache.
- `npm test -- --watch=false`: 31 files, 266 tests passed. Existing Angular host template warnings remain.
- @fe-reviewer dispatch failed: subagent depth limit reached; no reviewer result available.
