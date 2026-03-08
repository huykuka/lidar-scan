# QA Implementation Tasks — WebSocket Topic Cleanup

**Feature:** `websocket-topic-cleanup`  
**Owner:** @qa  
**References:**
- Technical Specification: `technical.md`
- API Contract: `api-spec.md`
- Backend Implementation Tasks: `backend-tasks.md`

**Test Coverage Goal:** 95%+ for modified files, 100% for new async methods.

---

## Phase 1 — Unit Test Validation

### ConnectionManager Tests
- [ ] **1.1** — Verify `test_unregister_topic_closes_websocket_connections` passes: WebSocket connections receive `1001 Going Away` close code
- [ ] **1.2** — Verify `test_unregister_topic_cancels_pending_futures` passes: All interceptor futures are cancelled properly
- [ ] **1.3** — Verify `test_unregister_topic_idempotent_on_missing_topic` passes: No exception on non-existent topic
- [ ] **1.4** — Verify `test_unregister_topic_with_already_cancelled_future` passes: Pre-cancelled futures handled gracefully
- [ ] **1.5** — Verify `test_unregister_topic_ws_close_error_does_not_abort_others` passes: One failed close doesn't prevent others

### LifecycleManager Tests
- [ ] **1.6** — Verify `test_remove_node_async_uses_stored_ws_topic` passes: Stored `_ws_topic` takes precedence over re-derivation
- [ ] **1.7** — Verify `test_remove_node_async_falls_back_to_derived_topic` passes: Fallback logic works when `_ws_topic` absent
- [ ] **1.8** — Verify `test_remove_node_async_missing_node_is_noop` passes: Non-existent node removal is safe

### NodeManager Orchestrator Tests
- [ ] **1.9** — Verify `test_reload_config_sweeps_orphaned_topics` passes: Orphaned topics from failed inits are cleaned
- [ ] **1.10** — Verify `test_reload_config_system_topics_not_swept` passes: System topics like `system_status` are preserved
- [ ] **1.11** — Verify `test_reload_config_concurrent_calls_blocked_by_lock` passes: Re-entrant lock prevents race conditions
- [ ] **1.12** — Verify `test_reload_config_stores_ws_topic_on_new_nodes` passes: All new nodes have `_ws_topic` attribute

### API Integration Tests
- [ ] **1.13** — Verify `test_capture_frame_returns_503_on_topic_removal` passes: HTTP 503 returned when topic removed during capture

---

## Phase 2 — Integration Test Development

### WebSocket Connection Lifecycle Tests
- [ ] **2.1** — Create test: `test_full_reload_cycle_closes_client_connections`
  - Setup: Register 2 nodes, connect WebSocket clients to both topics
  - Action: Remove one node from DB, call `POST /nodes/reload`
  - Assert: Client connection to removed node receives close event
  - Assert: Client connection to remaining node stays open
- [ ] **2.2** — Create test: `test_node_deletion_closes_websocket_immediately`
  - Setup: Register node, connect WebSocket client to its topic
  - Action: Call `DELETE /api/v1/nodes/{node_id}`
  - Assert: Client receives `1001 Going Away` close within 1 second
- [ ] **2.3** — Create test: `test_config_import_replace_triggers_reload`
  - Setup: Import config with `merge: false`
  - Assert: Response includes `"reloaded": true`
  - Assert: Old topics are cleaned, new topics available

### Topic Registry Consistency Tests
- [ ] **2.4** — Create test: `test_topics_endpoint_reflects_reality_after_reload`
  - Setup: Register 3 nodes
  - Action: Remove 1 node via config change, reload
  - Assert: `GET /api/v1/topics` returns only 2 topics
  - Assert: All returned topics have active producing nodes
- [ ] **2.5** — Create test: `test_orphaned_topic_from_failed_init_gets_swept`
  - Setup: Manually add topic to `ConnectionManager.active_connections` without corresponding node
  - Action: Call `reload_config()`
  - Assert: Orphaned topic is removed and logged as swept

### Error Handling & Recovery Tests
- [ ] **2.6** — Create test: `test_concurrent_reload_requests_handled_gracefully`
  - Action: Send 3 concurrent `POST /nodes/reload` requests
  - Assert: First request returns `200 OK`
  - Assert: Subsequent requests return `409 Conflict` or wait for completion
  - Assert: Final state is consistent (no partial cleanup)
- [ ] **2.7** — Create test: `test_capture_during_reload_returns_503_not_504`
  - Setup: Start `GET /topics/capture?topic=test_topic`
  - Action: Trigger node removal while capture is waiting
  - Assert: HTTP response is `503 Service Unavailable`
  - Assert: Response contains "Topic was removed while waiting" message

---

## Phase 3 — Load & Performance Testing

### Resource Cleanup Validation
- [ ] **3.1** — Memory leak test: Verify no futures or WebSocket objects are leaked after reload cycles
  - Setup: Monitor memory usage baseline
  - Action: Perform 50 reload cycles with varying node counts
  - Assert: Memory returns to baseline ±5% after each cycle
  - Assert: No indefinitely pending futures remain
- [ ] **3.2** — Connection scaling test: Verify proper cleanup with many concurrent connections
  - Setup: Register 1 node, connect 100 WebSocket clients
  - Action: Delete the node
  - Assert: All 100 clients receive close event within 5 seconds
  - Assert: Server memory usage decreases appropriately

### Performance Impact Validation
- [ ] **3.3** — Reload performance test: Measure impact of orphan sweep
  - Setup: Create scenario with 10 orphaned topics
  - Baseline: Measure reload time without orphans
  - Test: Measure reload time with orphan sweep
  - Assert: Orphan sweep adds <200ms to reload time
