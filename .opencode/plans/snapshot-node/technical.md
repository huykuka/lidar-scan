# Snapshot Node — Technical Design

## 1. Overview

A flow-control `ModuleNode` that acts as a **triggered passthrough gate**: it caches the most recent upstream
payload in memory and, on receiving a `POST /api/v1/nodes/{node_id}/trigger` call, atomically snapshots that
payload and forwards it downstream via `manager.forward_data()`. No WebSocket topic; no persistence.

---

## 2. Module Layout

```
app/modules/flow_control/snapshot/
├── __init__.py
├── node.py        ← SnapshotNode class
└── registry.py    ← NodeFactory registration + node_schema_registry entry

app/api/v1/flow_control/
├── handler.py     ← ADD trigger endpoint (extend existing router)
├── service.py     ← ADD trigger_snapshot() service function
└── dto.py         ← ADD SnapshotTriggerResponse Pydantic model
```

`app/modules/flow_control/registry.py` — add import of `snapshot.registry`.

---

## 3. `SnapshotNode` Class (`node.py`)

```python
class SnapshotNode(ModuleNode):
    id: str
    name: str
    manager: Any
    _ws_topic = None            # invisible node

    # ── mutable state ──────────────────────────────────────────────
    _latest_payload: Optional[Dict[str, Any]]   # last upstream frame
    _is_processing: bool                         # concurrency guard (409)
    _last_trigger_time: float                    # throttle clock (429)
    throttle_ms: float                           # config: 0 = no limit

    # ── counters for emit_status() ─────────────────────────────────
    _snapshot_count: int
    _last_trigger_at: Optional[float]
    _last_error: Optional[str]
    _error_count: int
```

### 3.1 `async def on_input(self, payload)`

Called by `NodeManager` for every upstream frame. Simply stores the payload:

```
self._latest_payload = payload
```

No forwarding; no side effects. This method must be non-blocking and fast.

### 3.2 `async def trigger_snapshot(self) -> None`  *(called by service layer)*

```
1.  Check _is_processing → raise HTTPException 409
2.  Check throttle_ms window  → raise HTTPException 429
3.  Check _latest_payload is None → raise HTTPException 404
4.  Set _is_processing = True
5.  try:
      snapshot = dict(_latest_payload)   # shallow copy — safe for immutable numpy refs
      await manager.forward_data(self.id, snapshot)
      _snapshot_count += 1
      _last_trigger_at = time.time()
      _last_error = None
      notify_status_change(self.id)
6.  except Exception as e:
      _last_error = str(e)
      _error_count += 1
      notify_status_change(self.id)
      raise HTTPException(500, detail=…)
7.  finally:
      _is_processing = False
      _last_trigger_time = now  (only on success path, step 5)
```

> **Threading**: `manager.forward_data` is already async. If downstream processing is heavy
> (e.g. Open3D ops inside a downstream node), those nodes offload to `asyncio.to_thread()` 
> themselves — the snapshot node does **not** need its own threadpool dispatch.

### 3.3 `def emit_status(self) -> NodeStatusUpdate`

| Condition | `operational_state` | `application_state` |
|---|---|---|
| `_last_error` set | `ERROR` | `label="snapshot"`, `value="error"`, `color="red"` |
| `_last_trigger_at` < 5 s ago | `RUNNING` | `label="snapshot"`, `value=_snapshot_count`, `color="blue"` |
| idle | `RUNNING` | `label="snapshot"`, `value=_snapshot_count`, `color="gray"` |

---

## 4. Registry (`registry.py`)

Pattern mirrors `if_condition/registry.py` exactly:

