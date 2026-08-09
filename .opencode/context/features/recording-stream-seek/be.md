# Recording stream seek

- `stream_recording` starts paused; `start` starts paced producer.
- `seek` cancels producer, waits cancellation, sends `seeked`, sends target LIDR frame immediately.
- Paused seek remains paused; playing seek resumes from target + 1.
- EOF accepts `frameIndex == frame_count`; emits `seeked` then `eof`.
- Targeted tests pass: 10; full suite blocked by pre-existing removed `app.modules.application.*` imports.
