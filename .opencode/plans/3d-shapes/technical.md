# Technical Design — 3D Shape Rendering

**Feature:** Real-time 3D shape overlay (cube, plane, label/billboard) on the Three.js viewport  
**Architect:** @architecture  
**Date:** 2026-04-19  
**Status:** Draft

---

## 1. Overview

This feature introduces a dedicated **shape rendering layer** that composites over the existing point cloud visualization without touching or disrupting it. All shapes originate from backend DAG nodes (via Open3D bounding boxes or other geometric outputs), are collected by the `NodeManager`, assigned a backend-generated unique UUID, and broadcast to the frontend as a JSON array on a single, stable WebSocket topic `shapes`. The frontend decodes this stream and maintains shape identity and full lifecycle (create/update/destroy) by `id` using Three.js Layers to keep geometry strictly separated from the point cloud mesh.

---

## 2. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ DAG Pipeline                                                  │
│                                                               │
│  [SensorNode] → [ProcessingNode] → [BBoxNode / CustomNode]   │
│                                          │                    │
│                                    shape.emit()               │
│                                          │                    │
│                             ┌────────────▼────────────┐      │
│                             │  ShapeCollectorMixin     │      │
│                             │  (per-node, per-frame)   │      │
│                             └────────────┬────────────┘      │
│                                          │                    │
│                             ┌────────────▼────────────┐      │
│                             │  NodeManager             │      │
│                             │  collect_shapes()        │      │
│                             │  assign uuid + node_name │      │
│                             │  publish → WS 'shapes'   │      │
│                             └────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
                                     │  JSON over WS topic 'shapes'
                    ─────────────────▼──────────────────────────
┌──────────────────────────────────────────────────────────────┐
│ Angular Frontend                                              │
│                                                               │
│  ShapesWsService                                             │
│    └── RxJS Subject<ShapeFrame>                              │
│                                                               │
│  ShapeLayerService  (Injectable, singleton)                  │
│    ├── Map<id, ShapeObject3D>   (shape registry)             │
│    ├── THREE.Layers bit = 2     (SHAPE_LAYER)                │
│    ├── diffShapes(prev, next)   (add/update/remove by id)    │
│    └── disposeShape(id)                                       │
│                                                               │
│  PointCloudComponent (UNCHANGED)                             │
│    └── scene shared via SceneRef token                       │
│         └── Layer 1 = point cloud (default)                  │
│         └── Layer 2 = shapes (SHAPE_LAYER)                   │
│                                                               │
│  renderer.render(scene, camera)                              │
│    camera.layers.enableAll()   (renders both layers)         │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Backend Design

### 3.1 Shape Emission Contract — `ShapeCollectorMixin`

Any DAG node that wants to emit shapes inherits `ShapeCollectorMixin` (lives in `app/services/nodes/`). This mixin is intentionally decoupled from `ModuleNode` so it is opt-in.

```python
class ShapeCollectorMixin:
    """Opt-in mixin for nodes that emit 3D shapes per frame."""

    def __init__(self):
        self._pending_shapes: List[ShapePayload] = []

    def emit_shape(self, shape: ShapePayload) -> None:
        """Buffer one shape for this processing frame."""
        self._pending_shapes.append(shape)

    def collect_and_clear_shapes(self) -> List[ShapePayload]:
        """Called by NodeManager after on_input() returns."""
        shapes = list(self._pending_shapes)
        self._pending_shapes.clear()
        return shapes
```

Nodes that produce shapes call `self.emit_shape(shape)` inside `on_input()`. They do NOT publish directly to WebSocket.

### 3.2 Shape Publishing — `NodeManager` Extension

After `DataRouter.forward_data()` completes for a given frame, the `NodeManager` iterates all nodes, collects pending shapes, stamps each with a stable `id` and the emitting node's `node_name`, and publishes the entire batch to the `shapes` topic via `websocket_manager.broadcast("shapes", payload)`.

