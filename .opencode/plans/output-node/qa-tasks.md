# Output Node — QA Tasks

**Assignee:** @qa  
**Feature Branch:** `feature/output-node`  
**References:** `technical.md`, `api-spec.md`, `backend-tasks.md`, `frontend-tasks.md`  
**Note:** All checkboxes MUST be updated (`[ ]` → `[x]`) as steps complete. File `qa-report.md` when complete.

---

## Phase 1 — Backend Unit Test Coverage

### OutputNode Core Logic
- [ ] **Q1.1** `test_on_input_broadcasts_metadata`: Verify `ws_manager.broadcast("system_status", ...)` called with `type = "output_node_metadata"` and correct `node_id`
- [ ] **Q1.2** `test_on_input_fires_webhook_when_enabled`: Mock `WebhookSender.send`; assert called once per `on_input`
- [ ] **Q1.3** `test_on_input_does_not_fire_webhook_when_disabled`: `webhook_enabled = False` → `WebhookSender.send` never called
- [ ] **Q1.4** `test_extract_metadata_excludes_points_key`: Payload with `points` → `points` absent from metadata dict
- [ ] **Q1.5** `test_extract_metadata_excludes_node_id_key`: `node_id` absent from metadata
- [ ] **Q1.6** `test_extract_metadata_excludes_processed_by`: `processed_by` absent from metadata
- [ ] **Q1.7** `test_extract_metadata_coerces_numpy_float32`: `numpy.float32(0.5)` → Python `float(0.5)` in metadata
- [ ] **Q1.8** `test_extract_metadata_coerces_numpy_int64`: `numpy.int64(100)` → Python `int(100)` in metadata
- [ ] **Q1.9** `test_extract_metadata_returns_empty_on_exception`: Force exception → returns `{}`, ERROR logged, does not raise
- [ ] **Q1.10** `test_on_input_increments_metadata_count`: Count increments by 1 per call
- [ ] **Q1.11** `test_on_input_updates_last_metadata_at`: Timestamp updated after call
- [ ] **Q1.12** `test_emit_status_running_active`: Within 5s of last input → `RUNNING` / `blue` / `value=True`
- [ ] **Q1.13** `test_emit_status_running_idle`: More than 5s since last input → `RUNNING` / `gray` / `value=False`
- [ ] **Q1.14** `test_emit_status_no_input_yet`: `last_metadata_at is None` → `RUNNING` / `gray`

### WebhookSender
- [ ] **Q1.15** `test_from_config_returns_none_when_disabled`: `webhook_enabled = False` → `None`
- [ ] **Q1.16** `test_from_config_returns_none_when_url_empty`: `webhook_enabled = True, webhook_url = ""` → `None`
- [ ] **Q1.17** `test_from_config_bearer_header`: Auth type `bearer` → `Authorization: Bearer <token>`
- [ ] **Q1.18** `test_from_config_basic_auth_b64`: Auth type `basic` → `Authorization: Basic <base64>`
- [ ] **Q1.19** `test_from_config_api_key_header`: Auth type `api_key` → custom header name/value
- [ ] **Q1.20** `test_from_config_none_auth_no_auth_header`: Auth type `none` → no `Authorization` header
- [ ] **Q1.21** `test_from_config_merges_custom_headers`: Custom headers JSON merged into final headers
- [ ] **Q1.22** `test_from_config_invalid_custom_headers_json`: Non-JSON string → ignores custom headers, does not raise
- [ ] **Q1.23** `test_send_success_logs_debug`: Mock 200 response → DEBUG log, no error
- [ ] **Q1.24** `test_send_4xx_logs_error`: Mock 404 response → ERROR log, no raise
- [ ] **Q1.25** `test_send_5xx_logs_error`: Mock 503 response → ERROR log, no raise
- [ ] **Q1.26** `test_send_timeout_logs_error_does_not_raise`: `httpx.TimeoutException` → ERROR log, no raise
- [ ] **Q1.27** `test_send_connection_error_does_not_raise`: `httpx.ConnectError` → ERROR log, no raise
- [ ] **Q1.28** `test_send_does_not_log_credentials`: Assert token/password NOT present in any log output during error

### WebSocket Registration
- [ ] **Q1.29** `test_output_node_ws_topic_is_none`: Confirm `_ws_topic is None` after node creation (websocket_enabled=False)
- [ ] **Q1.30** `test_output_node_not_in_public_topics`: After DAG reload, `output_node` does not appear in `GET /api/v1/ws/topics`

---

## Phase 2 — API Integration Tests

