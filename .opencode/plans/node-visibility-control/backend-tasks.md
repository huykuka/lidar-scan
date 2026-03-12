# Backend Implementation Tasks — Node Visibility Control

**Feature:** `node-visibility-control`  
**Assignee:** @be-dev  
**References:**
- Requirements: `.opencode/plans/node-visibility-control/requirements.md`
- Technical Spec: `.opencode/plans/node-visibility-control/technical.md`
- API Contract: `.opencode/plans/node-visibility-control/api-spec.md`

---

## Execution Order

Tasks are ordered by layer dependency (DB → Repository → DAG Services → API). Tasks within a section may be parallelized unless a dependency note is present.

---

## Phase 1 — Database & Migration

- [ ] **BE-1.1** Add `visible: Mapped[bool]` column to `NodeModel` in `app/db/models.py`
  - Use `mapped_column(Boolean, default=True, server_default="1")`
  - Update `to_dict()` to include `"visible": self.visible` in the returned dict

- [ ] **BE-1.2** Add migration in `app/db/migrate.py` inside `ensure_schema()`
  - Guard with `if "visible" not in _table_cols(conn, "nodes"):`
  - Execute: `ALTER TABLE nodes ADD COLUMN visible INTEGER NOT NULL DEFAULT 1`
  - Verify idempotency: calling `ensure_schema()` twice must not raise errors

---

## Phase 2 — Repository Layer

*Depends on: Phase 1*

- [ ] **BE-2.1** Update `NodeRepository.upsert()` in `app/repositories/node_orm.py`
  - Read `visible = data.get("visible", True)` from input dict
  - For new nodes: pass `visible=visible` to `NodeModel(...)`
  - For existing nodes: update `existing.visible = data.get("visible", existing.visible)`

- [ ] **BE-2.2** Add `NodeRepository.set_visible(node_id: str, visible: bool) -> None` method
  - Single-column atomic `UPDATE` — must not touch any other column
  - Must raise `ValueError` if node not found (service layer converts to 404)
  - Must `session.rollback()` on any exception before re-raising

---

## Phase 3 — DAG Orchestrator & Service Managers

*Depends on: Phase 1 (for visibility flag in DB-loaded node dicts)*

- [ ] **BE-3.1** Update `ConfigLoader._register_node_websocket_topic()` in `app/services/nodes/managers/config.py`
  - Read `visible = node.get("visible", True)` from node config dict
  - If `visible=True`: call `manager.register_topic(topic)`, set `node_instance._ws_topic = topic`
  - If `visible=False`: set `node_instance._ws_topic = None` (do NOT call `register_topic()`)
  - Log at `DEBUG` level for both branches

- [ ] **BE-3.2** Update `DataRouter._get_node_topic()` in `app/services/nodes/managers/routing.py`
  - Return `Optional[str]` (update return type annotation)
  - Prefer `node_instance._ws_topic` if the attribute exists (may be `None`)
  - Keep legacy fallback (re-derive from name) only for nodes without `_ws_topic` attribute at all

- [ ] **BE-3.3** Update `DataRouter._broadcast_to_websocket()` in `app/services/nodes/managers/routing.py`
  - Add early return guard: `if topic is None: return`
  - This must be the **first** check in the method, before `"points" not in payload`

- [ ] **BE-3.4** Update `DataRouter.forward_data()` in `app/services/nodes/managers/routing.py`
  - Ensure `_get_node_topic()` result (which may be `None`) is passed through correctly to `_broadcast_to_websocket()`
  - Confirm `_record_node_data()` and `_forward_to_downstream_nodes()` are **not** conditioned on topic — they must run regardless of visibility

- [ ] **BE-3.5** Update `LifecycleManager._unregister_node_websocket_topic_async()` in `app/services/nodes/managers/lifecycle.py`
  - Add early return guard at top: `if hasattr(node_instance, "_ws_topic") and node_instance._ws_topic is None: return`
  - This prevents calling `unregister_topic()` on a non-existent topic for invisible nodes

- [ ] **BE-3.6** Add `NodeManager.set_node_visible()` method to `app/services/nodes/orchestrator.py`
  - Signature: `async def set_node_visible(self, node_id: str, visible: bool) -> None`
  - If `node_id` not in `self.nodes`: log at DEBUG and return (disabled nodes — DB already updated by caller)
  - If `not visible` and `node_instance._ws_topic is not None`: call `await self._lifecycle_manager._unregister_node_websocket_topic_async(node_id, node_instance)`, then set `node_instance._ws_topic = None`
  - If `visible` and `node_instance._ws_topic is None`: derive topic, call `websocket_manager.register_topic(topic)`, set `node_instance._ws_topic = topic`
  - If `visible` and `node_instance._ws_topic is not None`: no-op (already visible)
  - Import `slugify_topic_prefix` from `app.services.shared.topics` — do NOT duplicate the logic

---

## Phase 4 — API Layer

*Depends on: Phase 2 (repository `set_visible`), Phase 3 (orchestrator `set_node_visible`)*

