# Frontend Tasks — 3D Shape Rendering

**Feature:** Real-time 3D shape overlay  
**References:** `technical.md` §4, `api-spec.md`  
**Assigned to:** @fe-dev

---

## Prerequisites

- Read `technical.md` §4 (Frontend Design) fully before starting.
- Read `api-spec.md` for exact JSON schema and all shape fields.
- All new components/services MUST use the Angular CLI: `cd web && ng g service core/services/<name>`
- Use Angular Signals for reactive state; RxJS only for the WebSocket stream.
- Do NOT modify `PointCloudComponent`'s `animate()` method or the `BufferGeometry` mutation path.
- Scaffold all files via Angular CLI before editing.

---

## Tasks

### FE-01 — TypeScript Interfaces for Shape Protocol
- [ ] Create `web/src/app/core/models/shapes.model.ts`
- [ ] Define `BaseShape` interface with `id: string`, `node_name: string`, `type: string`
- [ ] Define `CubeDescriptor extends BaseShape` — all fields per `api-spec.md §4.1`
- [ ] Define `PlaneDescriptor extends BaseShape` — all fields per `api-spec.md §4.2`
- [ ] Define `LabelDescriptor extends BaseShape` — all fields per `api-spec.md §4.3`
- [ ] Define `ShapeDescriptor = CubeDescriptor | PlaneDescriptor | LabelDescriptor`
- [ ] Define `ShapeFrame` interface: `{ timestamp: number; shapes: ShapeDescriptor[] }`
- [ ] Export all from `shapes.model.ts`

### FE-02 — `ShapesWsService`
- [ ] Scaffold: `cd web && ng g service core/services/shapes-ws`
- [ ] Inject `WebSocketService` or reuse existing WS infrastructure for topic subscription
- [ ] Expose `frames$: Observable<ShapeFrame>` — subscribes to topic `"shapes"`
- [ ] Parse incoming JSON messages into `ShapeFrame` (use try/catch; drop malformed frames with `console.error`)
- [ ] Handle WS close code `1001`: call `subject.complete()`, do NOT reconnect
- [ ] Handle other WS close codes: schedule reconnect per existing pattern
- [ ] Add `MOCK_SHAPE_FRAME` constant covering one shape of each type (for local dev without backend)
- [ ] If `environment.mockShapes === true`, return `of(MOCK_SHAPE_FRAME).pipe(repeat({ delay: 100 }))` instead of live WS

### FE-03 — Three.js Layer Constant
- [ ] In `web/src/app/core/models/shapes.model.ts` (or a shared `constants.ts`), export:
  ```typescript
  export const SHAPE_LAYER = 2;
  ```
- [ ] Document: Layer 0 = point clouds/grid/axes (default), Layer 2 = 3D shapes

### FE-04 — `ShapeBuilders` — Three.js Object Factories
- [ ] Create `web/src/app/core/utils/shape-builders.ts`
- [ ] Implement `ShapeBuilders` class with static methods:
  - [ ] `buildCube(d: CubeDescriptor): THREE.Group`
    - [ ] Create `THREE.BoxGeometry(d.size[0], d.size[1], d.size[2])`
    - [ ] If `d.wireframe === true`: use `THREE.EdgesGeometry` + `THREE.LineSegments` with `LineBasicMaterial`
    - [ ] If `d.wireframe === false`: use `THREE.MeshBasicMaterial({ transparent: true, depthWrite: false })`
    - [ ] Apply `d.color`, `d.opacity`
    - [ ] If `d.label` is present: attach a `THREE.Sprite` label above the box (reuse label builder)
    - [ ] Wrap mesh in a `THREE.Group` with coordinate transform applied (see §4.6 in technical.md)
    - [ ] Set `group.position.set(d.center[0], d.center[1], d.center[2])`
    - [ ] Set `group.rotation.set(d.rotation[0], d.rotation[1], d.rotation[2])` on the inner mesh
  - [ ] `buildPlane(d: PlaneDescriptor): THREE.Group`
    - [ ] Create `THREE.PlaneGeometry(d.width, d.height)`
    - [ ] `MeshBasicMaterial({ color: d.color, transparent: true, opacity: d.opacity, side: THREE.DoubleSide, depthWrite: false })`
    - [ ] Orient plane via `quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), normalVec.normalize())`
    - [ ] Wrap in coordinate-transform group, position at `d.center`
  - [ ] `buildLabel(d: LabelDescriptor): THREE.Sprite`
    - [ ] Create a `CanvasTexture` (128×64 canvas) rendering `d.text` with `d.font_size`, `d.color`, `d.background_color`
    - [ ] Return a `THREE.Sprite` at `d.position` with `d.scale`
    - [ ] **Note:** Sprites are always camera-facing — no rotation group needed
  - [ ] `updateCube(obj: THREE.Group, d: CubeDescriptor): void` — mutate position/rotation/color/opacity in-place
  - [ ] `updatePlane(obj: THREE.Group, d: PlaneDescriptor): void` — mutate position/orientation/color/opacity in-place
  - [ ] `updateLabel(obj: THREE.Sprite, d: LabelDescriptor): void` — redraw canvas texture if text changed

