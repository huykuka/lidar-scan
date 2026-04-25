# Snapshot Node — QA Tasks

> **References**: `requirements.md` · `technical.md` · `api-spec.md`

---

## TDD Preparation

- [ ] Write failing unit tests in `tests/modules/flow_control/test_snapshot_node.py` **before** implementation
- [ ] Write failing integration tests in `tests/api/test_snapshot_trigger.py` **before** API layer is wired

---

## Unit Tests (`tests/modules/flow_control/test_snapshot_node.py`)

### Core Behaviour
- [ ] `on_input` stores payload; calling twice overwrites with latest
- [ ] Successful `trigger_snapshot` calls `manager.forward_data(node_id, payload)` with a copy
- [ ] Snapshot copy is shallow (numpy array reference is shared, not deep-copied)
- [ ] `_snapshot_count` increments by 1 per successful trigger
- [ ] `_last_trigger_at` is set after success
- [ ] `_is_processing` is `False` after both success and error paths

### Error Guards
- [ ] Trigger with no prior `on_input` → raises `HTTPException(404)`
- [ ] Trigger while `_is_processing=True` → raises `HTTPException(409)`
- [ ] Trigger within `throttle_ms` window → raises `HTTPException(429)`
- [ ] `forward_data` exception → sets `_last_error`, increments `_error_count`, raises `HTTPException(500)`

### `emit_status()`
- [ ] Idle state → `RUNNING`, `color="gray"`
- [ ] Triggered < 5 s ago → `RUNNING`, `color="blue"`, `value=snapshot_count`
- [ ] `_last_error` set → `ERROR`, `color="red"`
- [ ] `operational_state` is never `STOPPED` or `INITIALIZE`

### WebSocket Invisibility
- [ ] `_ws_topic is None` on a freshly constructed `SnapshotNode`

---

## Integration Tests (`tests/api/test_snapshot_trigger.py`)

### HTTP Contract
- [ ] `POST /api/v1/nodes/{node_id}/trigger` → `200 {"status": "ok"}` after seeding payload via `on_input`
- [ ] Response body matches `SnapshotTriggerResponse` schema exactly
- [ ] Returns `404` when `node_id` absent from `node_manager.nodes`
- [ ] Returns `404` when node present but `_latest_payload` is `None`
- [ ] Returns `400` when `node_id` maps to a non-`SnapshotNode` (e.g. `FusionService`)
- [ ] Returns `409` when `_is_processing=True` at time of request
- [ ] Returns `429` when second request arrives within `throttle_ms` window
- [ ] Returns `500` when `forward_data` raises internally

### Status Integration
- [ ] `notify_status_change` is called after a successful trigger
- [ ] After an error, `emit_status()` returns `ERROR` state

---

## Concurrency Tests

- [ ] Fire two concurrent `POST /trigger` requests via `asyncio.gather` → exactly one returns 200, one returns 409
- [ ] Under 10 rapid sequential calls with `throttle_ms=100` → only the first returns 200, rest return 429
- [ ] Zero crashes or hangs under 50 concurrent trigger attempts

---

## DAG Integration Tests

- [ ] `SnapshotNode` registered in `node_schema_registry` under type `"snapshot"`
- [ ] `NodeFactory.build("snapshot", ...)` returns a `SnapshotNode` instance
- [ ] `SnapshotNode` appears in `GET /api/v1/nodes/definitions` response
- [ ] No WebSocket topic created for `SnapshotNode` during `node_manager.load_config()`
- [ ] DAG with Upstream → Snapshot → Downstream: downstream receives payload only on trigger, not on every `on_input`
- [ ] `manager.forward_data` is called with `self.id` (not upstream node id) as source

---

## Linter & Type Checks

- [ ] `ruff check app/modules/flow_control/snapshot/` passes
- [ ] `ruff check app/api/v1/flow_control/` passes (after additions)
- [ ] `mypy app/modules/flow_control/snapshot/` passes with strict typing
- [ ] `mypy app/api/v1/flow_control/service.py` passes

---

## Pre-PR Checklist

- [ ] All unit tests pass: `pytest tests/modules/flow_control/test_snapshot_node.py -v`
- [ ] All integration tests pass: `pytest tests/api/test_snapshot_trigger.py -v`
- [ ] Full test suite passes: `pytest` (no regressions)
- [ ] Linter clean: `ruff check app/`
- [ ] Type checker clean: `mypy app/`
- [ ] `@be-dev` confirms all `backend-tasks.md` checkboxes marked `[x]`
