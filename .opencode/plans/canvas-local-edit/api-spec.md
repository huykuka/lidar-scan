# Canvas Local Edit — API Specification

**Feature:** `canvas-local-edit`  
**Version:** v1  
**Base path:** `/api/v1`  
**Content-Type:** `application/json`

---

## Endpoints Summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/dag/config` | Fetch full DAG (nodes + edges) + current version |
| `PUT` | `/api/v1/dag/config` | Atomic save: replace DAG + trigger reload |

All other existing endpoints (`/nodes`, `/edges`, etc.) remain unchanged and are not used by the save/revert flow.

---

## `GET /api/v1/dag/config`

### Description
Returns the full current DAG configuration (all nodes, all edges) plus the monotonic `config_version` integer. Used by the frontend on initial load and after a Cancel/Revert action.

### Authentication
None (same as all other existing endpoints).

### Query Parameters
None.

### Response `200 OK`

```json
{
  "config_version": 7,
  "nodes": [
    {
      "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "name": "MultiScan Left",
      "type": "sensor",
      "category": "sensor",
      "enabled": true,
      "visible": true,
      "config": {
        "lidar_type": "multiscan",
        "hostname": "192.168.1.10",
        "udp_receiver_ip": "192.168.1.100",
        "port": 2115
      },
      "pose": {
        "x": 0.0, "y": 0.0, "z": 0.0,
        "roll": 0.0, "pitch": 0.0, "yaw": 0.0
      },
      "x": 120.0,
      "y": 200.0
    },
    {
      "id": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
      "name": "ICP Fusion",
      "type": "fusion",
      "category": "fusion",
      "enabled": true,
      "visible": true,
      "config": {
        "fusion_method": "icp_registration",
        "distance_threshold": 0.05,
        "max_iterations": 100
      },
      "pose": null,
      "x": 500.0,
      "y": 200.0
    }
  ],
  "edges": [
    {
      "id": "edge001",
      "source_node": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "source_port": "out",
      "target_node": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
      "target_port": "in"
    }
  ]
}
```

### Response Schema: `DagConfigResponse`

| Field | Type | Description |
|---|---|---|
| `config_version` | `integer` | Monotonic counter. Increments on every successful PUT. |
| `nodes` | `NodeRecord[]` | Full node array. Same schema as `GET /api/v1/nodes` items. |
| `edges` | `EdgeRecord[]` | Full edge array. Same schema as `GET /api/v1/edges` items. |

### NodeRecord fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `string` | yes | 32-char hex UUID |
| `name` | `string` | yes | |
| `type` | `string` | yes | |
| `category` | `string` | yes | `sensor \| fusion \| operation \| calibration` |
| `enabled` | `boolean` | yes | |
| `visible` | `boolean` | yes | defaults `true` |
| `config` | `object` | yes | arbitrary node-type config dict |
| `pose` | `Pose \| null` | no | `{x,y,z,roll,pitch,yaw}` floats |
| `x` | `number` | no | canvas X position |
| `y` | `number` | no | canvas Y position |

### EdgeRecord fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `string` | yes | 32-char hex UUID |
| `source_node` | `string` | yes | Node ID |
| `source_port` | `string` | yes | Port ID (e.g. `"out"`, `"true"`, `"false"`) |
| `target_node` | `string` | yes | Node ID |
| `target_port` | `string` | yes | Port ID (e.g. `"in"`) |

---

## `PUT /api/v1/dag/config`

### Description
Atomically replaces the full DAG (nodes + edges), increments `config_version`, then triggers a backend DAG reload. This is the **only** backend mutation during a canvas save operation.

### Request Body: `DagConfigSaveRequest`

```json
{
  "base_version": 7,
  "nodes": [
    {
      "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "name": "MultiScan Left",
      "type": "sensor",
      "category": "sensor",
      "enabled": true,
      "visible": true,
      "config": {
        "lidar_type": "multiscan",
        "hostname": "192.168.1.10",
        "udp_receiver_ip": "192.168.1.100",
        "port": 2115
      },
      "pose": {
        "x": 0.0, "y": 0.0, "z": 0.0,
        "roll": 0.0, "pitch": 0.0, "yaw": 0.0
      },
      "x": 120.0,
      "y": 200.0
    },
    {
      "id": "__new__1",
      "name": "Debug Pass-Through",
      "type": "debug_save",
      "category": "operation",
      "enabled": true,
      "visible": false,
      "config": { "op_type": "debug_save" },
      "pose": null,
      "x": 350.0,
      "y": 300.0
    }
  ],
  "edges": [
    {
      "id": "edge001",
      "source_node": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "source_port": "out",
      "target_node": "__new__1",
      "target_port": "in"
    }
  ]
}
```

### Request Schema: `DagConfigSaveRequest`

| Field | Type | Required | Notes |
|---|---|---|---|
| `base_version` | `integer` | **yes** | Must match current `config_version`; conflict protection |
| `nodes` | `NodeRecord[]` | yes | Full desired node set. Nodes not in list are deleted. |
| `edges` | `EdgeRecord[]` | yes | Full desired edge set. Previous edges are replaced. |

