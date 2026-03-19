# QA Tasks - Flow Control Module

## Overview

Comprehensive test plan covering TDD preparation, unit testing, integration testing, API validation, performance testing, and final verification for the IF condition node module.

**Scope:**
- Expression parser correctness and security
- IF node routing logic (dual outputs)
- API endpoint validation
- Frontend UI functionality
- End-to-end DAG workflows
- Performance benchmarks
- Error resilience

**Reference:**
- Requirements: `requirements.md`
- Technical Design: `technical.md`
- API Specification: `api-spec.md`

---

## Phase 1: TDD Preparation (Pre-Development)

### Backend TDD Setup

- [ ] **Task 1.1:** Create test stubs BEFORE implementation
  - [ ] File: `tests/modules/flow_control/test_expression_parser.py`
    - [ ] Stub test cases for all expression operators
    - [ ] Stub security tests (eval rejection, whitelist enforcement)
  - [ ] File: `tests/modules/flow_control/test_if_node.py`
    - [ ] Stub test cases for routing logic (true/false paths)
    - [ ] Stub test cases for external state integration
  - [ ] File: `tests/api/test_flow_control_api.py`
    - [ ] Stub test cases for `/set` and `/reset` endpoints
  - [ ] All stubs should FAIL initially (red phase of TDD)

- [ ] **Task 1.2:** Define test data fixtures
  - [ ] File: `tests/fixtures/flow_control_fixtures.py`
  - [ ] Sample payloads:
    - [ ] High-quality payload: `{"point_count": 1500, "intensity_avg": 60, "timestamp": 12345}`
    - [ ] Low-quality payload: `{"point_count": 500, "intensity_avg": 30, "timestamp": 12346}`
    - [ ] Missing-field payload: `{"point_count": 1000}` (no intensity_avg)
  - [ ] Sample expressions:
    - [ ] Simple: `"point_count > 1000"`
    - [ ] Complex: `"(point_count > 1000 AND intensity_avg > 50) OR external_state == true"`
    - [ ] Invalid: `"point_count >< 1000"`

### Frontend TDD Setup

- [ ] **Task 1.3:** Create component test stubs BEFORE implementation
  - [ ] File: `if-condition-card.component.spec.ts`
    - [ ] Stub test: "should truncate long expressions"
    - [ ] Stub test: "should display evaluation status badge"
  - [ ] File: `if-condition-editor.component.spec.ts`
    - [ ] Stub test: "should validate expression syntax"
    - [ ] Stub test: "should emit saved event on save"
  - [ ] All stubs should FAIL initially

- [ ] **Task 1.4:** Set up mock services
  - [ ] Create `FlowControlApiService` mock with test data from `api-spec.md` section 12
  - [ ] Mock `NodeStoreService` for editor tests

---

## Phase 2: Unit Testing - Backend

### Expression Parser Tests

- [ ] **Task 2.1:** Basic expression evaluation
  - [ ] Test: `"point_count > 1000"` with context `{point_count: 1500}` → `True`
  - [ ] Test: `"point_count > 1000"` with context `{point_count: 500}` → `False`
  - [ ] Test: `"intensity_avg >= 50"` with context `{intensity_avg: 50}` → `True`
  - [ ] Test: `"intensity_avg >= 50"` with context `{intensity_avg: 49}` → `False`
  - [ ] Test: `"external_state == true"` with context `{external_state: True}` → `True`
  - [ ] Test: `"external_state == true"` with context `{external_state: False}` → `False`

- [ ] **Task 2.2:** Boolean operator tests
  - [ ] Test: `"A AND B"` with `{A: True, B: True}` → `True`
  - [ ] Test: `"A AND B"` with `{A: True, B: False}` → `False`
  - [ ] Test: `"A OR B"` with `{A: False, B: True}` → `True`
  - [ ] Test: `"A OR B"` with `{A: False, B: False}` → `False`
  - [ ] Test: `"NOT A"` with `{A: True}` → `False`
  - [ ] Test: `"NOT A"` with `{A: False}` → `True`

- [ ] **Task 2.3:** Parentheses grouping tests
  - [ ] Test: `"(A OR B) AND C"` with `{A: True, B: False, C: True}` → `True`
  - [ ] Test: `"(A OR B) AND C"` with `{A: False, B: False, C: True}` → `False`
  - [ ] Test: `"A OR (B AND C)"` with `{A: False, B: True, C: True}` → `True`
  - [ ] Test: Nested: `"((A OR B) AND C) OR D"` → correct evaluation

