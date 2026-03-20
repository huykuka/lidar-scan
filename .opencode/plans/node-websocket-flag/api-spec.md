# Node WebSocket Streaming Flag - API Specification

## Overview

This document specifies the API contract for the `websocket_enabled` flag in node definitions. The flag is **read-only** from the client perspective and is part of the node type schema, not individual node instances.

---

## Affected Endpoint

### `GET /api/v1/nodes/definitions`

**Purpose:** Returns metadata for all available node types, including streaming capabilities.

**Request:**
```http
GET /api/v1/nodes/definitions HTTP/1.1
Host: localhost:8000
Accept: application/json
```

**Response Schema:**
```json
[
  {
    "type": "string",
    "display_name": "string",
    "category": "string",
    "description": "string | null",
    "icon": "string",
    "websocket_enabled": "boolean",  // ← NEW FIELD (required)
    "properties": [
      {
        "name": "string",
        "label": "string",
        "type": "string",
        "default": "any",
        "required": "boolean",
        "help_text": "string | null",
        "depends_on": "object | null"
      }
    ],
    "inputs": [
      {
        "id": "string",
        "label": "string",
        "data_type": "string",
        "multiple": "boolean"
      }
    ],
    "outputs": [
      {
        "id": "string",
        "label": "string",
        "data_type": "string",
        "multiple": "boolean"
      }
    ]
  }
]
```

---

## Response Examples

### Example 1: Sensor Node (Streaming Enabled)

```json
{
  "type": "sensor",
  "display_name": "LiDAR Sensor",
  "category": "sensor",
  "description": "Interface for physical SICK sensors or PCD file simulations",
  "icon": "sensors",
  "websocket_enabled": true,
  "properties": [
    {
      "name": "lidar_type",
      "label": "LiDAR Model",
      "type": "select",
      "default": "multiscan",
      "required": true,
      "help_text": "Select the SICK LiDAR hardware model for this node",
      "options": [
        {"label": "multiScan136", "value": "multiscan"}
      ]
    }
  ],
  "inputs": [],
  "outputs": [
    {
      "id": "out",
      "label": "Output",
      "data_type": "pointcloud",
      "multiple": false
    }
  ]
}
```

---

### Example 2: Fusion Node (Streaming Enabled)

```json
{
  "type": "fusion",
  "display_name": "Multi-Sensor Fusion",
  "category": "fusion",
  "description": "Merges multiple point cloud streams into a unified coordinate system",
  "icon": "hub",
  "websocket_enabled": true,
  "properties": [
    {
      "name": "throttle_ms",
      "label": "Throttle (ms)",
      "type": "number",
      "default": 0,
      "min": 0,
      "step": 10,
      "help_text": "Minimum time between processing frames (0 = no limit)"
    }
  ],
  "inputs": [
    {
      "id": "sensor_inputs",
      "label": "Inputs",
      "data_type": "pointcloud",
      "multiple": true
    }
  ],
  "outputs": [
    {
      "id": "fused_output",
      "label": "Fused",
      "data_type": "pointcloud",
      "multiple": false
    }
  ]
}
```

---

### Example 3: Calibration Node (Streaming Disabled)

```json
{
  "type": "calibration",
  "display_name": "ICP Calibration",
  "category": "calibration",
  "description": "Automatically align multiple LiDAR sensors using Iterative Closest Point (ICP) registration",
  "icon": "tune",
  "websocket_enabled": false,
  "properties": [
    {
      "name": "icp_method",
      "label": "ICP Method",
      "type": "select",
      "default": "point_to_plane",
      "options": [
        {"label": "Point-to-Plane (Recommended)", "value": "point_to_plane"},
        {"label": "Point-to-Point", "value": "point_to_point"}
      ]
    }
  ],
  "inputs": [
    {
      "id": "sensor_inputs",
      "label": "Inputs",
      "data_type": "pointcloud",
      "multiple": true
    }
  ],
  "outputs": []
}
```

**Key Observation:** `websocket_enabled: false` and `outputs: []` indicate this node:
- Does not produce streamable output
- Should not display visibility toggle or recording controls in UI

---

### Example 4: Flow Control Node (Streaming Disabled)

```json
{
  "type": "if_condition",
  "display_name": "If Condition",
  "category": "flow_control",
  "description": "Conditionally route point clouds based on attribute values",
  "icon": "call_split",
  "websocket_enabled": false,
  "properties": [
    {
      "name": "attribute",
      "label": "Attribute",
      "type": "string",
      "default": "point_count",
      "help_text": "Attribute name to evaluate (e.g., 'point_count', 'intensity_mean')"
    },
    {
      "name": "operator",
      "label": "Operator",
      "type": "select",
      "default": ">",
      "options": [
        {"label": "Greater Than (>)", "value": ">"},
        {"label": "Less Than (<)", "value": "<"},
        {"label": "Equals (==)", "value": "=="}
      ]
    },
    {
      "name": "threshold",
      "label": "Threshold",
      "type": "number",
      "default": 1000
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
      "id": "true_branch",
      "label": "True",
      "data_type": "pointcloud",
      "multiple": false
    },
    {
      "id": "false_branch",
      "label": "False",
      "data_type": "pointcloud",
      "multiple": false
    }
  ]
}
```

**Key Observation:** `websocket_enabled: false` but `outputs: [...]` indicates conditional routing. The node has outputs, but doesn't stream continuously — it only forwards data when conditions match.

---

## Field Specification

