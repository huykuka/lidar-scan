# QA Tasks — 3D Shape Rendering

**Feature:** Real-time 3D shape overlay  
**References:** `technical.md`, `api-spec.md`, `backend-tasks.md`, `frontend-tasks.md`  
**Assigned to:** @qa

---

## QA Checklist Instructions

Update each checkbox (`[ ]` → `[x]`) as tasks are executed. Append brief notes where required.

---

## Phase 1 — TDD Preparation (Before Development Starts)

- [ ] **QA-TDD-01**: Write failing unit test for `compute_shape_id()` — verify same geometry always yields same 16-char hex id
- [ ] **QA-TDD-02**: Write failing unit test for `ShapeCollectorMixin.collect_and_clear_shapes()` — verify list is cleared after collection
- [ ] **QA-TDD-03**: Write failing unit test for `ShapeFrame` Pydantic model — verify `extra="forbid"` rejects unknown fields
- [ ] **QA-TDD-04**: Write failing Angular unit test for `ShapeLayerService.applyFrame()` with new id → `scene.add` called once
- [ ] **QA-TDD-05**: Write failing Angular unit test for `ShapeLayerService.applyFrame()` with same id repeated → `scene.add` called only once (update path)
- [ ] **QA-TDD-06**: Write failing Angular unit test for unknown shape type → no exception, shape not added

---

## Phase 2 — Backend Unit Tests

- [ ] **QA-BE-01**: Run `pytest tests/unit/test_shapes.py`
  - [ ] `CubeShape`, `PlaneShape`, `LabelShape` models serialize to exact `api-spec.md` field names
  - [ ] `ShapeFrame` with all three types serializes without error
  - [ ] `extra="forbid"` rejects unknown fields on all models
- [ ] **QA-BE-02**: Run `pytest tests/unit/test_shape_collector.py`
  - [ ] `emit_shape()` buffers correctly
  - [ ] `collect_and_clear_shapes()` returns all buffered shapes and empties the list
  - [ ] Multiple calls to `collect_and_clear_shapes()` without `emit_shape()` returns empty list each time
- [ ] **QA-BE-03**: Verify `compute_shape_id()` determinism
  - [ ] Same node_id + same geometry → same id (run 100 times)
  - [ ] Different center (0.001m delta) → different id
  - [ ] Different node_id + same geometry → different id
- [ ] **QA-BE-04**: Verify shape count cap at 500
  - [ ] Emit 600 shapes from a single node → broadcast contains exactly 500; warning logged

---

## Phase 3 — Backend Integration Tests

- [ ] **QA-INT-01**: Run `pytest tests/integration/test_shapes_ws.py`
  - [ ] WebSocket connects to `/ws/shapes` successfully
  - [ ] After triggering a processing frame, client receives a valid `ShapeFrame` JSON message
  - [ ] `shapes` topic does NOT appear in `GET /api/v1/topics` response
  - [ ] After `reload_config()`, WebSocket client reconnects and continues receiving frames (topic survives reload)
- [ ] **QA-INT-02**: Concurrent nodes test
  - [ ] Two nodes both emit shapes in the same frame
  - [ ] Output `ShapeFrame.shapes` contains shapes from both nodes with correct `node_name` on each
- [ ] **QA-INT-03**: Empty frame test
  - [ ] When no nodes emit shapes, server still publishes `{ timestamp: ..., shapes: [] }` within 1 frame interval
- [ ] **QA-INT-04**: WS lifecycle on reload
  - [ ] Client connected to `shapes` topic, full reload triggered
  - [ ] Client receives close code `1001` (Going Away) OR the topic remains open (system topic survives — verify the expected behavior matches `technical.md §5`)

---

## Phase 4 — Frontend Unit Tests

- [ ] **QA-FE-01**: Run `ng test` and verify all passing:
  - [ ] `shapes-ws.service.spec.ts` — valid frame parse, malformed JSON drop, 1001 close complete
  - [ ] `shape-layer.service.spec.ts` — add/update/remove/clear/unknown-type paths
  - [ ] `shape-builders.spec.ts` — `buildCube`, `buildPlane`, `buildLabel` return correct Three.js types
- [ ] **QA-FE-02**: TypeScript strict mode — `ng build --configuration production` must complete with 0 errors

---

## Phase 5 — Visual / E2E Integration Tests

- [ ] **QA-E2E-01**: Frame-synchronized rendering
  - [ ] With a live backend: point cloud and shapes update in the same render tick with no visible frame lag between them
  - [ ] Bounding box visually aligns with the clustered region in the point cloud
