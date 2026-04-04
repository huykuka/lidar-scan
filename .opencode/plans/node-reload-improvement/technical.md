# Node Reload Improvement — Technical Blueprint

## 1. Executive Summary

The current `reload_config()` in `NodeManager` forces a **full DAG teardown** including stopping all nodes, a mandatory 2-second `asyncio.sleep`, and destroying all WebSocket topics. This causes multi-second outages and WebSocket reconnections across the entire graph for even single-node config changes.

This blueprint introduces a **Selective Node Reload** system that:
- Diffs incoming node configs against running instances using SHA-256 hash comparison
- Tears down and reinstantiates **only changed nodes** (O(n\_changed) instead of O(n\_total))
- **Preserves WebSocket topic identifiers** for unchanged nodes so frontend connections never drop
- **Buffers data at downstream nodes** during reload via a per-node asyncio.Event gate
- Targets <500ms end-to-end reload for a single-node change

---

## 2. Architecture Decision Record — Open Questions

### Q1: State Preservation Strategy

**Decision: Clean-State Restart for Changed Nodes**

When a node is reloaded, it is torn down and re-instantiated fresh with the new configuration. Internal buffers and caches (e.g., calibration frame buffers in `CalibrationNode`) are **not preserved**. Rationale:
- Config changes to sensor parameters (IP, port, scan profiles) require hardware-level reconnection; preserving stale buffers would emit corrupt data.
- Config changes to processing operations (filter thresholds, ICP params) require reprocessing with clean inputs to produce valid output.
- State preservation complexity is prohibitive for v1.
- Downstream buffering (Q4 below) prevents data loss across the boundary.

For future rollback capability (Q5), the **old instance is held in a temporary variable** until the new instance confirms its first successful `on_input` or `start()` call. After confirmation, the old instance is discarded. This "warm swap" slot enables rollback without a separate API.

### Q2: Dependency Chain Notification

**Decision: Pause-and-Buffer Pattern (no cache invalidation)**

When Node A (an upstream node) is reloaded:
1. All **direct downstream nodes** (e.g., Node B, Node C) receive a `pause_input()` signal before teardown begins.
2. They gate incoming data in a bounded `asyncio.Queue` (capacity = 30 frames, ~500ms at 60fps).
3. After Node A's new instance starts and emits its first frame, downstream nodes receive a `resume_input()` signal and drain the buffer sequentially.
4. **There is no cache invalidation** — nodes process fresh data from the restarted upstream.

Downstream nodes do **not** self-restart. Only the explicitly changed node restarts. This prevents cascading restarts.

### Q3: Thread Pool Management

**Decision: New Thread Pool Slot per Reload; No Explicit Pool Reuse**

The system already uses `asyncio.to_thread()` for Open3D operations (from `routing.py::_broadcast_to_websocket`). Python's default `ThreadPoolExecutor` managed by asyncio handles thread lifecycle automatically.

For node-specific threads (e.g., a `LidarSensor` spawning a `multiprocessing.Process`):
- On reload, the old node's `.stop()` method is called, which must terminate its subprocess.
- The `NodeManager.data_queue` is **not** replaced during selective reload (unlike full reload). The existing `mp.Queue` continues to serve unchanged sensor nodes.
- The new sensor node instance receives the same `data_queue` reference.
- The `_queue_listener` task is **not** cancelled or restarted.

**Architectural Constraint**: Nodes must implement `.stop()` correctly to terminate their subprocess and release UDP port bindings. The reload system trusts this contract. Any port-binding errors during re-initialization surface as reload failures.

### Q4: WebSocket Topic Management

**Decision: Topic Preservation for Unchanged Nodes + Re-registration for Changed Nodes**

This is the **critical insight** that enables zero connection drops:

- **Unchanged nodes**: Their `_ws_topic` attribute remains untouched. The `ConnectionManager.active_connections` dict entry is never removed. Clients streaming that topic never receive a `1001` close frame and continue uninterrupted.
- **Changed nodes**: The old instance's `_ws_topic` is read before teardown. The new instance is **re-registered to the same topic name** (since the topic is deterministically derived from `{slugified_name}_{node_id[:8]}` and neither the name nor the node ID changes). The topic's WebSocket connections are NOT closed — they are preserved across the instance swap.