### FE-05 — `ShapeLayerService`
- [ ] Scaffold: `cd web && ng g service core/services/shape-layer`
- [ ] Internal state: `private shapeMap = new Map<string, THREE.Object3D>()`
- [ ] Internal state: `private scene: THREE.Scene | null = null`
- [ ] Implement `init(scene: THREE.Scene): void` — stores scene reference
- [ ] Implement `applyFrame(frame: ShapeFrame): void`:
  - [ ] Compute `incomingIds = new Set(frame.shapes.map(s => s.id))`
  - [ ] **Remove stale shapes**: iterate `shapeMap`, for any `id` not in `incomingIds`:
    - [ ] `scene.remove(obj)`
    - [ ] Dispose geometry and material recursively
    - [ ] `shapeMap.delete(id)`
  - [ ] **Add or update shapes**: iterate `frame.shapes`:
    - [ ] If `shape.id` not in `shapeMap`: call `buildShape(shape)`, set `obj.layers.set(SHAPE_LAYER)`, `scene.add(obj)`, `shapeMap.set(shape.id, obj)`
    - [ ] If `shape.id` already in `shapeMap`: call `updateShape(shapeMap.get(id), shape)` (in-place mutation)
  - [ ] Guard: if `shape.id === ""`, log contract violation warning and skip
- [ ] Implement `disposeAll(): void` — remove and dispose all shapes, clear map
- [ ] Helper `private buildShape(d: ShapeDescriptor): THREE.Object3D | null` — switch on `d.type`, call `ShapeBuilders.*`, return `null` for unknown types with `console.warn`
- [ ] Helper `private updateShape(obj: THREE.Object3D, d: ShapeDescriptor): void` — switch on type, call `ShapeBuilders.update*`

### FE-06 — Integrate into `PointCloudComponent`
- [ ] Inject `ShapeLayerService` and `ShapesWsService` into `PointCloudComponent`
- [ ] In `ngAfterViewInit`, after `this.initThree()` succeeds:
  - [ ] Call `this.shapeLayerService.init(this.scene)`
  - [ ] Enable all camera layers: `this.perspCamera.layers.enableAll()` and `this.orthoCamera.layers.enableAll()`
  - [ ] Subscribe to `this.shapesWs.frames$` → call `this.shapeLayerService.applyFrame(frame)` on each emission
  - [ ] Store the subscription in a class field for cleanup
- [ ] In `ngOnDestroy`:
  - [ ] Unsubscribe from the shapes stream
  - [ ] Call `this.shapeLayerService.disposeAll()`
- [ ] **CRITICAL:** Do NOT modify `animate()`, the `BufferGeometry` mutation code, or any existing point cloud logic

### FE-07 — Coordinate System Alignment Verification
- [ ] In `ShapeBuilders.buildCube` and `buildPlane`, confirm the wrapping `THREE.Group` applies:
  ```typescript
  group.rotation.x = -Math.PI / 2;
  group.rotation.z = -Math.PI / 2;
  ```
  This mirrors the point cloud coordinate rotation so all shapes align with the point cloud in world space.
- [ ] Visual test: place a cube at `[0,0,0]` with size `[1,1,1]` — it should sit on top of the origin marker, not at a rotated offset.

### FE-08 — Forward-Compatibility Guard
- [ ] In `ShapeLayerService.buildShape()`, the `default` case of the switch MUST:
  - [ ] Log `console.warn('[ShapeLayerService] Unknown shape type: "' + d.type + '" — skipping')`
  - [ ] Return `null`
- [ ] Write a unit test that passes a frame with an unknown type (`type: "arrow"`) and verifies no exception is thrown and shape count in `shapeMap` is 0

### FE-09 — Unit Tests
- [ ] Create `web/src/app/core/services/shapes-ws.service.spec.ts`
  - [ ] Test: valid JSON frame → emits `ShapeFrame`
  - [ ] Test: malformed JSON → drops frame, no crash
  - [ ] Test: WS close code 1001 → observable completes
- [ ] Create `web/src/app/core/services/shape-layer.service.spec.ts`
  - [ ] Test: `applyFrame` with new shape → adds to scene (spy on `scene.add`)
  - [ ] Test: `applyFrame` with updated shape → calls `updateShape`, does NOT call `scene.add` again
  - [ ] Test: `applyFrame` with removed id → calls `scene.remove` and disposes
  - [ ] Test: `applyFrame` with empty shapes → clears all
  - [ ] Test: unknown `type` → returns null, map stays empty, no exception
- [ ] Create `web/src/app/core/utils/shape-builders.spec.ts`
  - [ ] Test: `buildCube` returns `THREE.Group` with correct position
  - [ ] Test: `buildPlane` returns `THREE.Group` oriented by normal
  - [ ] Test: `buildLabel` returns `THREE.Sprite`

---

## Dependencies / Order

```
FE-01 → FE-02 → FE-03 → FE-04 → FE-05 → FE-06 → FE-07 → FE-08 → FE-09
```

FE-03 (constant) can be done in parallel with FE-02.  
FE-09 (tests) should be written alongside or immediately after each corresponding task (TDD preferred).

---

## Constraints & Reminders

- Do NOT alter the `BufferGeometry` write path or the `animate()` render loop in `PointCloudComponent`.
- Do NOT add a new Angular component — shapes are pure Three.js objects managed by a service.
- All services must be `providedIn: 'root'` unless a scoping reason dictates otherwise.
- If the backend is not yet ready, use `environment.mockShapes = true` and `MOCK_SHAPE_FRAME` from `ShapesWsService` to develop and test independently.
