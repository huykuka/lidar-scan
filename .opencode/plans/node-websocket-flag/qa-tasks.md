# QA Testing Tasks - Node WebSocket Streaming Flag

## Summary
Comprehensive test plan covering unit tests, integration tests, and E2E scenarios to verify that non-streaming nodes (calibration, flow control) correctly hide visibility/recording controls while streaming nodes (sensor, fusion, operations) continue to show them.

---

## Test Categories

### ✅ Unit Tests (Backend)
### ✅ Unit Tests (Frontend)
### ✅ Integration Tests (API)
### ✅ E2E Tests (UI Behavior)
### ✅ Regression Tests (Existing Functionality)

---

## Backend Unit Tests

**Owner:** Backend Developer  
**File:** `tests/modules/test_node_definitions.py`

### Test 1: Schema Validation
- [ ] **Test:** All registered node definitions include `websocket_enabled` field
- [ ] **Method:** `test_all_definitions_have_websocket_enabled_field()`
- [ ] **Success Criteria:** No node definitions missing the field
- [ ] **Command:** `pytest tests/modules/test_node_definitions.py::test_all_definitions_have_websocket_enabled_field -v`

### Test 2: Streaming Nodes Configuration
- [ ] **Test:** Sensor, fusion, and operation nodes have `websocket_enabled=True`
- [ ] **Method:** `test_streaming_nodes_have_websocket_enabled_true()`
- [ ] **Success Criteria:** All 10 streaming node types return `True`
- [ ] **Command:** `pytest tests/modules/test_node_definitions.py::test_streaming_nodes_have_websocket_enabled_true -v`

**Expected streaming nodes:**
- `sensor`
- `fusion`
- `crop`
- `downsample`
- `outlier_removal`
- `radius_outlier_removal`
- `plane_segmentation`
- `clustering`
- `boundary_detection`
- `filter_by_key`
- `debug_save`

### Test 3: Non-Streaming Nodes Configuration
- [ ] **Test:** Calibration and flow control nodes have `websocket_enabled=False`
- [ ] **Method:** `test_non_streaming_nodes_have_websocket_enabled_false()`
- [ ] **Success Criteria:** Both non-streaming types return `False`
- [ ] **Command:** `pytest tests/modules/test_node_definitions.py::test_non_streaming_nodes_have_websocket_enabled_false -v`

**Expected non-streaming nodes:**
- `calibration`
- `if_condition`

### Test 4: Backend Coverage
- [ ] **Test:** Achieve 100% coverage of registry files
- [ ] **Command:** `pytest tests/modules/ --cov=app/modules --cov-report=html`
- [ ] **Success Criteria:** All registry files show green coverage

---

## Frontend Unit Tests

**Owner:** Frontend Developer  
**File:** `web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.spec.ts`

### Test 5: Hide Visibility Toggle (Calibration)
- [ ] **Test:** Visibility toggle hidden when `websocket_enabled=false`
- [ ] **Method:** `should hide visibility toggle when websocket_enabled is false`
- [ ] **Setup:** Mock calibration node definition
- [ ] **Assert:** `app-node-visibility-toggle` component not in DOM

### Test 6: Hide Recording Controls (Flow Control)
- [ ] **Test:** Recording controls hidden when `websocket_enabled=false`
- [ ] **Method:** `should hide recording controls when websocket_enabled is false`
- [ ] **Setup:** Mock if_condition node definition
- [ ] **Assert:** `app-node-recording-controls` component not in DOM

### Test 7: Show Visibility Toggle (Sensor)
- [ ] **Test:** Visibility toggle shown when `websocket_enabled=true`
- [ ] **Method:** `should show visibility toggle when websocket_enabled is true`
- [ ] **Setup:** Mock sensor node definition
- [ ] **Assert:** `app-node-visibility-toggle` component exists in DOM

### Test 8: Show Recording Controls (Sensor with Output)
- [ ] **Test:** Recording controls shown when `websocket_enabled=true` and node has outputs
- [ ] **Method:** `should show recording controls when websocket_enabled is true and node has outputs`
- [ ] **Setup:** Mock sensor node with output port
- [ ] **Assert:** `app-node-recording-controls` component exists in DOM

### Test 9: Backward Compatibility
- [ ] **Test:** Controls shown when node definition is missing
- [ ] **Method:** `should default to showing controls when definition is missing`
- [ ] **Setup:** Empty node definitions array
- [ ] **Assert:** Controls visible (safe default behavior)