**The key procedure for changed nodes:**
1. Read `old_instance._ws_topic` → save as `preserved_topic`.
2. Call `old_instance.stop()` only (do NOT call `unregister_topic`).
3. Remove old instance from `NodeManager.nodes`.
4. Create new instance via `NodeFactory.create()`.
5. Set `new_instance._ws_topic = preserved_topic` (do not call `register_topic` again since the topic already exists in `active_connections`).
6. Insert new instance into `NodeManager.nodes`.

This avoids any `unregister_topic` call and therefore no `1001` close frames are sent.

### Q5: Config Rollback Architecture (Future-Readiness)

**Decision: Warm-Swap Slot + Rollback-Ready Architecture**

While auto-rollback is out of scope for v1, the design must not foreclose it. The `SelectiveReloadManager` will maintain a `_rollback_slot: Dict[str, Any]` dict mapping `node_id → old_instance`. This slot is populated before teardown and cleared after the new instance confirms healthy (first frame forwarded). 

In v2, a rollback API can simply pop the slot and do a reverse swap. For v1, the slot is always cleared after successful new-instance startup (or on reload failure, logged and cleared).

### Q6: Batching / Debounce Strategy

**Decision: Reject Concurrent Reloads + 150ms Frontend Debounce**

Per requirements, concurrent server-side reloads are rejected via the existing `_reload_lock`. However, a **150ms debounce** is applied **in the frontend** (`CanvasEditStoreService.saveAndReload`) before dispatching the HTTP PUT. This is sufficient to batch rapid slider adjustments or multi-field form edits into a single save operation. No server-side debounce is added (adds complexity, breaks the simple lock model).

The 150ms debounce window:
- Is below the 500ms perception threshold.
- Is reset on each additional change within the window.
- Does not apply to programmatic saves (import, topology changes).

---

## 3. System Design

### 3.1 New Component: `SelectiveReloadManager`

A new manager class added to `app/services/nodes/managers/selective_reload.py`, following the existing sub-manager pattern (see `ConfigLoader`, `LifecycleManager`, `DataRouter`).

```
app/services/nodes/managers/
├── config.py          (existing)
├── lifecycle.py       (existing)
├── routing.py         (existing)
├── throttling.py      (existing)
├── selective_reload.py  ← NEW
└── __init__.py        (updated to export SelectiveReloadManager)
```

**Responsibilities:**
- Config hashing and change detection
- Orchestrating the partial tear-down + rebuild sequence
- Managing the per-node input buffer gate (pause/resume)
- Owning the warm-swap rollback slot

### 3.2 New Method: `NodeManager.selective_reload_node()`

A new public async method on `NodeManager` that replaces `reload_config()` as the target for single-node changes:

```python
async def selective_reload_node(self, node_id: str) -> SelectiveReloadResult
```

The existing `reload_config()` is **not removed** — it remains for full DAG reloads (topology changes, import, initial startup). The new `selective_reload_node()` is used exclusively when the diff logic determines only parameter changes to a running node.

### 3.3 Config Hashing & Change Detection

A new service module: `app/services/nodes/config_hasher.py`

```python
def compute_node_config_hash(node_data: Dict[str, Any]) -> str:
    """SHA-256 of (id, type, category, enabled, visible, config, pose) sorted JSON."""
```

Fields **excluded** from hash (do not trigger reload):
- `x`, `y` (canvas position — cosmetic only, not runtime-relevant)
- `name` (does not affect node behavior; topic names use node_id prefix)

Fields **included** in hash (trigger reload when changed):
- `type`, `category`, `enabled`, `visible`, `config`, `pose`

A `ConfigHashStore` maintains a dict `node_id → hash` of the **currently running** node configurations. It is populated during `load_config()` and updated after each successful selective reload.

### 3.4 New REST Endpoint: `POST /api/v1/nodes/{node_id}/reload`

This endpoint triggers a selective reload of a single node's runtime. It is called automatically by the updated `save_dag_config()` service when only parameter changes are detected.

The `save_dag_config()` logic is enhanced with a **post-save diff** step:

```
PUT /dag/config → DB transaction → diff changed IDs → 
  if only_parameter_changes → POST /nodes/{id}/reload (per changed node, sequential)
  else → reload_config() (full reload, topology change)
```

### 3.5 Input Buffer Gate

New class `NodeInputGate` in `app/services/nodes/input_gate.py`:

