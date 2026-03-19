# Flow Control Module - API Specification

## Overview

This document defines the complete API contract for the Flow Control Module, including node configuration schemas, REST endpoints for external state control, and WebSocket behavior.

---

## 1. Node Definition Schema

### GET `/api/v1/nodes/definitions`

Returns all available node types, including the new `if_condition` node.

**Response Schema (Partial - IF Node Only):**

```json
{
  "type": "if_condition",
  "display_name": "Conditional If",
  "category": "flow_control",
  "description": "Routes data based on boolean expression",
  "icon": "call_split",
  "properties": [
    {
      "name": "expression",
      "label": "Condition Expression",
      "type": "string",
      "default": "true",
      "required": true,
      "help_text": "Boolean expression: point_count > 1000 AND external_state == true",
      "min": null,
      "max": null,
      "step": null,
      "hidden": false,
      "depends_on": null,
      "options": null
    },
    {
      "name": "throttle_ms",
      "label": "Throttle (ms)",
      "type": "number",
      "default": 0,
      "required": false,
      "help_text": "Minimum time between evaluations (0 = no limit)",
      "min": 0,
      "max": null,
      "step": 10,
      "hidden": false,
      "depends_on": null,
      "options": null
    }
  ],
  "inputs": [
    {
      "id": "in",
      "label": "Input",
      "data_type": "pointcloud",
      "multiple": false
    }
  ],
  "outputs": [
    {
      "id": "true",
      "label": "True",
      "data_type": "pointcloud",
      "multiple": false
    },
    {
      "id": "false",
      "label": "False",
      "data_type": "pointcloud",
      "multiple": false
    }
  ]
}
```

**Validation Rules:**
- `expression` must be non-empty string
- `expression` must contain only allowed tokens: `a-zA-Z0-9_`, comparison operators (`>`, `<`, `==`, `!=`, `>=`, `<=`), boolean operators (`AND`, `OR`, `NOT`), parentheses, whitespace
- `throttle_ms` must be >= 0

---

## 2. Node Instance Management

### POST `/api/v1/nodes`

Create or update an IF condition node instance.

**Request Body:**

```json
{
  "id": "if_abc123",
  "type": "if_condition",
  "name": "Quality Gate",
  "enabled": true,
  "config": {
    "expression": "point_count > 1000 AND intensity_avg > 50",
    "throttle_ms": 0
  },
  "ui_metadata": {
    "position": { "x": 100, "y": 200 }
  }
}
```

**Response:**

```json
{
  "status": "success",
  "message": "Node created/updated",
  "node_id": "if_abc123"
}
```

**Error Responses:**

- `400 Bad Request`: Invalid expression syntax or missing required fields
- `409 Conflict`: Node ID already exists (on create)

---

## 3. Node Status API

### GET `/api/v1/nodes/status/all`

Returns runtime status for all nodes, including IF node-specific metrics.

**Response (Partial - IF Node Example):**

```json
{
  "nodes": [
    {
      "id": "if_abc123",
      "name": "Quality Gate",
      "type": "if_condition",
      "category": "flow_control",
      "running": true,
      "expression": "point_count > 1000 AND intensity_avg > 50",
      "external_state": false,
      "last_evaluation": true,
      "last_error": null,
      "frame_age_seconds": 0.023
    }
  ]
}
```

**Field Definitions:**

| Field | Type | Description |
|-------|------|-------------|
| `expression` | string | Current configured expression |
| `external_state` | boolean | Current external state value (API-controlled) |
| `last_evaluation` | boolean \| null | Most recent condition result (`true`, `false`, or `null` if not yet evaluated) |
| `last_error` | string \| null | Most recent error message (or `null` if no error) |

---

## 4. External State Control API

### POST `/api/v1/nodes/{node_id}/flow-control/set`

Set the `external_state` boolean for a specific IF node.

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `node_id` | string | Yes | ID of the IF condition node |

**Request Body:**

```json
{
  "value": true
}
```

**Pydantic Model:**

```python
class SetExternalStateRequest(BaseModel):
    value: bool = Field(
        ..., 
        description="Boolean state value (true or false)"
    )
```

**Success Response (200 OK):**

```json
{
  "node_id": "if_abc123",
  "state": true,
  "timestamp": 1234567890.123
}
```

**Pydantic Model:**