### Test 10: Frontend Coverage
- [ ] **Command:** `cd web && npm test -- --code-coverage`
- [ ] **Success Criteria:** `flow-canvas-node.component.ts` shows >90% coverage

---

## Integration Tests (API)

**Owner:** QA Engineer  
**Environment:** Local development server

### Test 11: API Response Format
- [ ] **Test:** `/api/v1/nodes/definitions` includes `websocket_enabled` in all definitions
- [ ] **Method:** Manual cURL or Postman request
- [ ] **Command:** `curl http://localhost:8000/api/v1/nodes/definitions | jq '.[].websocket_enabled'`
- [ ] **Success Criteria:** All definitions return boolean value (no `null` or missing)

### Test 12: Sensor Node API Response
- [ ] **Test:** Sensor definition returns `websocket_enabled: true`
- [ ] **Command:** `curl http://localhost:8000/api/v1/nodes/definitions | jq '.[] | select(.type=="sensor")'`
- [ ] **Expected:**
```json
{
  "type": "sensor",
  "websocket_enabled": true,
  ...
}
```

### Test 13: Calibration Node API Response
- [ ] **Test:** Calibration definition returns `websocket_enabled: false`
- [ ] **Command:** `curl http://localhost:8000/api/v1/nodes/definitions | jq '.[] | select(.type=="calibration")'`
- [ ] **Expected:**
```json
{
  "type": "calibration",
  "websocket_enabled": false,
  ...
}
```

### Test 14: All Operation Nodes API Response
- [ ] **Test:** All 9 operation types return `websocket_enabled: true`
- [ ] **Command:** `curl http://localhost:8000/api/v1/nodes/definitions | jq '.[] | select(.category=="operation") | {type, websocket_enabled}'`
- [ ] **Success Criteria:** All operation nodes show `"websocket_enabled": true`

---

## E2E Tests (UI Behavior)

**Owner:** QA Engineer  
**Environment:** Full stack (backend + frontend running)

### Test 15: Calibration Node UI (No Streaming Controls)
- [ ] **Scenario:** Create calibration node on canvas
- [ ] **Steps:**
  1. Navigate to `/settings`
  2. Drag "ICP Calibration" from palette to canvas
  3. Wait for node to render
  4. Inspect node control bar
- [ ] **Expected:** 
  - ✅ Enable/disable toggle visible
  - ✅ Settings icon visible
  - ❌ Visibility toggle NOT visible
  - ❌ Recording button NOT visible
- [ ] **Screenshot:** Capture node control bar for documentation

### Test 16: Sensor Node UI (Streaming Controls Present)
- [ ] **Scenario:** Create sensor node on canvas
- [ ] **Steps:**
  1. Navigate to `/settings`
  2. Drag "LiDAR Sensor" from palette to canvas
  3. Wait for node to render
  4. Inspect node control bar
- [ ] **Expected:**
  - ✅ Enable/disable toggle visible
  - ✅ Settings icon visible
  - ✅ Visibility toggle visible
  - ✅ Recording button visible
- [ ] **Screenshot:** Capture node control bar for comparison

### Test 17: Flow Control Node UI (No Streaming Controls)
- [ ] **Scenario:** Create if_condition node on canvas
- [ ] **Steps:**
  1. Navigate to `/settings`
  2. Drag "If Condition" from palette to canvas
  3. Wait for node to render
  4. Inspect node control bar
- [ ] **Expected:**
  - ✅ Enable/disable toggle visible
  - ✅ Settings icon visible
  - ❌ Visibility toggle NOT visible
  - ❌ Recording button NOT visible

### Test 18: Operation Node UI (Streaming Controls Present)
- [ ] **Scenario:** Create crop filter node on canvas
- [ ] **Steps:**
  1. Navigate to `/settings`
  2. Drag "Crop Filter" from palette to canvas
  3. Wait for node to render
  4. Inspect node control bar
- [ ] **Expected:**
  - ✅ Enable/disable toggle visible
  - ✅ Settings icon visible
  - ✅ Visibility toggle visible
  - ✅ Recording button visible

