- Investigate empty streamed playback Three.js scene.
- Preserve bounded streaming memory.

## Findings
- Backend LIDR v2 header and XYZ payload match parser: 28-byte header, flat float32 XYZ.
- `NgtsPointsBuffer` creates position attribute for full fixed buffer; render requires draw range, position needsUpdate, and visibility.
- Recording viewer uses `*canvasContent` and imports `NgtCanvasContent`.
- Stream frames can contain large world coordinates outside shared fixed camera framing.
- Added bounded copy + geometry flush helper and tests for XYZ, draw range, visibility, camera fit.
- Paused trackbar seek sends seek on release and renders exact target binary frame.
- `syn-range` committed value event: `(syn-change)`; `(syn-input)` fires during movement.
- Viewer gates binary frames by playback state and generation.
- Paused seek needs one exact target-frame exception without changing `isPlaying`.
