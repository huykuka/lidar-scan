# Application Module Scaffold — API Specification

> **Scope**: Python API surface only (no new REST or WebSocket endpoints are introduced).
> `HelloWorldNode` is a pure DAG node. All external communication happens via the existing
> `NodeManager.forward_data()` pipeline and the `system_status` WebSocket topic.

---

## 1. Public Class API — `HelloWorldNode`

### 1.1 Constructor

```python
HelloWorldNode(
    manager:     Any,           # NodeManager instance (injected by registry factory)
    node_id:     str,           # Unique node ID from DB (e.g. "550e8400-e29b-41d4-a716")
    name:        str,           # Display name (from node["name"] or "Hello World")
    config:      Dict[str, Any], # Full config dict from node["config"]
    throttle_ms: float = 0,     # Accepted for interface compatibility; throttle is central
) -> None
```

**Required attributes set by constructor:**

| Attribute | Type | Description |
|---|---|---|
| `self.id` | `str` | Must equal `node_id` — read by `NodeManager`, `StatusAggregator` |
| `self.name` | `str` | Display name — read by `ConfigLoader` for topic slug generation |
| `self.manager` | `Any` | `NodeManager` reference — used for `forward_data()` calls |
| `self.config` | `Dict[str, Any]` | Full config dict — for introspection and future sub-configs |
| `self.message` | `str` | Extracted from `config["message"]`, default `"Hello from DAG!"` |
| `self.input_count` | `int` | Frame counter (starts at 0) |
| `self.last_input_at` | `Optional[float]` | Unix timestamp of last `on_input` call |
| `self.last_error` | `Optional[str]` | Last exception string, or `None` |
| `self.processing_time_ms` | `float` | Duration of last `on_input` execution in ms |

---

### 1.2 `async def on_input(payload: Dict[str, Any]) -> None`

**Called by**: `DataRouter` (inside `NodeManager`) when an upstream DAG node forwards data.

#### Input Payload Schema

All fields are the **standard DAG payload dictionary** forwarded from upstream nodes:

| Key | Type | Required | Description |
|---|---|---|---|
| `points` | `np.ndarray` shape `(N, ≥3)` float32 | Recommended | XYZ + optional attribute columns |
| `timestamp` | `float` | Recommended | Unix epoch seconds of frame capture |
| `node_id` | `str` | Recommended | ID of the last node that emitted this payload |
| `lidar_id` | `str` | Optional | Canonical leaf `LidarSensor` node ID (set at hardware source) |
| `processing_chain` | `List[str]` | Optional | Ordered list of DAG node IDs the payload has passed through |
| `processed_by` | `str` | Optional | ID of the last processing node (set by OperationNode) |

#### Processing Steps

1. Record `self.last_input_at = time.time()`.
2. Extract `points` and compute `point_count`.
3. Increment `self.input_count`.
4. Log at INFO: `"{node_id} on_input: {point_count} points from node_id={…}"`.
5. Build `new_payload = payload.copy()` (shallow copy — do NOT mutate upstream dict).
6. Annotate `new_payload` with keys below.
7. Call `asyncio.create_task(self.manager.forward_data(self.id, new_payload))`.
8. On exception: set `self.last_error`, call `notify_status_change(self.id)`, log ERROR.

#### Output Payload Schema

`new_payload` inherits all keys from the input payload, plus:

| Key | Type | Value | Description |
|---|---|---|---|
| `node_id` | `str` | `self.id` | Updated to identify this node as the last emitter |
| `processed_by` | `str` | `self.id` | Same as `node_id` (convention from `OperationNode`) |
| `app_message` | `str` | `self.message` | The configured greeting message |
| `app_point_count` | `int` | `len(points)` or `0` | Point count at time of processing |

#### Behavior on Edge Cases

| Condition | Behavior |
|---|---|
| `payload["points"]` is `None` | `point_count = 0`; payload still forwarded with `app_point_count=0` |
| `payload["points"]` is empty array | Same as above |
| Any exception in processing | `self.last_error` set; payload NOT forwarded; `emit_status()` will reflect ERROR |

---

### 1.3 `def emit_status() -> NodeStatusUpdate`

**Called by**: `StatusAggregator._collect_and_broadcast()` on status change events.

#### Return Schema

Returns `app.schemas.status.NodeStatusUpdate` (Pydantic V2 model):

```python
NodeStatusUpdate(
    node_id=self.id,                         # str
    operational_state=OperationalState.XXX,  # enum → serialized as string
    application_state=ApplicationState(
        label="processing",                  # str — constant for this node type
        value=bool,                          # True = actively processing
        color="blue" | "gray",               # UI color hint
    ),
    error_message=Optional[str],             # Only when operational_state=ERROR
    timestamp=float,                         # Auto-set by Pydantic default_factory
)
```

#### State Machine

| Condition | `operational_state` | `application_state.value` | `application_state.color` | `error_message` |
|---|---|---|---|---|
| `self.last_error` is set | `ERROR` | `False` | `"gray"` | error string |
| `self.last_input_at` within last 5 s | `RUNNING` | `True` | `"blue"` | `None` |
| idle (never received input or >5 s ago) | `RUNNING` | `False` | `"gray"` | `None` |

---

### 1.4 `def start(data_queue=None, runtime_status=None) -> None`

**Called by**: `LifecycleManager.start_all_nodes()` when `NodeManager.start()` is invoked.

