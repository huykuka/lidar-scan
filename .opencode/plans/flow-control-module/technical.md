# Flow Control Module - Technical Design

## Overview

The Flow Control Module introduces conditional logic to the DAG orchestrator via an `if` node that evaluates boolean expressions against payload metadata and external state, routing data to dual outputs (`true`/`false`).

**Core Principles:**
- Fail-safe design: expression errors route to `false` port
- Zero DAG blocking: expression evaluation on threadpool if needed
- Dual-output routing via existing downstream_map architecture
- External state is volatile and node-scoped
- Backwards-compatible with existing DAG engine

---

## Architecture

### 1. Backend Node Implementation

#### 1.1 Module Structure

The `flow_control` module uses a **sub-folder per operation type** to allow future operations (`switch/`, `while/`, etc.) to be added cleanly without polluting a flat namespace.

```
app/modules/flow_control/
├── __init__.py
└── if_condition/
    ├── __init__.py
    ├── registry.py          # NodeFactory registration + NodeDefinition schema
    ├── node.py              # IfConditionNode class
    └── expression_parser.py # Safe AST evaluator

tests/
├── modules/
│   └── flow_control/
│       ├── __init__.py
│       ├── test_if_node.py              # Unit tests for routing logic
│       └── test_expression_parser.py   # Parser edge cases
└── api/
    ├── test_flow_control_api.py         # REST endpoint tests
    └── test_if_node_dag.py              # Full DAG integration tests
```

**Extensibility:** When `switch` is added later, it lands in `app/modules/flow_control/switch/` with its own `registry.py` and `node.py`, and tests in `tests/modules/flow_control/test_switch_node.py`.

#### 1.2 IfConditionNode Class Design

**File:** `app/modules/flow_control/if_condition/node.py`

**Inherits:** `ModuleNode` (from `app/services/nodes/base_module.py`)

**Attributes:**
- `id: str` - Node identifier
- `name: str` - Display name
- `manager: NodeManager` - Reference to orchestrator
- `expression: str` - Boolean condition string
- `external_state: bool` - API-controlled boolean (default: `False`)
- `_ws_topic: Optional[str]` - WebSocket topic (invisible node: `None`)
- `last_evaluation: Optional[bool]` - Most recent condition result
- `last_error: Optional[str]` - Latest error message
- `_parser: ExpressionParser` - Sandboxed evaluator instance

**Key Methods:**

```python
async def on_input(self, payload: Dict[str, Any]) -> None:
    """
    1. Extract metadata fields from payload
    2. Evaluate expression with metadata + external_state
    3. Route to true/false downstream nodes
    4. Update last_evaluation and diagnostics
    """

def get_status(self, runtime_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Returns:
        - id, name, type="if_condition", category="flow_control"
        - expression: current expression string
        - external_state: current boolean value
        - last_evaluation: true/false/None
        - last_error: error message or None
    """
```

#### 1.3 Dual Output Port Strategy

**Problem:** Existing DAG architecture assumes single output per node.

**Solution:** Leverage port-labeled edges in `downstream_map`.

**Edge Schema Extension (already exists):**
```json
{
  "id": "edge_123",
  "source_id": "if_node_1",
  "source_port": "true",    // NEW: identifies output port
  "target_id": "downsample_2",
  "target_port": "in"
}
```

**Routing Logic:**
```python
# In IfConditionNode.on_input():
result = self._evaluate(payload)

# Build port-specific downstream targets
if result:
    targets = [edge for edge in self.manager.downstream_map.get(self.id, []) 
               if edge.get("source_port") == "true"]
else:
    targets = [edge for edge in self.manager.downstream_map.get(self.id, [])
               if edge.get("source_port") == "false"]

# Forward to port-specific targets
for target_id in targets:
    await self.manager.forward_data(target_id, payload)
```

**Impact on Existing Code:**
- `DataRouter._forward_to_downstream_nodes()` currently expects `downstream_map[source_id]` to be `List[str]`
- **Required Change:** Modify to support `List[Union[str, Dict]]` where Dict contains `{"target_id": str, "source_port": str}`
- OR: Store dual downstream maps: `downstream_map_true` and `downstream_map_false`

**Selected Strategy:** Store edges with port metadata in `downstream_map` as structured objects, not flat strings.

