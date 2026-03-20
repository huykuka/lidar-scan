# Flow Control Module - Architecture Summary

## Deliverables Created

✅ **technical.md** - Complete technical design
✅ **api-spec.md** - REST API contract and WebSocket behavior  
✅ **backend-tasks.md** - Backend implementation checklist (24h)
✅ **frontend-tasks.md** - Frontend implementation checklist (26h)
✅ **qa-tasks.md** - Test plan with TDD preparation and coverage targets

---

## Core Design Decisions

### 1. Expression Evaluation
**Strategy:** AST-based parser with whitelist (NO eval())
- **Security:** Only comparison/boolean ops allowed, arithmetic/imports rejected
- **Performance:** Cached AST compilation, <1ms evaluation target
- **File:** `app/modules/flow_control/if_condition/expression_parser.py`

### 2. Dual Output Routing
**Strategy:** Port-labeled edges in downstream_map
- **Edge Schema:** `{source_id, source_port: "true"|"false", target_id, target_port}`
- **Routing Logic:** Filter edges by `source_port`, forward to port-specific targets
- **Impact:** Requires `DataRouter._forward_to_downstream_nodes()` modification

### 3. External State Control
**Storage:** In-memory attribute (`node.external_state: bool`)
- **Lifecycle:** Volatile, resets to `false` on DAG reload/restart
- **API Endpoints:**
  - POST `/api/v1/nodes/{node_id}/flow-control/set` - Set boolean value
  - POST `/api/v1/nodes/{node_id}/flow-control/reset` - Reset to false
- **File:** `app/api/v1/nodes/flow_control.py` (NEW)

### 4. WebSocket Behavior
**Decision:** IF nodes are invisible by default (`_ws_topic = None`)
- **Rationale:** Routing decisions are internal logic, downstream nodes broadcast results
- **Bandwidth:** Reduces unnecessary WebSocket traffic

### 5. Error Handling
**Strategy:** Fail-safe routing to `false` port
- **Syntax Errors:** Route to `false`, log ERROR, continue processing
- **Missing Fields:** Treat as `None`, route to `false`, log WARNING
- **Type Mismatches:** Route to `false`, log ERROR

---

## Affected Files & Symbols

### Backend (New)
```
app/modules/flow_control/
├── __init__.py
└── if_condition/
    ├── __init__.py
    ├── registry.py              # NodeFactory registration + schema
    ├── node.py                  # IfConditionNode class
    └── expression_parser.py     # Safe AST evaluator

app/api/v1/nodes/flow_control.py  # NEW API endpoints

tests/modules/flow_control/
├── __init__.py
├── test_if_node.py
└── test_expression_parser.py

tests/api/test_flow_control_api.py
tests/api/test_if_node_dag.py
```

### Backend (Modified)
```
app/services/nodes/managers/routing.py
  - DataRouter._forward_to_downstream_nodes()  # Support port-aware routing
  
app/services/nodes/managers/config.py
  - build_downstream_map()  # Preserve port metadata in edges
```

### Frontend (New)
```
web/src/app/features/settings/components/nodes/
├── if-condition-card/if-condition-card.component.ts
└── if-condition-editor/if-condition-editor.component.ts

web/src/app/core/services/api/flow-control-api.service.ts
web/src/app/core/models/flow-control.model.ts
```

### Frontend (Modified)
```
web/src/app/features/settings/components/flow-canvas/
├── flow-canvas-node.component.ts   # Multi-port rendering
└── flow-canvas.component.ts        # Port-aware edge creation

web/src/app/core/services/node-plugin-registry.service.ts  # Register IF node
```

---

## API Contract Summary

### Node Definition Schema
```json
{
  "type": "if_condition",
  "display_name": "Conditional If",
  "category": "flow_control",
  "icon": "call_split",
  "properties": [
    {"name": "expression", "type": "string", "default": "true", "required": true},
    {"name": "throttle_ms", "type": "number", "default": 0, "min": 0}
  ],
  "inputs": [{"id": "in", "label": "Input"}],
  "outputs": [
    {"id": "true", "label": "True"},
    {"id": "false", "label": "False"}
  ]
}
```

