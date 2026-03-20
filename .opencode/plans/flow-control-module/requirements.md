# Flow Control Module - Requirements

## Feature Overview

The **Flow Control Module** introduces conditional logic capabilities into the LiDAR DAG orchestration engine. The first implementation is an **'if' conditional node** that enables dynamic routing of point cloud data based on runtime conditions.

### What It Enables

- **Conditional Data Routing**: Route point clouds to different processing branches based on metadata conditions (e.g., point count, intensity averages, timestamps).
- **External Control Integration**: Allow external applications to gate or trigger data flows via REST API (e.g., start/stop recording, enable calibration mode).
- **Multi-Source Conditional Logic**: Combine internal DAG metadata (from upstream nodes) with external API-controlled state flags.
- **Fail-Safe Operation**: Gracefully handle invalid expressions or missing data without crashing the DAG.

### How It Fits in the DAG

The 'if' node acts as a **decision point** in the processing pipeline:

1. Receives point cloud payload from upstream nodes.
2. Evaluates a boolean expression against:
   - Payload metadata (point_count, intensity_avg, timestamp, etc.)
   - External state (controlled via REST API `/reset` and `/set` endpoints)
3. Routes data to one of two output ports:
   - **`true` port**: Forwards data when condition evaluates to truthy.
   - **`false` port**: Forwards data when condition evaluates to falsy or encounters errors.

**Example Workflows:**
- **Quality Gate**: `if (point_count > 1000 AND intensity_avg > 50) -> downstream processing | else -> discard`
- **External Trigger**: `if (external_state == true) -> record to file | else -> skip`
- **Time-Based Routing**: `if (timestamp - start_time > 60.0) -> analysis branch | else -> preview branch`

---

## User Stories

### US1: Data Quality Gate

**As a** point cloud processing engineer,  
**I want to** conditionally route data only when quality thresholds are met,  
**So that** downstream expensive operations (ICP, meshing) only process high-quality frames.

**Acceptance Criteria:**
- Configure an 'if' node with condition: `point_count > 5000 AND variance > 0.01`
- When condition is TRUE, data flows to expensive processing branch
- When condition is FALSE, data flows to lightweight preview/discard branch
- Node logs condition evaluation results for debugging

---

### US2: External Application Control

**As an** external automation script,  
**I want to** start and stop point cloud recording via REST API,  
**So that** I can trigger data capture events without modifying the DAG configuration.

**Acceptance Criteria:**
- POST `/api/v1/nodes/{node_id}/flow-control/set` with `{"value": true}` enables data flow
- POST `/api/v1/nodes/{node_id}/flow-control/reset` disables data flow (sets to false)
- 'if' node evaluates `external_state == true` in its condition expression
- State is volatile (resets on DAG restart)
- API returns current state after set/reset operations

---

### US3: Multi-Condition Logic with Metadata

**As a** sensor fusion developer,  
**I want to** combine multiple metadata fields in a single boolean expression,  
**So that** I can implement complex routing rules (e.g., "high-quality AND recent AND not during calibration").

**Acceptance Criteria:**
- Support boolean operators: `AND`, `OR`, `NOT`
- Support comparison operators: `>`, `<`, `==`, `!=`, `>=`, `<=`
- Support grouped conditions with parentheses: `(A AND B) OR C`
- Expressions like `point_count > 1000 AND intensity_avg < 200 AND external_state == true` evaluate correctly
- Invalid expressions (syntax errors) route to 'false' port and log error

---

## Acceptance Criteria

### Functional Requirements

#### F1: Dual Output Port Routing
- [x] Node has exactly two output ports: `true` and `false`
- [x] When condition evaluates to TRUE, data forwards ONLY to the `true` port
- [x] When condition evaluates to FALSE or error occurs, data forwards ONLY to the `false` port
- [x] Original payload metadata is preserved during forwarding
- [x] Example: Node evaluates `point_count > 1000`. Input has 1500 points → data appears on `true` port. Input has 500 points → data appears on `false` port.

#### F2: Boolean Expression Evaluation
- [x] Supports comparison operators: `>`, `<`, `==`, `!=`, `>=`, `<=`
- [x] Supports boolean operators: `AND`, `OR`, `NOT`
- [x] Supports parentheses for grouping: `(A OR B) AND C`
- [x] Expressions are case-insensitive for operators (`and`, `AND`, `And` all work)
- [x] Example valid expressions:
  - `point_count > 1000`
  - `intensity_avg >= 50 AND point_count < 10000`
  - `(variance > 0.01 OR point_count > 5000) AND external_state == true`
  - `NOT (timestamp < 12345678)`

#### F3: Metadata Field Access
- [x] Can access any field from the input payload metadata dictionary
- [x] Common fields include: `point_count`, `intensity_avg`, `timestamp`, `variance`, `node_id`, `sensor_name`
- [x] Missing fields are treated as `None` (trigger fail-safe routing to 'false')
- [x] Example: Expression `point_count > 1000` reads `payload.get("point_count")` value

#### F4: External State Control via API
- [x] Exposes POST endpoint: `/api/v1/nodes/{node_id}/flow-control/set`
- [x] Request body: `{"value": true}` or `{"value": false}` (boolean only)
- [x] Response: `{"node_id": "...", "state": true, "timestamp": 1234567890.123}`
- [x] Exposes POST endpoint: `/api/v1/nodes/{node_id}/flow-control/reset`
- [x] Reset sets internal `external_state` to `false`
- [x] Response: `{"node_id": "...", "state": false, "timestamp": 1234567890.123}`
- [x] State is accessible in expressions as `external_state` variable
- [x] State is **volatile**: resets to `false` on DAG restart or node reconfiguration