#### 1.4 Expression Parser Design

**File:** `app/modules/flow_control/if_condition/expression_parser.py`

**Class:** `ExpressionParser`

**Supported Syntax:**
- Comparison: `>`, `<`, `==`, `!=`, `>=`, `<=`
- Boolean: `AND`, `OR`, `NOT` (case-insensitive)
- Grouping: `(`, `)`
- Variables: metadata field names (e.g., `point_count`, `intensity_avg`)
- Special: `external_state` (injected at evaluation time)

**Safety Strategy:** 
Option 1: **Restricted `eval()` with custom `__builtins__`**
- Pros: Fast, simple, Pythonic syntax
- Cons: Security risks if improperly sandboxed

Option 2: **Custom AST Parser using `ast.parse()`**
- Pros: Fully controlled, no eval risks
- Cons: More code, edge cases

**Decision:** Use `ast.parse()` + whitelist visitor for production safety.

**Implementation:**
```python
import ast
from typing import Any, Dict

class SafeExpressionEvaluator(ast.NodeVisitor):
    """AST visitor that only allows safe comparison/boolean operations."""
    ALLOWED_OPS = {
        ast.Gt, ast.Lt, ast.Eq, ast.NotEq, ast.GtE, ast.LtE,  # Comparisons
        ast.And, ast.Or, ast.Not,  # Boolean
    }
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        
    def visit_Compare(self, node):
        # Evaluate left, ops, comparators
        ...
        
    def visit_BoolOp(self, node):
        # Evaluate AND/OR
        ...
        
    def visit_Name(self, node):
        # Lookup variable in context
        return self.context.get(node.id)

class ExpressionParser:
    def parse(self, expression: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate boolean expression with sandboxed context.
        
        Raises:
            SyntaxError: Invalid expression syntax
            ValueError: Unsupported operation
        """
        try:
            tree = ast.parse(expression, mode='eval')
            evaluator = SafeExpressionEvaluator(context)
            return evaluator.visit(tree.body)
        except Exception as e:
            raise ValueError(f"Expression evaluation failed: {e}")
```

**Fallback Behavior:** All exceptions route to `false` port.

---

### 2. REST API Extensions

**File:** `app/api/v1/nodes/flow_control.py` (NEW)

#### 2.1 Endpoints

##### POST `/api/v1/nodes/{node_id}/flow-control/set`

**Purpose:** Set external_state to `true` or `false`

**Request Body:**
```json
{
  "value": true
}
```

**Validation:**
- `node_id` must exist and be type `if_condition`
- `value` must be boolean (strict)

**Response:**
```json
{
  "node_id": "if_abc123",
  "state": true,
  "timestamp": 1234567890.123
}
```

**Implementation:**
```python
@router.post("/nodes/{node_id}/flow-control/set")
async def set_external_state(node_id: str, req: SetExternalStateRequest):
    node = get_node_manager().nodes.get(node_id)
    if not node or not isinstance(node, IfConditionNode):
        raise HTTPException(404, "Node not found or not a flow control node")
    
    node.external_state = req.value
    return {
        "node_id": node_id,
        "state": node.external_state,
        "timestamp": time.time()
    }
```

##### POST `/api/v1/nodes/{node_id}/flow-control/reset`

**Purpose:** Reset external_state to `false`

**Request Body:** None

**Response:**
```json
{
  "node_id": "if_abc123",
  "state": false,
  "timestamp": 1234567890.123
}
```

**Implementation:**
```python
@router.post("/nodes/{node_id}/flow-control/reset")
async def reset_external_state(node_id: str):
    node = get_node_manager().nodes.get(node_id)
    if not node or not isinstance(node, IfConditionNode):
        raise HTTPException(404, "Node not found or not a flow control node")
    
    node.external_state = False
    return {
        "node_id": node_id,
        "state": node.external_state,
        "timestamp": time.time()
    }
```

#### 2.2 OpenAPI Documentation

**Pydantic Models:**
```python
class SetExternalStateRequest(BaseModel):
    value: bool = Field(..., description="Boolean state value")

class ExternalStateResponse(BaseModel):
    node_id: str
    state: bool
    timestamp: float
```