- [ ] **3.4** — Async conversion impact: Verify `reload_config()` doesn't block event loop
  - Setup: Start continuous HTTP requests to health endpoint
  - Action: Trigger `POST /nodes/reload`
  - Assert: Health endpoint remains responsive (<100ms) during reload
  - Assert: No "blocking operation in async context" warnings

---

## Phase 4 — End-to-End Scenario Testing

### Real-World Usage Scenarios
- [ ] **4.1** — Developer workflow test: Config reload during active development
  - Scenario: Developer imports new config via frontend, has active visualizer connections
  - Assert: Old visualizer connections close gracefully
  - Assert: New topics appear in topic selector
  - Assert: New connections can be established immediately
- [ ] **4.2** — Production deployment test: Node reconfiguration without service interruption
  - Scenario: Remove underperforming sensor node, add new one with different topic name
  - Assert: System topic (`system_status`) remains available throughout
  - Assert: Other unaffected nodes continue streaming data
  - Assert: No memory or connection leaks occur

### Error Recovery Scenarios
- [ ] **4.3** — Partial failure recovery: Node initialization fails during reload
  - Setup: Configure reload with one valid node and one that will fail to initialize
  - Assert: Valid node is operational
  - Assert: Failed node's topic is not registered
  - Assert: No orphaned topics remain from partial initialization
- [ ] **4.4** — Network disconnection during reload
  - Setup: Active WebSocket clients, network interruption during reload
  - Assert: Clients handle connection loss gracefully
  - Assert: Server state remains consistent
  - Assert: Clients can reconnect after network recovery

---

## Phase 5 — Frontend Integration Testing

### Angular Component Response
- [ ] **5.1** — Verify `MultiWebsocketService` handles `1001` close code correctly
  - Test: WebSocket receives close with code `1001`
  - Assert: `onclose` handler calls `subject.complete()`
  - Assert: Connection removed from `connections` Map
  - Assert: No reconnection attempt is made for code `1001`
- [ ] **5.2** — Verify topic selector updates after reload
  - Setup: Monitor `system_status` broadcasts for node list changes
  - Action: Trigger reload that changes available topics
  - Assert: Angular topic selector reflects new topic list
  - Assert: UI shows correct number of available topics

### Dashboard Metrics Integration
- [ ] **5.3** — Verify performance monitoring captures cleanup metrics
  - Action: Perform reload with WebSocket cleanup
  - Assert: Cleanup timing metrics are recorded
  - Assert: Connection count metrics decrease appropriately
  - Assert: No metrics collection errors during async operations

---

## Phase 6 — Regression Testing

### Existing Functionality Preservation
- [ ] **6.1** — Verify all existing WebSocket streaming tests still pass
- [ ] **6.2** — Verify node creation and deletion workflows remain functional
- [ ] **6.3** — Verify config import/export functionality is unchanged
- [ ] **6.4** — Verify system health monitoring continues during operations
- [ ] **6.5** — Verify Three.js rendering performance is unaffected

### Backward Compatibility
- [ ] **6.6** — Verify sync `remove_node()` method still works for existing callers
- [ ] **6.7** — Verify existing test suite passes without modification
- [ ] **6.8** — Verify no new LSP/type errors introduced in unchanged code

---

## Phase 7 — Documentation & Acceptance Testing

### Documentation Verification
- [ ] **7.1** — Verify `QUICK_REFERENCE.md` documents `_ws_topic` convention
- [ ] **7.2** — Verify API documentation reflects new error codes (503 vs 504)
- [ ] **7.3** — Verify async method preferences are documented

### Final Acceptance Criteria
- [ ] **7.4** — **CRITICAL**: WebSocket clients receive proper close notification when their topic is removed
- [ ] **7.5** — **CRITICAL**: `GET /api/v1/topics` never returns topics without active producing nodes
- [ ] **7.6** — **CRITICAL**: No futures remain indefinitely pending after topic removal
- [ ] **7.7** — **CRITICAL**: Config reload sweeps orphaned topics from failed prior initializations
- [ ] **7.8** — **CRITICAL**: System remains responsive during reload operations (no event loop blocking)
- [ ] **7.9** — **CRITICAL**: Concurrent reload requests are handled safely without race conditions
- [ ] **7.10** — Memory usage returns to baseline after reload cycles (no leaks)

---

## Test Coverage Requirements

| Component | Minimum Coverage | Focus Areas |
|---|---|---|
| `ConnectionManager.unregister_topic()` | 100% | WebSocket close, future cancellation, error handling |
| `LifecycleManager.*_async()` methods | 100% | Topic derivation, cleanup sequencing |
| `NodeManager.reload_config()` | 95% | Orphan sweep, lock behavior, async flow |
| API route handlers | 90% | Error responses, async promotion |
| Edge cases | 80% | Concurrent operations, failure scenarios |

---

## Dependencies & Blocking Issues

- **Blocks Frontend Testing**: Backend Phase 4-5 must complete before frontend integration tests
- **Blocks Performance Testing**: All backend phases must complete before load testing
- **Dependency**: Backend implementation must be deployed to test environment

---

## Sign-off Checklist

- [ ] All unit tests pass with required coverage
- [ ] Integration tests validate real-world scenarios  
- [ ] Performance tests confirm no regression
- [ ] Memory leak testing shows no resource leaks
- [ ] Frontend integration works correctly
- [ ] Documentation is accurate and complete
- [ ] **FINAL SIGN-OFF**: Feature meets all acceptance criteria and is ready for production deployment