#### F5: Fail-Safe Error Handling
- [x] Invalid syntax in expression → routes to `false` port, logs error, continues processing
- [x] Missing metadata field → treats as `None`, logs warning, evaluates to falsy
- [x] Division by zero or math errors → routes to `false` port, logs error
- [x] Type mismatches (e.g., `"string" > 100`) → routes to `false` port, logs error
- [x] Node status includes `last_error` field showing most recent evaluation error
- [x] Example: Expression `invalid syntax here` logs `"Expression syntax error: ..."` and routes all data to `false` port until expression is fixed

#### F6: Configuration via Angular UI
- [ ] Node properties panel includes `expression` field (type: `string`, multiline text editor)
- [ ] Default expression: `true` (always forwards to `true` port)
- [ ] UI provides syntax hints/placeholder: `point_count > 1000 AND external_state == true`
- [ ] Real-time validation feedback in UI (syntax errors highlighted)
- [ ] Example configuration:
  ```json
  {
    "type": "if_condition",
    "config": {
      "expression": "point_count > 1000 AND intensity_avg < 200",
      "throttle_ms": 0
    }
  }
  ```

---

### Non-Functional Requirements

#### NF1: Performance
- [ ] Condition evaluation adds <1ms latency per frame (measured with 10k point clouds)
- [ ] Does not block the async event loop (expression parsing may run on threadpool if needed)
- [ ] Supports standard DAG throttling via `throttle_ms` config property

#### NF2: Logging & Observability
- [ ] Logs expression evaluation results at DEBUG level: `"Node if_1: Condition 'point_count > 1000' evaluated to TRUE"`
- [ ] Logs errors at ERROR level with full expression and error details
- [ ] Node status includes:
  - `expression`: current configured expression
  - `external_state`: current external state value
  - `last_evaluation`: `true`, `false`, or `error`
  - `last_error`: most recent error message (or `null`)
  - `true_count`, `false_count`: counters for each output route

#### NF3: DAG Schema Integration
- [ ] Node type: `if_condition`
- [ ] Category: `flow_control`
- [ ] Display name: `Conditional If`
- [ ] Icon: `call_split` (Material Icons branching symbol)
- [ ] Registered via `app/modules/flow_control/registry.py`
- [ ] Factory builder: `@NodeFactory.register("if_condition")`

#### NF4: API Documentation
- [ ] Swagger annotations for `/flow-control/set` and `/flow-control/reset` endpoints
- [ ] Request/response schemas documented in OpenAPI spec
- [ ] Example requests in Swagger UI

---

## Out of Scope

### Explicitly NOT Included in This Feature

- **Advanced Expression Functions**: No support for math functions (`sqrt`, `abs`, `sin`, etc.), string operations, or custom user-defined functions. Only comparison and boolean logic.
- **Multi-Output Routing**: Only two outputs (`true`/`false`). No support for switch-case or N-way routing.
- **Persistent State**: External state does NOT persist across DAG restarts. Always resets to `false`.
- **Stateful Counters/Accumulators**: Cannot maintain frame counters or running averages within the node. Each evaluation is independent.
- **Dynamic Expression Updates**: Expression cannot self-modify based on runtime conditions. Must be manually updated via UI or API.
- **Loop Detection**: No built-in protection against DAG cycles created by conditional routing. User must ensure acyclic graph structure.
- **Data Transformation**: The 'if' node routes data unchanged. It does NOT modify point cloud data or metadata (except adding `condition_result` metadata for debugging).
- **Other Flow Control Types**: `for`, `while`, `switch`, `try-catch` nodes are out of scope for this feature. Only `if` is included.

---

## Success Metrics

- [ ] 'if' node successfully routes data based on conditions in at least 2 integration tests
- [ ] API endpoints (`/set`, `/reset`) tested with automated API tests
- [ ] Expression evaluation performance <1ms measured in load tests
- [ ] Zero DAG crashes due to expression errors in 1000-frame stress test
- [ ] Documentation includes 3+ real-world example DAG configurations using 'if' node

---

## Dependencies & Prerequisites

- **Backend**: FastAPI, Open3D, existing DAG orchestrator (`app/services/nodes/`)
- **Frontend**: Angular flow-canvas node editor, Synergy UI components
- **Protocol**: WebSocket topic routing for dual outputs (reuses existing topic system)
- **Expression Parser**: Use Python `eval()` with restricted globals for simple boolean logic (safe sandbox required) OR implement custom parser

---

## Open Questions (Resolved)

1. **Q:** Should external state support multiple named values or single boolean?  
   **A:** Single boolean `external_state` only. Simple set/reset API.

2. **Q:** Persistent or volatile state?  
   **A:** Volatile. Resets to `false` on DAG restart.

3. **Q:** Routing strategy for true/false?  
   **A:** Dual output ports (`true` and `false`).

4. **Q:** Error handling behavior?  
   **A:** Fail-safe: route to `false` port, log error, continue processing.

5. **Q:** UI configuration approach?  
   **A:** Text expression editor with syntax validation.

---

## Next Steps for Architecture & Planning

1. **@architecture**: Design expression parser/evaluator (sandboxed `eval()` vs custom AST parser)
2. **@architecture**: Define REST API contract in `api-spec.md` (endpoint schemas, validation rules)
3. **@architecture**: Specify WebSocket topic handling for dual outputs (topic naming, cleanup)
4. **@architecture**: Document state management lifecycle (when external_state resets, how errors propagate)
5. **@be-dev** & **@fe-dev**: Review `technical.md` for implementation tasks breakdown
6. **@qa**: Define test scenarios in `qa-tasks.md` (expression edge cases, API behavior, DAG routing)

---

**Document Status:** ✅ READY FOR ARCHITECTURE REVIEW  
**Next Phase:** Architecture to produce `technical.md` and `api-spec.md`