**Swagger Annotations:**
```python
@router.post(
    "/nodes/{node_id}/flow-control/set",
    response_model=ExternalStateResponse,
    responses={
        404: {"description": "Node not found or wrong type"},
        400: {"description": "Invalid request body"}
    },
    summary="Set External State",
    description="Update external_state boolean for conditional routing"
)
```

---

### 3. Frontend Integration

#### 3.1 Node Schema Registration

**File:** `app/modules/flow_control/if_condition/registry.py`

```python
from app.services.nodes.schema import NodeDefinition, PropertySchema, PortSchema, node_schema_registry

node_schema_registry.register(NodeDefinition(
    type="if_condition",
    display_name="Conditional If",
    category="flow_control",
    description="Routes data based on boolean expression",
    icon="call_split",
    properties=[
        PropertySchema(
            name="expression",
            label="Condition Expression",
            type="string",
            default="true",
            required=True,
            help_text="Boolean expression: point_count > 1000 AND external_state == true"
        ),
        PropertySchema(
            name="throttle_ms",
            label="Throttle (ms)",
            type="number",
            default=0,
            min=0,
            step=10,
            help_text="Minimum time between evaluations (0 = no limit)"
        ),
    ],
    inputs=[
        PortSchema(id="in", label="Input", data_type="pointcloud")
    ],
    outputs=[
        PortSchema(id="true", label="True", data_type="pointcloud"),
        PortSchema(id="false", label="False", data_type="pointcloud")
    ]
))

@NodeFactory.register("if_condition")
def build_if_condition(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> IfConditionNode:
    config = node.get("config", {})
    expression = config.get("expression", "true")
    throttle_ms = float(config.get("throttle_ms", 0))
    
    return IfConditionNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name", "If Condition"),
        expression=expression,
        throttle_ms=throttle_ms
    )
```

#### 3.2 Angular UI Components

**New Files:**
- `web/src/app/features/settings/components/nodes/if-condition-editor/if-condition-editor.component.ts`
- `web/src/app/features/settings/components/nodes/if-condition-card/if-condition-card.component.ts`

**Editor Component (`if-condition-editor.component.ts`):**

```typescript
@Component({
  selector: 'app-if-condition-editor',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponents],
  template: `
    <form [formGroup]="form" (ngSubmit)="onSave()">
      <syn-textarea
        label="Condition Expression"
        formControlName="expression"
        rows="3"
        placeholder="point_count > 1000 AND intensity_avg < 200"
        helpText="Supports: >, <, ==, !=, >=, <=, AND, OR, NOT, ( )"
        [error]="validationError()"
      />
      
      <syn-input
        label="Throttle (ms)"
        type="number"
        formControlName="throttle_ms"
        min="0"
        step="10"
      />
      
      <syn-button type="submit" [disabled]="!form.valid">Save</syn-button>
      <syn-button variant="ghost" (click)="onCancel()">Cancel</syn-button>
    </form>
  `
})
export class IfConditionEditorComponent implements OnInit, NodeEditorComponent {
  saved = output<void>();
  cancelled = output<void>();
  
  private nodeStore = inject(NodeStoreService);
  form: FormGroup;
  validationError = signal<string | null>(null);
  
  ngOnInit() {
    const node = this.nodeStore.selectedNode();
    this.form = new FormGroup({
      expression: new FormControl(node?.config?.expression || 'true', Validators.required),
      throttle_ms: new FormControl(node?.config?.throttle_ms || 0)
    });
    
    // Real-time validation
    this.form.get('expression')?.valueChanges.subscribe(expr => {
      this.validateExpression(expr);
    });
  }
  
  validateExpression(expr: string) {
    // Basic client-side validation (regex check for allowed tokens)
    const allowedPattern = /^[a-z_0-9\s><=!&|()\.]+$/i;
    if (!allowedPattern.test(expr)) {
      this.validationError.set('Invalid characters in expression');
    } else {
      this.validationError.set(null);
    }
  }
  
  onSave() {
    const node = this.nodeStore.selectedNode();
    const updated = {
      ...node,
      config: {
        ...node.config,
        expression: this.form.value.expression,
        throttle_ms: this.form.value.throttle_ms
      }
    };
    this.nodeStore.updateNode(updated);
    this.saved.emit();
  }
  
  onCancel() {
    this.cancelled.emit();
  }
}
```

