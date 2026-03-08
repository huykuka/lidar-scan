# API Specification — WebSocket Topic Cleanup

**Feature:** `websocket-topic-cleanup`  
**Author:** @architecture  
**Date:** 2026-03-08  
**Version:** 1.0

---

## Overview

This document specifies the API contract changes introduced by the WebSocket topic cleanup fix. No new endpoints are created; three existing endpoints change behavior and two change their async signature.

---

## 1. Modified Endpoints

### 1.1 `POST /api/v1/nodes/reload`

**File:** `app/api/v1/nodes.py`

Reloads the entire node and edge configuration from the database, fully unregistering all topics for nodes no longer present.

#### Request

```
POST /api/v1/nodes/reload
Content-Type: application/json
```

No request body required.

#### Response — Success

```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "success"
}
```

#### Response — Reload In Progress (New)

```json
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "detail": "A configuration reload is already in progress. Please wait and retry."
}
```

This response is returned when a second concurrent `POST /nodes/reload` is received while the first is still executing (re-entrant lock guard — see technical.md §8 EC-3).

#### Behavioral Changes

| Behavior | Before Fix | After Fix |
|---|---|---|
| WebSocket clients on removed-node topics | Left open indefinitely | Receive `1001 Going Away` close frame |
| Pending `wait_for_next()` futures on removed topics | Left suspended indefinitely | `asyncio.CancelledError` raised in awaiting coroutine |
| `GET /topics` after reload | May still list removed-node topics | Only lists topics for active nodes |
| `time.sleep(2.0)` blocking the event loop | Yes | Replaced with `await asyncio.sleep(2.0)` |
| Re-entrant call guard | None | `asyncio.Lock` prevents concurrent reloads |

---

### 1.2 `DELETE /api/v1/nodes/{node_id}`

**File:** `app/api/v1/nodes.py`

Dynamically removes a single node from the running pipeline, now with proper async WebSocket teardown.

#### Request

```
DELETE /api/v1/nodes/{node_id}
```

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `node_id` | `string` | UUID of the node to delete |

#### Response — Success

```json
HTTP/1.1 200 OK

{
  "status": "success"
}
```

#### Response — Not Found

```json
HTTP/1.1 404 Not Found

{
  "detail": "Node not found"
}
```

#### Behavioral Changes

| Behavior | Before Fix | After Fix |
|---|---|---|
| WebSocket clients on deleted-node topic | Left open | Receive `1001 Going Away` close frame |
| Pending interceptor futures | Left suspended | Cancelled |
| Route handler | `node_manager.remove_node(node_id)` (sync, fire-and-forget) | `await node_manager.remove_node_async(node_id)` |

---

### 1.3 `POST /api/v1/config/import`

**File:** `app/api/v1/config.py`

When `merge: false` (replace mode), the endpoint now triggers `await node_manager.reload_config()` after writing the new config to the DB. This ensures in-memory DAG state is synchronized with the new configuration.

#### Request

```
POST /api/v1/config/import
Content-Type: application/json

{
  "nodes": [...],
  "edges": [...],
  "merge": false
}
```

#### Response — Success

```json
HTTP/1.1 200 OK

{
  "success": true,
  "mode": "replace",
  "imported": {
    "nodes": 3,
    "edges": 2
  },
  "node_ids": ["uuid-1", "uuid-2", "uuid-3"],
  "reloaded": true
}
```

The `reloaded` field is new — it indicates whether `reload_config()` was triggered as part of this import.

#### Response — Merge Mode (No Reload)

```json
HTTP/1.1 200 OK

{
  "success": true,
  "mode": "merge",
  "imported": {
    "nodes": 2,
    "edges": 0
  },
  "node_ids": ["uuid-1", "uuid-2"],
  "reloaded": false
}
```

#### Behavioral Changes

| Behavior | Before Fix | After Fix |
|---|---|---|
| Replace-mode import syncs in-memory DAG | No — requires manual reload | Yes — `reload_config()` called automatically |
| `reloaded` field in response | Not present | Present (`true` for replace, `false` for merge) |

