# Node Reload Improvement — API Specification

> **Frontend developers**: Mock all new endpoints using the schemas defined here.
> **Backend developers**: Implement to these exact contracts. No deviations without updating this doc.

---

## Overview of Changes

| # | Method | Path | Status | Description |
|---|--------|------|--------|-------------|
| 1 | `PUT` | `/api/v1/dag/config` | **MODIFIED** | Response now includes `reload_mode` field |
| 2 | `POST` | `/api/v1/nodes/{node_id}/reload` | **NEW** | Selective single-node reload |
| 3 | `GET` | `/api/v1/nodes/reload/status` | **NEW** | Current reload lock status |
| 4 | WS | `system_status` topic | **MODIFIED** | Broadcast now includes `reload_event` field |

---

## 1. `PUT /api/v1/dag/config` — Modified Response

### Request Body (unchanged)

```typescript
interface DagConfigSaveRequest {
  base_version: number;    // Optimistic lock version
  nodes: NodeRecord[];
  edges: EdgeRecord[];
}
```

### Response Body — Modified

**HTTP 200 OK**

```typescript
interface DagConfigSaveResponse {
  config_version: number;              // New version after save
  node_id_map: Record<string, string>; // temp_id → real_id for new nodes
  reload_mode: "selective" | "full" | "none";
  // "selective" — only parameter-changed nodes were reloaded (< 500ms)
  // "full"      — full DAG reload was triggered (topology changed)
  // "none"      — no runtime changes needed (only cosmetic changes: x/y)
  reloaded_node_ids: string[];         // IDs of nodes that were reloaded
  // Empty array when reload_mode = "full" or "none"
}
```

**Example — selective reload (single node param change):**
```json
{
  "config_version": 8,
  "node_id_map": {},
  "reload_mode": "selective",
  "reloaded_node_ids": ["a1b2c3d4"]
}
```

**Example — full reload (topology changed):**
```json
{
  "config_version": 9,
  "node_id_map": { "__new__1": "e5f6a7b8" },
  "reload_mode": "full",
  "reloaded_node_ids": []
}
```

**Example — no reload (only x/y positions changed):**
```json
{
  "config_version": 10,
  "node_id_map": {},
  "reload_mode": "none",
  "reloaded_node_ids": []
}
```

### Error Responses (unchanged behavior, new messages)

**HTTP 409 Conflict**
```json
{
  "detail": "A configuration reload is already in progress. Please wait and retry."
}
```
```json
{
  "detail": "Version conflict: base_version=7 but current version is 8. Another save has occurred. Please reload and reapply your changes."
}
```

**HTTP 500 Internal Server Error**
```json
{
  "detail": "Selective reload failed for node abc12345: Address already in use (port 2115). Node restored to previous state."
}
```

---

## 2. `POST /api/v1/nodes/{node_id}/reload` — New Endpoint

Triggers selective reload of a single node's runtime without affecting other nodes or WebSocket connections. Can be called directly by operators for forced runtime reset without config change.

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `node_id` | `string` | UUID hex of the node to reload (from `NodeRecord.id`) |

### Request Body

None (empty body or omit Content-Type).

### Response

**HTTP 200 OK — Reload Successful**

```typescript
interface NodeReloadResponse {
  node_id: string;
  status: "reloaded";
  duration_ms: number;   // Actual reload duration in milliseconds
  ws_topic: string | null; // The WebSocket topic that was preserved (null if node has no WS topic)
}
```

```json
{
  "node_id": "a1b2c3d4",
  "status": "reloaded",
  "duration_ms": 73,
  "ws_topic": "multiscan_left_a1b2c3d4"
}
```

**HTTP 404 Not Found**
```json
{
  "detail": "Node 'a1b2c3d4' not found in running DAG. Ensure the node is enabled."
}
```

**HTTP 409 Conflict**
```json
{
  "detail": "A configuration reload is already in progress. Please wait and retry."
}
```

