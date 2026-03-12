# API Specification — Node Visibility Control

**Feature:** `node-visibility-control`  
**Author:** @architecture  
**Date:** 2026-03-12  
**Version:** v1  
**Base Path:** `/api/v1`

---

## Overview

This document specifies all API contract changes required to support node-level visibility control. It covers REST endpoint additions and modifications, request/response schema changes, WebSocket protocol behavior changes, and system status broadcast payload updates.

Frontend developers (`@fe-dev`) **MUST mock all responses defined in this document** while backend implementation is in progress. Backend developers (`@be-dev`) **MUST conform exactly** to these schemas.

---

## 1. Modified Endpoints

### 1.1 `GET /api/v1/nodes`

Returns all configured nodes. The `visible` field is added to each node object.

**Response Body** — `NodeRecord[]`

```json
[
  {
    "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    "name": "MultiScan Left",
    "type": "sensor",
    "category": "sensor",
    "enabled": true,
    "visible": true,
    "config": {
      "lidar_type": "multiscan",
      "hostname": "192.168.1.10"
    },
    "x": 120.0,
    "y": 200.0
  },
  {
    "id": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
    "name": "Point Cloud Fusion",
    "type": "fusion",
    "category": "fusion",
    "enabled": true,
    "visible": false,
    "config": {},
    "x": 300.0,
    "y": 200.0
  }
]
```

**Field Additions:**

| Field | Type | Default | Description |
|---|---|---|---|
| `visible` | `boolean` | `true` | Whether the node's WebSocket topic is registered and streaming |

**Backward Compatibility:** Clients that do not read `visible` continue to function unchanged.

---

### 1.2 `GET /api/v1/nodes/{node_id}`

Returns a single node by ID. The `visible` field is included.

**Path Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | `string` | Yes | The node's unique ID (UUID hex string) |

**Response Body** — `NodeRecord` (same schema as §1.1, single object)

**Error Responses:**

| Status | Description |
|---|---|
| `404 Not Found` | Node does not exist |

---

### 1.3 `POST /api/v1/nodes` (Create/Update)

Creates a new node or updates an existing one. Now accepts `visible` in the request body.

**Request Body:**

```json
{
  "name": "Front Sensor",
  "type": "sensor",
  "category": "sensor",
  "enabled": true,
  "visible": true,
  "config": {
    "lidar_type": "multiscan",
    "hostname": "192.168.1.10"
  },
  "x": 150.0,
  "y": 200.0
}
```

**Request Body Schema — `NodeCreateUpdate`:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | `string \| null` | No | `null` (auto-generated) | Existing node ID for updates |
| `name` | `string` | Yes | — | Human-readable node name |
| `type` | `string` | Yes | — | Node type identifier |
| `category` | `string` | Yes | — | `"sensor"`, `"fusion"`, `"operation"` |
| `enabled` | `boolean` | No | `true` | Whether node participates in DAG |
| `visible` | `boolean` | No | `true` | Whether node streams to WebSocket **[NEW]** |
| `config` | `object` | No | `{}` | Node-specific configuration |
| `x` | `number \| null` | No | `null` | Canvas X position |
| `y` | `number \| null` | No | `null` | Canvas Y position |

**Response Body:**

```json
{
  "status": "success",
  "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
}
```

---

### 1.4 `GET /api/v1/nodes/status/all`

Returns runtime status of all nodes. The `visible` field is added to each status item.

**Response Body** — `NodesStatusResponse`

```json
{
  "nodes": [
    {
      "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "name": "MultiScan Left",
      "type": "sensor",
      "category": "sensor",
      "enabled": true,
      "visible": true,
      "running": true,
      "topic": "multiscan_left_a1b2c3d4",
      "last_error": null,
      "throttle_ms": 0.0,
      "throttled_count": 0
    },
    {
      "id": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
      "name": "Point Cloud Fusion",
      "type": "fusion",
      "category": "fusion",
      "enabled": true,
      "visible": false,
      "running": true,
      "topic": null,
      "last_error": null,
      "throttle_ms": 0.0,
      "throttled_count": 0
    }
  ]
}
```

**Behavioral Note on `topic` field**: When `visible=false`, the node has no registered WebSocket topic. The `topic` field MUST be `null` in this case (not a derived string), to clearly signal to consumers that no topic is available.

---

## 2. New Endpoint

### 2.1 `PUT /api/v1/nodes/{node_id}/visible`

