# Technical Specification — WebSocket Topic Cleanup on Config Reload

**Feature:** `websocket-topic-cleanup`  
**Author:** @architecture  
**Date:** 2026-03-08  
**Status:** Approved for Implementation

---

## 1. Problem Statement & Root-Cause Analysis

### 1.1 Bug Description

When a node is removed from the system configuration and `NodeManager.reload_config()` is called (via `POST /api/v1/nodes/reload` or `POST /api/v1/config/import`), WebSocket topics that belonged to the removed node persist in `ConnectionManager.active_connections`. This has three concrete consequences:

1. **Stale topics appear in `GET /api/v1/topics`** — the frontend `TopicApiService` lists topics that have no producing node behind them, leading to ghost entries in the workspace UI.
2. **`_interceptors` hold live `asyncio.Future` objects** tied to dead topics — these futures will never resolve, causing silent memory growth and potential timeout storms when many reloads occur.
3. **Active WebSocket client connections on dead topics are never closed** — clients (`MultiWebsocketService`) remain in a `OPEN` readyState while the server-side `active_connections[topic]` list holds stale `WebSocket` objects that will cause `RuntimeError: Unexpected ASGI message` on the next broadcast attempt.

### 1.2 Precise Failure Path

```
reload_config()
  └── stop()                             ← nodes stopped, queue listener cancelled
  └── _cleanup_all_nodes()
        └── for node_id in nodes:
              remove_node(node_id)
                └── LifecycleManager.remove_node()
                      └── _unregister_node_websocket_topic()
                            └── ConnectionManager.unregister_topic(topic)
                                  del active_connections[topic]   ← ✓ cleaned
                                  del _interceptors[topic]        ← ✓ cleaned
  └── _topic_registry.clear()           ← internal TopicRegistry cleared ✓
  └── load_config()
        └── _create_node() for each NEW node
              └── _register_node_websocket_topic()
                    └── manager.register_topic(topic)   ← NEW topics added ✓
```

This path looks correct for the **single-node dynamic-delete** flow. The bug surfaces in a subtler race specific to `reload_config()`:

#### Root Cause A — Topic Name Derivation Is Not Stored

The topic name for a node is derived at both **registration time** (in `ConfigLoader._register_node_websocket_topic`) **and** at **unregistration time** (in `LifecycleManager._unregister_node_websocket_topic`). Both derive the topic identically via `slugify_topic_prefix(node.name) + "_" + node_id[:8]`. However, the **node's `name` attribute comes from the live instance** (`getattr(node_instance, "name", node_id)`). If the node instance was partially constructed or its `name` attribute diverges from what was stored at registration time (e.g., a node factory sets a different display name on the object), the derived topic during cleanup will **not match** the registered topic string, causing the `unregister_topic` call to silently no-op on a wrong key.

#### Root Cause B — `reload_config()` Calls `self._topic_registry.clear()` But Not `ConnectionManager` Cleanup

Looking at `reload_config()` lines 122-123:

```python
self._cleanup_all_nodes()
self._topic_registry.clear()
```

`_cleanup_all_nodes()` → `remove_node(node_id)` → `_unregister_node_websocket_topic()` should call `manager.unregister_topic()`. But there is **no guard** for the case where a topic was registered for a node that is now **absent from `self.nodes`** (i.e., a node that failed to instantiate on a previous `load_config`, or a node that was inserted into the DB but skipped during initialization). `_cleanup_all_nodes` only iterates `self.nodes.keys()`, meaning any topics orphaned from a failed prior init remain in `ConnectionManager.active_connections` forever.

#### Root Cause C — No Active Connection Teardown on Unregister

`ConnectionManager.unregister_topic()` currently:

```python
def unregister_topic(self, topic: str):
    if topic in self.active_connections:
        del self.active_connections[topic]   # ← abandons live WebSocket objects
    if topic in self._interceptors:
        del self._interceptors[topic]         # ← abandons unresolved Futures
```

Deleting the dict entry **does not close** the WebSocket connections stored inside the list, and **does not cancel/resolve** the pending `asyncio.Future` objects in `_interceptors`. This causes:
- Client-side sockets stuck in `OPEN` state receiving no data, eventually timing out.
- Server-side tasks that called `wait_for_next()` are still awaiting those futures, keeping the coroutine alive.