- [ ] **BE-4.1** Update `NodeRecord` Pydantic schema in `app/api/v1/schemas/nodes.py`
  - Add `visible: bool = True` field with `Field(default=True, description="Whether node streams to WebSocket")`
  - Update the `json_schema_extra` examples to include `"visible": true`

- [ ] **BE-4.2** Update `NodeStatusItem` Pydantic schema in `app/api/v1/schemas/nodes.py`
  - Add `visible: bool = True` field
  - Change `topic: Optional[str]` annotation comment to note: `null when visible=false`

- [ ] **BE-4.3** Add `NodeVisibilityToggle` DTO and `set_node_visible()` service function in `app/api/v1/nodes/service.py`
  - `NodeVisibilityToggle(BaseModel)`: single field `visible: bool`
  - `async def set_node_visible(node_id: str, req: NodeVisibilityToggle)`:
    1. Fetch node by ID; raise `HTTPException(404)` if not found
    2. Derive topic name and check against `SYSTEM_TOPICS`; raise `HTTPException(400)` if protected
    3. Call `repo.set_visible(node_id, req.visible)`
    4. `await node_manager.set_node_visible(node_id, req.visible)`
    5. Return `{"status": "success"}`

- [ ] **BE-4.4** Register `PUT /nodes/{node_id}/visible` route in `app/api/v1/nodes/handler.py`
  - Import `set_node_visible, NodeVisibilityToggle` from `service.py`
  - Add Swagger annotations: summary, description, response_model, responses dict (400, 404)
  - Route must be defined **before** the `GET /nodes/{node_id}` route to avoid path conflicts (it won't conflict since it's PUT not GET, but place consistently)

- [ ] **BE-4.5** Update `NodeCreateUpdate` DTO in `app/api/v1/nodes/service.py`
  - Add `visible: bool = True` field
  - Update `json_schema_extra` examples to include `"visible": true`

- [ ] **BE-4.6** Update `get_nodes_status()` in `app/api/v1/nodes/service.py`
  - Add `status["visible"] = cnfg.get("visible", True)` to the status dict for running nodes
  - Add `"visible": cnfg.get("visible", True)` to the fallback dict for non-running nodes
  - Set `status["topic"] = None` when the node instance has `_ws_topic = None` (invisible running node)

---

## Phase 5 — Status Broadcaster

*Depends on: Phase 3 (node instance `_ws_topic` attribute)*

- [ ] **BE-5.1** Update `app/services/status_broadcaster.py`
  - Add `"visible"` field to each node status dict in the broadcast payload
  - Set `"topic"` to `None` when `_ws_topic is None` on the instance (mirrors §1.4 of api-spec)
  - Confirm the broadcaster reads from either the node instance or the DB record for visibility state
  - **Preferred**: read from `cnfg["visible"]` (DB value) since it is the source of truth

---

## Phase 6 — Validation & Cleanup

- [ ] **BE-6.1** Verify `reload_config()` preserves visibility state
  - Manually test: set node A to `visible=false`, call `POST /nodes/reload`, confirm node A's topic is still absent from `GET /api/v1/topics`
  - No code change required if Phase 3.1 is correctly implemented (DB value is read on each `load_config()`)

- [ ] **BE-6.2** Verify DAG config import/export handles `visible` field
  - Export config via `GET /api/v1/config`, confirm `visible` appears for each node
  - Import a config file with `visible: false` on a node, confirm it takes effect
  - Import a legacy config file without `visible`, confirm nodes default to `visible=true`

- [ ] **BE-6.3** Verify recording is unaffected by visibility
  - Start a recording on a visible node, toggle to `visible=false`, confirm recording data continues accumulating

---

## Dependencies & Blockers

| Task | Blocked By |
|---|---|
| BE-2.x (Repository) | BE-1.x (DB model `to_dict()` must include `visible`) |
| BE-3.x (DAG services) | BE-1.x (DB nodes dict must have `visible` key loaded) |
| BE-4.x (API layer) | BE-2.x (`set_visible()` must exist), BE-3.x (`set_node_visible()` must exist) |
| BE-5.x (Broadcaster) | BE-3.x (`_ws_topic` None-awareness) |

---

## Definition of Done

All tasks are checked off AND:
- [ ] `PUT /api/v1/nodes/{node_id}/visible` returns `200` for a valid toggle
- [ ] `GET /api/v1/topics` does NOT include invisible nodes' topics
- [ ] `GET /api/v1/nodes` returns `visible` field for every node
- [ ] `GET /api/v1/nodes/status/all` returns `visible` and `topic=null` for invisible nodes
- [ ] Hiding a node sends `1001 Going Away` to connected WebSocket clients (verified in browser DevTools)
- [ ] Recording continues after a node is hidden (verified manually)
- [ ] `POST /api/v1/nodes/reload` after hiding a node keeps that node hidden
- [ ] Python linter passes with no new errors (`ruff check app/`)
- [ ] All type hints are complete (`mypy app/` or equivalent passes)