**Shape ID strategy:** `id` = `sha256(node_id + shape_type + deterministic_geometry_key)[:16]` — so re-emitting the identical bounding box from the same node always produces the same `id` (idempotent). Geometry keys for each type:
- **cube** — `center_x|center_y|center_z|size_x|size_y|size_z` (rounded to 3 dp)
- **plane** — `center_x|center_y|center_z|normal_x|normal_y|normal_z|width|height`
- **label** — `position_x|position_y|position_z|text`

This ensures the frontend can track shapes stably without re-creating Three.js objects on every identical frame.

**`shapes` topic** is a SYSTEM_TOPIC (added to the `SYSTEM_TOPICS` set in `manager.py`), meaning it never appears in the `/topics` endpoint and is always registered at startup.

### 3.3 Open3D Bounding Box → Cube Shape

When a node has an `open3d.geometry.OrientedBoundingBox` (OBB) or `AxisAlignedBoundingBox` (AABB) from a detection step, it converts it as follows:

```python
# AABB → CubeShape
from app.services.nodes.shapes import CubeShape
bbox = pcd.get_axis_aligned_bounding_box()
center = bbox.get_center()   # ndarray [x, y, z]
extent = bbox.get_extent()   # ndarray [sx, sy, sz]
self.emit_shape(CubeShape(
    center=center.tolist(),
    size=extent.tolist(),
    color="#00ff00",
    opacity=0.4,
    wireframe=True,
    label="cluster_0",
))
```

### 3.4 Plane Shape

A plane is defined by a center point, a normal vector, and physical width/height dimensions. Nodes that fit a ground plane (e.g., via RANSAC) call:

```python
self.emit_shape(PlaneShape(
    center=[0.0, 0.0, 0.0],
    normal=[0.0, 0.0, 1.0],
    width=10.0,
    height=10.0,
    color="#4488ff",
    opacity=0.25,
))
```

### 3.5 Label / Billboard Shape

A text billboard at a 3D world position (always camera-facing):

```python
self.emit_shape(LabelShape(
    position=[1.5, 2.0, 0.5],
    text="Cluster A  (42 pts)",
    font_size=14,
    color="#ffffff",
    background_color="#000000cc",
))
```

### 3.6 Pydantic Models — `app/services/nodes/shapes.py`

```python
from __future__ import annotations
from typing import Literal, List, Optional, Union
from pydantic import BaseModel, Field
import hashlib, json

class _BaseShape(BaseModel):
    id: str = ""           # filled by NodeManager before broadcast
    node_name: str = ""    # filled by NodeManager before broadcast
    type: str

    class Config:
        extra = "forbid"

class CubeShape(_BaseShape):
    type: Literal["cube"] = "cube"
    center: List[float]          # [x, y, z] world units
    size: List[float]            # [sx, sy, sz] world units
    rotation: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])  # Euler XYZ radians
    color: str = "#00ff00"
    opacity: float = 0.4
    wireframe: bool = True
    label: Optional[str] = None

class PlaneShape(_BaseShape):
    type: Literal["plane"] = "plane"
    center: List[float]          # [x, y, z]
    normal: List[float]          # [nx, ny, nz] unit vector
    width: float = 10.0
    height: float = 10.0
    color: str = "#4488ff"
    opacity: float = 0.25

class LabelShape(_BaseShape):
    type: Literal["label"] = "label"
    position: List[float]        # [x, y, z]
    text: str
    font_size: int = 14
    color: str = "#ffffff"
    background_color: str = "#000000cc"
    scale: float = 1.0

ShapePayload = Union[CubeShape, PlaneShape, LabelShape]

class ShapeFrame(BaseModel):
    """Published to WS topic 'shapes' every frame."""
    timestamp: float
    shapes: List[ShapePayload]
```

### 3.7 NodeManager Integration

In `app/services/nodes/managers/routing.py` (DataRouter), after `forward_data()` publishes to WebSocket per-node, the `NodeManager` aggregates shapes from all nodes that implement `ShapeCollectorMixin`:

```python
# After all forward_data calls per frame settle:
all_shapes: List[dict] = []
for node in self.nodes.values():
    if isinstance(node, ShapeCollectorMixin):
        for shape in node.collect_and_clear_shapes():
            # stamp id and node_name
            shape.id = _compute_shape_id(node.id, shape)
            shape.node_name = node.name
            all_shapes.append(shape.model_dump())

if all_shapes or websocket_manager.has_subscribers("shapes"):
    frame = ShapeFrame(timestamp=time.time(), shapes=all_shapes)
    await websocket_manager.broadcast("shapes", frame.model_dump())
```

> **Threading note:** `collect_and_clear_shapes()` is called from the asyncio event loop (after `await asyncio.to_thread()` returns), so no locking is needed.

---

## 4. Frontend Design

### 4.1 Three.js Layer Strategy

Three.js `Layers` is a bitmask mechanism. Each `Object3D` carries a `layers` property. The renderer only draws objects whose layer bits overlap with the camera's layer mask.

| Layer Bit | Contents | Camera mask |
|-----------|----------|-------------|
| 0 (default) | Grid, axes helpers, point clouds | enabled (always on) |
| 1 | (reserved — future use) | — |
| 2 | **3D shapes** (cubes, planes, labels) | enabled (always on) |

Point cloud `THREE.Points` objects are added to the scene without any explicit layer change (they remain on layer 0). Shape objects are explicitly set to layer 2 via:

```typescript
object.layers.set(2); // SHAPE_LAYER = 2
```

The camera enables all layers: `camera.layers.enableAll()` — both layers render in the same render pass with no extra draw call overhead.

### 4.2 Service Architecture

#### `ShapesWsService` (`core/services/shapes-ws.service.ts`)

Subscribes to the `shapes` WebSocket topic. Returns an `Observable<ShapeFrame>`. Follows the existing WS lifecycle protocol (code 1001 = intentional close, no reconnect; other codes = reconnect).

```typescript
interface ShapeFrame {
  timestamp: number;
  shapes: ShapeDescriptor[];
}

type ShapeDescriptor = CubeDescriptor | PlaneDescriptor | LabelDescriptor;
```

#### `ShapeLayerService` (`core/services/shape-layer.service.ts`)

Injectable singleton. Owns all Three.js shape objects.

**Responsibilities:**
1. Accept a `THREE.Scene` reference (injected once from `PointCloudComponent` via a shared `SceneRef` token — see §4.3).
2. Maintain `Map<string, THREE.Object3D>` — keyed by shape `id`.
3. On each `ShapeFrame`:
   - Diff incoming `id` set vs. existing map.
   - **New ids** → create Three.js object, assign `layers.set(SHAPE_LAYER)`, add to scene, add to map.
   - **Updated ids** (same id, geometry changed) → mutate existing object (update matrix/uniforms), **do not recreate**.
   - **Stale ids** (in map but not in frame) → remove from scene, dispose geometry+material, delete from map.
4. `disposeAll()` — called on component destroy.

**Shape Builders (static factories):**

```typescript
class ShapeBuilders {
  static buildCube(d: CubeDescriptor): THREE.Object3D;
  static buildPlane(d: PlaneDescriptor): THREE.Object3D;
  static buildLabel(d: LabelDescriptor): THREE.Sprite;
}
```

- **Cube** → `THREE.BoxGeometry(sx, sy, sz)` + `THREE.EdgesGeometry` + `THREE.LineSegments` (wireframe) or `THREE.MeshBasicMaterial` with `transparent: true, depthWrite: false` for solid fill. Positioned via `object.position.set(cx, cy, cz)` + `object.rotation.set(rx, ry, rz)`. Coordinate transform mirrors the point cloud rotation (`rotation.x = -Math.PI/2`, `rotation.z = -Math.PI/2`).

- **Plane** → `THREE.PlaneGeometry(width, height)`. Orientation computed via `quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), normalVec)`. `MeshBasicMaterial` with `transparent: true, side: THREE.DoubleSide`.

- **Label** → `THREE.Sprite` with a `CanvasTexture` (matching existing `createTextSprite` pattern in `PointCloudComponent`). Billboard is camera-facing by default (Three.js Sprite behavior). Position set to `[px, py, pz]`.