### Test 19: Node Enable State Interaction
- [ ] **Scenario:** Verify controls hide when node is disabled
- [ ] **Steps:**
  1. Create sensor node (streaming controls visible)
  2. Click enable/disable toggle to disable node
  3. Verify visibility/recording controls disappear
  4. Re-enable node
  5. Verify visibility/recording controls reappear
- [ ] **Expected:** Controls only visible when node is enabled AND `websocket_enabled=true`

### Test 20: Node Editor Accessibility
- [ ] **Scenario:** Non-streaming nodes still allow configuration
- [ ] **Steps:**
  1. Create calibration node (no streaming controls)
  2. Click settings icon
  3. Verify node editor opens
  4. Modify configuration values
  5. Save changes
- [ ] **Expected:** Configuration works normally despite hidden streaming controls

---

## Regression Tests

**Owner:** QA Engineer  
**Purpose:** Ensure existing functionality unchanged

### Test 21: Existing Sensor Streaming
- [ ] **Test:** Sensor nodes continue to stream point clouds
- [ ] **Steps:**
  1. Create sensor node with mock PCD file
  2. Enable node
  3. Navigate to `/workspaces`
  4. Verify point cloud renders in 3D viewer
- [ ] **Expected:** No regression in streaming behavior

### Test 22: Existing Recording Functionality
- [ ] **Test:** Recording still works on sensor nodes
- [ ] **Steps:**
  1. Create sensor node
  2. Enable node
  3. Click recording button (visible)
  4. Record for 10 seconds
  5. Stop recording
  6. Navigate to `/recordings`
  7. Verify recording appears in list
- [ ] **Expected:** Recording workflow unchanged

### Test 23: Existing Visibility Toggle
- [ ] **Test:** Visibility toggle still controls WebSocket streaming
- [ ] **Steps:**
  1. Create sensor node
  2. Enable node (visible by default)
  3. Navigate to `/workspaces`
  4. Verify point cloud visible
  5. Return to `/settings`
  6. Click visibility toggle (hide)
  7. Return to `/workspaces`
  8. Verify point cloud disappeared
- [ ] **Expected:** Visibility toggle functionality unchanged

### Test 24: Calibration Workflow
- [ ] **Test:** Calibration node computes transformations as before
- [ ] **Steps:**
  1. Create two sensor nodes
  2. Create calibration node
  3. Connect sensors to calibration node
  4. Enable all nodes
  5. Trigger calibration
  6. Verify calibration results appear
- [ ] **Expected:** Calibration logic unaffected by UI changes

### Test 25: Flow Control Routing
- [ ] **Test:** If_condition node routes data correctly
- [ ] **Steps:**
  1. Create sensor → if_condition → two downstream nodes
  2. Configure condition (e.g., `point_count > 1000`)
  3. Enable all nodes
  4. Feed data through sensor
  5. Verify data routes to correct branch
- [ ] **Expected:** Conditional routing works despite hidden controls

---

## Performance Tests

### Test 26: Rendering Performance
- [ ] **Test:** No performance degradation from conditional rendering
- [ ] **Method:** Create 20 nodes on canvas (mix of streaming/non-streaming)
- [ ] **Measure:** Time to render all nodes
- [ ] **Success Criteria:** <100ms (baseline: existing performance)

### Test 27: API Response Time
- [ ] **Test:** `/nodes/definitions` response time unchanged
- [ ] **Method:** Benchmark API endpoint before/after changes
- [ ] **Command:** `ab -n 100 -c 10 http://localhost:8000/api/v1/nodes/definitions`
- [ ] **Success Criteria:** No regression in response time (baseline: ~50ms)

---

## Cross-Browser Testing

### Test 28: Chrome
- [ ] Run E2E tests 15-20 in Chrome
- [ ] Verify all UI controls render correctly
- [ ] Check console for errors

### Test 29: Firefox
- [ ] Run E2E tests 15-20 in Firefox
- [ ] Verify all UI controls render correctly
- [ ] Check console for errors

### Test 30: Safari (if available)
- [ ] Run E2E tests 15-20 in Safari
- [ ] Verify all UI controls render correctly
- [ ] Check console for errors

---

## Accessibility Testing

### Test 31: Keyboard Navigation
- [ ] **Test:** All visible controls accessible via keyboard
- [ ] **Steps:**
  1. Create sensor node (all controls visible)
  2. Tab through controls
  3. Verify focus indicators
  4. Activate controls with Enter/Space
- [ ] **Expected:** Full keyboard accessibility