```python
node_schema_registry.register(NodeDefinition(
    type="snapshot",
    display_name="Snapshot",
    category="flow_control",
    description="Captures latest upstream point cloud on HTTP trigger",
    icon="camera",
    websocket_enabled=False,
    properties=[
        PropertySchema(name="throttle_ms", label="Throttle (ms)",
                       type="number", default=0, min=0, step=10,
                       help_text="Min ms between successful triggers (0=off)")
    ],
    inputs=[PortSchema(id="in", label="Input", data_type="pointcloud")],
    outputs=[PortSchema(id="out", label="Output", data_type="pointcloud")]
))

@NodeFactory.register("snapshot")
def build(node, service_context, edges): ...
```

---

## 5. API Layer

### 5.1 `dto.py` additions

```python
class SnapshotTriggerResponse(BaseModel):
    status: Literal["ok"]
```

### 5.2 `service.py` — `trigger_snapshot(node_id: str)`

```python
async def trigger_snapshot(node_id: str) -> SnapshotTriggerResponse:
    node = node_manager.nodes.get(node_id)
    if not node or not isinstance(node, SnapshotNode):
        raise HTTPException(404, "Node not found or not a snapshot node")
    # Let SnapshotNode.trigger_snapshot() raise 404/409/429/500 as appropriate
    await node.trigger_snapshot()
    return SnapshotTriggerResponse(status="ok")
```

`HTTPException` from `SnapshotNode.trigger_snapshot()` propagates directly up to FastAPI —
consistent with `trigger_calibration` pattern in `app/api/v1/calibration/service.py`.

### 5.3 `handler.py` — new endpoint added to existing `flow_control` router

```python
@router.post(
    "/nodes/{node_id}/trigger",
    response_model=SnapshotTriggerResponse,
    responses={
        404: {"description": "No upstream data available or node not found"},
        400: {"description": "Invalid node_id"},
        409: {"description": "Trigger dropped: prior snapshot still processing"},
        429: {"description": "Trigger dropped: throttle window active"},
        500: {"description": "Internal processing error"},
    },
    summary="Trigger Snapshot",
    description="Capture the latest upstream point cloud and forward it downstream."
)
async def trigger_snapshot_endpoint(node_id: str):
    return await trigger_snapshot(node_id)
```

**No separate router/`__init__.py` changes needed** — the new endpoint is added to the
*existing* `flow_control_router` which is already registered in `app/api/v1/__init__.py`.

---

## 6. DAG Integration Points

| Integration Point | Action |
|---|---|
| `app/modules/flow_control/registry.py` | Add `from .snapshot import registry as snapshot_registry` |
| `app/api/v1/flow_control/dto.py` | Add `SnapshotTriggerResponse` |
| `app/api/v1/flow_control/service.py` | Add `trigger_snapshot()` |
| `app/api/v1/flow_control/handler.py` | Add `POST /nodes/{node_id}/trigger` endpoint |
| Node `_ws_topic = None` | Ensures no WebSocket topic is registered during `load_config` |

---

## 7. Concurrency & Edge Cases

| Scenario | Handling |
|---|---|
| Trigger before first upstream frame | `_latest_payload is None` → HTTP 404 |
| Concurrent triggers (racing POST calls) | `_is_processing` flag → HTTP 409 (drop) |
| Rapid triggers within `throttle_ms` window | Compare `time.time() - _last_trigger_time` → HTTP 429 |
| `forward_data` raises (downstream crash) | Catch `Exception`, set `_last_error`, raise HTTP 500 |
| `on_input` racing with `trigger_snapshot` | Python GIL + asyncio single-threaded event loop provides safe read of `_latest_payload`; shallow copy before forwarding eliminates mutation risk |
| Node removed from DAG mid-trigger | Service layer `node_manager.nodes.get()` returns `None` → 404 |

---

## 8. Code Reuse Notes

- **`IfConditionNode`**: Structural template (same `__init__` shape, `emit_status` pattern, registry layout).
- **`trigger_calibration` service**: Template for the service→handler→HTTPException propagation pattern.
- **`notify_status_change`**: Reused directly, no changes.
- **`NodeFactory.register` / `node_schema_registry`**: Reused unchanged.
- No new base classes or abstractions needed. The node is purposefully simple.