---

## 2. Unchanged Endpoints (Reference)

These endpoints are not modified but are referenced for context.

### `GET /api/v1/topics`

Returns the current list of registered public WebSocket topics. After the fix, this list will accurately reflect only topics belonging to live nodes following a reload.

```json
HTTP/1.1 200 OK

{
  "topics": ["front_lidar_abc12345", "crop_filter_def67890"],
  "description": {
    "raw_points": "Stream of raw point cloud data (sub-sampled for performance)",
    "processed_points": "Stream of preprocessed data with algorithm results"
  }
}
```

### `GET /api/v1/topics/capture?topic={topic}`

Returns a single binary frame (LIDR format) from the named topic. If a reload/topic-removal occurs while this request is pending, the endpoint will return `503 Service Unavailable` (not `504 Timeout`).

#### New Error Response

```json
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "detail": "Topic was removed while waiting for frame. Please retry."
}
```

**File:** `app/api/v1/websocket.py`  
The `capture_frame()` handler must catch `asyncio.CancelledError` in addition to `asyncio.TimeoutError`:

```python
@router.get("/topics/capture")
async def capture_frame(topic: str):
    try:
        data = await manager.wait_for_next(topic, timeout=5.0)
        return Response(content=data, media_type="application/octet-stream")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout waiting for frame")
    except asyncio.CancelledError:
        raise HTTPException(status_code=503, detail="Topic was removed while waiting for frame. Please retry.")
```

---

## 3. WebSocket Protocol Changes

### Topic Closure Notification

When a topic is unregistered, connected clients receive a standard WebSocket close frame:

| Field | Value |
|---|---|
| Close code | `1001` (Going Away) |
| Close reason | `"Topic removed"` *(optional, implementation detail)* |

This is a protocol-level close, not a message. Clients must handle `WebSocket.onclose` — no new LIDR protocol message type is introduced.

### No New LIDR Binary Messages

The fix does not introduce any new binary frame types. The existing `LIDR` frame format (magic, version, timestamp, point count, XYZ data) is unchanged.

---

## 4. Internal State Contract Changes

### `ConnectionManager.active_connections`

| Invariant | Before Fix | After Fix |
|---|---|---|
| Topic keys always have a live producing node | Not guaranteed | **Guaranteed** post-reload |
| WebSocket objects in lists are always open | Not guaranteed | **Guaranteed** (closed ones self-remove on broadcast error) |

### `ConnectionManager._interceptors`

| Invariant | Before Fix | After Fix |
|---|---|---|
| Futures are always eventually resolved or timed-out | Not guaranteed (topic removal leaves futures hanging) | **Guaranteed** — all futures cancelled on `unregister_topic` |

### `NodeManager.nodes` ↔ `ConnectionManager.active_connections` Consistency

After the fix, for any non-system topic `T` in `ConnectionManager.active_connections`, there must exist a node instance `N` in `NodeManager.nodes` such that `N._ws_topic == T`. This invariant is maintained by:

1. Topic registered **only** in `ConfigLoader._register_node_websocket_topic()`.
2. Topic unregistered **only** in `LifecycleManager._unregister_node_websocket_topic_async()` (single node removal) or the orphan sweep in `NodeManager.reload_config()`.

---

## 5. Mock Data for Frontend Development

Frontend developers can mock the topics API response during development:

```typescript
// Mock: GET /api/v1/topics — after reload with one node removed
const MOCK_TOPICS_AFTER_RELOAD = {
  topics: ['front_lidar_abc12345'],  // 'crop_filter_def67890' is now gone
  description: {
    raw_points: 'Stream of raw point cloud data (sub-sampled for performance)',
    processed_points: 'Stream of preprocessed data with algorithm results'
  }
};

// Mock: WebSocket close event for dead topic
// Simulated in unit tests via:
//   socket.dispatchEvent(new CloseEvent('close', { code: 1001, reason: 'Topic removed' }));
```