- [ ] **Task 2.4:** Case-insensitivity tests
  - [ ] Test: `"point_count > 1000 and intensity_avg > 50"` → works (lowercase `and`)
  - [ ] Test: `"point_count > 1000 AND intensity_avg > 50"` → works (uppercase `AND`)
  - [ ] Test: `"point_count > 1000 And intensity_avg > 50"` → works (mixed case)

- [ ] **Task 2.5:** Missing field handling
  - [ ] Test: Expression `"missing_field > 100"` with context `{}` → returns `False` (not error)
  - [ ] Test: Expression `"point_count > 100 AND missing_field > 50"` → evaluates `AND` with `None`

- [ ] **Task 2.6:** Type mismatch tests
  - [ ] Test: `"string_field > 100"` with `{string_field: "hello"}` → raises `TypeError`
  - [ ] Test: `"point_count == 'string'"` with `{point_count: 1000}` → raises `TypeError`
  - [ ] Verify parser catches exception and returns safe result

- [ ] **Task 2.7:** Syntax error tests
  - [ ] Test: `"point_count >"` (missing operand) → raises `SyntaxError`
  - [ ] Test: `"point_count >< 1000"` (invalid operator) → raises `SyntaxError`
  - [ ] Test: `"(point_count > 1000"` (unbalanced parentheses) → raises `SyntaxError`

- [ ] **Task 2.8:** Security tests (whitelist enforcement)
  - [ ] Test: `"point_count + 500 > 1000"` (arithmetic) → raises `ValueError`
  - [ ] Test: `"__import__('os').system('ls')"` (import) → raises `ValueError`
  - [ ] Test: `"exec('code')"` (exec) → raises `ValueError`
  - [ ] Test: `"lambda x: x > 1000"` (lambda) → raises `ValueError`
  - [ ] Verify NO `eval()` is used anywhere in parser

- [ ] **Task 2.9:** Performance tests
  - [ ] Test: Benchmark 1000 evaluations of simple expression → measure average time
  - [ ] Verify average < 1ms (NF1 requirement)
  - [ ] Test: Benchmark complex expression `(A AND B) OR (C AND D)` → verify <1ms

### IfConditionNode Tests

- [ ] **Task 2.10:** Basic routing tests
  - [ ] Test: Expression `"true"` → all payloads routed to `true` port
  - [ ] Test: Expression `"false"` → all payloads routed to `false` port
  - [ ] Test: Expression `"point_count > 1000"` with 1500 points → `true` port
  - [ ] Test: Expression `"point_count > 1000"` with 500 points → `false` port

- [ ] **Task 2.11:** External state integration
  - [ ] Test: Expression `"external_state == true"` with `node.external_state=False` → `false` port
  - [ ] Test: Expression `"external_state == true"` with `node.external_state=True` → `true` port
  - [ ] Test: Change state mid-stream: set to `True`, send payload, verify routing switches

- [ ] **Task 2.12:** Error handling tests
  - [ ] Test: Invalid expression → all payloads routed to `false` port
  - [ ] Test: Invalid expression → `last_error` field populated
  - [ ] Test: Type mismatch during evaluation → `false` port, error logged
  - [ ] Test: Missing field → `false` port, warning logged

- [ ] **Task 2.14:** Status reporting tests
  - [ ] Test: `get_status()` returns all required fields
  - [ ] Test: `last_evaluation` field updates correctly (True/False/None)
  - [ ] Test: `last_error` field cleared after successful evaluation

---

## Phase 3: Unit Testing - Frontend

### Card Component Tests

- [ ] **Task 3.1:** Expression truncation test
  - [ ] Test: Expression longer than 30 chars → displays `...`
  - [ ] Test: Expression shorter than 30 chars → displays full text

- [ ] **Task 3.2:** Status badge display tests
  - [ ] Test: Status with `last_evaluation=true` → displays green "TRUE" badge
  - [ ] Test: Status with `last_evaluation=false` → displays neutral "FALSE" badge
  - [ ] Test: Status with `last_evaluation=null` → displays neutral "—" badge

