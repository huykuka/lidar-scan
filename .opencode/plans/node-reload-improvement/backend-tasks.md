# Node Reload Improvement — Backend Tasks

> **Reference documents**:
> - Requirements: `.opencode/plans/node-reload-improvement/requirements.md`
> - Technical blueprint: `.opencode/plans/node-reload-improvement/technical.md`
> - API contracts: `.opencode/plans/node-reload-improvement/api-spec.md`

> **GitNexus**: Run `gitnexus_impact` before touching any existing symbol. Run `gitnexus_detect_changes` before every commit.

---

## Phase 1: Foundation — New Services and Data Structures

### 1.1 Config Hasher Module
- [ ] Create `app/services/nodes/config_hasher.py`
  - [ ] Implement `compute_node_config_hash(node_data: Dict[str, Any]) -> str`
    - SHA-256 over canonicalized JSON of keys: `id, type, category, enabled, visible, config, pose`
    - Explicitly exclude `x`, `y` (canvas-only, no runtime effect)
    - Use `json.dumps(sorted_dict, sort_keys=True, default=str)` for deterministic serialization
  - [ ] Implement `ConfigHashStore` class:
    - `def update(self, node_id: str, hash_val: str) -> None`
    - `def get(self, node_id: str) -> Optional[str]`
    - `def remove(self, node_id: str) -> None`
    - `def clear(self) -> None`
    - Internal: `_hashes: Dict[str, str] = {}`

### 1.2 Input Gate Module
- [ ] Create `app/services/nodes/input_gate.py`
  - [ ] Implement `NodeInputGate` class:
    - `__init__(self, capacity: int = 30)` — creates `asyncio.Event` (initially set = open) and `asyncio.Queue(maxsize=capacity)`
    - `def is_open(self) -> bool` — returns `self._gate.is_set()`
    - `async def pause(self) -> None` — clears the gate event
    - `async def resume_and_drain(self, target_node: Any) -> None` — sets gate event, then drains buffer by calling `target_node.on_input(payload)` for each buffered frame in order
    - `def buffer_nowait(self, payload: Any) -> bool` — `put_nowait`, returns False (with DEBUG log) if queue full

### 1.3 Schema Updates
- [ ] Update `app/schemas/status.py`:
  - [ ] Add `ReloadEvent` Pydantic model (fields: `node_id`, `status`, `error_message`, `reload_mode`, `timestamp`)
  - [ ] Add optional `reload_event: Optional[ReloadEvent] = None` field to `SystemStatusBroadcast`
- [ ] Update `app/api/v1/schemas/dag.py`:
  - [ ] Add `reload_mode: Literal["selective", "full", "none"]` to `DagConfigSaveResponse`
  - [ ] Add `reloaded_node_ids: List[str]` to `DagConfigSaveResponse`
- [ ] Create new schemas in `app/api/v1/schemas/nodes.py` (or new file):
  - [ ] `NodeReloadResponse` model
  - [ ] `ReloadStatusResponse` model
  - [ ] `SelectiveReloadResult` internal model (not exposed via REST directly, used in service layer)

---

## Phase 2: Selective Reload Manager