```python
class NodeInputGate:
    """asyncio.Event-based gate + bounded queue for pause/resume data flow."""
    
    def __init__(self, capacity: int = 30):
        self._gate: asyncio.Event  # set = open, clear = paused
        self._buffer: asyncio.Queue
    
    async def wait_if_paused(self, payload): ...  # blocks if gate cleared
    async def pause(self): ...  # clears gate, activates buffering
    async def resume(self): ...  # drains buffer, sets gate
```

The `DataRouter._forward_to_downstream_nodes()` is augmented to check a per-node gate before calling `on_input`.

### 3.6 New WebSocket Event: `node_reload_status`

A new JSON broadcast on the `system_status` topic (no new topic needed) carries reload progress. The `SystemStatusBroadcast` schema is extended:

```json
{
  "nodes": [...],
  "reload_event": {
    "node_id": "abc123",
    "status": "reloading" | "ready" | "error",
    "error_message": null
  }
}
```

Frontend `SystemStatusService` already subscribes to `system_status` — it will receive reload progress events without new WebSocket connections.

---

## 4. Call Graph Changes

### 4.1 Backend: New Code Path

```
PUT /dag/config
  └─ save_dag_config() [dag/service.py]
       ├─ DB transaction (unchanged)
       ├─ NEW: compute diff (compare new node configs vs ConfigHashStore)
       ├─ if topology_change (add/remove nodes OR edge changes):
       │    └─ node_manager.reload_config()       [existing full reload]
       └─ if param_change_only (same node_ids, only config/pose/visible changed):
            └─ for each changed_node_id:
                 └─ node_manager.selective_reload_node(node_id)  [NEW]
```

```
NodeManager.selective_reload_node(node_id)
  └─ SelectiveReloadManager.reload_single_node(node_id)
       ├─ 1. Broadcast reload_event: "reloading"
       ├─ 2. Pause downstream nodes (NodeInputGate.pause())
       ├─ 3. _lifecycle_manager._stop_node(old_instance)  [existing]
       ├─ 4. NodeFactory.create(new_node_data, ...)       [existing]
       ├─ 5. Preserve _ws_topic: new_instance._ws_topic = old_instance._ws_topic
       ├─ 6. new_instance.start() or new_instance.enable()
       ├─ 7. node_manager.nodes[node_id] = new_instance
       ├─ 8. ConfigHashStore.update(node_id, new_hash)
       ├─ 9. Resume downstream nodes (NodeInputGate.resume())
       └─ 10. Broadcast reload_event: "ready"
```

### 4.2 Backend: Modified Symbols (GitNexus Impact Assessment)

| Symbol | File | Change Type | Risk |
|--------|------|-------------|------|
| `save_dag_config` | `app/api/v1/dag/service.py` | Modified (add diff logic) | MEDIUM — tested by `TestSaveDagConfig` |
| `NodeManager.__init__` | `orchestrator.py` | Modified (add `_selective_reload_manager`, `_config_hash_store`) | LOW |
| `NodeManager.load_config` | `orchestrator.py` | Modified (populate hash store after init) | LOW |
| `DataRouter._forward_to_downstream_nodes` | `routing.py` | Modified (add gate check) | MEDIUM — hot path |
| `ConfigLoader._create_node` | `config.py` | Modified (record hash after creation) | LOW |
| `SelectiveReloadManager` | `selective_reload.py` | NEW | — |
| `ConfigHasher` | `config_hasher.py` | NEW | — |
| `NodeInputGate` | `input_gate.py` | NEW | — |
| `LifecycleManager` | `lifecycle.py` | **NOT MODIFIED** — used as-is via delegation | — |
| `ConnectionManager` | `websocket/manager.py` | **NOT MODIFIED** | — |
| `reload_config` | `orchestrator.py` | **NOT MODIFIED** — still handles full reload | — |

### 4.3 Frontend: Modified Components

| Component/Service | File | Change |
|-------------------|------|--------|
| `CanvasEditStoreService` | `canvas-edit-store.service.ts` | Add 150ms debounce to `saveAndReload()` |
| `SystemStatusService` | `system-status.service.ts` | Parse `reload_event` from `system_status` broadcast |
| `FlowCanvasNodeComponent` | `flow-canvas-node.component.ts` | Read `reloadingNodeIds` signal, apply visual state |
| `DagApiService` | `dag-api.service.ts` | No changes needed (uses existing PUT /dag/config) |

---

## 5. WebSocket Topic Preservation — Detailed Flow