**Card Component (`if-condition-card.component.ts`):**

Displays expression summary and current evaluation status on the flow canvas node card.

```typescript
@Component({
  selector: 'app-if-condition-card',
  standalone: true,
  template: `
    <div class="if-card">
      <div class="expression-preview">{{ shortExpression() }}</div>
      <div class="status-row">
        @if (status()?.last_evaluation === true) {
          <span class="eval-true">TRUE</span>
        } @else if (status()?.last_evaluation === false) {
          <span class="eval-false">FALSE</span>
        } @else {
          <span class="eval-null">—</span>
        }
      </div>
    </div>
  `
})
export class IfConditionCardComponent implements NodeCardComponent {
  node = input.required<CanvasNode>();
  status = input<NodeStatus | null>(null);
  
  shortExpression = computed(() => {
    const expr = this.node().config?.expression || 'true';
    return expr.length > 30 ? expr.substring(0, 27) + '...' : expr;
  });
}
```

**Plugin Registration (`web/src/app/core/services/node-plugin-registry.service.ts`):**

```typescript
registry.register({
  type: 'if_condition',
  category: 'flow_control',
  displayName: 'Conditional If',
  description: 'Routes data based on boolean expression',
  icon: 'call_split',
  style: { color: '#9c27b0', backgroundColor: '#f3e5f5' },
  ports: {
    inputs: [{ id: 'in', label: 'Input', dataType: 'pointcloud' }],
    outputs: [
      { id: 'true', label: 'True', dataType: 'pointcloud' },
      { id: 'false', label: 'False', dataType: 'pointcloud' }
    ]
  },
  cardComponent: IfConditionCardComponent,
  editorComponent: IfConditionEditorComponent,
  createInstance: () => ({
    type: 'if_condition',
    name: 'If Condition',
    config: {
      expression: 'true',
      throttle_ms: 0
    }
  })
});
```

#### 3.3 Flow Canvas Port Rendering

**File:** `web/src/app/features/settings/components/flow-canvas/flow-canvas-node.component.ts`

**Required Changes:**
- Support rendering multiple output ports (currently assumes single output)
- Port positioning: vertically stack outputs on right edge
- Edge routing: track `source_port` and `target_port` in edge metadata

**Edge Data Structure:**
```typescript
interface CanvasEdge {
  id: string;
  source_id: string;
  source_port: string;  // NEW: "true" or "false"
  target_id: string;
  target_port: string;  // "in"
}
```

**Port Rendering Logic:**
```typescript
// In flow-canvas-node.component.ts
renderOutputPorts(node: CanvasNode): PortRenderData[] {
  const definition = this.pluginRegistry.get(node.type);
  const outputs = definition?.ports?.outputs || [{ id: 'out', label: 'Output' }];
  
  // Calculate vertical spacing
  const spacing = 40; // pixels between ports
  const startY = (this.nodeHeight - (outputs.length - 1) * spacing) / 2;
  
  return outputs.map((port, idx) => ({
    id: port.id,
    label: port.label,
    x: this.nodeWidth,  // Right edge
    y: startY + idx * spacing,
    type: 'output'
  }));
}
```

---

### 4. Data Flow & Lifecycle

#### 4.1 Request Flow: Expression Evaluation

```
1. Upstream node → forward_data(source_id, payload)
2. DataRouter → routes to IfConditionNode.on_input(payload)
3. IfConditionNode:
   a. Extract metadata: point_count, intensity_avg, timestamp, etc.
   b. Build context: { ...metadata, external_state: self.external_state }
   c. Evaluate: result = self._parser.parse(self.expression, context)
    d. On success:
       - Update self.last_evaluation = result
       - Route to port-specific downstream nodes
   e. On error:
      - Set self.last_error = str(error)
      - Route to 'false' port (fail-safe)
4. DataRouter.forward_data() → broadcasts to WebSocket (if visible)
5. DataRouter._forward_to_downstream_nodes() → next nodes in chain
```

#### 4.2 External State Control Flow

