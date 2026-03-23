# Output Node — Backend Tasks

**Assignee:** @be-dev  
**Feature Branch:** `feature/output-node`  
**References:** `technical.md`, `api-spec.md`  
**Note:** All checkboxes MUST be updated (`[ ]` → `[x]`) as steps complete.

---

## Phase 1 — Module Scaffolding

- [x] **B1.1** Create `app/modules/flow_control/output/` directory with `__init__.py`
- [x] **B1.2** Create `app/modules/flow_control/output/registry.py` with `NodeDefinition` registration (see `technical.md §2.2`)
  - `type = "output_node"`, `category = "flow_control"`, `websocket_enabled = False`
  - All webhook `PropertySchema` entries with `depends_on` guards
  - Input port: `PortSchema(id="in", multiple=False)` — no output ports
  - `@NodeFactory.register("output_node")` builder function
- [x] **B1.3** Update `app/modules/flow_control/registry.py` to import the new sub-module:
  ```python
  from .output import registry as output_registry
  ```
  This triggers registration via the existing `discover_modules()` flow — no other changes needed.

---

## Phase 2 — OutputNode Class

- [x] **B2.1** Create `app/modules/flow_control/output/node.py` with `OutputNode(ModuleNode)` class
- [x] **B2.2** Implement `__init__(self, manager, node_id, name, config)`:
  - Store `manager`, `id`, `name`, `_config`
  - Instantiate `_webhook = WebhookSender.from_config(config)` (may be `None`)
  - Initialize runtime counters: `metadata_count`, `error_count`, `last_metadata_at`
- [x] **B2.3** Implement `_extract_metadata(payload: Dict) -> Dict`:
  - Strip `"points"`, `"node_id"`, `"processed_by"` keys
  - Coerce numpy scalar types to Python native (`float`, `int`) — use `item()` where available
  - Return JSON-serializable dict
  - Wrap in try/except; return `{}` and log ERROR on failure
- [x] **B2.4** Implement `async on_input(self, payload)`:
  - Call `_extract_metadata`
  - Build `{"type": "output_node_metadata", "node_id": self.id, "timestamp": ..., "metadata": ...}`
  - `asyncio.create_task(ws_manager.broadcast("system_status", message))`
  - `asyncio.create_task(self._webhook.send(message))` if `self._webhook is not None`
  - Increment `metadata_count`, update `last_metadata_at`
  - Wrap full method body in try/except; log ERROR, increment `error_count`
- [x] **B2.5** Implement `emit_status(self) -> NodeStatusUpdate`:
  - `RUNNING` + `application_state` label `"metadata"` with:
    - `value = True` and `color = "blue"` if `last_metadata_at` within 5s
    - `value = False` and `color = "gray"` otherwise
  - `ERROR` + error_message if `error_count > 0` and no recent metadata

---

## Phase 3 — WebhookSender

- [x] **B3.1** Create `app/modules/flow_control/output/webhook.py` with `WebhookSender` class
- [x] **B3.2** Implement `from_config(cls, config) -> Optional[WebhookSender]`:
  - Return `None` if `webhook_enabled` is falsy or `webhook_url` empty
  - Construct auth headers via `_build_auth_headers(config)`
  - Merge with parsed `webhook_custom_headers` (JSON string → dict, fail silently)
  - Always add `Content-Type: application/json`
- [x] **B3.3** Implement `_build_auth_headers(config) -> Dict[str, str]`:
  - `"none"` → empty dict
  - `"bearer"` → `{"Authorization": "Bearer <token>"}`
  - `"basic"` → `{"Authorization": "Basic " + base64(user:pass)}`
  - `"api_key"` → `{key_name: key_value}`
- [x] **B3.4** Implement `async send(self, payload) -> None`:
  - `await asyncio.to_thread(self._sync_post, json.dumps(payload))`
  - Wrap in try/except; log ERROR on failure — NEVER raise
- [x] **B3.5** Implement `_sync_post(self, body: str) -> None`:
  - Use `httpx.Client(timeout=self._timeout)` in a context manager
  - POST with `content=body, headers=self._headers`
  - Log DEBUG on 2xx; log ERROR on 4xx/5xx (log status code, NOT body or credentials)
- [x] **B3.6** Add `httpx` to `requirements.txt` if not already present

---

## Phase 4 — API Endpoints

- [x] **B4.1** Create `app/api/v1/output/` directory with `__init__.py`, `handler.py`, `service.py`, `dto.py`
- [x] **B4.2** Define Pydantic models in `dto.py`:
  - `WebhookConfigRequest` (all webhook fields, with `@model_validator` for URL when enabled)
  - `WebhookConfigResponse` (all webhook fields, same shape)
  - `WebhookUpdateResponse(status: str, node_id: str)`