### 2.1 Create `SelectiveReloadManager`
- [ ] Create `app/services/nodes/managers/selective_reload.py`
  - [ ] Class `SelectiveReloadManager` with `__init__(self, manager_ref)`
  - [ ] Implement `async def reload_single_node(self, node_id: str) -> SelectiveReloadResult`:
    1. Record start timestamp
    2. Read `old_instance = self.manager.nodes[node_id]` (KeyError → raise ValueError)
    3. Read `preserved_topic = old_instance._ws_topic` (may be None)
    4. Store old instance in `self.manager._rollback_slot[node_id] = old_instance`
    5. Identify downstream node IDs from `self.manager.downstream_map.get(node_id, [])`
    6. For each downstream node: create `NodeInputGate`, store in `self.manager._input_gates[downstream_id]`; call `await gate.pause()`
    7. Call `self.manager._lifecycle_manager._stop_node(old_instance)` (existing method)
    8. Remove old instance: `self.manager.nodes.pop(node_id)`
    9. Load fresh node data from DB: `NodeRepository().get(node_id)` → returns single dict
    10. Call `NodeFactory.create(node_data, self.manager, self.manager.edges_data)`
    11. Set `new_instance._ws_topic = preserved_topic` (do NOT call `register_topic`)
    12. Initialize throttling: call `self.manager._config_loader._initialize_node_throttling(node_data)`
    13. Insert: `self.manager.nodes[node_id] = new_instance`
    14. Call start/enable on new instance if `self.manager.is_running`:
        - `new_instance.start(self.manager.data_queue, self.manager.node_runtime_status)` if has `start`
        - else `new_instance.enable()` if has `enable`
    15. Update hash store: `self.manager._config_hash_store.update(node_id, new_hash)`
    16. For each downstream: `await gate.resume_and_drain(downstream_node_instance)`; delete gate from `self.manager._input_gates`
    17. Clear rollback slot: `self.manager._rollback_slot.pop(node_id, None)`
    18. Return `SelectiveReloadResult(status="reloaded", duration_ms=elapsed, ...)`
  - [ ] Implement error handling within `reload_single_node`:
    - On any exception after step 8 (node removed): attempt rollback — restore old instance from `_rollback_slot`, call `old_instance.start()` or `old_instance.enable()` if running
    - Always clean up input gates on exception (resume all paused downstream nodes before propagating)
    - Return `SelectiveReloadResult(status="error", ...)` on non-recoverable error

### 2.2 Register NodeRepository `get()` method if missing
- [ ] Verify `app/repositories/__init__.py` and `NodeRepository` have a `.get(node_id: str) -> dict` method
- [ ] If absent, add it to `NodeRepository` (single-row lookup by primary key)

### 2.3 Update `app/services/nodes/managers/__init__.py`
- [ ] Export `SelectiveReloadManager` from the package

---

## Phase 3: NodeManager Integration

### 3.1 Update `NodeManager.__init__`
- [ ] Add `_selective_reload_manager = SelectiveReloadManager(self)` (after existing sub-managers)
- [ ] Add `_config_hash_store = ConfigHashStore()` 
- [ ] Add `_input_gates: Dict[str, NodeInputGate] = {}` (active gates during reload)
- [ ] Add `_rollback_slot: Dict[str, Any] = {}` (old instances during reload)
- [ ] Add `_active_reload_node_id: Optional[str] = None` (for status endpoint)

### 3.2 Update `NodeManager.load_config`
- [ ] After `initialize_nodes()` completes, populate the hash store:
  ```python
  for node_data in self.nodes_data:
      if node_data.get("enabled", True):
          self._config_hash_store.update(
              node_data["id"],
              compute_node_config_hash(node_data)
          )
  ```
- [ ] On full reload, call `self._config_hash_store.clear()` before re-populating

### 3.3 Add `NodeManager.selective_reload_node()`
- [ ] Implement `async def selective_reload_node(self, node_id: str) -> SelectiveReloadResult`:
  ```python
  async with self._reload_lock:
      self._active_reload_node_id = node_id
      try:
          await self._broadcast_reload_event(node_id, "reloading", "selective")
          result = await self._selective_reload_manager.reload_single_node(node_id)
          status = "ready" if result.status == "reloaded" else "error"
          await self._broadcast_reload_event(node_id, status, "selective", result.error_message)
          return result
      finally:
          self._active_reload_node_id = None
  ```
- [ ] Implement `async def _broadcast_reload_event(self, node_id, status, reload_mode, error_message=None)`:
  - Constructs `SystemStatusBroadcast(nodes=[], reload_event=ReloadEvent(...))`
  - Calls `manager.broadcast("system_status", payload.model_dump())`

---

## Phase 4: DAG Save Service — Diff Logic