- [ ] **QA-E2E-02**: Layer isolation
  - [ ] Toggling a point cloud topic off/on does NOT remove or recreate any shape objects
  - [ ] Verify via browser DevTools that `shapeMap` size is unchanged across point cloud topic toggle
- [ ] **QA-E2E-03**: Shape lifecycle over multiple frames
  - [ ] Shapes with stable geometry maintain the same id across 60 consecutive frames (no flicker/recreate)
  - [ ] When a node stops emitting a shape (id disappears from frame), the shape is removed from the scene within 1 frame
- [ ] **QA-E2E-04**: Coordinate alignment
  - [ ] Cube at `[0,0,0]` aligns with the world origin as viewed from all 4 camera modes (perspective, top, front, side)
  - [ ] Plane with normal `[0,0,1]` appears horizontal (aligned with LiDAR Z-up ground plane)
  - [ ] Label billboard is always readable (camera-facing) when rotating the camera in perspective mode
- [ ] **QA-E2E-05**: Empty frame clears shapes
  - [ ] While shapes are visible, instruct backend to emit zero shapes
  - [ ] All shape objects disappear from viewport within the next frame
- [ ] **QA-E2E-06**: Unknown shape type resilience
  - [ ] Manually inject a WS message with `type: "arrow"` via browser DevTools
  - [ ] Application does not crash; `console.warn` is emitted; existing shapes unchanged

---

## Phase 6 — Performance Tests

- [ ] **QA-PERF-01**: 60 FPS maintained with shapes
  - [ ] With 50 cube shapes active, measure FPS using browser DevTools Performance panel
  - [ ] FPS must stay ≥ 58 FPS on a reference machine with a 100k-point cloud active
- [ ] **QA-PERF-02**: 500-shape stress test
  - [ ] Inject a frame with 500 shapes (all cubes) via mock
  - [ ] FPS must not drop below 30 FPS
  - [ ] No memory leak: heap snapshot before and after 60 frames of 500 shapes must not grow unboundedly
- [ ] **QA-PERF-03**: No geometry recreation
  - [ ] Over 300 identical frames (same shape ids), `scene.add` must NOT be called after the first frame
  - [ ] Instrument with a counter in `ShapeLayerService` (or mock) to verify

---

## Phase 7 — Linter & Type Check

- [ ] **QA-LINT-01**: Backend — `ruff check app/services/nodes/shapes.py app/services/nodes/shape_collector.py` → 0 errors
- [ ] **QA-LINT-02**: Backend — `ruff check app/services/nodes/managers/routing.py` → 0 errors
- [ ] **QA-LINT-03**: Frontend — `cd web && ng lint` → 0 errors
- [ ] **QA-LINT-04**: Frontend — `cd web && npx tsc --noEmit` → 0 errors

---

## Phase 8 — Pre-PR Verification

- [ ] **QA-PRE-PR-01**: `pytest` full suite passes (no regressions in existing tests)
- [ ] **QA-PRE-PR-02**: `cd web && ng build --configuration production` passes with 0 errors
- [ ] **QA-PRE-PR-03**: `cd web && ng test --watch=false` → 0 test failures
- [ ] **QA-PRE-PR-04**: Backend dev (`@be-dev`) confirms BE-01 through BE-08 all checked off in `backend-tasks.md`
- [ ] **QA-PRE-PR-05**: Frontend dev (`@fe-dev`) confirms FE-01 through FE-09 all checked off in `frontend-tasks.md`
- [ ] **QA-PRE-PR-06**: No regressions on existing `PointCloudComponent` tests (`point-cloud.component.spec.ts`)

---

## Integration / Notes for QA

1. **Frame synchronization**: Shapes topic publishes once per frame (same cadence as point cloud frames). The frontend subscribes independently — there is no explicit gating. Minor drift (<1 frame) between point cloud and shape updates is acceptable.

2. **Topic survives reload**: `shapes` is a system topic. After `reload_config()`, existing WebSocket connections to `shapes` should NOT receive a `1001` close unless the backend explicitly closes them. Verify this matches `technical.md §5`.

3. **Coordinate system**: LiDAR uses Z-up; Three.js uses Y-up. The rotation transform (`rotation.x = -π/2, rotation.z = -π/2`) is applied at the shape group level. If shapes appear misaligned, check that all `ShapeBuilders` wrap in the rotation group.

4. **Wireframe vs solid cubes**: Test both `wireframe: true` and `wireframe: false` paths — they use different Three.js geometry paths (`EdgesGeometry + LineSegments` vs `BoxGeometry + MeshBasicMaterial`).

5. **Label canvas disposal**: `THREE.CanvasTexture` created in `buildLabel` must be disposed on shape removal to avoid GPU texture leaks. Verify in `QA-PERF-02` heap snapshot.