- [x] **B4.3** Implement `GET /api/v1/nodes/{node_id}/webhook` in `handler.py`:
  - Validate node exists (`NodeRepository.get_by_id`)
  - Validate `node["type"] == "output_node"` → 400 if not
  - Return `WebhookConfigResponse` extracted from `node["config"]`
  - Defaults: all fields default to disabled/empty if not present in config
- [x] **B4.4** Implement `PATCH /api/v1/nodes/{node_id}/webhook` in `handler.py`:
  - Validate node exists and is `output_node` type → 404 / 400
  - Validate request body with `WebhookConfigRequest` Pydantic model → 422 on failure
  - Persist merged config via `NodeRepository.update_node_config`
  - Hot-reload: if node is running in `node_manager.nodes`, call `node_instance._rebuild_webhook(config)` to avoid full DAG reload
  - Return `WebhookUpdateResponse`
- [x] **B4.5** Add `_rebuild_webhook(self, config)` method to `OutputNode`:
  - Re-instantiates `self._webhook = WebhookSender.from_config(config)`
  - Allows live config update without restarting node
- [x] **B4.6** Register output router in API aggregator (e.g., `app/api/v1/__init__.py` or `app/app.py`)
- [x] **B4.7** Add Swagger annotations to all endpoints (`summary`, `description`, `response_model`, error `responses`)

---

## Phase 5 — DB Migration

- [x] **B5.1** Confirm no schema change is needed (webhook config lives in `config_json` blob) — no `migrate.py` change required
- [x] **B5.2** Verify existing `NodeRepository.update_node_config` correctly updates the `config_json` without clobbering other config fields (use merge, not replace)

---

## Phase 6 — Integration

- [x] **B6.1** Write unit tests in `tests/modules/test_output_node.py`:
  - `test_on_input_broadcasts_metadata` — mock `ws_manager.broadcast`, assert called with correct type/node_id
  - `test_on_input_fires_webhook` — mock `WebhookSender.send`, assert called when enabled
  - `test_extract_metadata_strips_points` — assert `"points"` key absent in result
  - `test_extract_metadata_coerces_numpy` — assert numpy float32 becomes Python float
  - `test_extract_metadata_empty_on_error` — simulate exception, assert returns `{}`
  - `test_on_input_no_webhook_when_disabled` — assert `WebhookSender.send` NOT called
  - `test_emit_status_running` — active node returns RUNNING/blue
  - `test_emit_status_idle` — inactive node returns RUNNING/gray
- [x] **B6.2** Write unit tests in `tests/modules/test_webhook_sender.py`:
  - `test_from_config_returns_none_when_disabled`
  - `test_from_config_returns_none_when_url_empty`
  - `test_build_auth_headers_bearer`
  - `test_build_auth_headers_basic_base64`
  - `test_build_auth_headers_api_key`
  - `test_send_success_logs_debug` — mock `httpx.Client.post`, assert DEBUG log
  - `test_send_failure_logs_error_does_not_raise` — mock httpx raises, assert ERROR log, no exception
  - `test_send_4xx_logs_error` — mock 404 response, assert ERROR log
- [x] **B6.3** Write API integration tests in `tests/api/test_output_webhook.py`:
  - `test_get_webhook_config_returns_defaults_for_new_node`
  - `test_patch_webhook_config_persists` — PATCH, then GET, assert values match
  - `test_patch_webhook_config_invalid_url_returns_400`
  - `test_patch_webhook_config_enabled_empty_url_returns_400`
  - `test_get_webhook_config_wrong_node_type_returns_400`
  - `test_get_webhook_config_unknown_node_returns_404`
- [x] **B6.4** Write WebSocket registration test in `tests/services/nodes/test_websocket_registration.py`:
  - `test_output_node_skips_websocket_topic_registration` — assert `_ws_topic is None`
- [x] **B6.5** Confirm all existing tests pass after module addition (`pytest tests/`)

---

## Edge Cases to Handle

- Upstream node sends payload with NO extra metadata fields beyond `points`, `timestamp`, `node_id` → broadcast `metadata: {}` (valid, not an error)
- `webhook_custom_headers` stored as invalid JSON string → `WebhookSender.from_config` logs WARNING and ignores custom headers, still builds webhook
- Node receives input before `_webhook` is initialized (race condition on startup) → `_webhook` is set in `__init__` before any data can arrive; safe
- `asyncio.to_thread` in `WebhookSender.send` blocks the thread pool for up to 10s on timeout → acceptable; threadpool is not exhausted by a single slow webhook call under normal operation