**Signature (from `ModuleNode` base):**
```python
def start(
    self,
    data_queue: Any = None,
    runtime_status: Optional[Dict[str, Any]] = None,
) -> None
```

**Behavior**: Log startup message at INFO level. No background process spawning (unlike
`LidarSensor`). Method is synchronous.

**Log format:**
```
[{node_id}] HelloWorldNode '{name}' started. message='{message}'
```

---

### 1.5 `def stop() -> None`

**Called by**: `LifecycleManager.stop_all_nodes()` when `NodeManager.stop()` is invoked, or
`LifecycleManager.remove_node()` during dynamic teardown.

**Behavior**: Log shutdown message at INFO level. No resources to release.

**Log format:**
```
[{node_id}] HelloWorldNode '{name}' stopped.
```

---

### 1.6 `enable() / disable()` (Inherited no-ops)

Inherited from `ModuleNode` as no-ops. Application nodes that need pause/resume semantics can
override these. `HelloWorldNode` does not.

---

## 2. Registry Factory Function

```python
build_hello_world(
    node:            Dict[str, Any],  # Full node record from DB (NodeModel.to_dict())
    service_context: Any,             # NodeManager instance
    edges:           List[Dict[str, Any]],  # All DAG edges (may be used to find upstream nodes)
) -> HelloWorldNode
```

### `node` Dictionary Shape

The `node` dict is produced by `NodeModel.to_dict()` in the SQLite ORM layer. Relevant keys:

| Key | Type | Example |
|---|---|---|
| `"id"` | `str` | `"550e8400-e29b-41d4-a716-446655440000"` |
| `"name"` | `str` | `"My Hello World Node"` |
| `"type"` | `str` | `"hello_world"` |
| `"category"` | `str` | `"application"` |
| `"enabled"` | `bool` | `True` |
| `"visible"` | `bool` | `True` |
| `"config"` | `Dict[str, Any]` | `{"message": "Hi!", "throttle_ms": 100}` |
| `"pose"` | `Dict[str, Any]` | `{}` (application nodes typically have no pose) |

### `config` Sub-Dictionary Shape

| Key | Type | Default | Description |
|---|---|---|---|
| `"message"` | `str` | `"Hello from DAG!"` | Custom message string |
| `"throttle_ms"` | `int \| float` | `0` | Frame rate limiter (enforced by NodeManager) |

---

## 3. NodeDefinition Schema (Angular UI Palette Contract)

Registered at module load time via `node_schema_registry.register(...)`.

Serialized form (as returned by `GET /api/v1/nodes/schemas`):

```json
{
  "type": "hello_world",
  "display_name": "Hello World App",
  "category": "application",
  "description": "Example application node: logs data, counts points, and forwards payload",
  "icon": "celebration",
  "websocket_enabled": true,
  "properties": [
    {
      "name": "message",
      "label": "Message",
      "type": "string",
      "default": "Hello from DAG!",
      "required": false,
      "help_text": "Custom message appended to every forwarded payload",
      "options": null,
      "min": null,
      "max": null,
      "step": null,
      "hidden": false,
      "depends_on": null
    },
    {
      "name": "throttle_ms",
      "label": "Throttle (ms)",
      "type": "number",
      "default": 0,
      "required": false,
      "help_text": "Minimum milliseconds between processing frames (0 = no limit)",
      "min": 0,
      "max": null,
      "step": 10,
      "hidden": false,
      "depends_on": null
    }
  ],
  "inputs": [
    { "id": "in", "label": "Input", "data_type": "pointcloud", "multiple": false }
  ],
  "outputs": [
    { "id": "out", "label": "Output", "data_type": "pointcloud", "multiple": false }
  ]
}
```

---

## 4. NodeFactory Registration Contract

After `discover_modules()` runs, `NodeFactory._registry` must contain:

```python
NodeFactory._registry["hello_world"] = build_hello_world  # callable
```

Verification:
```python
from app.services.nodes.node_factory import NodeFactory
assert "hello_world" in NodeFactory._registry
```

---

## 5. Existing API Endpoints (No Changes Required)

The `hello_world` node type participates in the following existing REST endpoints
**without any modification to backend API code**:

| Endpoint | Behavior |
|---|---|
| `GET /api/v1/nodes/schemas` | Returns `hello_world` NodeDefinition in the list |
| `POST /api/v1/nodes` | Creates a node record with `type="hello_world"` |
| `GET /api/v1/nodes/{id}` | Returns the node record |
| `PUT /api/v1/nodes/{id}` | Updates config; selective reload kicks in |
| `DELETE /api/v1/nodes/{id}` | Removes node from DAG |
| `GET /api/v1/status` (WebSocket `system_status`) | `emit_status()` included in broadcast |
| `WebSocket ws://.../ws/{topic}` | `hello_world_{id[:8]}` topic streams forwarded payloads |

---

## 6. Error Contracts

| Error Scenario | Behavior |
|---|---|
| `build_hello_world()` raises | `ConfigLoader._create_node()` catches and logs ERROR; node not added to `manager.nodes` |
| `on_input()` raises | `self.last_error` set; `notify_status_change()` called; next `emit_status()` returns `ERROR` |
| `manager.forward_data()` raises inside `asyncio.create_task` | Task exception — logged by asyncio unhandled exception handler |
| Registry import fails (syntax error, missing dep) | `discover_modules()` catches; logs ERROR; app continues without this module |