- [ ] **Task 3.3:** Error badge test
  - [ ] Test: Status with `last_error="Syntax error"` → displays red error badge
  - [ ] Test: Status with `last_error=null` → no error badge shown

### Editor Component Tests

- [ ] **Task 3.4:** Form initialization tests
  - [ ] Test: Editor loads node config → form pre-filled with expression
  - [ ] Test: New node → form defaults to `expression="true"`, `throttle_ms=0`

- [ ] **Task 3.5:** Validation tests
  - [ ] Test: Invalid characters in expression → validation error displayed
  - [ ] Test: Unbalanced parentheses → validation error displayed
  - [ ] Test: Valid expression → no validation error

- [ ] **Task 3.6:** Save/Cancel tests
  - [ ] Test: Click save → `saved` event emitted
  - [ ] Test: Click save → node store updated with new config
  - [ ] Test: Click cancel → `cancelled` event emitted
  - [ ] Test: Click cancel → node config unchanged

### API Service Tests

- [ ] **Task 3.7:** `setExternalState()` tests
  - [ ] Test: Call with `value=true` → POST request to correct endpoint
  - [ ] Test: Response contains `{node_id, state, timestamp}`
  - [ ] Test: HTTP error (404) → error observable returned

- [ ] **Task 3.8:** `resetExternalState()` tests
  - [ ] Test: Call → POST request to `/reset` endpoint
  - [ ] Test: Response contains `state=false`

---

## Phase 4: Integration Testing - Backend

### API Endpoint Tests

- [ ] **Task 4.1:** POST `/flow-control/set` validation
  - [ ] Test: Valid request `{"value": true}` → 200 response
  - [ ] Test: Response body matches schema: `{node_id, state, timestamp}`
  - [ ] Test: State persists: call `/set` then check node status
  - [ ] Test: Invalid body (string instead of boolean) → 400 error
  - [ ] Test: Missing `value` field → 400 error
  - [ ] Test: Node not found → 404 error
  - [ ] Test: Wrong node type (downsample node) → 404 error

- [ ] **Task 4.2:** POST `/flow-control/reset` validation
  - [ ] Test: Valid request → 200 response
  - [ ] Test: Response `state=false`
  - [ ] Test: State resets: call `/set` with `true`, then `/reset`, verify `false`
  - [ ] Test: Node not found → 404 error

### DAG Integration Tests

- [ ] **Task 4.3:** Full routing workflow
  - [ ] Create DAG: `sensor → if_node → (true: downsample, false: discard)`
  - [ ] Configure expression: `"point_count > 1000"`
  - [ ] Send high-quality payload (1500 points) → verify downsample receives data
  - [ ] Send low-quality payload (500 points) → verify discard receives data
  - [ ] Verify sensor → if_node connection works

- [ ] **Task 4.4:** External state workflow
  - [ ] Create IF node with expression: `"external_state == true"`
  - [ ] Send payload → verify routes to `false` port (initial state)
  - [ ] Call `/set` with `value=true`
  - [ ] Send payload → verify routes to `true` port
  - [ ] Call `/reset`
  - [ ] Send payload → verify routes back to `false` port

- [ ] **Task 4.5:** Multi-branch routing
  - [ ] Create DAG: `if_node → (true: branch_A, false: branch_B → branch_C)`
  - [ ] Verify data flows to correct downstream chain based on condition

- [ ] **Task 4.6:** Error resilience test
  - [ ] Create IF node with invalid expression: `"point_count ><"`
  - [ ] Send 100 payloads → verify all route to `false` port
  - [ ] Verify DAG does NOT crash
  - [ ] Verify error logged in backend logs

### WebSocket Behavior Tests

- [ ] **Task 4.7:** Invisible node verification
  - [ ] Create IF node → verify NO WebSocket topic registered
  - [ ] Send data through IF node → verify NO WebSocket broadcast
  - [ ] Verify downstream nodes still broadcast correctly

---

## Phase 5: Integration Testing - Frontend

### Node Creation Workflow

- [ ] **Task 5.1:** E2E test: Create IF node
  - [ ] Open flow canvas
  - [ ] Drag IF node from palette to canvas
  - [ ] Verify node appears with default config
  - [ ] Verify node displays two output ports (True, False)

