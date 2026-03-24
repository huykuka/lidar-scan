# Output Node — API Contract

**Status:** READY FOR PM REVIEW  
**Author:** @architecture  
**Base path:** `/api/v1`  
**Consumers:** `@fe-dev` MUST mock all endpoints below while `@be-dev` implements.

---

## 1. REST Endpoints

### 1.1 Get Webhook Configuration

```
GET /api/v1/nodes/{node_id}/webhook
```

Returns the current webhook configuration for an Output Node.

**Path Parameters:**

| Param | Type | Description |
|---|---|---|
| `node_id` | `string` | Output Node ID |

**Responses:**

`200 OK`
```json
{
  "webhook_enabled": false,
  "webhook_url": "",
  "webhook_auth_type": "none",
  "webhook_auth_token": null,
  "webhook_auth_username": null,
  "webhook_auth_password": null,
  "webhook_auth_key_name": "X-API-Key",
  "webhook_auth_key_value": null,
  "webhook_custom_headers": {}
}
```

`404 Not Found`
```json
{ "detail": "Node not found: {node_id}" }
```

`400 Bad Request`
```json
{ "detail": "Node {node_id} is not an output_node" }
```

---

### 1.2 Update Webhook Configuration

```
PATCH /api/v1/nodes/{node_id}/webhook
```

Updates the webhook configuration for an Output Node. Merges into the node's existing `config_json`. Triggers in-memory update of the running `OutputNode` instance's `_webhook` field (hot-reload without full DAG reload).

**Path Parameters:**

| Param | Type | Description |
|---|---|---|
| `node_id` | `string` | Output Node ID |

**Request Body:**
```json
{
  "webhook_enabled": true,
  "webhook_url": "https://api.example.com/webhook",
  "webhook_auth_type": "bearer",
  "webhook_auth_token": "my-secret-token",
  "webhook_auth_username": null,
  "webhook_auth_password": null,
  "webhook_auth_key_name": null,
  "webhook_auth_key_value": null,
  "webhook_custom_headers": {
    "X-Source": "lidar-standalone"
  }
}
```

**Validation Rules (enforced by backend Pydantic):**
- If `webhook_enabled = true`: `webhook_url` MUST be a valid `http://` or `https://` URL.
- `webhook_auth_type` MUST be one of: `"none"`, `"bearer"`, `"basic"`, `"api_key"`.
- `webhook_custom_headers` values MUST be strings.
- All credential fields are optional strings (nullable). Not encrypted in MVP.

**Responses:**

`200 OK`
```json
{ "status": "ok", "node_id": "{node_id}" }
```

`400 Bad Request` (validation failure)
```json
{
  "detail": "webhook_url must be a valid HTTP/HTTPS URL when webhook is enabled"
}
```

`404 Not Found`
```json
{ "detail": "Node not found: {node_id}" }
```

`400 Bad Request` (wrong node type)
```json
{ "detail": "Node {node_id} is not an output_node" }
```

---

### 1.3 Get Output Node Details

Reuses the existing `GET /api/v1/nodes/{node_id}` endpoint. No change needed. Response includes the `config` dict which contains webhook fields.

```
GET /api/v1/nodes/{node_id}
```

`200 OK` (existing schema, config now includes webhook fields when set):
```json
{
  "id": "abc123",
  "name": "My Output",
  "type": "output_node",
  "category": "flow_control",
  "enabled": true,
  "visible": false,
  "config": {
    "webhook_enabled": true,
    "webhook_url": "https://api.example.com/webhook",
    "webhook_auth_type": "bearer",
    "webhook_auth_token": "my-secret-token",
    "webhook_custom_headers": {}
  },
  "pose": null,
  "x": 300.0,
  "y": 150.0
}
```

---

## 2. WebSocket Protocol

### 2.1 System Topic Connection

The Output Node broadcasts metadata over the **existing system topic**.

**URL:**
```
ws://{host}/api/v1/ws/system_status
```
or
```
wss://{host}/api/v1/ws/system_status
```

> `@fe-dev`: Use `environment.wsUrl` base. The existing `MultiWebsocketService` handles connection lifecycle.

### 2.2 Output Node Metadata Message

**Direction:** Server → Client (broadcast)  
**Format:** JSON text frame

```typescript
interface OutputNodeMetadataMessage {
  type: "output_node_metadata";   // discriminator — filter by this
  node_id: string;                 // ID of the Output Node that emitted this
  timestamp: number;               // Unix epoch seconds (float)
  metadata: Record<string, any>;   // All non-binary fields from upstream payload
}
```

**Example:**
```json
{
  "type": "output_node_metadata",
  "node_id": "abc123def",
  "timestamp": 1700000000.123,
  "metadata": {
    "point_count": 45000,
    "intensity_avg": 0.72,
    "sensor_name": "lidar_front",
    "processing_time_ms": 12.4,
    "frame_id": "frame_001"
  }
}
```

