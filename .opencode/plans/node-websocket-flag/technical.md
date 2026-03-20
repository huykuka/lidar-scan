# Node WebSocket Streaming Flag - Technical Design

## System Architecture

This feature modifies the **node metadata schema layer** to include a static capability flag. The flag is:
1. **Defined** in backend Python `NodeDefinition` schema
2. **Hardcoded** per node type in each module's `registry.py`
3. **Exposed** via REST API `/api/v1/nodes/definitions`
4. **Consumed** by Angular to conditionally render UI controls

**Data Flow:**
```
Backend registry.py
  ↓ (NodeDefinition with websocket_enabled)
Schema Registry (app/services/nodes/schema.py)
  ↓ (GET /nodes/definitions)
Angular NodePluginRegistry
  ↓ (NodeDefinition model)
flow-canvas-node.component
  ↓ (computed signal: isWebsocketEnabled)
Conditional template rendering (@if)
```

## Backend Architecture

### 1. Schema Layer (`app/services/nodes/schema.py`)

**Current state:** The `NodeDefinition` Pydantic model already has `websocket_enabled: bool = True` (line 36).

**Changes:** ✅ **None needed** - field already exists with correct default.

**Rationale:** The schema was future-proofed for this exact use case. Default value of `True` ensures backward compatibility with any dynamically loaded plugins or legacy configs.

---

### 2. Node Registries (Module-specific)

Each module's `registry.py` must explicitly set `websocket_enabled` in its `NodeDefinition`.

#### Modules to Update:

| Module | File | Node Type | websocket_enabled | Rationale |
|--------|------|-----------|-------------------|-----------|
| Sensor | `app/modules/lidar/registry.py` | `sensor` | `True` | Streams raw point cloud data via LIDR protocol |
| Fusion | `app/modules/fusion/registry.py` | `fusion` | `True` | Streams merged point cloud output |
| Operations | `app/modules/pipeline/registry.py` | `crop`, `downsample`, etc. | `True` | Transform/filter point clouds, stream results |
| Calibration | `app/modules/calibration/registry.py` | `calibration` | `False` | Only computes transformations, no continuous stream |
| Flow Control | `app/modules/flow_control/if_condition/registry.py` | `if_condition` | `False` | Conditional routing logic, no data output |

#### Implementation Pattern:

```python
# Before:
node_schema_registry.register(NodeDefinition(
    type="calibration",
    display_name="ICP Calibration",
    category="calibration",
    # ... properties
))

# After:
node_schema_registry.register(NodeDefinition(
    type="calibration",
    display_name="ICP Calibration",
    category="calibration",
    websocket_enabled=False,  # ← Add this line
    # ... properties
))
```

**Trade-offs:**
- ✅ **Pro:** Declarative, self-documenting in each registry
- ✅ **Pro:** No runtime logic needed, simple boolean check
- ⚠️ **Con:** Requires manual updates for new node types (mitigated by safe default of `True`)

---

### 3. API Layer (`app/api/v1/nodes/service.py`)

**Current state:** The `/nodes/definitions` endpoint at line 78-80 returns `node_schema_registry.get_all()`.

**Changes:** ✅ **None needed** - Pydantic automatically serializes the `websocket_enabled` field.

**Verification:** The field will appear in the JSON response:
```json
{
  "type": "calibration",
  "websocket_enabled": false,
  ...
}
```

---

## Frontend Architecture

### 1. Model Layer (`web/src/app/core/models/node.model.ts`)

**Current state:** Line 50 already defines `websocket_enabled: boolean` in the `NodeDefinition` interface.

**Changes:** ✅ **None needed** - model already matches backend schema.

---

### 2. Service Layer (`web/src/app/core/services/node-plugin-registry.service.ts`)

**Current state:** The `definitionToPlugin()` function (line 26-62) transforms backend definitions into `NodePlugin` objects.

**Changes:** ✅ **None needed** - the function directly spreads properties from backend `NodeDefinition`, so `websocket_enabled` is automatically included.

**Verification:** The field flows through to `NodePlugin` objects stored in the registry.

---

### 3. Component Layer (`flow-canvas-node.component.ts`)