### 4.3 Scene Sharing — `SceneRef` Token

Rather than passing `scene` as an `@Input`, introduce an Angular injection token:

```typescript
// core/tokens/scene-ref.token.ts
export const SCENE_REF = new InjectionToken<{ scene: THREE.Scene | null }>('SceneRef');
```

`PointCloudComponent` provides the token:
```typescript
providers: [{ provide: SCENE_REF, useFactory: () => ({ scene: null }) }]
```

After `initThree()`, the component sets `sceneRef.scene = this.scene`. `ShapeLayerService` injects `SCENE_REF` and accesses the scene once it is non-null.

> **Alternative (simpler):** Pass scene through a `ShapeLayerService.init(scene)` call from `PointCloudComponent.ngAfterViewInit()`, after `initThree()` returns. This avoids the token complexity and is preferred.

### 4.4 Frame Processing Flow

```
ShapesWsService.frames$  (Observable<ShapeFrame>)
         │
         ▼
ShapeLayerService.applyFrame(frame: ShapeFrame)
  1. const incomingIds = new Set(frame.shapes.map(s => s.id))
  2. // Remove stale shapes
     for (id of shapeMap.keys()) {
       if (!incomingIds.has(id)) { scene.remove(shapeMap.get(id)); dispose; shapeMap.delete(id); }
     }
  3. // Add or update shapes
     for (shape of frame.shapes) {
       if (!shapeMap.has(shape.id)) {
         obj = ShapeBuilders.build(shape);
         obj.layers.set(SHAPE_LAYER);
         scene.add(obj); shapeMap.set(shape.id, obj);
       } else {
         ShapeBuilders.update(shapeMap.get(shape.id), shape);  // mutate in-place
       }
     }
```

`applyFrame` is called from the RxJS subscription inside `PointCloudComponent` (which already owns the render loop). The subscription is set up in `ngAfterViewInit` after `ShapeLayerService.init(this.scene)`.

### 4.5 Render Loop — No Changes

The existing `animate()` loop in `PointCloudComponent` calls `this.renderer.render(this.scene, this.activeCamera)`. Because `camera.layers.enableAll()` is set during `initThree()`, shape objects on layer 2 are composited into the same render pass automatically. **No changes to `animate()` are required.**

### 4.6 Coordinate System Alignment

Point clouds apply a coordinate rotation at the `THREE.Points` object level:
```
pointsObj.rotation.x = -Math.PI / 2
pointsObj.rotation.z = -Math.PI / 2
```

Shape objects MUST apply the same rotation at the group/mesh level so that world coordinates from the backend (LiDAR Z-up frame) map correctly:
```typescript
const group = new THREE.Group();
group.rotation.x = -Math.PI / 2;
group.rotation.z = -Math.PI / 2;
// add shape mesh as child of group
group.add(shapeMesh);
```

All `ShapeBuilders` must wrap shapes in this rotation group.

### 4.7 Angular Component Structure

```
ShapeLayerService        ← new singleton service
ShapesWsService          ← new WS subscription service  
SceneRef injection call  ← init(scene) in PointCloudComponent

PointCloudComponent      ← inject ShapeLayerService + ShapesWsService
                            call shapeLayer.init(scene) in ngAfterViewInit
                            subscribe shapesWs.frames$ → shapeLayer.applyFrame()
                            call shapeLayer.disposeAll() in ngOnDestroy
```

No new Angular components are required for the initial shape rendering; shapes are pure Three.js objects. A future `ShapeDebugOverlayComponent` (showing shape count/types in a HUD badge) can be added separately.

---

## 5. WebSocket Topic Lifecycle

- Topic `shapes` is registered in `SYSTEM_TOPICS` in `app/services/websocket/manager.py` — it is created at startup and never torn down by node reload.
- Topic `shapes` is registered via `websocket_manager.register_topic("shapes")` in `app/app.py` at startup.
- The frontend `ShapesWsService` subscribes to `shapes`. On WS close code `1001`, it completes the stream (normal DAG reload, shapes will stop updating). On non-1001, it attempts reconnect per existing protocol.
- When no shapes are present in a frame, the backend still publishes `{ timestamp: ..., shapes: [] }` so the frontend can clear all stale objects within the same frame.