```
1. External app → POST /api/v1/nodes/{node_id}/flow-control/set {"value": true}
2. API handler → lookup IfConditionNode by node_id
3. Set node.external_state = true
4. Return response {"node_id": "...", "state": true, "timestamp": ...}
5. Next on_input() call uses updated external_state in expression context
```

**State Reset Triggers:**
- Manual: POST `/flow-control/reset`
- Automatic: DAG reload (node recreation)
- Automatic: Node deletion

#### 4.3 WebSocket Topic Handling

**Decision:** IfConditionNode should be **invisible** by default.

**Rationale:**
- The IF node doesn't transform data, only routes it
- Broadcasting intermediate routing decisions wastes bandwidth
- Downstream nodes already broadcast their results

**Implementation:**
```python
class IfConditionNode(ModuleNode):
    def __init__(self, ...):
        self._ws_topic = None  # Invisible node
```

**Override Option:** Add `visible` config property if debugging is needed.

---

### 5. Error Handling Strategy

#### 5.1 Expression Syntax Errors

**Scenario:** User enters `point_count > >< 1000`

**Behavior:**
1. Parser raises `SyntaxError`
2. Caught in `on_input()`, logged at ERROR level
3. Set `last_error = "Expression syntax error: unexpected token"`
4. Route to `false` port
5. Continue processing (no DAG crash)

#### 5.2 Missing Metadata Fields

**Scenario:** Expression references `intensity_avg` but payload only has `point_count`

**Behavior:**
1. Context builder sets `intensity_avg = None`
2. Comparison `None > 50` evaluates to `False`
3. Route to `false` port
4. Log WARNING: "Field 'intensity_avg' missing from payload"

#### 5.3 Type Mismatches

**Scenario:** Expression `"string_field" > 100`

**Behavior:**
1. Python raises `TypeError`
2. Caught in `on_input()`, logged at ERROR level
3. Set `last_error = "Type error: cannot compare str and int"`
4. Route to `false` port

#### 5.4 Division by Zero / Math Errors

**Out of scope** for MVP (no arithmetic operators supported).

---

### 6. Performance Considerations

#### 6.1 Expression Evaluation Cost

**Target:** <1ms per evaluation (NF1 requirement)

**Optimization:**
- Cache parsed AST tree (parse once, evaluate many times)
- Store `ast.Expression` object in `IfConditionNode._parsed_ast`
- Only re-parse when expression config changes

**Implementation:**
```python
class IfConditionNode(ModuleNode):
    def __init__(self, expression: str, ...):
        self.expression = expression
        self._parsed_ast = self._parser.compile(expression)  # Cache
        
    async def on_input(self, payload: Dict[str, Any]):
        context = self._build_context(payload)
        result = self._parser.evaluate(self._parsed_ast, context)  # Fast
```

#### 6.2 Threadpool Offloading

**Decision:** Expression evaluation runs on main thread (synchronous).

**Rationale:**
- AST evaluation is pure CPU (no I/O)
- Overhead of `asyncio.to_thread()` likely > evaluation time
- Keep simple unless profiling shows bottleneck

**Future Optimization:** If expressions become complex (e.g., regex support), offload to threadpool.

---

### 7. Testing Strategy

#### 7.1 Backend Unit Tests

**File:** `tests/modules/flow_control/test_if_node.py`

**Coverage:**
- Basic expression evaluation: `point_count > 1000` → true path
- Boolean operators: `A AND B`, `A OR B`, `NOT A`
- Parentheses grouping: `(A OR B) AND C`
- External state integration: `external_state == true`
- Missing fields: `missing_field > 100` → false path
- Syntax errors: `invalid ><` → false path, error logged
- Type mismatches: `"string" > 100` → false path
- Dual output routing: verify correct downstream targets

**File:** `tests/modules/flow_control/test_expression_parser.py`

**Coverage:**
- Whitelist enforcement: arithmetic operators rejected
- Case-insensitive operators: `and`, `AND`, `And`
- Nested parentheses: `((A OR B) AND C) OR D`
- Edge cases: empty string, whitespace, special characters

#### 7.2 Backend Integration Tests

**File:** `tests/api/test_flow_control_api.py`

**Coverage:**
- POST `/flow-control/set` with valid boolean
- POST `/flow-control/set` with invalid type (string) → 400 error
- POST `/flow-control/reset` → state becomes false
- Node not found → 404 error
- Wrong node type → 400 error