**HTTP 500 Internal Server Error — Reload Failed, Node Restored**
```json
{
  "detail": "Reload failed for node 'a1b2c3d4': [OSError] [Errno 98] Address already in use. Node has been restored to previous configuration."
}
```

**HTTP 500 Internal Server Error — Reload Failed, Node Not Restored**
```json
{
  "detail": "Reload failed for node 'a1b2c3d4' and rollback also failed. Node is offline. Manual intervention required."
}
```

---

## 3. `GET /api/v1/nodes/reload/status` — New Endpoint

Provides the current state of the reload lock and any in-progress reload. Useful for frontend polling when a 409 is received.

### Request

No parameters, no body.

### Response

**HTTP 200 OK**

```typescript
interface ReloadStatusResponse {
  locked: boolean;          // True if _reload_lock is held
  reload_in_progress: boolean; // Alias for locked (convenience)
  active_reload_node_id: string | null; // Node currently being reloaded, null if full reload or not locked
  estimated_completion_ms: number | null; // null when not locked
}
```

**When idle:**
```json
{
  "locked": false,
  "reload_in_progress": false,
  "active_reload_node_id": null,
  "estimated_completion_ms": null
}
```

**During selective reload:**
```json
{
  "locked": true,
  "reload_in_progress": true,
  "active_reload_node_id": "a1b2c3d4",
  "estimated_completion_ms": 150
}
```

**During full reload:**
```json
{
  "locked": true,
  "reload_in_progress": true,
  "active_reload_node_id": null,
  "estimated_completion_ms": 3000
}
```

---

## 4. WebSocket `system_status` Topic — Modified Broadcast Schema

The existing `system_status` WebSocket topic (already consumed by `SystemStatusService`) carries a new optional `reload_event` field. The `nodes` array remains unchanged and continues to broadcast on every 1-second poll cycle.

### Broadcast Message Schema (extended)

```typescript
interface SystemStatusBroadcast {
  nodes: NodeStatusUpdate[];   // Unchanged — all node statuses
  reload_event?: ReloadEvent;  // NEW — present only during/after reload
}

interface ReloadEvent {
  node_id: string | null;  // null for full DAG reload events
  status: "reloading" | "ready" | "error";
  error_message: string | null;  // Present only when status = "error"
  reload_mode: "selective" | "full"; // Which reload path triggered this event
  timestamp: number;  // Unix timestamp (float, seconds)
}
```

### Reload Lifecycle Events

**Event 1: Reload started**
```json
{
  "nodes": [...],
  "reload_event": {
    "node_id": "a1b2c3d4",
    "status": "reloading",
    "error_message": null,
    "reload_mode": "selective",
    "timestamp": 1743750000.123
  }
}
```

**Event 2: Reload completed successfully**
```json
{
  "nodes": [...],
  "reload_event": {
    "node_id": "a1b2c3d4",
    "status": "ready",
    "error_message": null,
    "reload_mode": "selective",
    "timestamp": 1743750000.196
  }
}
```

**Event 3: Reload failed**
```json
{
  "nodes": [...],
  "reload_event": {
    "node_id": "a1b2c3d4",
    "status": "error",
    "error_message": "Address already in use (port 2115)",
    "reload_mode": "selective",
    "timestamp": 1743750000.350
  }
}
```

**Event 4: Full DAG reload started**
```json
{
  "nodes": [...],
  "reload_event": {
    "node_id": null,
    "status": "reloading",
    "error_message": null,
    "reload_mode": "full",
    "timestamp": 1743750010.000
  }
}
```

---

## 5. Pydantic Models Summary (Backend)

### New: `SelectiveReloadResult` (internal use)

```python
class SelectiveReloadResult(BaseModel):
    node_id: str
    status: Literal["reloaded", "error"]
    duration_ms: float
    ws_topic: Optional[str]
    error_message: Optional[str] = None
    rolled_back: bool = False
```

### New: `NodeReloadResponse` (REST response)

```python
class NodeReloadResponse(BaseModel):
    node_id: str
    status: Literal["reloaded"]
    duration_ms: float
    ws_topic: Optional[str]
```