**New node IDs:** Nodes with IDs starting with `__new__` (or any ID not present in the DB) will be assigned a new server-generated UUID. The mapping is returned in `node_id_map`.

### Response `200 OK`: `DagConfigSaveResponse`

```json
{
  "config_version": 8,
  "node_id_map": {
    "__new__1": "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `config_version` | `integer` | New version after increment |
| `node_id_map` | `Dict[str, str]` | Maps client temp IDs to server-assigned IDs. Empty if no new nodes. |

### Response `409 Conflict`

Returned when the stored `config_version` does not match `base_version` in the request.

```json
{
  "detail": "Version conflict: base_version=7 but current version is 9. Another save has occurred. Please reload and reapply your changes."
}
```

### Response `422 Unprocessable Entity`

Returned when the request body fails Pydantic validation (malformed node types, missing required fields at the schema level).

```json
{
  "detail": [
    {
      "loc": ["body", "nodes", 0, "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Response `409 Reload In Progress`

Returned when another reload is already in progress (acquired `_reload_lock`).

```json
{
  "detail": "A configuration reload is already in progress. Please wait and retry."
}
```

### Response `500 Internal Server Error`

Returned on DB transaction failure or DAG reload exception. The DB transaction is rolled back on failure; `config_version` is NOT incremented.

```json
{
  "detail": "Save failed: <error message>"
}
```

---

## Error Handling Matrix

| Scenario | HTTP Status | Frontend Action |
|---|---|---|
| Success | 200 | Sync NodeStore, clear dirty, show toast |
| Version conflict (stale) | 409 `"Version conflict"` | Show conflict dialog; preserve local edits |
| Reload already running | 409 `"already in progress"` | Toast "Reload in progress, retry in a moment"; keep dirty |
| Validation error (schema) | 422 | Toast first error detail; keep dirty |
| Server error | 500 | Toast "Save failed: <message>"; keep dirty |
| Network timeout | (no response) | Toast "Request timed out"; keep dirty |

---

## Frontend Mock Data (for parallel FE development)

The frontend team MUST use the following mock responses while the backend is being implemented. The mock should be switchable via `environment.useMockDag = true`.

### `GET /api/v1/dag/config` mock

```typescript
// web/src/app/core/services/api/dag-api.service.ts
// Mock GET response
const MOCK_DAG_CONFIG: DagConfigResponse = {
  config_version: 1,
  nodes: [
    {
      id: 'mock-node-001',
      name: 'Mock Sensor',
      type: 'sensor',
      category: 'sensor',
      enabled: true,
      visible: true,
      config: { lidar_type: 'multiscan', hostname: '192.168.1.10', port: 2115 },
      pose: { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 },
      x: 100,
      y: 150
    }
  ],
  edges: []
};
```

### `PUT /api/v1/dag/config` mock (success)

```typescript
const MOCK_SAVE_RESPONSE: DagConfigSaveResponse = {
  config_version: 2,
  node_id_map: {}
};
// Simulate 800ms network delay
await new Promise(r => setTimeout(r, 800));
return MOCK_SAVE_RESPONSE;
```

### `PUT /api/v1/dag/config` mock (409 conflict simulation)

```typescript
// Trigger conflict when base_version === 0 (for testing)
if (req.base_version === 0) {
  throw {
    status: 409,
    error: { detail: 'Version conflict: base_version=0 but current version is 3.' }
  };
}
```

---

## TypeScript Interface Definitions

Add to `web/src/app/core/models/dag.model.ts`:

```typescript
import { NodeConfig, Edge } from './node.model';

export interface DagConfigResponse {
  config_version: number;
  nodes: NodeConfig[];
  edges: Edge[];
}

export interface DagConfigSaveRequest {
  base_version: number;
  nodes: NodeConfig[];
  edges: Edge[];
}

export interface DagConfigSaveResponse {
  config_version: number;
  node_id_map: Record<string, string>;
}

export interface DagConflictError {
  status: 409;
  error: {
    detail: string;
  };
}
```

---

## WebSocket — No Changes

The LIDR binary WebSocket protocol is **not modified** by this feature. After a successful `PUT /api/v1/dag/config`, the backend calls `reload_config()` which triggers the existing WebSocket topic lifecycle (cleanup + re-registration per `protocols.md`). The frontend already handles `1001 Going Away` close codes correctly.

---

## Swagger Annotations (backend)

All new endpoints must include:
- `summary`, `description`
- `response_model`
- `responses={409: ..., 422: ..., 500: ...}` entries
- `tags=["DAG"]`

Example:
```python
@router.put(
    "/dag/config",
    response_model=DagConfigSaveResponse,
    responses={
        409: {"description": "Version conflict or reload in progress"},
        422: {"description": "Invalid DAG configuration"},
        500: {"description": "Save or reload failure"},
    },
    summary="Save DAG Configuration",
    description=(
        "Atomically replaces all nodes and edges, increments the config version, "
        "and triggers a DAG reload. Rejects with 409 if base_version is stale."
    ),
    tags=["DAG"],
)
async def dag_config_save_endpoint(req: DagConfigSaveRequest):
    ...
```