Toggles a node's visibility state. This is a lightweight, targeted endpoint that only modifies the `visible` field, triggers WebSocket topic lifecycle management, and leaves all other node properties unchanged.

**Path Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `node_id` | `string` | Yes | The node's unique ID |

**Request Body:**

```json
{
  "visible": false
}
```

**Request Body Schema — `NodeVisibilityToggle`:**

| Field | Type | Required | Description |
|---|---|---|---|
| `visible` | `boolean` | Yes | New visibility state |

**Success Response** — `200 OK`:

```json
{
  "status": "success"
}
```

**Error Responses:**

| Status Code | Condition | Response Body |
|---|---|---|
| `400 Bad Request` | Target node's topic is a system topic (e.g., `system_status`) | `{"detail": "Cannot change visibility of system topic 'system_status'"}` |
| `404 Not Found` | Node ID does not exist in database | `{"detail": "Node not found"}` |

**Side Effects:**

| `visible` transition | WebSocket Effect | DB Effect |
|---|---|---|
| `true → false` | `ConnectionManager.unregister_topic()` called; all clients on that topic receive `1001 Going Away` close frame | `nodes.visible = 0` committed |
| `false → true` | `ConnectionManager.register_topic()` called; topic appears in `GET /api/v1/topics` | `nodes.visible = 1` committed |
| No change (same value) | No WebSocket operation performed | DB write is still committed (idempotent) |

**Timing Contract:**
- DB update: committed synchronously before response
- WebSocket teardown: fully awaited before response (all `ws.close(1001)` calls complete before `200 OK` is returned)
- Response latency: expected <200ms under normal conditions; <1000ms under load with 50+ nodes

---

## 3. WebSocket Protocol Changes

### 3.1 `WS /api/v1/websocket/{topic}` — No Protocol Change

The binary `LIDR` frame format is unchanged:

| Offset | Size | Type | Description |
|---|---|---|---|
| 0 | 4 | char[4] | Magic `"LIDR"` |
| 4 | 4 | uint32 | Version |
| 8 | 8 | float64 | Timestamp |
| 16 | 4 | uint32 | Point count |
| 20 | N×12 | float32 | Points (x, y, z) × count |

### 3.2 Topic Visibility Close Behavior

When `PUT /api/v1/nodes/{node_id}/visible` with `visible=false` is processed:

1. The server calls `ws.close(code=1001)` for all active WebSocket connections on the node's topic.
2. Clients receive a standard WebSocket close frame with code `1001 Going Away`.
3. Clients MUST interpret `code=1001` as **intentional topic removal**, NOT as a network error.
4. Clients MUST NOT attempt to reconnect after receiving `code=1001`.

**Frontend Client Contract** (already implemented in `MultiWebsocketService`):

```typescript
socket.onclose = (event: CloseEvent) => {
  this.connections.delete(topic);
  if (event.code === 1001) {
    subject.complete();     // intentional — stream ended normally
    // Do NOT call scheduleReconnect()
  } else {
    subject.error(event);   // network error — caller handles reconnect
  }
};
```

### 3.3 Topic Visibility Restore Behavior

When `PUT /api/v1/nodes/{node_id}/visible` with `visible=true` is processed:

1. The server calls `register_topic(topic)` — the topic now appears in `GET /api/v1/topics`.
2. Existing connected clients are NOT notified automatically — they must poll `/api/v1/topics` or receive a `system_status` broadcast.
3. The `system_status` WebSocket broadcast (every 500ms) will include the updated node status with `visible=true` and a non-null `topic`, triggering the frontend to refresh its topic list.

---

## 4. System Status WebSocket Payload Update

**Topic:** `system_status`  
**Endpoint:** `WS /api/v1/websocket/system_status`

The `system_status` broadcast payload already carries node status. The `visible` field and a corrected `topic` field (null when invisible) must be added to each node item.

**Updated Broadcast Payload Schema:**

```json
{
  "nodes": [
    {
      "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "name": "MultiScan Left",
      "type": "sensor",
      "category": "sensor",
      "enabled": true,
      "visible": true,
      "running": true,
      "topic": "multiscan_left_a1b2c3d4",
      "connection_status": "connected",
      "frame_age_seconds": 0.02,
      "last_error": null
    },
    {
      "id": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
      "name": "Point Cloud Fusion",
      "type": "fusion",
      "category": "fusion",
      "enabled": true,
      "visible": false,
      "running": true,
      "topic": null,
      "last_error": null
    }
  ]
}
```