### `websocket_enabled` (required)

**Type:** `boolean`

**Default:** `true` (when field is omitted, for backward compatibility)

**Purpose:** Indicates whether the node type supports WebSocket streaming and related UI controls.

**Behavior:**

| Value | UI Controls Shown | Streaming Behavior |
|-------|-------------------|-------------------|
| `true` | Visibility toggle, recording button | Node can broadcast point clouds via WebSocket |
| `false` | Only enable/disable toggle and settings icon | Node performs computation but doesn't stream |

**When to use `true`:**
- Sensor nodes (produce raw point cloud data)
- Fusion nodes (merge and stream combined point clouds)
- Transform/filter operations (modify and forward point clouds)

**When to use `false`:**
- Calibration nodes (compute transformations, no continuous output)
- Flow control nodes (conditional routing, no streaming)
- Utility nodes (logging, debugging, metrics)

---

## Frontend Consumption Pattern

### TypeScript Model

```typescript
// web/src/app/core/models/node.model.ts
export interface NodeDefinition {
  type: string;
  display_name: string;
  category: string;
  description?: string;
  icon: string;
  websocket_enabled: boolean;  // Required field
  properties: PropertySchema[];
  inputs: PortSchema[];
  outputs: PortSchema[];
}
```

### Service Layer

```typescript
// web/src/app/core/services/node-plugin-registry.service.ts
async loadFromBackend(): Promise<void> {
  const definitions = await this.nodesApi.getNodeDefinitions();
  // definitions automatically include websocket_enabled field
  this.plugins.clear();
  definitions.forEach((def) => this.plugins.set(def.type, definitionToPlugin(def)));
}
```

### Component Logic

```typescript
// web/src/app/features/settings/components/flow-canvas/node/flow-canvas-node.component.ts
protected isWebsocketEnabled = computed(() => {
  const def = this.nodeDefinition();
  // Default to true if definition is missing (backward compat)
  return def ? def.websocket_enabled !== false : true;
});
```

### Template Usage

```html
<!-- Only show visibility toggle for streaming-capable nodes -->
@if (isNodeEnabled() && isWebsocketEnabled()) {
  <app-node-visibility-toggle
    [node]="node().data"
    (visibilityChanged)="onToggleVisibility.emit($event)"
  />
}

<!-- Only show recording controls for streaming nodes with outputs -->
@if (isNodeEnabled() && hasOutputPort() && isWebsocketEnabled()) {
  <app-node-recording-controls [node]="node()" />
}
```

---

## Backend Implementation Contract

### Pydantic Schema

```python
# app/services/nodes/schema.py
class NodeDefinition(BaseModel):
    type: str
    display_name: str
    category: str
    description: Optional[str] = None
    icon: str = "settings_input_component"
    websocket_enabled: bool = True  # Default ensures backward compatibility
    properties: List[PropertySchema] = []
    inputs: List[PortSchema] = []
    outputs: List[PortSchema] = []
```

### Registry Example

```python
# app/modules/calibration/registry.py
node_schema_registry.register(NodeDefinition(
    type="calibration",
    display_name="ICP Calibration",
    category="calibration",
    description="Automatically align multiple LiDAR sensors using ICP",
    icon="tune",
    websocket_enabled=False,  # ← Explicitly disable streaming UI
    properties=[...],
    inputs=[PortSchema(id="sensor_inputs", label="Inputs", multiple=True)]
    # Note: No outputs defined — this node only computes transformations
))
```

---

## Error Handling

### Validation

**Backend:** Pydantic ensures `websocket_enabled` is always a boolean. If a registry mistakenly provides a non-boolean value, FastAPI returns a 500 error during schema validation.

**Frontend:** TypeScript strict mode enforces the field is present. If backend omits the field:
- Pydantic defaults to `true`
- Frontend receives `websocket_enabled: true`
- UI shows all controls (safe fallback)

### Missing Definitions

If frontend requests a node type that doesn't exist in the registry:
- `nodeDefinition()` returns `undefined`
- `isWebsocketEnabled()` defaults to `true` (backward compat)
- UI shows controls (safe fallback)

---

## Testing Checklist

### Backend Tests
- [ ] All node definitions include `websocket_enabled` field
- [ ] Sensor/fusion/operation nodes have `websocket_enabled: true`
- [ ] Calibration/flow control nodes have `websocket_enabled: false`
- [ ] `/nodes/definitions` response includes the field in JSON

### Frontend Tests
- [ ] `NodeDefinition` model includes `websocket_enabled: boolean`
- [ ] `isWebsocketEnabled()` computed signal correctly reads the flag
- [ ] Template conditionally renders visibility toggle based on flag
- [ ] Template conditionally renders recording controls based on flag
- [ ] Default behavior (missing definition) shows controls

### Integration Tests
- [ ] Create calibration node → verify no visibility/recording buttons
- [ ] Create sensor node → verify visibility/recording buttons appear
- [ ] Toggle node enabled state → verify controls show/hide correctly

---

## Version Compatibility

| API Version | Field Support | Notes |
|-------------|---------------|-------|
| Current (before) | ❌ Field exists but not populated | All nodes default to `websocket_enabled: true` |
| After deployment | ✅ Field explicitly set per type | Calibration/flow control nodes set to `false` |
| Future | ✅ Backward compatible | Adding new node types requires explicit flag |

**Migration:** No breaking changes. Existing clients that ignore the field will see no behavior change (default remains `true`).