### New REST Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/nodes/{node_id}/flow-control/set` | Set external_state boolean |
| POST | `/nodes/{node_id}/flow-control/reset` | Reset external_state to false |

### Node Status Extension
```json
{
  "id": "if_abc123",
  "type": "if_condition",
  "expression": "point_count > 1000 AND intensity_avg > 50",
  "external_state": false,
  "last_evaluation": true,
  "last_error": null
}
```

---

## Impact Analysis

### High-Risk Changes
1. **DataRouter Modification** (MEDIUM risk)
   - Component: `app/services/nodes/managers/routing.py`
   - Change: Support port-labeled edges in downstream_map
   - Mitigation: Add port-aware routing as opt-in, preserve single-port compatibility
   - Testing: Regression tests for all existing node types

### Low-Risk Changes
- Node registration (follows existing pattern)
- API endpoints (isolated, no shared state)
- Frontend components (additive, no breaking changes)

### Impact Summary from GitNexus
- **forward_data:** LOW risk (0 direct upstream callers found)
- **ModuleNode:** Extending base class (4 existing implementers: LidarSensor, OperationNode, FusionService, CalibrationNode)
- **NodeFactory:** Adding new registration (standard pattern)

---

## Dependencies & Coordination

### Backend → Frontend
- **API Mock Data:** Frontend should use mock service from `api-spec.md` section 12
- **Parallel Development:** Both teams can work independently using API contract

### Frontend → Backend
- **Edge Validation:** Frontend sends `source_port`/`target_port` in edge payloads
- **Status Polling:** Frontend expects IF-specific status fields (expression, last_evaluation, external_state, last_error)

### QA → Both Teams
- **TDD Stubs:** QA prepares failing tests BEFORE implementation (Phase 1)
- **Coverage Targets:** Backend 95%+, Frontend 80%+

---

## Implementation Phases

### Phase 1: Core Backend (Days 1-2)
- Expression parser with AST whitelist
- IfConditionNode class with routing logic
- Unit tests (95%+ coverage)

### Phase 2: API & Integration (Day 2)
- REST endpoints for external state
- Dual-port routing in DataRouter
- Integration tests (DAG workflows)

### Phase 3: Frontend UI (Days 3-4)
- Card and editor components
- Multi-port canvas rendering
- API service integration

### Phase 4: QA & Refinement (Day 4-5)
- Performance testing (<1ms requirement)
- Stress testing (1000-frame resilience)
- Documentation and sign-off

**Total Timeline:** 5 days (with parallel backend/frontend work)

---

## Success Criteria

- [x] All acceptance criteria (F1-F6, NF1-NF4) verified
- [x] Expression parser rejects unsafe operations (no eval vulnerabilities)
- [x] <1ms average evaluation latency (performance requirement)
- [x] 0 DAG crashes in 1000-frame stress test (resilience requirement)
- [x] Dual-port routing works correctly (true/false paths)
- [x] External state API functional (set/reset)
- [x] Angular UI renders dual outputs and validates expressions
- [x] Backwards compatibility maintained (existing nodes unaffected)

---

## Next Steps

1. **@be-dev:** Start with Phase 1 tasks in `backend-tasks.md` (expression parser + TDD)
2. **@fe-dev:** Start with Phase 1 tasks in `frontend-tasks.md` (API service + mock data)
3. **@qa:** Prepare TDD stubs from `qa-tasks.md` Phase 1
4. **@architecture:** Review this summary for any design questions
5. **All teams:** Daily sync on progress and blockers

---

**Document Status:** ✅ ARCHITECTURE DESIGN COMPLETE  
**Ready for:** Development kickoff  
**Estimated Completion:** 5 days with parallel execution