### 4.1 Add Change Classification to `save_dag_config`
- [ ] In `app/api/v1/dag/service.py`, after the DB transaction (step 3), add diff logic:
  ```python
  def _classify_dag_changes(
      node_manager,
      new_nodes: List[NodeRecord],
      new_edges: List[EdgeRecord],
      existing_nodes: List[dict],
      existing_edges: List[dict]
  ) -> tuple[str, List[str]]:
      # Returns ("topology", []) | ("param_change", [ids...]) | ("no_change", [])
  ```
  - Check if node set (IDs) changed → return `"topology"`
  - Check if edges changed (compare sorted serializations) → return `"topology"`
  - Check each node's config hash vs `node_manager._config_hash_store.get(node.id)` → collect changed IDs
  - Return `("param_change", changed_ids)` or `("no_change", [])`

### 4.2 Update the reload trigger in `save_dag_config`
- [ ] Replace the current Step 4 (always calls `reload_config()`) with:
  ```python
  change_type, changed_ids = _classify_dag_changes(...)
  if change_type == "topology":
      await node_manager.reload_config()
      reload_mode = "full"
      reloaded_ids = []
  elif change_type == "param_change":
      for node_id in changed_ids:
          await node_manager.selective_reload_node(node_id)
      reload_mode = "selective"
      reloaded_ids = changed_ids
  else:  # no_change
      reload_mode = "none"
      reloaded_ids = []
  ```
- [ ] Update `DagConfigSaveResponse` construction to include `reload_mode` and `reloaded_node_ids`

### 4.3 Snapshot existing edges before transaction for diff
- [ ] Read `existing_edges = edge_repo.list()` before the delete/upsert block (needed for edge diff)

---

## Phase 5: New REST Endpoints

### 5.1 Add `POST /api/v1/nodes/{node_id}/reload` endpoint
- [ ] Create `app/api/v1/nodes/reload_handler.py` (or add to existing nodes handler):
  - `POST /nodes/{node_id}/reload` → calls `node_manager.selective_reload_node(node_id)`
  - Returns `NodeReloadResponse`
  - Returns 404 if `node_id not in node_manager.nodes`
  - Returns 409 if `node_manager._reload_lock.locked()`
  - Returns 500 with rollback status message on failure

### 5.2 Add `GET /api/v1/nodes/reload/status` endpoint
- [ ] Add to reload handler or nodes service:
  - Returns `ReloadStatusResponse`
  - Reads `node_manager._reload_lock.locked()`
  - Reads `node_manager._active_reload_node_id`
  - `estimated_completion_ms`: 150 for selective, 3000 for full (static estimate for v1)

### 5.3 Register new routes in `app/api/v1/router.py` (or equivalent)
- [ ] Register the new nodes reload endpoints under `/api/v1/nodes`

---

## Phase 6: DataRouter — Input Gate Integration

### 6.1 Update `DataRouter._forward_to_downstream_nodes`
- [ ] Add gate check before calling `_send_to_target_node`:
  ```python
  gate = self.manager._input_gates.get(target_id)
  if gate is not None:
      if not gate.is_open():
          gate.buffer_nowait(payload)
          continue
  ```
- [ ] Ensure the gate check is **O(1)** dict lookup — no additional overhead when no gates are active
- [ ] Add a comment explaining the gate lifecycle (created at pause, deleted after drain)

---

## Phase 7: Tests

### 7.1 Unit Tests — `ConfigHasher`
- [ ] Create `tests/services/nodes/test_config_hasher.py`
  - [ ] `test_hash_is_deterministic`: same input → same hash
  - [ ] `test_hash_differs_on_config_change`: modify `config.hostname` → different hash
  - [ ] `test_hash_ignores_position`: same config, different x/y → same hash
  - [ ] `test_hash_differs_on_pose_change`: modify `pose.yaw` → different hash
  - [ ] `test_hash_differs_on_enabled_toggle`: `enabled=False` → different hash
  - [ ] `test_config_hash_store_update_get`: update/get/remove/clear lifecycle

### 7.2 Unit Tests — `NodeInputGate`
- [ ] Create `tests/services/nodes/test_input_gate.py`
  - [ ] `test_gate_open_by_default`: `is_open()` returns True on construction
  - [ ] `test_pause_blocks_is_open`: after `pause()`, `is_open()` returns False
  - [ ] `test_buffer_nowait_when_paused`: payload stored in queue
  - [ ] `test_buffer_drops_when_full`: at capacity 1, second put returns False
  - [ ] `test_resume_drains_buffer_in_order`: 3 buffered frames delivered in FIFO order
  - [ ] `test_resume_calls_on_input_for_each_frame`: mock target node; verify `on_input` call count