```python
class ExternalStateResponse(BaseModel):
    node_id: str = Field(..., description="Node identifier")
    state: bool = Field(..., description="Current external state value")
    timestamp: float = Field(..., description="Unix timestamp of the state change")
```

**Error Responses:**

**404 Not Found:**
```json
{
  "detail": "Node not found or not a flow control node"
}
```

**400 Bad Request:**
```json
{
  "detail": "Invalid request body: value must be boolean"
}
```

**Example Usage:**

```bash
# Enable external gate
curl -X POST http://localhost:8000/api/v1/nodes/if_abc123/flow-control/set \
  -H "Content-Type: application/json" \
  -d '{"value": true}'

# Response
{
  "node_id": "if_abc123",
  "state": true,
  "timestamp": 1710123456.789
}
```

---

### POST `/api/v1/nodes/{node_id}/flow-control/reset`

Reset the `external_state` to `false` for a specific IF node.

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `node_id` | string | Yes | ID of the IF condition node |

**Request Body:** None

**Success Response (200 OK):**

```json
{
  "node_id": "if_abc123",
  "state": false,
  "timestamp": 1234567890.123
}
```

**Error Responses:**

**404 Not Found:**
```json
{
  "detail": "Node not found or not a flow control node"
}
```

**Example Usage:**

```bash
# Reset external state
curl -X POST http://localhost:8000/api/v1/nodes/if_abc123/flow-control/reset

# Response
{
  "node_id": "if_abc123",
  "state": false,
  "timestamp": 1710123456.789
}
```

---

## 5. Edge Configuration

### POST `/api/v1/edges`

Create edges connecting IF node ports to downstream nodes.

**Request Body (True Port Connection):**

```json
{
  "id": "edge_abc_true",
  "source_id": "if_abc123",
  "source_port": "true",
  "target_id": "downsample_xyz",
  "target_port": "in"
}
```

**Request Body (False Port Connection):**

```json
{
  "id": "edge_abc_false",
  "source_id": "if_abc123",
  "source_port": "false",
  "target_id": "discard_node",
  "target_port": "in"
}
```

**Validation Rules:**

- IF nodes MUST specify `source_port` as either `"true"` or `"false"`
- Attempting to create edge without `source_port` for IF node → `400 Bad Request`
- Target node's `target_port` must match an available input port

**Error Response Example:**

```json
{
  "detail": "IF condition nodes require source_port to be 'true' or 'false'"
}
```

---

## 6. Expression Language Specification

### Supported Operators

**Comparison Operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `>` | Greater than | `point_count > 1000` |
| `<` | Less than | `intensity_avg < 200` |
| `==` | Equal to | `external_state == true` |
| `!=` | Not equal to | `sensor_name != "lidar_1"` |
| `>=` | Greater than or equal | `variance >= 0.01` |
| `<=` | Less than or equal | `timestamp <= 12345678` |

**Boolean Operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `AND` | Logical AND (case-insensitive) | `A AND B` |
| `OR` | Logical OR (case-insensitive) | `A OR B` |
| `NOT` | Logical NOT (case-insensitive) | `NOT A` |

**Grouping:**

- Parentheses `()` for explicit precedence
- Nested grouping supported: `((A OR B) AND C) OR D`

**Case Sensitivity:**

- Operators are **case-insensitive**: `and`, `AND`, `And` are equivalent
- Variable names are **case-sensitive**: `point_count` ≠ `Point_Count`

### Available Context Variables

All metadata fields from the input payload are accessible as variables:

| Variable | Type | Description |
|----------|------|-------------|
| `point_count` | int | Number of points in the cloud |
| `intensity_avg` | float | Average intensity value |
| `timestamp` | float | Unix timestamp |
| `variance` | float | Statistical variance |
| `node_id` | string | Source node ID |
| `sensor_name` | string | Sensor identifier |
| `external_state` | boolean | API-controlled state flag |
| *(any custom metadata)* | any | User-defined payload fields |

**Missing Field Behavior:**

- If a variable is not present in the payload, it evaluates to `None`
- Comparisons involving `None` evaluate to `False`
- Example: `missing_field > 100` → `False`

### Expression Examples

**Simple Comparisons:**
```python
point_count > 1000
intensity_avg >= 50
external_state == true
```

**Boolean Logic:**
```python
point_count > 5000 AND variance > 0.01
intensity_avg < 200 OR point_count < 1000
NOT (timestamp < 12345678)
```