---

## 6. Forward Compatibility

The schema uses a `type` discriminator field on every shape. The frontend switch/factory pattern must include a default/unknown branch that **silently skips** unrecognized shape types (log warning only). This ensures future shape types (e.g., `"arrow"`, `"cylinder"`, `"polyline"`) can be added to the backend and deployed without breaking existing frontend builds.

```typescript
function buildShape(d: ShapeDescriptor): THREE.Object3D | null {
  switch (d.type) {
    case 'cube':   return ShapeBuilders.buildCube(d as CubeDescriptor);
    case 'plane':  return ShapeBuilders.buildPlane(d as PlaneDescriptor);
    case 'label':  return ShapeBuilders.buildLabel(d as LabelDescriptor);
    default:
      console.warn(`[ShapeLayerService] Unknown shape type: "${(d as any).type}" — skipping`);
      return null;
  }
}
```

---

## 7. Performance Constraints

| Concern | Constraint | Mitigation |
|---------|-----------|-----------|
| Shape count | ≤ 500 shapes/frame | Backend enforces cap; frontend logs warning if exceeded |
| Frame rate | No degradation of 60 FPS point cloud rendering | Shapes on separate layer; no geometry mutation in `animate()` |
| Geometry recreation | Never recreate geometry for unchanged `id` | `id` hashing ensures stable keys; `ShapeBuilders.update()` mutates uniforms only |
| JSON parse overhead | Shapes topic is JSON, not binary LIDR | Acceptable: shapes are low-frequency metadata (~50–500 objects, not 100k float32s) |
| Memory leaks | All disposed geometries/materials must be explicitly freed | `dispose()` called in all removal paths; `ngOnDestroy` disposes all |

---

## 8. Error Resilience

- **Malformed JSON frame**: `ShapesWsService` wraps parse in try/catch; drops frame and logs error; does not clear existing shapes.
- **Unknown shape type**: Silent skip (§6).
- **Missing `id` field**: Backend always assigns id before broadcast. Frontend guard: if `id` is empty string, generate a temporary local id but log a backend contract violation warning.
- **WebSocket disconnect during active session**: `ShapesWsService` attempts reconnect on non-1001 close. During the reconnect gap, shapes remain frozen on screen (intentional — better than flickering empty scene).

---

## 9. Files to Create / Modify

### Backend (new)
| File | Action |
|------|--------|
| `app/services/nodes/shapes.py` | New — Pydantic shape models + `ShapeFrame` |
| `app/services/nodes/shape_collector.py` | New — `ShapeCollectorMixin` |
| `app/services/nodes/managers/routing.py` | Modify — aggregate + publish shapes after forward_data |
| `app/services/websocket/manager.py` | Modify — add `"shapes"` to `SYSTEM_TOPICS` |
| `app/app.py` | Modify — register `shapes` topic at startup |

### Frontend (new)
| File | Action |
|------|--------|
| `web/src/app/core/services/shapes-ws.service.ts` | New — WS subscription + types |
| `web/src/app/core/services/shape-layer.service.ts` | New — Three.js shape lifecycle |
| `web/src/app/features/workspaces/components/point-cloud/point-cloud.component.ts` | Modify — init ShapeLayerService, subscribe ShapesWsService |

### Tests (new)
| File | Action |
|------|--------|
| `tests/unit/test_shapes.py` | New — Pydantic model tests, id hash stability |
| `tests/unit/test_shape_collector.py` | New — mixin emit/collect/clear cycle |
| `tests/integration/test_shapes_ws.py` | New — WS broadcast integration test |
| `web/src/app/core/services/shape-layer.service.spec.ts` | New — add/update/remove diffing |
| `web/src/app/core/services/shapes-ws.service.spec.ts` | New — WS message parsing |
