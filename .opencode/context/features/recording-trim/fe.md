# FE Feature Context — recording-trim
_Updated: 2026-08-09_

## Tasks
- [x] Add `status?: 'ready' | 'processing' | 'failed'` to Recording model
- [x] Fix onCreateTrim: reset immediately on 202, toast "Trim started — processing in background", clear in/out frames, refresh list
- [x] recording-card: isProcessing/isFailed computed signals, actionsDisabled, processing overlay+badge, failed badge, onPlay/onDownload guard methods
- [x] recordings list: polling every 3s while hasProcessing, stops when none; uses effect() + takeUntilDestroyed
- [x] Tests: 3 new describe blocks (202 reset, card status, polling logic), 301 pass

## Notes
- Pre-existing test failure: "preserves recording XYZ units and coordinates" — HTMLCanvasElement not available in test env; unrelated to this feature.
- Recording API trimRecording() already returns Observable<Recording>; HttpClient accepts 202 as success by default — no change needed.
- Polling: uses effect() in constructor + interval().pipe(takeUntilDestroyed(destroyRef)).
- Angular template comma operator not allowed — moved Play/Download click logic to onPlay()/onDownload() component methods.