**Filtering Rule (Frontend):**
```typescript
filter(msg => msg.type === 'output_node_metadata' && msg.node_id === routeNodeId)
```

**Close Codes:**
- `1001` → Topic intentionally removed (node deleted). Complete stream, do not reconnect.
- Other → Network error. Attempt reconnect.

---

## 3. Webhook HTTP Delivery

### 3.1 Outbound POST (Backend → External)

```
POST <webhook_url>
Content-Type: application/json
Authorization: Bearer <token>        (if auth_type = "bearer")
Authorization: Basic <b64(u:p)>      (if auth_type = "basic")
<key_name>: <key_value>              (if auth_type = "api_key")
<custom-header-key>: <value>         (per webhook_custom_headers)
```

**Body** (identical to WebSocket message format):
```json
{
  "type": "output_node_metadata",
  "node_id": "abc123def",
  "timestamp": 1700000000.123,
  "metadata": {
    "point_count": 45000,
    "intensity_avg": 0.72
  }
}
```

**Behavior:**
- Fire-and-forget. No response body is read.
- Timeout: 10 seconds (not configurable in MVP).
- No retry on failure.
- 4xx/5xx responses logged at ERROR level; do not raise.
- Credentials are NOT included in log output.

---

## 4. Mock Data for Frontend Development

`@fe-dev` MUST use the following mock data while `@be-dev` implements the backend.

### Mock: GET /api/v1/nodes/{node_id}/webhook
```json
{
  "webhook_enabled": false,
  "webhook_url": "",
  "webhook_auth_type": "none",
  "webhook_auth_token": null,
  "webhook_auth_username": null,
  "webhook_auth_password": null,
  "webhook_auth_key_name": "X-API-Key",
  "webhook_auth_key_value": null,
  "webhook_custom_headers": {}
}
```

### Mock: PATCH response (success)
```json
{ "status": "ok", "node_id": "mock-node-id" }
```

### Mock: WebSocket message stream (system_status topic)
```json
[
  {
    "type": "output_node_metadata",
    "node_id": "<routeNodeId>",
    "timestamp": 1700000001.0,
    "metadata": { "point_count": 45000, "intensity_avg": 0.72, "sensor_name": "lidar_front" }
  },
  {
    "type": "output_node_metadata",
    "node_id": "<routeNodeId>",
    "timestamp": 1700000002.0,
    "metadata": { "point_count": 46200, "intensity_avg": 0.68, "sensor_name": "lidar_front" }
  }
]
```

Emit mock messages every 1 second in a mock WebSocket service during development.

---

## 5. Node Definition Schema (from GET /api/v1/nodes/definitions)

The Output Node will appear in the definitions list with these fields:

```json
{
  "type": "output_node",
  "display_name": "Output",
  "category": "flow_control",
  "description": "Displays metadata from upstream node on a dedicated page",
  "icon": "dashboard",
  "websocket_enabled": false,
  "properties": [
    { "name": "webhook_enabled", "label": "Enable Webhook", "type": "boolean", "default": false },
    { "name": "webhook_url", "label": "Webhook POST URL", "type": "string", "default": "", "depends_on": { "webhook_enabled": [true] } },
    { "name": "webhook_auth_type", "label": "Authentication Type", "type": "select", "default": "none",
      "options": [
        { "label": "None", "value": "none" },
        { "label": "Bearer Token", "value": "bearer" },
        { "label": "Basic Auth", "value": "basic" },
        { "label": "API Key", "value": "api_key" }
      ],
      "depends_on": { "webhook_enabled": [true] }
    },
    { "name": "webhook_auth_token", "label": "Bearer Token", "type": "string", "default": "",
      "depends_on": { "webhook_enabled": [true], "webhook_auth_type": ["bearer"] } },
    { "name": "webhook_auth_username", "label": "Username", "type": "string", "default": "",
      "depends_on": { "webhook_enabled": [true], "webhook_auth_type": ["basic"] } },
    { "name": "webhook_auth_password", "label": "Password", "type": "string", "default": "",
      "depends_on": { "webhook_enabled": [true], "webhook_auth_type": ["basic"] } },
    { "name": "webhook_auth_key_name", "label": "Header Name", "type": "string", "default": "X-API-Key",
      "depends_on": { "webhook_enabled": [true], "webhook_auth_type": ["api_key"] } },
    { "name": "webhook_auth_key_value", "label": "Key Value", "type": "string", "default": "",
      "depends_on": { "webhook_enabled": [true], "webhook_auth_type": ["api_key"] } },
    { "name": "webhook_custom_headers", "label": "Custom Headers (JSON)", "type": "string", "default": "{}",
      "depends_on": { "webhook_enabled": [true] } }
  ],
  "inputs": [{ "id": "in", "label": "Input", "data_type": "pointcloud", "multiple": false }],
  "outputs": []
}
```
