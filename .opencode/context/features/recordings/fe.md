# Recordings FE Context

## Task
- Investigate empty streamed playback Three.js scene.
- Preserve bounded streaming memory.

## Findings
- Backend LIDR v2 header and XYZ payload match parser: 28-byte header, flat float32 XYZ.
- `NgtsPointsBuffer` creates position attribute for full fixed buffer; render requires draw range, position needsUpdate, and visibility.
- Recording viewer used `*canvasContent` but omitted `NgtCanvasContent` import, unlike working result/workspace viewers. This caused projected scene content not to attach reliably.
- Stream frames can contain large world coordinates outside shared fixed camera framing. In-place centering/scaling now fits current frame to bounded camera view; no frame cache added.
- Added bounded copy + geometry flush helper and tests for XYZ, draw range, visibility, camera fit.