- [ ] **Task 5.2:** E2E test: Configure IF node
  - [ ] Click IF node → editor opens
  - [ ] Enter expression: `point_count > 1000`
  - [ ] Set throttle: `100`
  - [ ] Click save → verify API called with correct payload
  - [ ] Verify node config updated in UI

- [ ] **Task 5.3:** E2E test: Expression validation
  - [ ] Open editor
  - [ ] Enter invalid expression: `point_count >< 1000`
  - [ ] Verify validation error displayed
  - [ ] Verify save button disabled

### Edge Creation Workflow

- [ ] **Task 5.4:** E2E test: Connect true port
  - [ ] Create IF node + downstream node
  - [ ] Drag from IF node's `true` port to downstream input
  - [ ] Verify edge created with `source_port="true"`
  - [ ] Verify API call includes port metadata

- [ ] **Task 5.5:** E2E test: Connect false port
  - [ ] Drag from IF node's `false` port to different downstream node
  - [ ] Verify edge created with `source_port="false"`
  - [ ] Verify both edges visible on canvas

- [ ] **Task 5.6:** E2E test: Edge color coding
  - [ ] Verify `true` port edge displayed in green
  - [ ] Verify `false` port edge displayed in orange (or distinct color)

### External State Control (if implemented)

- [ ] **Task 5.7:** E2E test: External state toggle
  - [ ] Open IF node editor
  - [ ] Click "External State Control" button
  - [ ] Set state to `true` → verify API called
  - [ ] Verify success toast displayed
  - [ ] Verify node card shows "Ext: ON" badge

---

## Phase 6: Performance Testing

### Latency Benchmarks

- [ ] **Task 6.1:** Expression evaluation performance
  - [ ] Load test: 1000 payloads through IF node
  - [ ] Measure average evaluation time per payload
  - [ ] Verify average < 1ms (NF1 requirement)
  - [ ] Test with simple expression: `point_count > 1000`
  - [ ] Test with complex expression: `(point_count > 1000 AND intensity_avg > 50) OR external_state == true`

- [ ] **Task 6.2:** DAG throughput test
  - [ ] Create DAG: `sensor → if_node → downstream processing`
  - [ ] Stream 10,000 frames at 30 FPS
  - [ ] Verify no frame drops due to IF node processing
  - [ ] Verify backend CPU usage increase < 5%

### Stress Testing

- [ ] **Task 6.3:** Error resilience stress test
  - [ ] Create IF node with invalid expression
  - [ ] Send 1000 payloads → verify 0 crashes
  - [ ] Verify all 1000 routed to `false` port
  - [ ] Verify backend continues processing after test

- [ ] **Task 6.4:** Rapid state changes
  - [ ] Call `/set` and `/reset` 100 times in rapid succession
  - [ ] Verify no race conditions or crashes
  - [ ] Verify final state is deterministic

---

## Phase 7: Final Verification

### Acceptance Criteria Checklist

**From `requirements.md`:**

- [ ] **F1:** Dual output port routing works (true/false paths)
- [ ] **F2:** Boolean expression evaluation works (all operators)
- [ ] **F3:** Metadata field access works (point_count, intensity_avg, etc.)
- [ ] **F4:** External state control API works (/set, /reset)
- [ ] **F5:** Fail-safe error handling works (syntax errors → false port)
- [ ] **F6:** Angular UI configuration works (expression editor, validation)

- [ ] **NF1:** Performance <1ms per evaluation
- [ ] **NF2:** Logging & observability (DEBUG/ERROR logs, status fields)
- [ ] **NF3:** DAG schema integration (node type registered, icon, category)
- [ ] **NF4:** API documentation (Swagger UI shows new endpoints)

### Regression Testing

- [ ] **Task 7.1:** Verify existing nodes still work
  - [ ] Create sensor → downsample → fusion DAG (no IF node)
  - [ ] Verify data flows correctly
  - [ ] Verify no performance degradation

- [ ] **Task 7.2:** Verify single-port nodes unaffected
  - [ ] Test existing operation nodes (crop, outlier removal, etc.)
  - [ ] Verify edges still create/delete correctly
  - [ ] Verify WebSocket broadcasting unchanged

### Documentation Verification