**Key change**: `topic` is `null` when `visible=false` (previously it was always a derived string).

---

## 5. DAG Configuration Import/Export

### 5.1 Export — `GET /api/v1/config`

The exported configuration now includes `visible` for each node. Existing configs without this field are treated as `visible=true` on import.

**Exported Node Object:**

```json
{
  "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "name": "MultiScan Left",
  "type": "sensor",
  "category": "sensor",
  "enabled": true,
  "visible": true,
  "config": { "lidar_type": "multiscan" },
  "x": 120.0,
  "y": 200.0
}
```

### 5.2 Import — `POST /api/v1/config/import`

The import handler reads the `visible` field from each node in the incoming JSON. Missing `visible` fields default to `true`.

**Import Node Object (acceptable variants):**

```json
// With visible field (new format)
{ "name": "...", "visible": false, ... }

// Without visible field (legacy format — treated as visible=true)
{ "name": "...", ... }
```

---

## 6. Mocking Guide for `@fe-dev`

Until the backend implements this feature, use the following mock data and behavior in frontend development.

### 6.1 Mock Service Implementation

```typescript
// In nodes-api.service.ts (mock mode)
async setNodeVisible(id: string, visible: boolean): Promise<any> {
  // Simulate 150ms network latency
  await new Promise(resolve => setTimeout(resolve, 150));
  
  // Simulate 400 for a known system node ID (for testing error handling)
  if (id === 'system_status_node') {
    throw { status: 400, error: { detail: "Cannot change visibility of system topic 'system_status'" } };
  }
  
  return { status: 'success' };
}
```

### 6.2 Mock Node List (with visible field)

```typescript
const MOCK_NODES: NodeConfig[] = [
  {
    id: 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4',
    name: 'MultiScan Left',
    type: 'sensor',
    category: 'sensor',
    enabled: true,
    visible: true,
    config: {},
    x: 120,
    y: 200
  },
  {
    id: 'b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5',
    name: 'Rear Sensor',
    type: 'sensor',
    category: 'sensor',
    enabled: true,
    visible: false,   // Pre-hidden to test dimming
    config: {},
    x: 300,
    y: 200
  }
];
```

### 6.3 Mock `GET /api/v1/topics` Behavior

When `visible=false` for a node, its topic should NOT appear in the topics list. Simulate this in the mock:

```typescript
async getTopics(): Promise<string[]> {
  const nodes = MOCK_NODES.filter(n => n.enabled && n.visible !== false);
  return nodes.map(n => `${n.name.toLowerCase().replace(/\s+/g, '_')}_${n.id.substring(0, 8)}`);
}
```

---

## 7. Error Reference

| Endpoint | Status | Error `detail` | Cause |
|---|---|---|---|
| `PUT /nodes/{id}/visible` | `400` | `"Cannot change visibility of system topic '{topic}'"` | Target node's topic is in the `SYSTEM_TOPICS` protected set |
| `PUT /nodes/{id}/visible` | `404` | `"Node not found"` | `node_id` does not exist in DB |
| `PUT /nodes/{id}/enabled` | `200` | *(existing behavior unchanged)* | — |
| `GET /nodes/{id}` | `404` | `"Node not found"` | `node_id` does not exist in DB |

---

## 8. Schema Reference

### `NodeRecord` (Full Schema)

```typescript
interface NodeRecord {
  id: string;
  name: string;
  type: string;
  category: string;
  enabled: boolean;
  visible: boolean;          // NEW in this feature
  config: Record<string, any>;
  x: number | null;
  y: number | null;
}
```

### `NodeVisibilityToggle` (Request)

```typescript
interface NodeVisibilityToggle {
  visible: boolean;          // Required
}
```

### `NodeStatusItem` (Full Schema)

```typescript
interface NodeStatusItem {
  id: string;
  name: string;
  type: string;
  category: string;
  enabled: boolean;
  visible: boolean;          // NEW in this feature
  running: boolean;
  topic: string | null;      // CHANGED: null when visible=false
  last_frame_at?: number | null;
  frame_age_seconds?: number | null;
  last_error: string | null;
  throttle_ms: number;
  throttled_count: number;
}
```

### `StatusResponse` (Success response)

```typescript
interface StatusResponse {
  status: "success";
}
```