- [ ] **Q2.1** `GET /api/v1/nodes/{node_id}/webhook` — known output_node → 200, default fields all present
- [ ] **Q2.2** `GET /api/v1/nodes/{node_id}/webhook` — unknown node → 404
- [ ] **Q2.3** `GET /api/v1/nodes/{node_id}/webhook` — wrong node type (e.g., sensor) → 400
- [ ] **Q2.4** `PATCH /api/v1/nodes/{node_id}/webhook` — valid bearer config → 200, persisted in DB
- [ ] **Q2.5** `PATCH /api/v1/nodes/{node_id}/webhook` — valid basic auth config → 200
- [ ] **Q2.6** `PATCH /api/v1/nodes/{node_id}/webhook` — valid api_key config → 200
- [ ] **Q2.7** `PATCH /api/v1/nodes/{node_id}/webhook` — enabled with empty URL → 400
- [ ] **Q2.8** `PATCH /api/v1/nodes/{node_id}/webhook` — invalid URL format → 400
- [ ] **Q2.9** `PATCH /api/v1/nodes/{node_id}/webhook` — unknown node → 404
- [ ] **Q2.10** `PATCH /api/v1/nodes/{node_id}/webhook` — confirm DB persisted (GET after PATCH returns updated values)
- [ ] **Q2.11** `PATCH` then node `reload_config` → webhook config survives reload (loaded from DB)
- [ ] **Q2.12** `PATCH` → confirm running `OutputNode._webhook` is hot-reloaded without full DAG restart
- [ ] **Q2.13** `GET /api/v1/nodes/definitions` → includes `output_node` with correct `websocket_enabled: false` and all properties

---

## Phase 3 — Frontend Unit Tests

### MetadataTableComponent
- [ ] **Q3.1** Renders "Waiting for data..." when `metadata = null`
- [ ] **Q3.2** Renders table rows for each field in metadata
- [ ] **Q3.3** Renders nested object as JSON string in pre tag
- [ ] **Q3.4** Renders array as JSON string
- [ ] **Q3.5** Renders null value as `—`
- [ ] **Q3.6** Type column shows `"number"` for numeric fields
- [ ] **Q3.7** Type column shows `"string"` for string fields
- [ ] **Q3.8** Type column shows `"boolean"` for boolean fields
- [ ] **Q3.9** Type column shows `"object"` for plain objects
- [ ] **Q3.10** Type column shows `"array"` for arrays
- [ ] **Q3.11** Type column shows `"null"` for null values

### OutputNodeComponent
- [ ] **Q3.12** Shows 404 card when API returns 404 for node
- [ ] **Q3.13** Displays `nodeName` in page header after API response
- [ ] **Q3.14** Shows `connecting` status before first WS message
- [ ] **Q3.15** Shows `connected` status after first WS message received
- [ ] **Q3.16** Shows `disconnected` status on WS error
- [ ] **Q3.17** Filters WS messages by `node_id` — ignores messages for other nodes
- [ ] **Q3.18** Filters WS messages by `type` — ignores non-`output_node_metadata` messages
- [ ] **Q3.19** Passes latest metadata to `MetadataTableComponent`
- [ ] **Q3.20** Unsubscribes WS subscription on `ngOnDestroy`

### WebhookConfigComponent
- [ ] **Q3.21** All webhook fields hidden when `webhook_enabled = false`
- [ ] **Q3.22** Webhook fields shown when toggle enabled
- [ ] **Q3.23** Only Bearer token input shown for `auth_type = bearer`
- [ ] **Q3.24** Username + password shown for `auth_type = basic`
- [ ] **Q3.25** Header name + key value shown for `auth_type = api_key`
- [ ] **Q3.26** No auth inputs shown for `auth_type = none`
- [ ] **Q3.27** Changing auth type clears previous credential fields
- [ ] **Q3.28** Inline error shown for empty URL when enabled
- [ ] **Q3.29** Inline warning shown for HTTP URL (not HTTPS)
- [ ] **Q3.30** Save button disabled when URL validation error present
- [ ] **Q3.31** Save button disabled while `isSaving = true`
- [ ] **Q3.32** `updateWebhookConfig` called on save with correct payload
- [ ] **Q3.33** API not called when validation error exists
- [ ] **Q3.34** `webhookSaved` output emitted on successful save
- [ ] **Q3.35** Form reset to original config on cancel
- [ ] **Q3.36** Token/password/key inputs use `type="password"` (masked)

### URL Validation Helper
- [ ] **Q3.37** Valid HTTPS URL → no error, no warning
- [ ] **Q3.38** Valid HTTP URL → no error, warning shown
- [ ] **Q3.39** Empty URL with enabled=true → error
- [ ] **Q3.40** Empty URL with enabled=false → no error (disabled)
- [ ] **Q3.41** Invalid format (e.g., `ftp://`) → error
- [ ] **Q3.42** Plain text (no scheme) → error

---

## Phase 4 — End-to-End / Integration Tests

- [ ] **Q4.1** **Happy path — sensor → output node → WebSocket → UI**:
  1. Create DAG: `sensor_node → output_node`
  2. Start data flow (mock or sim mode)
  3. Navigate to `/output/:nodeId`
  4. Verify metadata table populates within 100ms of data arriving
  5. Verify table updates continuously on new frames
- [ ] **Q4.2** **Multiple Output Nodes — correct filtering**:
  1. Create two Output Nodes (`A`, `B`) each connected to different upstream nodes
  2. Open page for Node A
  3. Verify only Node A metadata appears (Node B messages filtered out)