- [ ] **Task 7.3:** API documentation check
  - [ ] Open Swagger UI (`/docs`)
  - [ ] Verify `/flow-control/set` endpoint documented
  - [ ] Verify `/flow-control/reset` endpoint documented
  - [ ] Verify request/response schemas displayed
  - [ ] Verify example requests are accurate

- [ ] **Task 7.4:** Code documentation check
  - [ ] Verify all Python classes have docstrings
  - [ ] Verify all TypeScript components have JSDoc comments
  - [ ] Verify README updated with flow control module usage

---

## Phase 8: Test Report & Sign-Off

### Coverage Report

- [ ] **Task 8.1:** Generate backend coverage report
  - [ ] Run: `pytest --cov=app/modules/flow_control/if_condition --cov-report=html`
  - [ ] Verify coverage:
    - [ ] `expression_parser.py`: 95%+
    - [ ] `node.py`: 90%+
    - [ ] API endpoints: 100%

- [ ] **Task 8.2:** Generate frontend coverage report
  - [ ] Run: `cd web && npm run test:coverage`
  - [ ] Verify coverage:
    - [ ] Card component: 80%+
    - [ ] Editor component: 80%+
    - [ ] API service: 90%+

### QA Report

- [ ] **Task 8.3:** Create `qa-report.md`
  - [ ] Summary of test results (passed/failed counts)
  - [ ] List of identified bugs (with GitHub issue links)
  - [ ] Performance benchmark results
  - [ ] Coverage metrics
  - [ ] Risk assessment (high/medium/low)
  - [ ] Go/No-Go recommendation for release

### Sign-Off

- [ ] **Task 8.4:** QA approval
  - [ ] All critical tests passing
  - [ ] No high-severity bugs remaining
  - [ ] Performance requirements met
  - [ ] Documentation complete
  - [ ] **QA Sign-Off:** ✅ / ❌

---

## Test Data & Fixtures

### Sample Expressions

```python
# Simple comparisons
"point_count > 1000"
"intensity_avg >= 50"
"external_state == true"

# Boolean logic
"point_count > 1000 AND intensity_avg > 50"
"point_count < 500 OR external_state == true"
"NOT (point_count < 1000)"

# Complex grouping
"(point_count > 1000 AND intensity_avg > 50) OR external_state == true"
"(variance > 0.01 OR point_count > 5000) AND NOT (timestamp < 12345678)"

# Edge cases
"true"  # Always true
"false"  # Always false
""  # Empty string (should error)
"point_count ><"  # Syntax error
"point_count + 500 > 1000"  # Arithmetic (should reject)
```

### Sample Payloads

```python
# High-quality payload
{
  "points": np.random.rand(1500, 3),
  "point_count": 1500,
  "intensity_avg": 60.0,
  "variance": 0.02,
  "timestamp": 1234567890.0,
  "node_id": "sensor_1"
}

# Low-quality payload
{
  "points": np.random.rand(500, 3),
  "point_count": 500,
  "intensity_avg": 30.0,
  "variance": 0.005,
  "timestamp": 1234567891.0,
  "node_id": "sensor_1"
}

# Missing fields
{
  "points": np.random.rand(1000, 3),
  "point_count": 1000,
  "timestamp": 1234567892.0,
  # intensity_avg missing
}
```

---

## Bug Tracking

### Issue Template

When bugs are found during QA, create GitHub issues with:

**Title:** `[Flow Control] Brief description`

**Labels:** `bug`, `flow-control`, `priority:high/medium/low`

**Body:**
```markdown
## Bug Description
Clear description of the issue

## Steps to Reproduce
1. Step one
2. Step two
3. ...

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- Backend version: X.X.X
- Frontend version: X.X.X
- Browser (if frontend): Chrome 120

## Test Case
Link to failing test in `qa-tasks.md`

## Severity
Critical / High / Medium / Low
```

---

## Success Metrics

- [ ] **Zero high-severity bugs** in production code
- [ ] **95%+ backend coverage** for flow_control module
- [ ] **80%+ frontend coverage** for IF node components
- [ ] **<1ms average latency** for expression evaluation
- [ ] **0 DAG crashes** in 1000-frame stress test
- [ ] **All acceptance criteria** (F1-F6, NF1-NF4) verified

---

**Document Status:** ✅ READY FOR QA EXECUTION  
**Coordination:** Execute in parallel with development using TDD approach
