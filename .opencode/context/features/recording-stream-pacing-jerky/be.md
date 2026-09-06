# BE Context: recording-stream-pacing-jerky

_Updated: 2026-08-14_

## Root cause

`test_produce_seek_resume_reanchors_per_run` used `MagicMock()` for `mock_reader` **without setting `.duration`**.
`MagicMock.__float__()` returns 1.0 by default, so `float(reader.duration) = 1.0` →
`interval = 1.0 / (8-1) = 0.142857s`. Test asserted `abs(run1_sleeps[0] - 0.1) < 0.02` (tolerance 0.02) but
actual=0.142 → diff=0.042 > 0.02 → FAIL.

`produce()` itself was already correct (even-spacing, no stalls). The regression was a test setup omission.

## Evidence

- `interval = 1.0 / 7 = 0.142857` (MagicMock.duration auto-float=1.0)
- Expected: 0.1, got: 0.142857, diff: 0.042857 > 0.02 tolerance

## Fix

`tests/api/v1/recordings/test_streaming_websocket.py` (single change):

- Added `mock_reader.duration = 0.7` so `interval = 0.7/7 = 0.1s` → sleep ~0.1 ✓
- Updated assertion message to reflect even-spacing logic

## New test added

`test_produce_no_stall_quantized_second_timestamps` — 11 frames at integer-second timestamps, duration=2.0s. Verifies
consecutive sleep differences = interval (0.2s), not ~1s. Covers old Root Cause B (clamp-based pacing stalling at each
second boundary).

## Files changed

- `tests/api/v1/recordings/test_streaming_websocket.py`
    - Line ~573: added `mock_reader.duration = 0.7`
    - Lines ~668-674: updated comments
    - Lines ~683-686: updated assertion message
    - Lines ~824-920: added `test_produce_no_stall_quantized_second_timestamps`

## No service.py changes needed

`produce()` was already correct even-spacing. No backend logic changed.