**Current state:** Line 124-128 already computes `isWebsocketEnabled()` signal:
```typescript
protected isWebsocketEnabled = computed(() => {
  const def = this.nodeDefinition();
  return def ? def.websocket_enabled !== false : true;
});
```

**Changes:** ✅ **None needed** - reactive signal already exists and defaults to `true` for missing definitions.

**Logic breakdown:**
- If definition found → use `websocket_enabled` field (false is falsy, true is truthy)
- If definition missing → default to `true` (backward compat)
- The `!== false` pattern handles `undefined`/`null` gracefully

---

### 4. Template Layer (`flow-canvas-node.component.html`)

**Current state:** Lines 101-107 and 116-118 already use `@if (isWebsocketEnabled())` guards:

```html
@if (isNodeEnabled() && isWebsocketEnabled()) {
  <app-node-visibility-toggle ... />
}

@if (isNodeEnabled() && hasOutputPort() && isWebsocketEnabled()) {
  <app-node-recording-controls ... />
}
```

**Changes:** ✅ **None needed** - UI controls are already conditionally rendered.

**Behavior:**
- Visibility toggle: Hidden when `websocket_enabled === false`
- Recording controls: Hidden when `websocket_enabled === false` OR no output ports
- Enable/disable toggle: Always shown (independent of streaming capability)
- Settings icon: Always shown (independent of streaming capability)

---

## DAG Orchestrator Impact

**Question:** Does the orchestrator need changes to respect this flag?

**Answer:** ❌ **No changes needed.**

**Rationale:**
- The orchestrator (`app/services/nodes/orchestrator.py`) processes data based on DAG topology, not metadata flags
- Nodes without outputs naturally won't trigger `forward_data()` calls
- WebSocket topic registration happens only when a node explicitly calls `manager.register_ws_topic()`
- Calibration and flow control nodes don't register topics → no streaming behavior to disable
- The `websocket_enabled` flag is **purely a UI hint**, not an enforcement mechanism

**Recording System:** The recording subsystem intercepts at the DAG level via `manager.forward_data()`. If a node doesn't forward data, recording naturally has nothing to capture. The flag just hides the UI button.

---

## Testing Strategy

### Backend Tests

**File:** `tests/modules/test_node_definitions.py` (new)

```python
import pytest
from app.services.nodes.schema import node_schema_registry

def test_all_definitions_have_websocket_enabled_field():
    """Ensure all registered node types explicitly define websocket_enabled."""
    definitions = node_schema_registry.get_all()
    assert len(definitions) > 0, "No node definitions registered"
    
    for defn in definitions:
        assert hasattr(defn, 'websocket_enabled'), f"{defn.type} missing websocket_enabled"
        assert isinstance(defn.websocket_enabled, bool), f"{defn.type} websocket_enabled not bool"

def test_streaming_nodes_have_websocket_enabled_true():
    """Streaming node types must have websocket_enabled=True."""
    streaming_types = ["sensor", "fusion", "crop", "downsample", "outlier_removal"]
    
    for node_type in streaming_types:
        defn = node_schema_registry.get(node_type)
        assert defn is not None, f"Definition for {node_type} not found"
        assert defn.websocket_enabled is True, f"{node_type} should have websocket_enabled=True"

def test_non_streaming_nodes_have_websocket_enabled_false():
    """Non-streaming node types must have websocket_enabled=False."""
    non_streaming_types = ["calibration", "if_condition"]
    
    for node_type in non_streaming_types:
        defn = node_schema_registry.get(node_type)
        assert defn is not None, f"Definition for {node_type} not found"
        assert defn.websocket_enabled is False, f"{node_type} should have websocket_enabled=False"
```

---

### Frontend Tests

**File:** `flow-canvas-node.component.spec.ts` (update)

