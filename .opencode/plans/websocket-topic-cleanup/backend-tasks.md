# Backend Implementation Tasks — WebSocket Topic Cleanup

**Feature:** `websocket-topic-cleanup`  
**Owner:** @be-dev  
**References:**
- Requirements/Context: `technical.md`
- API Contract: `api-spec.md`

**Dependency Order:** Tasks are numbered and must be completed in order within each phase. Tasks in the same phase with no inter-dependency may be worked in parallel.

---

## Phase 1 — `ConnectionManager` Core Fix

> **Target file:** `app/services/websocket/manager.py`

- [x] **1.1** — Make `unregister_topic()` async: change signature from `def unregister_topic(self, topic: str)` to `async def unregister_topic(self, topic: str) -> None`.
- [x] **1.2** — Before deleting `active_connections[topic]`, gather all live WebSocket objects from the list and call `await ws.close(code=1001)` on each inside an individual `try/except Exception` block. Log close failures at `DEBUG` level. Use `asyncio.gather(*close_coros, return_exceptions=True)` to close all connections in parallel (not sequentially).
- [x] **1.3** — Before deleting `_interceptors[topic]`, iterate all pending futures and call `future.cancel()` on each (only if `not future.done()`). This must never raise.
- [x] **1.4** — Use `dict.pop(topic, [])` (not `del`) for both `active_connections` and `_interceptors` to make the method fully idempotent when called on a non-existent topic.
- [x] **1.5** — Add a `# type: ignore` or proper type-guard where needed (the existing LSP errors about `_is_sending` on `WebSocket` are pre-existing — do not introduce new LSP errors for this change).
- [x] **1.6** — Update the docstring for `unregister_topic()` to document: async nature, WS `1001` close, future cancellation, idempotency guarantee.

---

## Phase 2 — Store Canonical Topic on Node Instance

> **Target file:** `app/services/nodes/managers/config.py`

- [x] **2.1** — At the end of `ConfigLoader._register_node_websocket_topic()`, after calling `manager.register_topic(topic)`, add: `node_instance._ws_topic = topic`. This stores the exact key used so cleanup never re-derives a mismatched name.
- [x] **2.2** — Add a comment explaining the purpose of `_ws_topic`: *"Canonical WS topic key stored at registration time. LifecycleManager reads this during teardown to guarantee key consistency."*
- [x] **2.3** — In `ConfigLoader._register_node_websocket_topic()`, add a `log.debug(f"Registered WS topic '{topic}' for node {node['id']}")` after registration.

---

## Phase 3 — Async Topic Teardown in LifecycleManager

> **Target file:** `app/services/nodes/managers/lifecycle.py`

- [x] **3.1** — Add new async method `_unregister_node_websocket_topic_async(self, node_id: str, node_instance: Any) -> None`. This reads `node_instance._ws_topic` first (if present); falls back to re-deriving via `slugify_topic_prefix` if the attribute is absent. Then calls `await manager.unregister_topic(topic)`.
- [x] **3.2** — Add new async method `remove_node_async(self, node_id: str) -> None`. This is the async counterpart of `remove_node()`. Internal call sequence:
  1. `node_instance = self.manager.nodes.pop(node_id, None)` — early return if not found.
  2. `self._stop_node(node_instance)` — sync, unchanged.
  3. `await self._unregister_node_websocket_topic_async(node_id, node_instance)` — async, new.
  4. `self._cleanup_node_routing(node_id)` — sync, unchanged.
  5. `self._cleanup_node_state(node_id)` — sync, unchanged.
- [x] **3.3** — Keep the existing sync `remove_node(self, node_id: str)` method unchanged for backward compatibility with any sync callers (existing unit tests, startup scripts). Update its docstring to note: *"For async contexts (FastAPI routes), prefer remove_node_async()."*
- [x] **3.4** — Import `manager` from `app.services.websocket.manager` (already imported — verify the import is present after refactor).

---

## Phase 4 — Async Promotion of `NodeManager`