The following sequence shows a single-node reload where `node_id = "abc12345"` (e.g., a sensor node changing hostname):

```
t=0ms   User changes sensor IP in UI
t=150ms Debounce fires → PUT /dag/config sent
t=151ms DB transaction commits (new IP saved)
t=152ms save_dag_config: diff → param_change_only on ["abc12345"]
t=153ms selective_reload_node("abc12345") begins
        → WS broadcast: reload_event{node_id:"abc12345", status:"reloading"}
        → Frontend: node "abc12345" shows reloading indicator

t=155ms Downstream nodes [downstream B, C] paused via NodeInputGate
        → Data arriving at B/C's on_input goes into buffer queue

t=157ms old_instance._ws_topic = "multiscan_left_abc12345" (saved)
        old_instance.stop() called → sensor subprocess terminates
        NodeManager.nodes["abc12345"] = None (temporarily)

t=165ms NodeFactory.create(new_node_data, ...) → new_instance
        new_instance._ws_topic = "multiscan_left_abc12345"  ← SAME TOPIC, no unregister
        new_instance.start(data_queue, ...)
        NodeManager.nodes["abc12345"] = new_instance

t=175ms ConfigHashStore.update("abc12345", new_hash)
        NodeInputGate.resume() on downstream B, C → buffer drains
        WS broadcast: reload_event{node_id:"abc12345", status:"ready"}
        → Frontend: reloading indicator removed

t=176ms Frontend clients streaming "multiscan_left_abc12345":
        ZERO close frames received. Connection never interrupted.
```

**Total elapsed: ~26ms backend + network latency ≈ <100ms end-to-end** (well within 500ms target).

---

## 6. DataRouter Hot-Path Gate Modification

The gate check in `DataRouter._forward_to_downstream_nodes` must be minimal-overhead for the common case (gate open, no reload happening):

```python
# In DataRouter._forward_to_downstream_nodes:
for target in targets:
    target_id = target.get("target_id")
    ...
    # Gate check — O(1) dict lookup + Event.is_set() check (non-blocking)
    gate = self.manager._input_gates.get(target_id)
    if gate is not None and not gate.is_open():
        await gate.buffer(payload)  # non-blocking put_nowait, drops if full
        continue
    await self._send_to_target_node(source_id, target_id, payload)
```

The gate is only created (`NodeInputGate` instantiated) when a reload begins and deleted after resume. Normal operation has `None` for every gate lookup — essentially zero overhead.

---

## 7. Concurrent Reload Serialization

The existing `_reload_lock: asyncio.Lock` on `NodeManager` continues to protect both `reload_config()` and `selective_reload_node()`. Multiple concurrent save requests with different `node_id`s will be serialized. This is acceptable for v1.

The `save_dag_config()` service continues to reject incoming requests with a 409 if `_reload_lock.locked()`. Frontend shows appropriate error toast.

---

## 8. Error Handling

| Scenario | Behavior |
|----------|----------|
| `NodeFactory.create()` raises | New instance discarded. Old instance restored from rollback slot. Downstream gates resumed. `reload_event{status:"error"}` broadcast. HTTP 500 returned to caller. |
| `new_instance.start()` raises (e.g., port already bound) | Same as above — instance discarded, old instance restored. |
| `old_instance.stop()` raises | Logged as WARNING. Proceed with new instance creation (old process may be zombie, but port may still be bound — surface as start() failure). |
| Gate buffer fills up (>30 frames) | Frames dropped with DEBUG log. Downstream node may briefly stutter post-resume but does not crash. |
| Reload takes >500ms | Allowed to complete. Log WARNING. Reload event still sent as "ready" on completion. |

---

## 9. Topology Change Detection Logic

In `save_dag_config()`, after the DB transaction commits, the diff algorithm:

```python
def classify_dag_changes(old_nodes, new_nodes, old_edges, new_edges):
    old_ids = {n.id for n in old_nodes}
    new_ids = {n.id for n in new_nodes}
    
    if old_ids != new_ids:
        return "topology"  # nodes added/removed → full reload
    
    edges_changed = not edges_equal(old_edges, new_edges)
    if edges_changed:
        return "topology"  # routing changed → full reload
    
    # Same node set, same edges → find parameter-changed nodes
    changed_node_ids = []
    for node in new_nodes:
        if config_hash_store.get(node.id) != compute_node_config_hash(node.dict()):
            changed_node_ids.append(node.id)
    
    return ("param_change", changed_node_ids) if changed_node_ids else "no_change"
```

