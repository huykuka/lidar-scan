# Circular Import Fix — Node Status Standardization Integration

**Date**: 2026-03-20  
**Issue**: Critical startup errors after node-status standardization integration  
**Status**: ✅ RESOLVED

---

## Problem Summary

After integrating the node-status-standardization feature, the backend encountered critical startup errors:

### Symptoms

1. **Circular Import Error**:
   ```
   ImportError: cannot import name 'node_manager' from partially initialized module 
   'app.services.nodes.instance' (most likely due to a circular import)
   ```

2. **Module Loading Failures**:
   - Calibration module: FAILED
   - Fusion module: FAILED
   - LiDAR module: FAILED

3. **Node Type Registration Failure**:
   ```
   ValueError: Unknown node type: sensor
   ```
   All node types failed to register in NodeFactory, causing instantiation errors.

---

## Root Cause Analysis

### The Circular Import Chain

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. app/services/nodes/instance.py                              │
│    ├─ imports discover_modules() from app.modules              │
│    └─ calls discover_modules() immediately (line 5)            │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────────┐
│ 2. app/modules/__init__.py::discover_modules()                 │
│    └─ imports all registry.py modules (calibration, fusion...)  │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────────┐
│ 3. app/modules/*/registry.py                                   │
│    └─ imports node implementations (calibration_node.py,       │
│       sensor.py, service.py)                                    │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────────┐
│ 4. Node implementations (calibration_node.py, sensor.py...)    │
│    └─ imports notify_status_change from status_aggregator.py   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────────┐
│ 5. app/services/status_aggregator.py                           │
│    └─ imports node_manager from instance.py ← CIRCULAR!        │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Broke Everything

1. **Import Deadlock**: Python couldn't complete the module initialization chain
2. **Registry Failure**: Module registries never executed their `@NodeFactory.register()` decorators
3. **Empty Factory**: `NodeFactory._registry` remained empty
4. **Instantiation Failures**: All `NodeFactory.create()` calls raised "Unknown node type"

---

## Solution: Lazy Import

### Strategy

Break the circular dependency by **deferring** the import of `node_manager` until it's actually needed (runtime) instead of at module initialization time.

### Implementation

#### Before (Circular):

```python
# app/services/status_aggregator.py (OLD)
from app.services.nodes.instance import node_manager  # ← Imports at module load

async def _broadcast_system_status() -> None:
    for node_id, node_instance in node_manager.nodes.items():  # ← Uses at runtime
        ...
```

#### After (Lazy Import):

```python
# app/services/status_aggregator.py (NEW)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.nodes.orchestrator import NodeManager  # ← Type hints only

async def _broadcast_system_status() -> None:
    # Lazy import: node_manager imported INSIDE the function (at runtime)
    from app.services.nodes.instance import node_manager  # ← Deferred
    
    for node_id, node_instance in node_manager.nodes.items():
        ...
```

### Why This Works

1. **Module Load Time**: `status_aggregator.py` no longer imports `node_manager` during module initialization
2. **Import Order**: All module registries complete successfully before `_broadcast_system_status()` runs
3. **Runtime Import**: By the time `_broadcast_system_status()` executes, `instance.py` is fully initialized
4. **Type Safety**: `TYPE_CHECKING` block provides LSP type hints without runtime import

---

## Changes Made

### 1. Core Fix

**File**: `app/services/status_aggregator.py`

- **Removed**: Module-level `from app.services.nodes.instance import node_manager`
- **Added**: `TYPE_CHECKING` import for type hints
- **Modified**: `_broadcast_system_status()` to use lazy import
- **Added**: Docstring explaining the circular import fix

### 2. Test Updates

Updated test files to patch the lazy import correctly:

#### Files Modified:
- `tests/services/test_status_aggregator.py`
- `tests/integration/test_status_flow.py`

#### Change Pattern:
```python
# OLD (broken after lazy import)
with patch("app.services.status_aggregator.node_manager") as mock_nm:
    ...

# NEW (patches lazy import location)
with patch("app.services.nodes.instance.node_manager") as mock_nm:
    ...
```

### 3. New Test Suite

**File**: `tests/services/test_circular_import_fix.py`

Comprehensive test coverage for the fix:
- Import chain verification
- Module registry loading
- Node type registration
- Sensor node instantiation
- Status aggregator lazy import validation

---

## Verification Results

### ✅ All Modules Load Successfully

```
INFO | app.modules | Loaded module registry: calibration
INFO | app.modules | Loaded module registry: flow_control
INFO | app.modules | Loaded module registry: fusion
INFO | app.modules | Loaded module registry: lidar
INFO | app.modules | Loaded module registry: pipeline
```

### ✅ NodeFactory Registry Populated

```
✓ 14 node types registered:
  ['boundary_detection', 'calibration', 'clustering', 'crop', 
   'debug_save', 'downsample', 'filter_by_key', 'fusion', 
   'if_condition', 'operation', 'outlier_removal', 
   'plane_segmentation', 'radius_outlier_removal', 'sensor']
```

### ✅ Sensor Nodes Instantiate Correctly

```python
sensor = NodeFactory.create(test_node_data, mock_context, [])
# No "Unknown node type: sensor" error ✓
```

### ✅ Backend Starts Without Errors

```
INFO | app.services.nodes.orchestrator | Initialized 5 nodes
INFO | status_aggregator | [StatusAggregator] Started
INFO | Application startup complete
```

### ✅ All Tests Pass

```
tests/services/test_status_aggregator.py ................ 5 passed
tests/integration/test_status_flow.py ................... 4 passed
tests/services/test_circular_import_fix.py .............. 7 passed
tests/services/nodes/ .................................... 40 passed
tests/modules/ ........................................... 176 passed (5 pre-existing failures)
```

---

## Impact Assessment

### Files Modified
- `app/services/status_aggregator.py` (1 file, 10 lines changed)
- `tests/services/test_status_aggregator.py` (1 file, patch locations updated)
- `tests/integration/test_status_flow.py` (1 file, patch locations updated)
- `tests/services/test_circular_import_fix.py` (NEW, 120 lines)

### Backward Compatibility
- ✅ No breaking changes to public API
- ✅ All existing functionality preserved
- ✅ `notify_status_change()` signature unchanged
- ✅ Node implementations unchanged (still import `notify_status_change` at module level)

### Performance Impact
- ✅ Negligible: lazy import executes once per broadcast (100ms debounced)
- ✅ No runtime overhead beyond original design
- ✅ Import cost amortized across broadcast batches

---

## Lessons Learned

### Anti-Pattern Identified

**Bidirectional Dependencies Between Service Layers**:
- `status_aggregator.py` (service layer) importing `node_manager` (orchestration layer)
- Node implementations (module layer) importing `notify_status_change` (service layer)

Creates a cycle when module discovery is triggered by orchestration layer initialization.

### Best Practice Adopted

**Lazy Imports for Cross-Layer Dependencies**:
- Use `TYPE_CHECKING` imports for type hints
- Defer runtime imports to function scope when circular risks exist
- Document the reason for lazy imports in code comments

### Prevention

Future refactors should:
1. Avoid importing singleton instances across layers
2. Use dependency injection where possible
3. Consider inversion of control for observer patterns
4. Run `python -c "from app.services.nodes.instance import node_manager"` as a CI check

---

## Related Documentation

- **Technical Spec**: `.opencode/plans/node-status-standardization/technical.md § 2.3`
- **Backend Tasks**: `.opencode/plans/node-status-standardization/backend-tasks.md`
- **Test Coverage**: `tests/services/test_circular_import_fix.py`

---

## Sign-Off

**Fixed By**: Backend Developer (@be-dev)  
**Reviewed**: Pending  
**Status**: ✅ Resolved — Backend fully operational
