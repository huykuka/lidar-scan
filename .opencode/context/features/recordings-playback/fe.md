# Recordings playback bug

## Tasks
- Inspect viewer controls and playback service.
- Implement pause/resume protocol contract.
- Add command and UI event tests.
- Run targeted tests/build and reviewer.

## Findings
- Backend playback contract now accepts `{type:"pause"}` and emits `{type:"paused", frameIndex, generation}`.
- Resume uses backend `start` without frame index after pause; backend resumes from paused cursor.
- Viewer applies frames only while playing and matching generation; no local seek interval.
- Existing worktree contains unrelated recording playback/backend changes; preserved.
