# Backend Development Tasks - Node WebSocket Streaming Flag

## Summary
Update backend node registries to explicitly set `websocket_enabled` flag for each node type. The schema already exists; this task is purely about populating the field in each module's registry.

---

## Task Breakdown

### 1. Update Sensor Node Registry
**File:** `app/modules/lidar/registry.py`

- [x] Add `websocket_enabled=True` to the `NodeDefinition` registration (line ~30)
- [x] Verify sensor type produces streamable output (already does via LIDR protocol)
- [x] Run backend tests to validate schema correctness

**Expected change:**
```python
node_schema_registry.register(NodeDefinition(
    type="sensor",
    display_name="LiDAR Sensor",
    category="sensor",
    websocket_enabled=True,  # ← Add this line
    # ... rest of definition
))
```

---

### 2. Update Fusion Node Registry
**File:** `app/modules/fusion/registry.py`

- [x] Add `websocket_enabled=True` to the `NodeDefinition` registration (line ~17)
- [x] Verify fusion node streams merged point clouds (already does)
- [x] Run backend tests to validate schema correctness

**Expected change:**
```python
node_schema_registry.register(NodeDefinition(
    type="fusion",
    display_name="Multi-Sensor Fusion",
    category="fusion",
    websocket_enabled=True,  # ← Add this line
    # ... rest of definition
))
```

---

### 3. Update Pipeline Operation Nodes Registry
**File:** `app/modules/pipeline/registry.py`

- [x] Add `websocket_enabled=True` to ALL operation node definitions:
  - `crop` (line ~18)
  - `downsample` (line ~39)
  - `outlier_removal` (line ~56)
  - `radius_outlier_removal` (line ~75)
  - `plane_segmentation` (line ~94)
  - `clustering` (line ~115)
  - `boundary_detection` (line ~134)
  - `filter_by_key` (line ~155)
  - `debug_save` (line ~183)
- [x] Verify all operations forward transformed point clouds (they do)
- [x] Run backend tests to validate schema correctness

**Expected change pattern (repeat for each operation):**
```python
node_schema_registry.register(NodeDefinition(
    type="crop",  # or downsample, outlier_removal, etc.
    display_name="Crop Filter",
    category="operation",
    websocket_enabled=True,  # ← Add this line to EACH definition
    # ... rest of definition
))
```

---

### 4. Update Calibration Node Registry
**File:** `app/modules/calibration/registry.py`

- [x] Add `websocket_enabled=False` to the `NodeDefinition` registration (line ~17)
- [x] Verify calibration node only computes transformations (no continuous streaming)
- [x] Run backend tests to validate schema correctness

**Expected change:**
```python
node_schema_registry.register(NodeDefinition(
    type="calibration",
    display_name="ICP Calibration",
    category="calibration",
    websocket_enabled=False,  # ← Add this line (False!)
    # ... rest of definition
))
```

**Rationale:** Calibration nodes compute transformation matrices but don't produce continuous point cloud streams.

---

### 5. Update Flow Control Node Registry
**File:** `app/modules/flow_control/if_condition/registry.py`

- [x] Locate the `NodeDefinition` registration for `if_condition` type
- [x] Add `websocket_enabled=False` to the definition
- [x] Verify conditional routing doesn't require streaming UI controls
- [x] Run backend tests to validate schema correctness

**Expected change:**
```python
node_schema_registry.register(NodeDefinition(
    type="if_condition",
    display_name="If Condition",
    category="flow_control",
    websocket_enabled=False,  # ← Add this line (False!)
    # ... rest of definition
))
```

**Rationale:** Flow control nodes perform conditional routing logic but don't stream data continuously.

---

### 6. Enhance Node Registration Logic to Respect websocket_enabled Flag
**Files:** `app/services/nodes/managers/config.py`

- [x] Update `_register_node_websocket_topic()` method to check `websocket_enabled` from node definition
- [x] Non-streaming nodes (websocket_enabled=False) should NEVER register WebSocket topics regardless of visibility
- [x] Streaming nodes (websocket_enabled=True) register topics only when visible=True (existing behavior)
- [x] Add debug logging to distinguish between invisible nodes and non-streaming nodes

**Implementation:**
```python
def _register_node_websocket_topic(self, node: Dict[str, Any], node_instance: Any):
    from ..schema import node_schema_registry
    
    # Check if node type supports WebSocket streaming
    node_type = node.get("type")
    node_definition = node_schema_registry.get(node_type)
    websocket_enabled = node_definition.websocket_enabled if node_definition else True
    
    visible = node.get("visible", True)
    
    # Register topic only if BOTH websocket_enabled AND visible are True
    if websocket_enabled and visible:
        manager.register_topic(topic)
        node_instance._ws_topic = topic
    else:
        node_instance._ws_topic = None
```

---