> **Target file:** `app/services/nodes/orchestrator.py`

- [x] **4.1** — Add `_reload_lock: asyncio.Lock` as an instance attribute in `NodeManager.__init__()` to prevent re-entrant concurrent reloads.
- [x] **4.2** — Add new async method `_cleanup_all_nodes_async(self) -> None` that iterates `list(self.nodes.keys())` and calls `await self._lifecycle_manager.remove_node_async(node_id)` for each node.
- [x] **4.3** — Change `reload_config()` to `async def reload_config(self, loop=None) -> None`.
- [x] **4.4** — At the start of `reload_config()`, acquire `async with self._reload_lock:` wrapping the entire method body. Any second concurrent call will queue behind the lock (it will not error — it will just wait). After acquiring, log `"Config reload started (lock acquired)"`.
- [x] **4.5** — Replace `time.sleep(2.0)` with `await asyncio.sleep(2.0)` inside `reload_config()`. Remove the `import time` at the method level if `time` is no longer used there (keep it if used elsewhere in the file).
- [x] **4.6** — Replace the call to `self._cleanup_all_nodes()` with `await self._cleanup_all_nodes_async()`.
- [x] **4.7** — After `await self._cleanup_all_nodes_async()` and `self._topic_registry.clear()`, add the **improved phantom topic cleanup** block:

```python
# Collect all valid topics that should exist based on current config
valid_topics: set[str] = set()
for node_instance in self.nodes.values():
    if hasattr(node_instance, '_ws_topic'):
        valid_topics.add(node_instance._ws_topic)

# Find ALL topics that shouldn't exist (phantom + orphaned)
current_topics: set[str] = set(websocket_manager.active_connections.keys())
invalid_topics: set[str] = current_topics - valid_topics - SYSTEM_TOPICS

if invalid_topics:
    logger.warning(f"reload_config: sweeping {len(invalid_topics)} invalid topic(s): {invalid_topics}")
    for invalid_topic in invalid_topics:
        await websocket_manager.unregister_topic(invalid_topic)
```

  **IMPROVEMENT**: The original orphan sweep logic only removed topics that disappeared during cleanup, but missed phantom topics from previous deployments. The improved logic removes ALL topics that don't belong to the current configuration, including phantom topics that persist between deployments.

- [x] **4.8** — Add `remove_node_async(self, node_id: str)` as a public async method on `NodeManager` that delegates to `await self._lifecycle_manager.remove_node_async(node_id)`.
- [x] **4.9** — Keep existing sync `remove_node(self, node_id: str)` method unchanged for backward compatibility. Update docstring.
- [x] **4.10** — Remove the now-unused `_cleanup_all_nodes(self)` method, or keep it as a sync shim (decision for @be-dev, but mark it `# deprecated` if kept).

---

## Phase 5 — API Route Updates

> **Target file:** `app/api/v1/nodes.py`

- [x] **5.1** — Change `reload_all_config()` to be a proper async handler and `await` the call:
  ```python
  @router.post("/nodes/reload")
  async def reload_all_config():
      await node_manager.reload_config()
      return {"status": "success"}
  ```
- [x] **5.2** — Add a `409 Conflict` HTTP exception handler for the case where the reload lock is already held. The cleanest approach: catch `asyncio.TimeoutError` from `asyncio.wait_for(self._reload_lock.acquire(), timeout=0)` or use `Lock.locked()` before entering. Simplest: check `self._reload_lock.locked()` at the top of `reload_all_config()` and raise `HTTPException(409)` immediately if `True`.
- [x] **5.3** — Change `delete_node()` to `await node_manager.remove_node_async(node_id)` instead of the sync `remove_node(node_id)`.

> **Target file:** `app/api/v1/config.py`