### Test 32: Screen Reader Compatibility
- [ ] **Test:** Hidden controls don't confuse screen readers
- [ ] **Tool:** NVDA or VoiceOver
- [ ] **Steps:**
  1. Create calibration node
  2. Navigate controls with screen reader
  3. Verify hidden controls not announced
- [ ] **Expected:** Only visible controls announced

---

## Test Execution Summary

| Category | Tests | Owner | Time Estimate |
|----------|-------|-------|---------------|
| Backend Unit | 4 | Backend Dev | 30 min |
| Frontend Unit | 6 | Frontend Dev | 1 hour |
| Integration | 4 | QA | 30 min |
| E2E UI | 6 | QA | 1.5 hours |
| Regression | 5 | QA | 1 hour |
| Performance | 2 | QA | 30 min |
| Cross-Browser | 3 | QA | 45 min |
| Accessibility | 2 | QA | 30 min |
| **Total** | **32** | | **6 hours 15 min** |

---

## Test Report Template

**File:** `.opencode/plans/node-websocket-flag/qa-report.md`

```markdown
# QA Test Report - Node WebSocket Streaming Flag

**Date:** [Date]  
**Tester:** [Name]  
**Environment:** [Dev/Staging/Prod]  
**Build:** [Git commit hash]

## Summary
- **Total Tests:** 32
- **Passed:** [X]
- **Failed:** [Y]
- **Blocked:** [Z]
- **Pass Rate:** [X/32 * 100]%

## Failed Tests
[List any failed tests with details]

## Blockers
[List any blockers preventing test execution]

## Screenshots
[Attach screenshots of UI behavior]

## Recommendations
[Any recommendations for improvement]

## Sign-off
- [ ] All critical tests passed
- [ ] No P0/P1 bugs found
- [ ] Ready for production deployment
```

---

## Test Automation (Future)

**File:** `tests/e2e/test_node_ui_controls.py` (Playwright/Selenium)

```python
def test_calibration_node_hides_streaming_controls(browser):
    """E2E: Verify calibration node shows no visibility/recording controls."""
    browser.goto("http://localhost:4200/settings")
    
    # Add calibration node from palette
    palette = browser.wait_for_selector("[data-testid='node-palette']")
    calibration_btn = palette.query_selector("button:has-text('ICP Calibration')")
    calibration_btn.click()
    
    # Click on canvas to place node
    canvas = browser.wait_for_selector("[data-testid='flow-canvas']")
    canvas.click(position={'x': 400, 'y': 300})
    
    # Wait for node to appear
    node = browser.wait_for_selector("[data-node-type='calibration']")
    
    # Assert: No visibility toggle button
    assert node.query_selector("app-node-visibility-toggle") is None
    
    # Assert: No recording controls
    assert node.query_selector("app-node-recording-controls") is None
    
    # Assert: Enable toggle still exists
    assert node.query_selector("[data-testid='enable-toggle']") is not None

def test_sensor_node_shows_streaming_controls(browser):
    """E2E: Verify sensor node shows visibility/recording controls."""
    browser.goto("http://localhost:4200/settings")
    
    # Add sensor node
    palette = browser.wait_for_selector("[data-testid='node-palette']")
    sensor_btn = palette.query_selector("button:has-text('LiDAR Sensor')")
    sensor_btn.click()
    
    canvas = browser.wait_for_selector("[data-testid='flow-canvas']")
    canvas.click(position={'x': 400, 'y': 300})
    
    node = browser.wait_for_selector("[data-node-type='sensor']")
    
    # Assert: Visibility toggle exists
    assert node.query_selector("app-node-visibility-toggle") is not None
    
    # Assert: Recording controls exist
    assert node.query_selector("app-node-recording-controls") is not None
```

---

## Dependencies

**Blocked by:**
- Backend development (registry updates)
- Frontend development (test implementation)

**Blocks:**
- Production deployment
- User documentation updates

---

## References

- **Requirements:** `.opencode/plans/node-websocket-flag/requirements.md`
- **Technical design:** `.opencode/plans/node-websocket-flag/technical.md`
- **API spec:** `.opencode/plans/node-websocket-flag/api-spec.md`
- **Backend tasks:** `.opencode/plans/node-websocket-flag/backend-tasks.md`
- **Frontend tasks:** `.opencode/plans/node-websocket-flag/frontend-tasks.md`