---

## 2. Proposed Fix Architecture

The fix consists of **four coordinated changes** across three files:

```
ConnectionManager.unregister_topic()      [app/services/websocket/manager.py]
    ↑
LifecycleManager._unregister_node_websocket_topic()  [managers/lifecycle.py]
    ↑
ConfigLoader._register_node_websocket_topic()        [managers/config.py]
    ↑ (topic stored on node instance)
NodeManager.reload_config()                          [orchestrator.py]
    + new: _compute_node_topic() helper (shared utility)
```

### 2.1 Change 1 — Store Topic on Node Instance at Registration Time

**File:** `app/services/nodes/managers/config.py`  
**Method:** `ConfigLoader._register_node_websocket_topic()`

Instead of re-deriving the topic name during cleanup from the (potentially mutated) instance, **store the canonical topic string as an attribute on the node instance** immediately after registration.

```python
def _register_node_websocket_topic(self, node: Dict[str, Any], node_instance: Any):
    node_name = getattr(node_instance, "name", node["id"])
    safe_name = slugify_topic_prefix(node_name)
    topic = f"{safe_name}_{node['id'][:8]}"
    manager.register_topic(topic)
    # Store canonical topic on instance to ensure cleanup uses the exact same key
    node_instance._ws_topic = topic
```

**File:** `app/services/nodes/managers/lifecycle.py`  
**Method:** `LifecycleManager._unregister_node_websocket_topic()`

Read from the stored attribute first; fall back to re-derivation only if the attribute is absent (backward compatibility).

```python
def _unregister_node_websocket_topic(self, node_id: str, node_instance: Any):
    # Use stored topic if available to guarantee key match with registration
    if hasattr(node_instance, "_ws_topic"):
        topic = node_instance._ws_topic
    else:
        node_name = getattr(node_instance, "name", node_id)
        safe_name = slugify_topic_prefix(node_name)
        topic = f"{safe_name}_{node_id[:8]}"
    manager.unregister_topic(topic)
```

### 2.2 Change 2 — Graceful Teardown in `ConnectionManager.unregister_topic()`

**File:** `app/services/websocket/manager.py`  
**Method:** `ConnectionManager.unregister_topic()`

Add two teardown behaviors:

1. **Close all active WebSocket connections** on the topic before deleting the list, so clients receive a proper `1001 Going Away` close frame and their `onclose` handler fires.
2. **Cancel/resolve all pending interceptor Futures** before deleting the `_interceptors` entry, so no coroutine is left indefinitely suspended.

```python
async def unregister_topic(self, topic: str) -> None:
    """
    Fully unregisters a topic:
    - Closes all active WebSocket connections with a 1001 Going Away code.
    - Resolves (cancels) all pending interceptor futures with a TopicRemovedError.
    - Removes the topic from all tracking dicts.
    """
    # 1. Gracefully close all live WebSocket connections
    connections = self.active_connections.pop(topic, [])
    for ws in connections:
        try:
            await ws.close(code=1001)
        except Exception:
            pass  # Already closed or errored — ignore

    # 2. Cancel/resolve all pending interceptors for this topic
    futures = self._interceptors.pop(topic, [])
    for future in futures:
        if not future.done():
            future.cancel()  # CancelledError propagates to the awaiter
```

> **IMPORTANT:** `unregister_topic` must now be `async`. All call-sites must `await` it. See §2.4 for the cascading `async` promotion.

### 2.3 Change 3 — Sweep Orphaned Topics in `reload_config()`

**File:** `app/services/nodes/orchestrator.py`  
**Method:** `NodeManager.reload_config()`

Before calling `_cleanup_all_nodes()`, capture the **full set of topics registered in `ConnectionManager`** and after cleanup is done, diff against whatever topics survived — the difference is orphaned topics that no code path unregistered. These must be force-swept.

