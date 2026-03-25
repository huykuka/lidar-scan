# Split-View Feature — Backend Tasks

**Document Status**: Ready for Review  
**Created**: 2026-03-25  
**Author**: Architecture Agent  
**References**: `requirements.md`, `technical.md`, `api-spec.md`  
**Assigned to**: `@be-dev`

---

## Summary

**The split-view feature requires zero backend changes.**

This document exists to formally confirm the backend scope boundary and provide explicit sign-off tasks.

---

## Formal Sign-Off Tasks

### Task BE-01: Confirm existing topic API is adequate

- [x] Verify `GET /api/v1/topics` returns an array of active topic strings
- [x] Verify the endpoint correctly reflects currently active DAG node topics (no stale topics returned)
- [x] No changes required

### Task BE-02: Confirm LIDR WebSocket stream is stable

- [x] Verify `WS /ws/{topic}` streams binary frames in LIDR format (magic `LIDR`, uint32 version, float64 timestamp, uint32 count, float32[N×3] points)
- [x] Verify close code `1001` is sent when a topic is removed (per protocol spec `protocols.md`)
- [x] Verify concurrent connections to the same topic from the same client are handled (the frontend will open 1 connection per topic regardless of view count)
- [x] No changes required

### Task BE-03: Load/performance validation (optional, recommended)

- [x] Confirm that the backend correctly handles a sustained connection to a topic while the frontend opens/closes view panes (the WebSocket connection stays alive across view add/remove)
- [x] Confirm no server-side session or state is created per frontend WebSocket client (stateless streaming)
- [x] No changes required

---

## Notes for Backend Team

The frontend's `PointCloudDataService` will maintain **exactly one WebSocket connection per active topic**, regardless of how many views are open (1–4). This is identical to the current single-view behaviour from the server's perspective.

The frontend's existing binary parser (`parseLidrFrame`) is being extracted to a pure utility (`lidr-parser.ts`) but the protocol frame format is **not changing**.

If future feature requests require per-view rendering hints (e.g. LOD level negotiation), a new backend API will be specified in a separate document.