### New: `ReloadStatusResponse` (REST response)

```python
class ReloadStatusResponse(BaseModel):
    locked: bool
    reload_in_progress: bool
    active_reload_node_id: Optional[str]
    estimated_completion_ms: Optional[int]
```

### Modified: `DagConfigSaveResponse`

```python
class DagConfigSaveResponse(BaseModel):
    config_version: int
    node_id_map: Dict[str, str]
    reload_mode: Literal["selective", "full", "none"]  # NEW
    reloaded_node_ids: List[str]                        # NEW
```

### Modified: `SystemStatusBroadcast` (in `app/schemas/status.py`)

```python
class ReloadEvent(BaseModel):
    node_id: Optional[str]
    status: Literal["reloading", "ready", "error"]
    error_message: Optional[str] = None
    reload_mode: Literal["selective", "full"]
    timestamp: float

class SystemStatusBroadcast(BaseModel):
    nodes: List[NodeStatusUpdate]
    reload_event: Optional[ReloadEvent] = None  # NEW
```

---

## 6. Angular Model Updates

### Modified: `DagConfigSaveResponse`

```typescript
// web/src/app/core/models/dag.model.ts
export interface DagConfigSaveResponse {
  config_version: number;
  node_id_map: Record<string, string>;
  reload_mode: 'selective' | 'full' | 'none';   // NEW
  reloaded_node_ids: string[];                    // NEW
}
```

### New: `ReloadEvent`

```typescript
// web/src/app/core/models/status.model.ts
export interface ReloadEvent {
  node_id: string | null;
  status: 'reloading' | 'ready' | 'error';
  error_message: string | null;
  reload_mode: 'selective' | 'full';
  timestamp: number;
}

export interface SystemStatusBroadcast {
  nodes: NodeStatusUpdate[];
  reload_event?: ReloadEvent;  // NEW
}
```

---

## 7. Frontend Mock Data for Development

The frontend team must use these mock responses while the backend is being implemented.

### Mock for `PUT /dag/config`

```typescript
// In DagApiService mock mode
const MOCK_SAVE_RESPONSE: DagConfigSaveResponse = {
  config_version: 2,
  node_id_map: {},
  reload_mode: 'selective',
  reloaded_node_ids: ['mock-node-001'],
};
```

### Mock for `POST /api/v1/nodes/{node_id}/reload`

```typescript
const MOCK_NODE_RELOAD_RESPONSE: NodeReloadResponse = {
  node_id: 'mock-node-001',
  status: 'reloaded',
  duration_ms: 73,
  ws_topic: 'mock_sensor_mock_nod',
};
```

### Mock WebSocket `reload_event` (inject in SystemStatusService mock)

```typescript
// Sequence: reloading → 200ms delay → ready
const MOCK_RELOAD_SEQUENCE: SystemStatusBroadcast[] = [
  {
    nodes: [],
    reload_event: {
      node_id: 'mock-node-001',
      status: 'reloading',
      error_message: null,
      reload_mode: 'selective',
      timestamp: Date.now() / 1000,
    }
  },
  {
    nodes: [],
    reload_event: {
      node_id: 'mock-node-001',
      status: 'ready',
      error_message: null,
      reload_mode: 'selective',
      timestamp: (Date.now() + 200) / 1000,
    }
  },
];
```

---

## 8. Compatibility & Migration Notes

- **Backward compatibility**: The `PUT /dag/config` response is **additive only** — `reload_mode` and `reloaded_node_ids` are new optional fields. Existing clients that ignore unknown fields continue to work unchanged.
- **No breaking changes** to `DagConfigSaveRequest` (request body unchanged).
- **system_status broadcast**: The `reload_event` field is optional. Existing `SystemStatusService` code that destructures only `nodes` from the broadcast is unaffected.
- **The 2-second sleep**: The `await asyncio.sleep(2.0)` in `reload_config()` remains for **full** reloads. Selective reload does NOT have this sleep.