```typescript
it('should hide visibility toggle when websocket_enabled is false', () => {
  // Arrange: Mock node definition with websocket_enabled=false
  const mockDefinition: NodeDefinition = {
    type: 'calibration',
    websocket_enabled: false,
    // ... other fields
  };
  nodeStore.set('nodeDefinitions', [mockDefinition]);
  
  // Act: Create calibration node
  const node = { data: { type: 'calibration', enabled: true } };
  component.node.set(node);
  fixture.detectChanges();
  
  // Assert: Visibility toggle should not be rendered
  const visibilityToggle = fixture.debugElement.query(By.css('app-node-visibility-toggle'));
  expect(visibilityToggle).toBeNull();
});

it('should hide recording controls when websocket_enabled is false', () => {
  // Similar test for recording controls
  const mockDefinition: NodeDefinition = {
    type: 'if_condition',
    websocket_enabled: false,
    outputs: [{ id: 'out', label: 'Output' }],
  };
  nodeStore.set('nodeDefinitions', [mockDefinition]);
  
  const node = { data: { type: 'if_condition', enabled: true } };
  component.node.set(node);
  fixture.detectChanges();
  
  const recordingControls = fixture.debugElement.query(By.css('app-node-recording-controls'));
  expect(recordingControls).toBeNull();
});
```

---

### E2E Tests

**File:** `tests/e2e/test_node_ui_controls.py` (new)

```python
def test_calibration_node_hides_streaming_controls(browser):
    """Verify calibration node shows no visibility/recording controls."""
    # Navigate to settings page
    browser.goto("/settings")
    
    # Add calibration node from palette
    add_node_from_palette(browser, "ICP Calibration")
    
    # Wait for node to appear on canvas
    node = browser.wait_for_selector("[data-node-type='calibration']")
    
    # Assert: No visibility toggle button
    assert node.query_selector("app-node-visibility-toggle") is None
    
    # Assert: No recording controls
    assert node.query_selector("app-node-recording-controls") is None
    
    # Assert: Enable toggle still exists
    assert node.query_selector("[data-testid='enable-toggle']") is not None

def test_sensor_node_shows_streaming_controls(browser):
    """Verify sensor node shows visibility/recording controls."""
    browser.goto("/settings")
    add_node_from_palette(browser, "LiDAR Sensor")
    
    node = browser.wait_for_selector("[data-node-type='sensor']")
    
    # Assert: Visibility toggle exists
    assert node.query_selector("app-node-visibility-toggle") is not None
    
    # Assert: Recording controls exist
    assert node.query_selector("app-node-recording-controls") is not None
```

---

## Migration & Rollout

**Backward Compatibility:**
- ✅ Default value of `websocket_enabled: True` in Pydantic schema
- ✅ Frontend `isWebsocketEnabled()` defaults to `true` when definition missing
- ✅ Existing nodes continue working unchanged (they implicitly have `websocket_enabled=true`)

**Deployment Steps:**
1. **Backend first:** Update all registry files with explicit `websocket_enabled` values
2. **Test:** Run backend unit tests to verify schema correctness
3. **Deploy backend:** API now returns `websocket_enabled` in `/nodes/definitions`
4. **Frontend builds:** No code changes needed (already reactive to backend schema)
5. **E2E verification:** Smoke test calibration and sensor nodes in staging

**Rollback Plan:**
If issues arise, the system gracefully degrades:
- Remove `websocket_enabled=False` lines from registries → all nodes default to `True`
- Frontend continues working (safe default shows controls for all nodes)
- No database migrations required (this is schema-only, not persisted node data)

---

## Performance Impact

**Backend:**
- ✅ Zero runtime cost - flag is static metadata loaded once at startup
- ✅ No additional database queries

**Frontend:**
- ✅ Zero rendering cost - single boolean check in computed signal
- ✅ Slightly fewer DOM elements for non-streaming nodes (positive impact)

**WebSocket:**
- ✅ No changes to streaming protocol or connection lifecycle
- ✅ Recording subsystem unaffected (still intercepts at DAG level)

---

## Future Enhancements

**Phase 2 (Out of Scope):**
- Dynamic capability detection: Query node instance for `supports_streaming()` method
- Per-instance overrides: Allow users to disable streaming on specific sensor nodes
- Granular controls: Separate flags for `supports_visibility`, `supports_recording`, `supports_live_preview`

**Current Design Philosophy:**
Keep it simple - a single boolean flag at the type level is sufficient for 90% of use cases. More complex logic can be layered on later without breaking this foundation.