**File:** `tests/api/test_if_node_dag.py`

**Coverage:**
- Full DAG routing: sensor → if → true branch (downsample) + false branch (discard)
- External state toggle: `/set` changes routing behavior
- Error resilience: bad expression doesn't crash DAG

#### 7.3 Frontend Unit Tests

**Component Tests:**
- IfConditionEditorComponent: form validation, save/cancel events
- IfConditionCardComponent: expression truncation, evaluation status badge

**Integration Tests:**
- Node creation: drag IF node from palette → creates default config
- Node editing: open editor → change expression → save → API called
- Dual port rendering: IF node displays two output ports
- Edge creation: connect true port → downstream node

---

### 8. Dependencies & Import Order

**Critical:** Module discovery must happen before orchestrator starts.

**Current Discovery Mechanism:** `app/services/nodes/instance.py` scans `app/modules/*/registry.py`

**New Module Registration:**
```python
# In app/services/nodes/instance.py (existing discovery system)
# Automatically imports app/modules/flow_control/if_condition/registry.py at startup
# No manual changes needed if following existing pattern
```

**Verification:**
```bash
# On app startup, logs should show:
# "DEBUG: Registering node type: if_condition"
```

---

## API Contract Summary

See `api-spec.md` for full OpenAPI schemas.

**Key Endpoints:**
1. `POST /api/v1/nodes/{node_id}/flow-control/set` - Set external state
2. `POST /api/v1/nodes/{node_id}/flow-control/reset` - Reset to false
3. `GET /api/v1/nodes/definitions` - Returns IF node schema (existing)
4. `POST /api/v1/nodes` - Create IF node instance (existing)

**WebSocket:** No new WebSocket topics (node is invisible).

---

## Migration & Compatibility

**Breaking Changes:** None (additive feature)

**Backwards Compatibility:**
- Existing nodes unaffected
- Downstream map structure extended (supports both flat strings and port-aware dicts)
- Frontend edge rendering enhanced (supports multi-port nodes)

**Database Schema:** No changes (edges already have `source_port`/`target_port` in JSON config)

---

## Risk Analysis

### High Risk Areas

1. **Downstream Map Routing Change**
   - **Risk:** Modifying `DataRouter._forward_to_downstream_nodes()` could break existing single-output nodes
   - **Mitigation:** Add port-aware routing as opt-in (check if edge has `source_port` key)
   - **Impact Level:** MEDIUM (requires careful testing of all existing node types)

2. **Expression Parser Security**
   - **Risk:** `eval()` vulnerabilities if implemented incorrectly
   - **Mitigation:** Use AST parser exclusively, never `eval()`
   - **Impact Level:** CRITICAL (must be airtight)

3. **Frontend Edge Rendering**
   - **Risk:** Multi-port support could break existing single-port nodes
   - **Mitigation:** Graceful fallback (default to single port if schema missing)
   - **Impact Level:** LOW (visual only)

### Low Risk Areas

- Node registration (follows existing pattern)
- API endpoints (isolated, no shared state)
- WebSocket invisibility (opt-out feature)

---

## Success Criteria

- [ ] IfConditionNode routes to correct port based on expression evaluation
- [ ] External state API endpoints functional and validated
- [ ] Expression parser rejects unsafe operations (no eval exploits)
- [ ] <1ms evaluation latency (measured with 10k point payloads)
- [ ] Zero DAG crashes in 1000-frame stress test with syntax errors
- [ ] Angular UI renders dual output ports correctly
- [ ] All existing nodes continue working (backwards compatibility verified)

---

## Next Steps for Implementation

1. **@be-dev:** Implement `ExpressionParser` with AST whitelist
2. **@be-dev:** Create `IfConditionNode` class with dual routing logic
3. **@be-dev:** Modify `DataRouter` to support port-aware edges
4. **@be-dev:** Add REST API endpoints for external state control
5. **@fe-dev:** Build IF node editor and card components
6. **@fe-dev:** Extend flow canvas to render multiple output ports
7. **@qa:** Write unit tests for expression parser edge cases
8. **@qa:** Integration tests for full DAG routing scenarios
9. **@docs:** Update DAG architecture documentation with flow control examples