---

## 10. Frontend Reload Indicator

### Signal Architecture

In `SystemStatusService`, add a new computed signal:

```typescript
readonly reloadingNodeIds = signal<Set<string>>(new Set());
```

When a `system_status` broadcast arrives with `reload_event`:
- `status === "reloading"` → add `node_id` to the set
- `status === "ready" | "error"` → remove `node_id` from the set

### Visual Treatment in FlowCanvasNodeComponent

The `FlowCanvasNodeComponent` (presentation layer) receives `isReloading: InputSignal<boolean>` as a signal input. When true:
- Node card receives a Tailwind CSS class `animate-pulse opacity-70`
- A small spinner overlay appears on the node badge area
- Edges connected to this node are **not** affected visually

This is a purely CSS-class toggle — no Three.js re-render, no BufferGeometry mutation, no DAG re-layout.

---

## 11. Architectural Hazards Identified

### Hazard 1: `multiprocessing.Queue` data_queue is shared

The sensor node receives `data_queue` in `start()`. During selective reload, the **same queue** is passed to the new sensor instance. This is correct behavior — the queue listener task continues running uninterrupted. However, there is a **brief window** (stop→start) where no consumer processes queue frames from that sensor. With `maxsize=500`, this is safe unless the sensor is extremely high-throughput.

**Mitigation**: The `_queue_listener` task is not cancelled. Frames arriving during the 10-20ms gap sit in the queue and are processed as soon as the new instance registers its handler.

### Hazard 2: Duplicate `_ws_topic` registration

If `_register_node_websocket_topic()` in `ConfigLoader` is called during selective reload, it would call `manager.register_topic(topic)` again on an already-registered topic. The existing `register_topic()` is idempotent (`if topic not in active_connections`), so this is safe. But to be explicit: selective reload skips calling `_register_node_websocket_topic()` entirely and directly sets `new_instance._ws_topic = preserved_topic`.

### Hazard 3: Status Aggregator Node Iteration

`_collect_and_broadcast()` in `status_aggregator.py` iterates `node_manager.nodes.items()` and calls `emit_status()` on each node. During the brief window where `NodeManager.nodes[node_id]` is removed (step between stop and new instance creation), the status aggregator could miss this node's status update. This is acceptable — the aggregator broadcasts on a 1-second poll cycle and will include the new instance on its next broadcast.

**Mitigation**: The reload procedure does not set `nodes[node_id] = None` — it removes the key entirely (using `nodes.pop(node_id)`) then immediately re-inserts with the new instance. The window is a single coroutine switching point (not a full asyncio event loop tick), making a concurrent iteration collision extremely unlikely.

### Hazard 4: Throttle State Continuity

`_throttle_config`, `_last_process_time`, `_throttled_count` are keyed by `node_id`. During selective reload, these are **preserved** (not cleared) since the node_id does not change. The throttle interval from the new config is re-applied. This is the correct behavior — throttle rate may have changed in the new config.

### Hazard 5: `asyncio.Lock` and HTTP 409 UX

A selective reload for a large node (e.g., restarting an ICP fusion node that loads a 50MB point cloud) might hold the lock for 400ms. A second save arriving during this window receives a 409. The frontend must display a user-friendly message ("Reload in progress, please retry") and not mark the save as failed. The 409 message is already handled in `CanvasEditStoreService.saveAndReload()` for version conflicts but needs an update to distinguish reload-in-progress 409s.

---

## 12. Performance Budget

| Phase | Target | Mechanism |
|-------|--------|-----------|
| Config diff computation | <2ms | SHA-256 of sorted JSON, in-memory dict lookup |
| Downstream gate pause | <1ms | asyncio.Event.clear() per downstream node |
| old_instance.stop() | <10ms | node .stop() + subprocess join (with timeout) |
| NodeFactory.create() | <5ms | Python object instantiation, no I/O |
| new_instance.start() | <50ms | Network reconnection may take longer for sensors |
| Downstream gate resume + drain | <5ms | asyncio.Queue.get_nowait() in loop |
| WebSocket status broadcast | <1ms | Fire-and-forget JSON broadcast |
| **Total backend** | **<75ms** | Leaves 425ms budget for network/sensor reconnect |
| Frontend indicator update | <16ms | Signal update → one render frame |
| **Total user-perceived** | **<500ms** | Target met |

