# Snapshot Node — API Specification

## Base URL
`/api/v1`

---

## Endpoint

### `POST /nodes/{node_id}/trigger`

Capture the latest upstream point cloud held by the Snapshot Node and immediately forward it to all connected downstream nodes.

**Router**: Existing `flow_control_router` (`app/api/v1/flow_control/handler.py`)  
**Tags**: `["Flow Control"]`  
**Auth**: None (open endpoint)

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `node_id` | `string` | Unique node identifier (e.g. `"snapshot-abc123"`) |

#### Request Body
None.

#### Success Response — `200 OK`

```json
{ "status": "ok" }
```

**Schema** (`SnapshotTriggerResponse`):
```python
class SnapshotTriggerResponse(BaseModel):
    status: Literal["ok"]
```

---

#### Error Responses

| HTTP | Condition | `detail` example |
|---|---|---|
| `400` | `node_id` resolves to a node that is not a `SnapshotNode` | `"Node snap-1 is not a snapshot node (type: FusionService)"` |
| `404` | Node not found **or** node exists but no upstream data received yet | `"Node snap-1 not found"` / `"No upstream data available"` |
| `409` | A previous snapshot is still being processed (concurrency guard) | `"Trigger dropped: snapshot still processing"` |
| `429` | Trigger arrived within the configured `throttle_ms` window | `"Trigger dropped: throttle window active (50ms)"` |
| `500` | `manager.forward_data()` raised an unexpected exception | `"Snapshot forwarding failed: <error>"` |

All error bodies follow FastAPI default:
```json
{ "detail": "<message>" }
```

---

## Node Configuration Schema

Returned as part of DAG node definitions (`GET /api/v1/nodes/definitions`).

```json
{
  "type": "snapshot",
  "display_name": "Snapshot",
  "category": "flow_control",
  "description": "Captures latest upstream point cloud on HTTP trigger",
  "icon": "camera",
  "websocket_enabled": false,
  "properties": [
    {
      "name": "throttle_ms",
      "label": "Throttle (ms)",
      "type": "number",
      "default": 0,
      "min": 0,
      "step": 10,
      "help_text": "Min ms between successful triggers (0 = no limit)"
    }
  ],
  "inputs": [
    { "id": "in",  "label": "Input",  "data_type": "pointcloud" }
  ],
  "outputs": [
    { "id": "out", "label": "Output", "data_type": "pointcloud" }
  ]
}
```

---

## Example Payloads

### Successful trigger
```
POST /api/v1/nodes/snapshot-abc123/trigger
→ 200 OK
{ "status": "ok" }
```

### No data yet
```
POST /api/v1/nodes/snapshot-abc123/trigger
→ 404 Not Found
{ "detail": "No upstream data available" }
```

### Concurrent trigger
```
POST /api/v1/nodes/snapshot-abc123/trigger   (while first is processing)
→ 409 Conflict
{ "detail": "Trigger dropped: snapshot still processing" }
```

### Throttled
```
POST /api/v1/nodes/snapshot-abc123/trigger   (within throttle_ms window)
→ 429 Too Many Requests
{ "detail": "Trigger dropped: throttle window active (100ms)" }
```

---

## Node Status (via `system_status` WebSocket)

Emitted by `SnapshotNode.emit_status()` and broadcast on the `system_status` topic.

```json
{
  "node_id": "snapshot-abc123",
  "operational_state": "RUNNING",
  "application_state": {
    "label": "snapshot",
    "value": 42,
    "color": "blue"
  },
  "error_message": null,
  "timestamp": 1714000000.123
}
```

| `operational_state` | `application_state.color` | Meaning |
|---|---|---|
| `RUNNING` | `blue` | Triggered within last 5 seconds |
| `RUNNING` | `gray` | Idle (no recent trigger) |
| `ERROR` | `red` | Last trigger resulted in error |