### 7.3 Unit Tests — `SelectiveReloadManager`
- [ ] Create `tests/services/nodes/test_selective_reload.py`
  - [ ] `test_selective_reload_replaces_node_instance`: new instance in `nodes[node_id]`
  - [ ] `test_selective_reload_preserves_ws_topic`: `new_instance._ws_topic == old_instance._ws_topic`
  - [ ] `test_selective_reload_no_unregister_topic_called`: `websocket_manager.unregister_topic` NOT called
  - [ ] `test_selective_reload_pauses_downstream_before_stop`: gate.pause() called before old_instance.stop()
  - [ ] `test_selective_reload_resumes_downstream_after_start`: gate.resume_and_drain() called after new instance starts
  - [ ] `test_selective_reload_rollback_on_factory_failure`: NodeFactory raises → old instance restored
  - [ ] `test_selective_reload_rollback_on_start_failure`: start() raises → old instance restored
  - [ ] `test_selective_reload_updates_hash_store`: new hash stored after success

### 7.4 Integration Tests — `save_dag_config` diff logic
- [ ] Update `tests/api/test_dag_config.py` → `TestSaveDagConfig`:
  - [ ] `test_save_param_change_triggers_selective_reload`: mock `selective_reload_node`, not `reload_config`
  - [ ] `test_save_topology_change_triggers_full_reload`: add new node → `reload_config` called
  - [ ] `test_save_edge_change_triggers_full_reload`: add/remove edge → `reload_config` called
  - [ ] `test_save_position_only_change_triggers_no_reload`: only x/y changed → neither reload called
  - [ ] `test_save_response_includes_reload_mode`: response has `reload_mode` and `reloaded_node_ids`
  - [ ] `test_save_409_when_lock_held`: concurrent save rejected with 409

### 7.5 Integration Tests — new endpoints
- [ ] Create `tests/api/test_node_selective_reload.py`:
  - [ ] `test_post_node_reload_success`: 200 with NodeReloadResponse
  - [ ] `test_post_node_reload_404_unknown_node`: 404
  - [ ] `test_post_node_reload_409_lock_held`: 409
  - [ ] `test_get_reload_status_idle`: locked=False
  - [ ] `test_get_reload_status_during_reload`: locked=True, active_reload_node_id set

### 7.6 Tests — DataRouter gate integration
- [ ] Update `tests/services/nodes/test_routing.py` (or create):
  - [ ] `test_forward_skips_paused_downstream`: when gate is paused, payload buffered, on_input NOT called
  - [ ] `test_forward_normal_when_no_gate`: gate=None, on_input called normally

---

## Phase 8: Linting & Quality

- [ ] Run `ruff check app/` and fix all issues in new files
- [ ] Run `mypy app/services/nodes/managers/selective_reload.py` — ensure strict type compliance
- [ ] Run `mypy app/services/nodes/config_hasher.py`
- [ ] Run `mypy app/services/nodes/input_gate.py`
- [ ] Verify no circular imports: `python -c "from app.services.nodes.managers.selective_reload import SelectiveReloadManager"`

---

## Dependencies & Order of Operations

```
Phase 1 (Foundation) → must complete before Phase 2
Phase 2 (SelectiveReloadManager) → must complete before Phase 3 & 6
Phase 3 (NodeManager Integration) → must complete before Phase 4
Phase 4 (DAG Save Diff) → can start after Phase 3.3 is done
Phase 5 (Endpoints) → can be developed in parallel with Phase 4
Phase 6 (DataRouter Gate) → can start after Phase 1.2 is done
Phase 7 (Tests) — TDD: write failing tests before implementation
Phase 8 (Linting) — last step before PR
```

## Blocked Tasks

- Frontend reload indicator cannot be tested end-to-end until Phase 5 endpoints are live. Frontend uses mock mode per `api-spec.md`.