- [ ] **Q4.3** **Node deletion — graceful page state**:
  1. Open `/output/:nodeId`
  2. Delete the Output Node via DAG config save
  3. Verify page shows "Node not found" (not a crash or blank page)
- [ ] **Q4.4** **Webhook fire-and-forget — does not block DAG**:
  1. Configure webhook with slow external endpoint (mock 5s delay)
  2. Start data flow
  3. Measure DAG frame processing time — confirm not increased by webhook delay
  4. Verify WebSocket broadcasts are not delayed
- [ ] **Q4.5** **Webhook delivery — successful POST**:
  1. Configure webhook to `httpbin.org/post` (or local mock server)
  2. Send metadata through DAG
  3. Verify POST received with correct JSON body (type, node_id, metadata)
  4. Verify auth headers present
- [ ] **Q4.6** **Webhook failure — node survives**:
  1. Configure webhook to unreachable URL
  2. Start data flow
  3. Verify ERROR log entries appear
  4. Verify DAG continues processing, WebSocket still updates frontend
  5. Verify Output Node does NOT show ERROR status in canvas
- [ ] **Q4.7** **Webhook hot-reload**:
  1. Start DAG with webhook disabled
  2. PATCH webhook config to enable with a valid URL (no DAG reload)
  3. Verify next metadata triggers webhook POST
  4. PATCH webhook config to disable
  5. Verify subsequent metadata does NOT trigger webhook POST
- [ ] **Q4.8** **WebSocket reconnect**:
  1. Open Output Node page
  2. Kill/restart backend WebSocket service
  3. Verify frontend shows "disconnected" state, then reconnects (if reconnect logic implemented)
- [ ] **Q4.9** **Performance — metadata collection overhead**:
  1. Run 100k-point cloud through pipeline without Output Node → measure frame rate
  2. Add Output Node → measure frame rate again
  3. Verify overhead < 1% of DAG processing time
- [ ] **Q4.10** **Performance — UI with 100 metadata fields**:
  1. Inject payload with 100 metadata fields
  2. Verify Angular table renders without visible lag
  3. Verify no console errors
- [ ] **Q4.11** **DAG config persistence — webhook survives reload**:
  1. Configure webhook on an Output Node
  2. Save DAG config (PUT /dag/config)
  3. Call `/nodes/reload`
  4. GET webhook config → verify values persisted
  5. Verify webhook still fires on next metadata

---

## Phase 5 — Security & Edge Case Tests

- [ ] **Q5.1** Webhook log output does NOT contain bearer token or password (log sanitization)
- [ ] **Q5.2** PATCH webhook with `webhook_url = "javascript:alert(1)"` → 400 (URL validation rejects non-http/https)
- [ ] **Q5.3** PATCH webhook with very long URL (> 2048 chars) → verify handled (400 or truncation)
- [ ] **Q5.4** `webhook_custom_headers` containing injection characters → stored as-is, sent as HTTP header, no server-side injection
- [ ] **Q5.5** `webhook_auth_type` with unknown value → 422 Unprocessable Entity
- [ ] **Q5.6** Frontend password fields confirm `type="password"` attribute in DOM (not visible in plain text)
- [ ] **Q5.7** Frontend: navigating away from webhook config with unsaved changes → unsaved-changes guard prompts user

---

## Acceptance Criteria Traceability

| Requirement | Test(s) |
|---|---|
| F1: Single input port | Q4.1, Q1.29 |
| F2: Metadata broadcast via system WS | Q1.1, Q4.1 |
| F3: Dedicated Angular page | Q3.12–Q3.20, Q4.1 |
| F4: Navigation from canvas | Manual verification in Q4.1 |
| F5: Real-time WS updates | Q3.14–Q3.17, Q4.1 |
| F6: Error handling | Q1.9, Q3.12, Q3.28, Q4.3, Q4.6 |
| F7: Node registration in DAG | Q1.29, Q1.30, Q2.13 |
| Webhook F1: Config drawer | Q3.21–Q3.36 |
| Webhook F2: Fire-and-forget POST | Q1.2, Q4.4, Q4.5 |
| Webhook F3: URL validation | Q3.37–Q3.42, Q2.7, Q2.8 |
| Webhook F4: Error handling/logging | Q1.23–Q1.28, Q4.6 |
| Webhook F6: Config persistence | Q4.11, Q2.10 |
| Webhook F7: Backward compatibility | Q4.11 (existing nodes unaffected) |
| NF1: Performance < 1% overhead | Q4.9 |
| NF3: WS protocol / 1001 close | Q4.3 |
| NF3: Security — no credentials in logs | Q5.1, Q1.28 |

---

## Test Infrastructure Notes

- Backend tests: `pytest tests/modules/test_output_node.py tests/modules/test_webhook_sender.py tests/api/test_output_webhook.py -v`
- Frontend tests: `cd web && ng test --include="**/output-node/**"`
- Mock HTTP server for webhook E2E: use `pytest-httpserver` or a local `http.server` in a fixture
- Performance tests: run with `pytest tests/performance/` (if performance test suite exists) with `--benchmark` flag
