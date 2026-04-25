# Snapshot Node — Backend Tasks

> **References**: `requirements.md` · `technical.md` · `api-spec.md`

---

## Module: `app/modules/flow_control/snapshot/`

- [x] Create `app/modules/flow_control/snapshot/__init__.py` (empty)
- [x] Implement `SnapshotNode(ModuleNode)` in `node.py`:
  - [x] `__init__` with `manager`, `node_id`, `name`, `throttle_ms=0`; set `_ws_topic = None`
  - [x] Instance vars: `_latest_payload`, `_is_processing`, `_last_trigger_time`, `_snapshot_count`, `_last_trigger_at`, `_last_error`, `_error_count`
  - [x] `async def on_input(payload)` — store `self._latest_payload = payload`, nothing else
  - [x] `async def trigger_snapshot()` — full guard logic (409, 429, 404) → shallow copy → `await manager.forward_data(self.id, snapshot)` → counters → `notify_status_change` → 500 on exception
  - [x] `def emit_status()` — return `NodeStatusUpdate` per state table in `technical.md §3.3`
  - [x] All functions strictly type-hinted; use `get_logger()` for all log calls

- [x] Implement `registry.py`:
  - [x] `node_schema_registry.register(NodeDefinition(type="snapshot", ...))` with `throttle_ms` property, single `in` port, single `out` port, `websocket_enabled=False`
  - [x] `@NodeFactory.register("snapshot") def build(...)` — extract `throttle_ms` from `config`, return `SnapshotNode`

- [x] Register snapshot in `app/modules/flow_control/registry.py`:
  - [x] Add `from .snapshot import registry as snapshot_registry`
  - [x] Add `"snapshot_registry"` to `__all__`

---

## API Layer: `app/api/v1/flow_control/`

- [x] Add `SnapshotTriggerResponse(BaseModel)` to `dto.py`:
  - [x] Field: `status: Literal["ok"]`

- [x] Add `trigger_snapshot(node_id: str) -> SnapshotTriggerResponse` to `service.py`:
  - [x] Lookup `node_manager.nodes.get(node_id)` → HTTP 404 if missing
  - [x] `isinstance(node, SnapshotNode)` check → HTTP 400 if wrong type
  - [x] `await node.trigger_snapshot()` (node raises 404/409/429/500 internally)
  - [x] Return `SnapshotTriggerResponse(status="ok")`
  - [x] Import `SnapshotNode` with lazy import to avoid circular dependency

- [x] Add endpoint to `handler.py`:
  - [x] `POST /nodes/{node_id}/trigger` → `trigger_snapshot_endpoint(node_id)`
  - [x] Full Swagger `responses=` dict (400, 404, 409, 429, 500)
  - [x] Import `trigger_snapshot` and `SnapshotTriggerResponse`

---

## Tests

- [x] Unit tests — `tests/modules/flow_control/test_snapshot_node.py`:
  - [x] `TestSnapshotNodeOnInput`: `on_input` stores payload; second call overwrites
  - [x] `TestSnapshotNodeTrigger`:
    - [x] Successful trigger calls `manager.forward_data` with shallow copy
    - [x] Trigger before any `on_input` raises HTTP 404
    - [x] Concurrent trigger (set `_is_processing=True`) raises HTTP 409
    - [x] Trigger within throttle window raises HTTP 429
    - [x] `forward_data` raising exception sets `_last_error` and raises HTTP 500
    - [x] `_snapshot_count` increments on each success
    - [x] `_is_processing` cleared after error
  - [x] `TestSnapshotNodeEmitStatus`:
    - [x] Idle → RUNNING, gray
    - [x] Recent trigger (<5 s) → RUNNING, blue
    - [x] `_last_error` set → ERROR, red

- [x] Integration tests — `tests/api/test_snapshot_trigger.py`:
  - [x] `POST /api/v1/nodes/{node_id}/trigger` → 200 with `{"status": "ok"}` after seeding payload
  - [x] Returns 404 when node not in `node_manager.nodes`
  - [x] Returns 404 when node exists but `_latest_payload` is None
  - [x] Returns 400 when `node_id` resolves to non-`SnapshotNode`
  - [x] Returns 409 when `_is_processing = True`
  - [x] Returns 429 when within throttle window
  - [x] `notify_status_change` called after successful trigger

- [x] Registry test — `tests/api/test_snapshot_trigger.py` (TestSnapshotRegistryDAG):
  - [x] Verify `SnapshotNode._ws_topic is None` → no WebSocket topic registered

---

## Dependencies / Order

1. **Node module** (`node.py` + `registry.py`) must be complete before API layer work.
2. **API service** (`service.py`) requires `SnapshotNode` importable (lazy import ok).
3. **Unit tests** can be written in parallel with node implementation (TDD).
4. **Integration tests** require both node module and API layer complete.
