# Snapshot Node — Backend Tasks

> **References**: `requirements.md` · `technical.md` · `api-spec.md`

---

## Module: `app/modules/flow_control/snapshot/`

- [ ] Create `app/modules/flow_control/snapshot/__init__.py` (empty)
- [ ] Implement `SnapshotNode(ModuleNode)` in `node.py`:
  - [ ] `__init__` with `manager`, `node_id`, `name`, `throttle_ms=0`; set `_ws_topic = None`
  - [ ] Instance vars: `_latest_payload`, `_is_processing`, `_last_trigger_time`, `_snapshot_count`, `_last_trigger_at`, `_last_error`, `_error_count`
  - [ ] `async def on_input(payload)` — store `self._latest_payload = payload`, nothing else
  - [ ] `async def trigger_snapshot()` — full guard logic (409, 429, 404) → shallow copy → `await manager.forward_data(self.id, snapshot)` → counters → `notify_status_change` → 500 on exception
  - [ ] `def emit_status()` — return `NodeStatusUpdate` per state table in `technical.md §3.3`
  - [ ] All functions strictly type-hinted; use `get_logger()` for all log calls

- [ ] Implement `registry.py`:
  - [ ] `node_schema_registry.register(NodeDefinition(type="snapshot", ...))` with `throttle_ms` property, single `in` port, single `out` port, `websocket_enabled=False`
  - [ ] `@NodeFactory.register("snapshot") def build(...)` — extract `throttle_ms` from `config`, return `SnapshotNode`

- [ ] Register snapshot in `app/modules/flow_control/registry.py`:
  - [ ] Add `from .snapshot import registry as snapshot_registry`
  - [ ] Add `"snapshot_registry"` to `__all__`

---

## API Layer: `app/api/v1/flow_control/`

- [ ] Add `SnapshotTriggerResponse(BaseModel)` to `dto.py`:
  - [ ] Field: `status: Literal["ok"]`

- [ ] Add `trigger_snapshot(node_id: str) -> SnapshotTriggerResponse` to `service.py`:
  - [ ] Lookup `node_manager.nodes.get(node_id)` → HTTP 404 if missing
  - [ ] `isinstance(node, SnapshotNode)` check → HTTP 400 if wrong type
  - [ ] `await node.trigger_snapshot()` (node raises 404/409/429/500 internally)
  - [ ] Return `SnapshotTriggerResponse(status="ok")`
  - [ ] Import `SnapshotNode` with lazy import to avoid circular dependency

- [ ] Add endpoint to `handler.py`:
  - [ ] `POST /nodes/{node_id}/trigger` → `trigger_snapshot_endpoint(node_id)`
  - [ ] Full Swagger `responses=` dict (400, 404, 409, 429, 500)
  - [ ] Import `trigger_snapshot` and `SnapshotTriggerResponse`

---

## Tests

- [ ] Unit tests — `tests/modules/flow_control/test_snapshot_node.py`:
  - [ ] `TestSnapshotNodeOnInput`: `on_input` stores payload; second call overwrites
  - [ ] `TestSnapshotNodeTrigger`:
    - [ ] Successful trigger calls `manager.forward_data` with shallow copy
    - [ ] Trigger before any `on_input` raises HTTP 404
    - [ ] Concurrent trigger (set `_is_processing=True`) raises HTTP 409
    - [ ] Trigger within throttle window raises HTTP 429
    - [ ] `forward_data` raising exception sets `_last_error` and raises HTTP 500
    - [ ] `_snapshot_count` increments on each success
    - [ ] `_is_processing` cleared after error
  - [ ] `TestSnapshotNodeEmitStatus`:
    - [ ] Idle → RUNNING, gray
    - [ ] Recent trigger (<5 s) → RUNNING, blue
    - [ ] `_last_error` set → ERROR, red

- [ ] Integration tests — `tests/api/test_snapshot_trigger.py`:
  - [ ] `POST /api/v1/nodes/{node_id}/trigger` → 200 with `{"status": "ok"}` after seeding payload
  - [ ] Returns 404 when node not in `node_manager.nodes`
  - [ ] Returns 404 when node exists but `_latest_payload` is None
  - [ ] Returns 400 when `node_id` resolves to non-`SnapshotNode`
  - [ ] Returns 409 when `_is_processing = True`
  - [ ] Returns 429 when within throttle window
  - [ ] `notify_status_change` called after successful trigger

- [ ] Registry test — `tests/services/nodes/test_websocket_registration.py` (existing):
  - [ ] Verify `SnapshotNode._ws_topic is None` → no WebSocket topic registered

---

## Dependencies / Order

1. **Node module** (`node.py` + `registry.py`) must be complete before API layer work.
2. **API service** (`service.py`) requires `SnapshotNode` importable (lazy import ok).
3. **Unit tests** can be written in parallel with node implementation (TDD).
4. **Integration tests** require both node module and API layer complete.