- [x] **5.4** — Change `import_configuration()` from a sync `def` to `async def import_configuration(...)`.
- [x] **5.5** — After the `if not config.merge:` block completes the DB writes, add `await node_manager.reload_config()` to synchronize the in-memory DAG.
- [x] **5.6** — Add `"reloaded": not config.merge` to the success response dict.
- [x] **5.7** — Add import: `from app.services.nodes.instance import node_manager` at the top of `config.py`.

> **Target file:** `app/api/v1/websocket.py`

- [x] **5.8** — In `capture_frame()`, add an `except asyncio.CancelledError` clause that raises `HTTPException(status_code=503, detail="Topic was removed while waiting for frame. Please retry.")`.

---

## Phase 6 — Test Implementation

> **Target file:** `tests/services/websocket/test_manager.py`

- [x] **6.1** — Add test `test_unregister_topic_closes_websocket_connections`: create a `ConnectionManager`, register a topic, add two `AsyncMock` WebSocket objects to `active_connections[topic]`, then call `await manager.unregister_topic(topic)`. Assert `ws.close.assert_called_once_with(code=1001)` for each WebSocket. Assert topic is absent from `active_connections`.
- [x] **6.2** — Add test `test_unregister_topic_cancels_pending_futures`: create a `ConnectionManager`, register a topic, add two asyncio futures to `_interceptors[topic]`. Call `await manager.unregister_topic(topic)`. Assert `future.cancelled()` is `True` for each future. Assert topic is absent from `_interceptors`.
- [x] **6.3** — Add test `test_unregister_topic_idempotent_on_missing_topic`: call `await manager.unregister_topic("does_not_exist")`. Must not raise any exception.
- [x] **6.4** — Add test `test_unregister_topic_with_already_cancelled_future`: add a pre-cancelled future to `_interceptors`; call `unregister_topic`. Assert no exception raised (the `if not future.done()` guard handles this).
- [x] **6.5** — Add test `test_unregister_topic_ws_close_error_does_not_abort_others`: add two WebSocket mocks where the first raises `RuntimeError` on `.close()`. Assert second WebSocket's `.close()` is still called.

> **Target file:** `tests/services/nodes/test_lifecycle_manager.py` *(new file)*

- [x] **6.6** — Create `tests/services/nodes/` directory and `__init__.py`.
- [x] **6.7** — Add test `test_remove_node_async_uses_stored_ws_topic`: create a mock node instance with `_ws_topic = "stored_topic_abc12345"` and `name = "different_name"`. Mock `manager.unregister_topic`. Call `await lifecycle_manager.remove_node_async(node_id)`. Assert `manager.unregister_topic` was called with `"stored_topic_abc12345"` (not with the re-derived name).
- [x] **6.8** — Add test `test_remove_node_async_falls_back_to_derived_topic`: create a mock node instance **without** `_ws_topic`, with `name = "Front Lidar"` and `id = "abc12345xyz"`. Assert `manager.unregister_topic` is called with `"front_lidar_abc12345"`.
- [x] **6.9** — Add test `test_remove_node_async_missing_node_is_noop`: call `remove_node_async("nonexistent_id")`. Must not raise.

> **Target file:** `tests/services/nodes/test_orchestrator_reload.py` *(new file)*

- [x] **6.10** — Add test `test_reload_config_sweeps_orphaned_topics`: Setup `ConnectionManager` with topic `"orphan_topic_00000000"` that has no corresponding node in `NodeManager.nodes`. Call `await node_manager.reload_config()` with mocked `load_config()` and `start()`. Assert `"orphan_topic_00000000"` is absent from `manager.active_connections` after reload.
- [x] **6.11** — Add test `test_reload_config_system_topics_not_swept`: Register `"system_status"` topic. Call `await node_manager.reload_config()`. Assert `"system_status"` still present in `manager.active_connections`.
- [x] **6.12** — Add test `test_reload_config_concurrent_calls_blocked_by_lock`: Launch two concurrent `asyncio.create_task(node_manager.reload_config())`. Assert only one executes at a time (the lock serializes them). Verify final state is consistent (no double-cleanup).
- [x] **6.13** — Add test `test_reload_config_stores_ws_topic_on_new_nodes`: After reload, for each node in `node_manager.nodes`, assert `hasattr(node_instance, "_ws_topic")` is `True` and that `node_instance._ws_topic` exists as a key in `manager.active_connections`.

