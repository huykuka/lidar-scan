# Streaming Record Player

- Replaced archive playback with recording stream WebSocket.
- Parser validates LIDR v2 28-byte header and exact XYZ payload.
- Viewer filters stale generations, owns stream teardown and point-cloud disposal.
- Tests: `pnpm test` and `pnpm lint` from `web/`.
- Auto-start: viewer starts frame 0 once per connected stream session after ready; empty streams enter EOF without start.
- Tests: full `pnpm test` passes (32 files, 260 tests). `pnpm exec oxlint src/` reports existing repo-wide errors/warnings outside changed files.
- Diagnosis: stream payload is LIDR v2 raw XYZ (`28-byte header + Float32 XYZ`), not archive PCD bytes. Parser already matches backend format.
- Fix: retain bounded `MAX_POINTS` buffer and point count as signals; flush draw range after points view becomes available. Previously frame could arrive before angular-three `pointsRef()`, causing early return with no later geometry update.
- Regression: stream geometry flush test verifies visibility, draw range, and position attribute update for valid XYZ frame count.
