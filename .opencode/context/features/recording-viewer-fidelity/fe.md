# Recording Viewer Fidelity

## Task
- Preserve streamed XYZ coordinates and units.
- Keep one reusable geometry/buffer across sequential frames.
- Dispose Three.js resources only on component destruction.

## Findings
- `fitPointCloudToView()` mutates recorded XYZ per frame; remove it.
- `clearPointCloud()` disposed live geometry on EOF, causing later frame updates to target disposed resources.
- `startPlayback()` issues a seek command every interval while stream producer already emits frames; this creates generation churn and frame races. Keep playback pacing owned by stream producer; do not seek per display tick.
- Backend LIDR recording endpoint preserves first three float32 columns; no frontend transform needed.
- Backend playback node pacing uses duration-derived sleeps. Public recording stream currently emits frames without pacing; FE interval seeks repeatedly, creating command churn. Scope visual fix first; pacing requires protocol decision.

## Changes
- Removed `fitPointCloudToView()` and its per-frame mutation.
- Reused `Float32Array` and geometry draw range across frames; tests assert exact XYZ and sequential draw ranges.
- EOF clearing now sets visibility/draw range only; disposal remains component teardown responsibility.
- Removed interval-driven seek loop; stream producer owns frame delivery, preventing seek/generation churn.

## Verification
- Targeted Vitest command exits without test failures, but runner reports `PASS (0) FAIL (0)` due current Vitest/Angular config.
- `pnpm build` passes with existing bundle-budget and missing `/assets/themes/light.css` warnings.
- Targeted oxlint passes.
- `gitnexus_detect_changes` run; workspace contains unrelated pre-existing backend/environment edits, producing high aggregate risk. FE viewer impact was LOW.