```python
async def reload_config(self, loop=None) -> None:
    import time

    was_running = self.is_running
    logger.info("Starting config reload...")
    self.stop()

    # Snapshot all topics registered BEFORE cleanup
    topics_before: set[str] = set(manager.active_connections.keys())

    logger.info("Cleaning up all nodes...")
    await self._cleanup_all_nodes_async()   # awaits async unregister_topic
    self._topic_registry.clear()

    # Sweep any topics that survived cleanup (orphaned from prior failed inits)
    topics_after: set[str] = set(manager.active_connections.keys())
    orphaned = topics_before - topics_after - SYSTEM_TOPICS
    if orphaned:
        logger.warning(f"Sweeping {len(orphaned)} orphaned topics: {orphaned}")
        for topic in orphaned:
            await manager.unregister_topic(topic)

    logger.info("Waiting for process cleanup and port release...")
    await asyncio.sleep(2.0)   # replaced time.sleep — must not block the event loop

    logger.info("Loading new config...")
    self.load_config()

    if was_running:
        logger.info("Restarting system...")
        self.start(loop or self._loop)

    logger.info("Config reload complete.")
```

> **Note:** `reload_config` must be promoted from sync to `async`. See §2.4 for the cascade.

### 2.4 Async Promotion Cascade

Making `unregister_topic` and `reload_config` async requires updating all call-sites:

| Location | Current call | New call |
|---|---|---|
| `NodeManager.reload_config()` | `self._cleanup_all_nodes()` | `await self._cleanup_all_nodes_async()` |
| `NodeManager._cleanup_all_nodes_async()` | *(new method)* | `await self.remove_node_async(node_id)` |
| `NodeManager.remove_node()` | sync, kept for backward compat | delegates to `asyncio.run_coroutine_threadsafe` when called from sync context |
| `LifecycleManager.remove_node()` | sync | add async variant `remove_node_async()` |
| `LifecycleManager._unregister_node_websocket_topic()` | sync | add async variant |
| `app/api/v1/nodes.py` `reload_all_config()` | `node_manager.reload_config()` | `await node_manager.reload_config()` |
| `app/api/v1/nodes.py` `delete_node()` | `node_manager.remove_node()` | `await node_manager.remove_node_async()` |

#### Strategy for `remove_node()` Backward Compatibility

Keep the existing sync `remove_node()` method for tests and internal callers that do not have an event loop. Add a new `async remove_node_async()` that correctly awaits the WebSocket teardown. The sync version schedules the async version on the running loop if one is active, or falls back to closing connections synchronously (using `ws.close()` without `await`, relying on the ASGI server to complete the handshake later).

```python
# In NodeManager / LifecycleManager
def remove_node(self, node_id: str):
    """Sync remove — safe to call from non-async contexts."""
    self._lifecycle_manager.remove_node_sync(node_id)

async def remove_node_async(self, node_id: str):
    """Async remove — closes WebSocket connections gracefully."""
    await self._lifecycle_manager.remove_node_async(node_id)
```

---

## 3. DAG Component Interaction Diagram

```
POST /nodes/reload
    │
    ▼
NodeManager.reload_config()  [async]
    │
    ├── stop()                              ← cancel queue listener, stop nodes
    │
    ├── snapshot = set(CM.active_connections.keys())
    │
    ├── _cleanup_all_nodes_async()
    │       └── for each node_id in self.nodes:
    │               LifecycleManager.remove_node_async(node_id)
    │                   ├── _stop_node(instance)
    │                   ├── _unregister_ws_topic_async(node_id, instance)
    │                   │       └── CM.unregister_topic(topic)  [async]
    │                   │               ├── ws.close(1001) for ws in connections
    │                   │               └── future.cancel() for f in interceptors
    │                   ├── _cleanup_routing(node_id)
    │                   └── _cleanup_state(node_id)
    │
    ├── _topic_registry.clear()
    │
    ├── orphan_sweep: topics that survived cleanup → CM.unregister_topic() each
    │
    ├── asyncio.sleep(2.0)
    │
    └── load_config()
            └── for each new node:
                    ConfigLoader._create_node()
                        └── _register_node_websocket_topic()
                                ├── manager.register_topic(topic)
                                └── node_instance._ws_topic = topic   ← NEW
```

---