### 7. Write Backend Unit Tests
**File:** `tests/modules/test_node_definitions.py` (new file)

- [x] Create new test file with schema validation tests
- [x] Test 1: Verify all registered node definitions have `websocket_enabled` field
- [x] Test 2: Verify streaming node types have `websocket_enabled=True`
- [x] Test 3: Verify non-streaming node types have `websocket_enabled=False`
- [x] Test 4: Verify `/nodes/definitions` API endpoint includes the field

**Test implementation:**
```python
import pytest
from app.services.nodes.schema import node_schema_registry

def test_all_definitions_have_websocket_enabled_field():
    """Ensure all registered node types explicitly define websocket_enabled."""
    definitions = node_schema_registry.get_all()
    assert len(definitions) > 0, "No node definitions registered"
    
    for defn in definitions:
        assert hasattr(defn, 'websocket_enabled'), \
            f"{defn.type} missing websocket_enabled field"
        assert isinstance(defn.websocket_enabled, bool), \
            f"{defn.type} websocket_enabled is not boolean"

def test_streaming_nodes_have_websocket_enabled_true():
    """Streaming node types must have websocket_enabled=True."""
    streaming_types = [
        "sensor", "fusion", 
        "crop", "downsample", "outlier_removal", "radius_outlier_removal",
        "plane_segmentation", "clustering", "boundary_detection", 
        "filter_by_key", "debug_save"
    ]
    
    for node_type in streaming_types:
        defn = node_schema_registry.get(node_type)
        assert defn is not None, f"Definition for {node_type} not found"
        assert defn.websocket_enabled is True, \
            f"{node_type} should have websocket_enabled=True"

def test_non_streaming_nodes_have_websocket_enabled_false():
    """Non-streaming node types must have websocket_enabled=False."""
    non_streaming_types = ["calibration", "if_condition"]
    
    for node_type in non_streaming_types:
        defn = node_schema_registry.get(node_type)
        assert defn is not None, f"Definition for {node_type} not found"
        assert defn.websocket_enabled is False, \
            f"{node_type} should have websocket_enabled=False"
```

---

### 8. Write Integration Tests for WebSocket Registration Logic
**File:** `tests/services/nodes/test_websocket_registration.py` (new file)

- [x] Create comprehensive test suite validating WebSocket registration logic
- [x] Test 1: Streaming node with visible=True SHOULD register WebSocket topic
- [x] Test 2: Streaming node with visible=False should NOT register WebSocket topic
- [x] Test 3: Non-streaming node with visible=True should NOT register WebSocket topic (websocket_enabled=False overrides visible=True)
- [x] Test 4: Non-streaming node with visible=False should NOT register WebSocket topic
- [x] Test 5: Node definition without websocket_enabled defaults to True (backward compatibility)
- [x] Test 6-10: Integration tests validating real node definitions have correct websocket_enabled values

**Test Coverage:**
- All 10 tests passing
- Validates that non-streaming nodes (calibration, if_condition) never register WebSocket topics
- Validates that streaming nodes (sensor, fusion, pipeline operations) only register when visible
- Ensures backward compatibility with legacy node definitions

---

### 9. Verify API Response Format
**Manual Testing:**

- [x] Start backend server: `python main.py`
- [x] Make request: `curl http://localhost:8000/api/v1/nodes/definitions`
- [x] Verify response includes `"websocket_enabled": true/false` for each node type
- [x] Spot-check: `sensor` → `true`, `calibration` → `false`

**Expected JSON snippet:**
```json
[
  {
    "type": "sensor",
    "websocket_enabled": true,
    ...
  },
  {
    "type": "calibration",
    "websocket_enabled": false,
    ...
  }
]
```

---

## Testing Commands

```bash
# Run all backend tests
cd /home/thaiqu/Projects/personnal/lidar-standalone
pytest tests/modules/test_node_definitions.py -v

# Run full test suite to ensure no regressions
pytest tests/ -v

# Check test coverage
pytest tests/modules/test_node_definitions.py --cov=app/modules --cov-report=term-missing
```

---

## Dependencies

**Blocked by:** None (schema already exists)

**Blocks:** 
- Frontend development (needs API to return the field)
- QA testing (needs backend deployed with updated registries)

---

## References

- **Schema file:** `app/services/nodes/schema.py` (line 36 - `websocket_enabled` field already defined)
- **API endpoint:** `app/api/v1/nodes/handler.py` (line 28-35 - `/nodes/definitions` route)
- **Technical design:** `.opencode/plans/node-websocket-flag/technical.md`
- **API spec:** `.opencode/plans/node-websocket-flag/api-spec.md`

---

## Estimated Effort

- **Registry updates:** ~30 minutes (simple boolean additions)
- **Unit tests:** ~45 minutes (write + validate)
- **Manual verification:** ~15 minutes (API testing)
- **Total:** ~1.5 hours