**Complex Grouping:**
```python
(point_count > 1000 AND intensity_avg > 50) OR external_state == true
(variance > 0.01 OR point_count > 5000) AND NOT (timestamp < 12345678)
```

**Multi-Condition Quality Gate:**
```python
point_count > 1000 AND intensity_avg >= 50 AND variance > 0.01 AND external_state == true
```

### Syntax Errors

**Invalid Syntax Examples:**

```python
# Missing operand
point_count >

# Invalid operator
point_count >< 1000

# Arithmetic operations (not supported)
point_count + 500 > 1000

# Unbalanced parentheses
(point_count > 1000 AND intensity_avg > 50
```

**Error Handling:**

- Syntax errors route all data to `false` port
- Error logged at ERROR level
- `last_error` field set in node status
- Processing continues (no DAG crash)

---

## 7. WebSocket Behavior

### Topic Registration

IF nodes are **invisible by default** (do not broadcast to WebSocket).

**Rationale:**
- Routing decisions are internal DAG logic
- Downstream nodes already broadcast processed data
- Reduces unnecessary WebSocket traffic

**Implementation:**
```python
class IfConditionNode(ModuleNode):
    def __init__(self, ...):
        self._ws_topic = None  # Invisible
```

**Future Extension:**

If debugging is needed, add optional `visible` config property:

```json
{
  "type": "if_condition",
  "config": {
    "expression": "point_count > 1000",
    "visible": true  // Enable WebSocket broadcasting
  }
}
```

Topic would be: `if_condition_{node_id[:8]}`

**Binary Protocol:**

If visibility is enabled, broadcasts standard LIDR binary format (unchanged from existing nodes).

---

## 8. Validation & Constraints

### Configuration Validation

**On Node Creation/Update:**

1. **Expression Syntax Check:**
   - Parse expression using AST parser
   - Reject if contains disallowed operations (arithmetic, function calls, etc.)
   - Return `400 Bad Request` with error details

2. **Type Validation:**
   - `throttle_ms` must be numeric >= 0
   - `expression` must be non-empty string

**Example Error Response:**

```json
{
  "detail": "Expression validation failed: Syntax error at token '>>'",
  "field": "config.expression"
}
```

### Runtime Validation

**On Each Evaluation:**

1. **Safe Execution:**
   - All exceptions caught and logged
   - Failed evaluations route to `false` port
   - Node status updated with error details

2. **Performance Monitoring:**
   - Evaluation time tracked
   - Warning logged if >1ms (per NF1 requirement)

---

## 9. OpenAPI Schema Summary

**New Endpoints:**

| Method | Path | Tag | Summary |
|--------|------|-----|---------|
| POST | `/nodes/{node_id}/flow-control/set` | Flow Control | Set external state |
| POST | `/nodes/{node_id}/flow-control/reset` | Flow Control | Reset external state |

**New Schemas:**

```yaml
SetExternalStateRequest:
  type: object
  required:
    - value
  properties:
    value:
      type: boolean
      description: Boolean state value

ExternalStateResponse:
  type: object
  properties:
    node_id:
      type: string
      description: Node identifier
    state:
      type: boolean
      description: Current external state value
    timestamp:
      type: number
      format: float
      description: Unix timestamp of state change
```

**Updated Schemas:**

```yaml
NodeStatus:
  # Existing fields...
  # New conditional fields (only present for if_condition nodes):
  expression:
    type: string
    description: Current condition expression
  external_state:
    type: boolean
    description: API-controlled state flag
  last_evaluation:
    type: boolean
    nullable: true
    description: Most recent evaluation result
  last_error:
    type: string
    nullable: true
    description: Most recent error message
```

---

## 10. Frontend API Integration

### Angular Service Methods

**File:** `web/src/app/core/services/api/flow-control-api.service.ts` (NEW)

```typescript
@Injectable({ providedIn: 'root' })
export class FlowControlApiService {
  private http = inject(HttpClient);
  private baseUrl = environment.apiUrl;
  
  setExternalState(nodeId: string, value: boolean): Observable<ExternalStateResponse> {
    return this.http.post<ExternalStateResponse>(
      `${this.baseUrl}/nodes/${nodeId}/flow-control/set`,
      { value }
    );
  }
  
  resetExternalState(nodeId: string): Observable<ExternalStateResponse> {
    return this.http.post<ExternalStateResponse>(
      `${this.baseUrl}/nodes/${nodeId}/flow-control/reset`,
      {}
    );
  }
}
```