## 4. `ConnectionManager.unregister_topic()` Detailed Specification

### Signature Change

```python
# Before (sync)
def unregister_topic(self, topic: str) -> None:

# After (async)
async def unregister_topic(self, topic: str) -> None:
```

### Behavior Contract

| Condition | Expected Behavior |
|---|---|
| Topic has zero connections and zero interceptors | Removes topic key from both dicts silently. No error. |
| Topic has N active WebSocket connections | Sends `close(code=1001)` to each. Exceptions per connection are caught and logged at DEBUG level. Topic entry deleted. |
| Topic has M pending interceptor futures | Each future is cancelled (raises `asyncio.CancelledError` in the awaiting coroutine). Topic entry deleted. |
| Topic does not exist in either dict | No-op. No error raised. (Idempotent) |
| Topic is a system topic (e.g., `system_status`) | **Must not** be called with system topics. Caller is responsible for filtering. The method does not enforce this — it trusts the caller. |

### Error Handling

- WebSocket close errors (`ConnectionResetError`, `RuntimeError`) must be individually caught per connection and logged at `DEBUG` level. They must **not** prevent processing the remaining connections.
- Future cancellation is infallible (`future.cancel()` returns a bool but never raises).

---

## 5. `NodeManager.reload_config()` Revised Flow

### Phase 1 — Quiesce

```
stop()
  → is_running = False
  → _listener_task.cancel()
  → stop_all_nodes() (sync — no WebSocket involvement)
```

### Phase 2 — Snapshot & Sweep

```
topics_before = snapshot(ConnectionManager.active_connections)
```

### Phase 3 — Node Teardown (Async)

```
for node_id in list(self.nodes.keys()):
    await remove_node_async(node_id)
        → stops node
        → awaits ConnectionManager.unregister_topic(derived_topic)
        → cleans routing + state dicts
```

### Phase 4 — Orphan Sweep

```
topics_after = set(ConnectionManager.active_connections.keys())
orphaned = topics_before - topics_after - SYSTEM_TOPICS
for topic in orphaned:
    await ConnectionManager.unregister_topic(topic)
    log WARNING with topic list
_topic_registry.clear()
```

### Phase 5 — Port Release Buffer

```
await asyncio.sleep(2.0)   # replaces time.sleep(2.0)
```

> **Critical:** The existing `time.sleep(2.0)` blocks the FastAPI event loop thread, starving all pending WebSocket close handshakes and HTTP requests during reload. It must be replaced with `asyncio.sleep(2.0)` once `reload_config` is async.

### Phase 6 — Reinitialize

```
load_config()
  → nodes initialized
  → topics registered
  → _ws_topic stored on each instance
```

### Phase 7 — Restart (conditional)

```
if was_running:
    start(loop)
```

---

## 6. API Endpoint Impact

### `POST /api/v1/nodes/reload`

**File:** `app/api/v1/nodes.py`

Must be promoted to an async FastAPI route handler that `await`s `reload_config()`.

```python
@router.post("/nodes/reload")
async def reload_all_config():
    await node_manager.reload_config()
    return {"status": "success"}
```

### `DELETE /api/v1/nodes/{node_id}`

Must `await` the async remove:

```python
@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str):
    await node_manager.remove_node_async(node_id)
    ...
```

### `POST /api/v1/config/import`

**File:** `app/api/v1/config.py`

The import endpoint deletes nodes from the repository but does **not** call `node_manager.reload_config()`. After a full-replace import, the in-memory DAG and topic registry are out of sync with the DB until an explicit reload. As a secondary fix, the replace-mode import should trigger `reload_config()` automatically.

```python
@router.post("/config/import")
async def import_configuration(config: ConfigurationImport):
    ...
    if not config.merge:
        await node_manager.reload_config()
    return {...}
```

---

## 7. Frontend Awareness

### Must the Frontend Handle Disappearing Topics?

**Yes, minimally.** The frontend `MultiWebsocketService` holds a `Map<topic, {socket, subject}>`. When the backend unregisters a topic and sends a WebSocket close frame (`code=1001`), the browser fires the `socket.onclose` callback. The existing `onclose` handler in `MultiWebsocketService` already does:

```typescript
socket.onclose = () => {
    this.connections.delete(topic);
    subject.complete();   // completes the Observable
};
```

This is **correct behavior** — RxJS `complete()` is called, any subscriber is notified the stream ended. **No new Angular code is required** for the close itself.

However, the frontend must handle the UX scenario where a topic it was subscribed to disappears:

1. **`TopicApiService.getTopics()`** should be re-fetched after a config reload event so the workspace topic selector refreshes.
2. Visualizer components subscribed to a now-dead topic observable should unsubscribe and show a "disconnected" indicator.

The mechanism to trigger this refresh is the existing **`system_status` WebSocket broadcast** — `status_broadcaster.py` fires every 500ms and carries the node list with their topics. The frontend already consumes this. No new API endpoint is needed.

### Frontend Tasks (Informational — Owned by @fe-dev)

| Task | Priority | Notes |
|---|---|---|
| Handle `onclose` in `MultiWebsocketService` without reconnect-loop for `1001` code | Low | Current behavior is correct; only ensure reconnect logic (if added in future) gates on `code !== 1001`. |
| Re-fetch `/topics` on `system_status` topic list change | Medium | Use Angular `effect()` on the node status signal to trigger topic refresh. |
| Show "Stream Ended" indicator in visualizer when observable completes | Medium | Guard `complete()` path in the Three.js render loop subscription. |

These frontend tasks are **not blocking** for the backend fix. They are UX improvements.

---

## 8. Edge Cases & Risk Analysis

| # | Edge Case | Handling |
|---|---|---|
| EC-1 | `reload_config()` called while a `wait_for_next()` is pending on a topic being removed | Future is cancelled; caller receives `asyncio.CancelledError`. `/topics/capture` HTTP handler should catch this and return `503 Service Unavailable` (not `504 Timeout`). |
| EC-2 | Node instance creation fails in `_create_node()` — node never enters `self.nodes` but could have partially registered a topic | Orphan sweep in Phase 4 catches this. |
| EC-3 | Two concurrent `reload_config()` calls | A re-entrant reload guard (`_reload_in_progress: asyncio.Lock`) must prevent this. |
| EC-4 | `_ws_topic` attribute collision — a node manually sets `_ws_topic` in its `__init__` | Unlikely but possible. Mitigation: use a private mangled name `__ws_topic` or a dataclass field with a `None` default. Design uses `_ws_topic` (single underscore) — module authors are informed via docstring. |
| EC-5 | Large number of connections during reload (e.g., 50+ clients) | `ws.close()` calls are fire-and-forget tasks — can be `asyncio.gather(*[ws.close(1001) for ws in connections], return_exceptions=True)` for parallel teardown. |
| EC-6 | `config/import` replace-mode without subsequent `reload_config()` | Addressed in §6 — auto-trigger `reload_config()` in replace mode. |
| EC-7 | Topic registered in `system_status` category — must not be swept | Orphan sweep explicitly excludes `SYSTEM_TOPICS`. |
| EC-8 | `reload_config()` called from a sync context (e.g., startup script, unit test) | Provide `reload_config_sync()` shim that calls `asyncio.run(reload_config())` for non-async callers. |

---

## 9. Testing Strategy

See `backend-tasks.md` for the full checklist. Summary:

- **Unit:** `ConnectionManager.unregister_topic()` — verify `ws.close()` called, futures cancelled, dicts cleaned.
- **Unit:** `LifecycleManager._unregister_node_websocket_topic()` — verify `_ws_topic` attribute takes precedence over re-derivation.
- **Unit:** `NodeManager.reload_config()` orphan sweep — simulate a topic in `CM.active_connections` that is not in `self.nodes`; verify it is swept.
- **Integration:** Full reload cycle — register nodes, add WS subscribers, trigger reload with node removed, verify topic absent from `GET /topics`, verify client `onclose` fired.
- **Concurrency:** Two concurrent `reload_config()` calls — verify second call blocks on the re-entrant lock, not corrupts state.
- **Edge:** `wait_for_next()` pending during reload — verify `CancelledError` propagates, HTTP returns `503`.