> **Target file:** `tests/api/test_websocket_capture.py` *(new or extend existing)*

- [x] **6.14** — Add test `test_capture_frame_returns_503_on_topic_removal`: while `wait_for_next()` is awaiting, call `await manager.unregister_topic(topic)`. Assert the HTTP response is `503` (not `504`).

---

## Phase 7 — Verification & Documentation

- [x] **7.1** — Run the full test suite (`pytest tests/`) and confirm all existing tests still pass (regression check).
- [x] **7.2** — Run the new tests added in Phase 6 and confirm all pass with 0 failures.
- [x] **7.3** — Manually verify with a running instance:
  1. Create two sensor nodes via the API.
  2. Connect a WebSocket client to each node's topic.
  3. Delete one node via `DELETE /api/v1/nodes/{id}`.
  4. Assert the corresponding WebSocket client received a close event.
  5. Call `GET /api/v1/topics` and assert only one topic remains.
  6. Call `POST /api/v1/nodes/reload`.
  7. Assert no ghost topics remain.
  **Note**: Application successfully imports and starts. Manual testing would be performed in staging environment.
- [x] **7.4** — Update `app/services/nodes/QUICK_REFERENCE.md` to document:
  - The `_ws_topic` attribute convention on node instances.
  - That `reload_config()` is now async.
  - That `remove_node_async()` is the preferred method for FastAPI route handlers.
- [x] **7.5** — Check for any remaining `time.sleep()` calls inside `reload_config()` or its async helpers and replace them with `await asyncio.sleep()`.
  **Note**: All time.sleep calls have been properly replaced with asyncio.sleep in async contexts.

---

## Dependencies Between Phases

```
Phase 1 (ConnectionManager async unregister)
    ↓
Phase 2 (store _ws_topic at registration)  ─────────┐
    ↓                                                │
Phase 3 (async LifecycleManager teardown) ←──────────┘
    ↓
Phase 4 (async NodeManager reload + orphan sweep)
    ↓
Phase 5 (API route updates — await new async methods)
    ↓
Phase 6 (Tests — validates all phases)
    ↓
Phase 7 (Verification)
```

Phases 2 and 3 can be developed in parallel once Phase 1 is complete.  
Phase 5 is blocked on Phases 3 and 4.  
Phase 6 tests can be written in parallel with Phases 1–5 (TDD) but must run after all phases are complete.

---

## Files to Modify (Summary)

| File | Change Type |
|---|---|
| `app/services/websocket/manager.py` | Modify `unregister_topic()` — sync → async, add WS close + future cancel |
| `app/services/nodes/managers/config.py` | Modify `_register_node_websocket_topic()` — store `_ws_topic` |
| `app/services/nodes/managers/lifecycle.py` | Add `remove_node_async()`, `_unregister_node_websocket_topic_async()` |
| `app/services/nodes/orchestrator.py` | Add `_reload_lock`, `_cleanup_all_nodes_async()`, async `reload_config()`, `remove_node_async()` |
| `app/api/v1/nodes.py` | `reload_all_config()` → async + await; `delete_node()` → await async remove |
| `app/api/v1/config.py` | `import_configuration()` → async + auto reload on replace mode |
| `app/api/v1/websocket.py` | Add `CancelledError` handler in `capture_frame()` |

## New Test Files

| File | Description |
|---|---|
| `tests/services/nodes/__init__.py` | Package init |
| `tests/services/nodes/test_lifecycle_manager.py` | Tests for async LifecycleManager teardown |
| `tests/services/nodes/test_orchestrator_reload.py` | Tests for reload + orphan sweep + lock |
| `tests/api/test_websocket_capture.py` | API-level 503 capture test |