**Interfaces:**

```typescript
export interface ExternalStateResponse {
  node_id: string;
  state: boolean;
  timestamp: number;
}

  export interface IfNodeStatus extends NodeStatus {
      expression: string;
      external_state: boolean;
      last_evaluation: boolean | null;
      last_error: string | null;
    }
```

---

## 11. State Lifecycle

### State Persistence

**External State:**
- Stored in memory (`IfConditionNode.external_state` attribute)
- **NOT persisted** to database
- **Resets to `false`** on:
  - DAG reload (POST `/nodes/reload`)
  - Node deletion
  - Application restart

**Expression Config:**
- Stored in database (`nodes.config` JSON column)
- Persists across restarts
- Updated via `POST /nodes` (upsert endpoint)

### State Synchronization

**Backend → Frontend:**
- Status updates via `GET /nodes/status/all` (polled)
- WebSocket status broadcast (if implemented)

**Frontend → Backend:**
- Expression updates: `POST /nodes` with new config
- External state control: `POST /flow-control/set`

---

## 12. Testing Contracts

### Mock Responses

**For Frontend Development:**

**GET `/nodes/definitions` (IF Node):**
```json
{
  "type": "if_condition",
  "display_name": "Conditional If",
  "category": "flow_control",
  "description": "Routes data based on boolean expression",
  "icon": "call_split",
  "properties": [
    {"name": "expression", "label": "Condition Expression", "type": "string", "default": "true", "required": true},
    {"name": "throttle_ms", "label": "Throttle (ms)", "type": "number", "default": 0, "min": 0}
  ],
  "inputs": [{"id": "in", "label": "Input", "data_type": "pointcloud"}],
  "outputs": [
    {"id": "true", "label": "True", "data_type": "pointcloud"},
    {"id": "false", "label": "False", "data_type": "pointcloud"}
  ]
}
```

**GET `/nodes/status/all` (IF Node):**
```json
{
  "nodes": [
    {
      "id": "if_test_1",
      "name": "Quality Gate",
      "type": "if_condition",
      "category": "flow_control",
      "running": true,
      "expression": "point_count > 1000 AND intensity_avg > 50",
      "external_state": false,
      "last_evaluation": true,
      "last_error": null,
      "frame_age_seconds": 0.023
    }
  ]
}
```

**POST `/flow-control/set` Success:**
```json
{
  "node_id": "if_test_1",
  "state": true,
  "timestamp": 1710123456.789
}
```

**POST `/flow-control/set` Error (404):**
```json
{
  "detail": "Node not found or not a flow control node"
}
```

---

## 13. Backwards Compatibility

### Existing API Behavior

**No Breaking Changes:**

- All existing endpoints unchanged
- Node definition schema extended (additive)
- Edge schema already supports `source_port`/`target_port`
- Status schema extended (conditional fields)

### Migration Path

**For Existing Deployments:**

1. Deploy backend with flow control module
2. Frontend receives new node definitions automatically
3. Existing nodes continue operating unchanged
4. Users can add IF nodes via drag-and-drop palette

**No manual migration steps required.**

---

## 14. Rate Limits & Quotas

**External State Control:**

- No rate limiting implemented initially
- Throttling handled by standard FastAPI middleware
- Future: Add rate limit if external apps abuse `/set` endpoint

**Recommended Client Behavior:**

- Avoid polling `/set` endpoint
- Use event-driven updates (e.g., on user action, sensor trigger)

---

## 15. Security Considerations

### Expression Injection Prevention

**Threat:** Malicious user enters expression with code injection attempt

**Mitigation:**
- AST parser with strict whitelist
- No `eval()` usage
- Only comparison/boolean operations allowed
- Arithmetic, function calls, imports, lambdas rejected

**Example Rejected Expressions:**
```python
__import__('os').system('rm -rf /')  # Rejected: function call
exec('malicious code')               # Rejected: function call
point_count + (lambda: 1)()          # Rejected: lambda
1/0                                  # Rejected: arithmetic
```

### API Access Control

**Current Implementation:**
- No authentication (local deployment)

**Future Enhancement:**
- JWT bearer token authentication
- Role-based access (read-only vs admin)

---

## 16. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-03-19 | Initial specification for IF node module |

---

**Document Status:** ✅ READY FOR IMPLEMENTATION  
**Next Phase:** Backend and Frontend teams to implement according to spec
