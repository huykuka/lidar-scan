# Backend Tasks — 3D Shape Rendering

**Feature:** Real-time 3D shape overlay  
**References:** `technical.md` §3, `api-spec.md`  
**Assigned to:** @be-dev

---

## Prerequisites

- Read `technical.md` §3 (Backend Design) fully before starting.
- Read `api-spec.md` for the exact JSON schema and field constraints.
- All Pydantic models use V2 syntax (`model_dump()`, not `.dict()`).
- All Open3D operations in `on_input()` remain on `asyncio.to_thread()`.

---

## Tasks

### BE-01 — Shape Pydantic Models
- [x] Create `app/services/nodes/shapes.py`
- [x] Define `_BaseShape(BaseModel)` with `id: str`, `node_name: str`, `type: str`, `Config.extra = "forbid"`
- [x] Define `CubeShape(_BaseShape)` with all fields per `api-spec.md §4.1`
- [x] Define `PlaneShape(_BaseShape)` with all fields per `api-spec.md §4.2`
- [x] Define `LabelShape(_BaseShape)` with all fields per `api-spec.md §4.3`
- [x] Define `ShapePayload = Union[CubeShape, PlaneShape, LabelShape]` (discriminated by `type`)
- [x] Define `ShapeFrame(BaseModel)` with `timestamp: float` and `shapes: List[ShapePayload]`
- [x] Validate: `ShapeFrame.model_dump()` serializes cleanly to the example payload in `api-spec.md §5`

### BE-02 — ShapeCollectorMixin
- [x] Create `app/services/nodes/shape_collector.py`
- [x] Implement `ShapeCollectorMixin` class with:
  - [x] `_pending_shapes: List[ShapePayload]` initialized in `__init__`
  - [x] `emit_shape(shape: ShapePayload) -> None` — appends to `_pending_shapes`
  - [x] `collect_and_clear_shapes() -> List[ShapePayload]` — returns copy and clears list
- [x] Add module exports to `app/services/nodes/__init__.py`

### BE-03 — Shape ID Hashing Utility
- [x] In `app/services/nodes/shapes.py`, implement `compute_shape_id(node_id: str, shape: ShapePayload) -> str`
- [x] Strategy: `sha256(node_id + "|" + shape.type + "|" + geometry_key)[:16]`
- [x] Geometry key rules:
  - `cube` → `"|".join(str(round(v,3)) for v in center + size)`
  - `plane` → `"|".join(str(round(v,3)) for v in center + normal)`
  - `label` → `"|".join(str(round(v,3)) for v in position) + "|" + text`
- [x] Verify: same geometry + same node_id always → same 16-char hex id
- [x] Verify: different geometry → different id (collision tests)

### BE-04 — Register `shapes` System Topic
- [x] In `app/services/websocket/manager.py`, add `"shapes"` to the `SYSTEM_TOPICS` set
- [x] In `app/app.py` (startup/lifespan), call `websocket_manager.register_topic("shapes")`
- [x] Verify `shapes` does NOT appear in the `/api/v1/topics` response

### BE-05 — NodeManager Shape Aggregation
- [x] In `app/services/nodes/managers/routing.py` (DataRouter), after the per-node `forward_data` path:
  - [x] Iterate `self.manager.nodes.values()`
  - [x] For each node that `isinstance(node, ShapeCollectorMixin)`:
    - [x] Call `node.collect_and_clear_shapes()`
    - [x] For each shape, assign `shape.id = compute_shape_id(node.id, shape)`
    - [x] Assign `shape.node_name = node.name`
    - [x] Append `shape.model_dump()` to `all_shapes`
  - [x] If `all_shapes` is non-empty OR `websocket_manager.has_subscribers("shapes")`:
    - [x] Build `ShapeFrame(timestamp=time.time(), shapes=all_shapes)`
    - [x] `await websocket_manager.broadcast("shapes", frame.model_dump())`
- [x] Aggregation must NOT block the event loop — `collect_and_clear_shapes()` is synchronous and fast

### BE-06 — Example Node: Open3D Bounding Box Emitter
- [x] Identify or create a processing node that produces Open3D `AxisAlignedBoundingBox` (e.g., in `app/modules/pipeline/` or `app/modules/application/`)
- [x] Make that node inherit both `ModuleNode` AND `ShapeCollectorMixin`
- [x] In `on_input()`, after computing the bounding box, call:
  ```python
  bbox = pcd.get_axis_aligned_bounding_box()
  self.emit_shape(CubeShape(
      center=bbox.get_center().tolist(),
      size=bbox.get_extent().tolist(),
      color="#00ff00",
      wireframe=True,
  ))
  ```
- [x] Run with `await asyncio.to_thread(...)` if the bbox computation is CPU-heavy

### BE-07 — Startup Shape Topic Lifecycle Test
- [x] Verify that after `app.py` startup, `GET /api/v1/topics` does NOT include `"shapes"`
- [x] Verify that a WebSocket client can connect to `ws://.../ws/shapes` and receive `ShapeFrame` JSON
- [x] Verify that after a full `reload_config()`, the `shapes` topic survives (it is a system topic)

### BE-08 — Shape Count Cap
- [x] In the aggregation loop (BE-05), after collecting all shapes:
  - [x] If `len(all_shapes) > 500`, truncate to first 500 and `logger.warning(...)`
- [x] Add unit test for the cap behavior

---

## Dependencies / Order

```
BE-01 → BE-02 → BE-03 → BE-04 → BE-05 → BE-06 → BE-07
```

BE-04 can be done in parallel with BE-01 through BE-03.
