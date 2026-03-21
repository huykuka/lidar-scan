# API Specification: Unified Sensor Pose Entity

**Feature:** `sensor-pose-entity`  
**Version:** Breaking Change (no backward compat)  
**Base URL:** `/api/v1`

---

## 1. Shared Schema: `Pose`

This object appears in all sensor-related request and response payloads.

```yaml
Pose:
  type: object
  required: [x, y, z, roll, pitch, yaw]
  properties:
    x:
      type: number
      format: float
      description: "Translation X in millimeters"
      example: 150.0
    y:
      type: number
      format: float
      description: "Translation Y in millimeters"
      example: -25.5
    z:
      type: number
      format: float
      description: "Translation Z in millimeters"
      example: 800.0
    roll:
      type: number
      format: float
      minimum: -180.0
      maximum: 180.0
      description: "Rotation around X axis in degrees [-180, +180]"
      example: 0.0
    pitch:
      type: number
      format: float
      minimum: -180.0
      maximum: 180.0
      description: "Rotation around Y axis in degrees [-180, +180]"
      example: -5.0
    yaw:
      type: number
      format: float
      minimum: -180.0
      maximum: 180.0
      description: "Rotation around Z axis in degrees [-180, +180]"
      example: 45.0
```

**Validation Rules:**
- `x`, `y`, `z`: Any finite float. No range constraint. Unit: millimeters.
- `roll`, `pitch`, `yaw`: Must satisfy `-180.0 ≤ value ≤ 180.0`. Unit: degrees.
- NaN and ±Infinity are rejected with HTTP 422.
- Omitted fields default to `0.0`.

---

## 2. Updated `NodeRecord` Schema (Response)

All `GET /nodes` and `GET /nodes/{id}` responses include `pose` as a top-level field for
sensor-type nodes. Non-sensor nodes return `pose: null`.

```yaml
NodeRecord:
  type: object
  required: [id, name, type, category, enabled, visible, config, pose, x, y]
  properties:
    id:
      type: string
      example: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    name:
      type: string
      example: "Front LiDAR"
    type:
      type: string
      example: "sensor"
    category:
      type: string
      example: "sensor"
    enabled:
      type: boolean
      example: true
    visible:
      type: boolean
      example: true
    config:
      type: object
      description: "Node-type-specific configuration (does NOT contain pose fields)"
      example:
        lidar_type: "multiscan"
        hostname: "192.168.1.10"
        udp_receiver_ip: "192.168.1.100"
        port: 2115
        mode: "real"
        throttle_ms: 0
    pose:
      $ref: '#/components/schemas/Pose'
      nullable: true
      description: "Sensor pose. null for non-sensor nodes."
    x:
      type: number
      format: float
      description: "DAG canvas position X (NOT sensor pose)"
      example: 120.0
    y:
      type: number
      format: float
      description: "DAG canvas position Y (NOT sensor pose)"
      example: 200.0
```

---

## 3. Endpoint Specifications

### 3.1 `GET /nodes` — List All Nodes

Returns all configured nodes including pose for sensor types.

**Response: `200 OK`**

```json
[
  {
    "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    "name": "Front LiDAR",
    "type": "sensor",
    "category": "sensor",
    "enabled": true,
    "visible": true,
    "config": {
      "lidar_type": "multiscan",
      "hostname": "192.168.1.10",
      "udp_receiver_ip": "192.168.1.100",
      "port": 2115,
      "mode": "real",
      "throttle_ms": 0
    },
    "pose": {
      "x": 150.0,
      "y": -25.5,
      "z": 800.0,
      "roll": 0.0,
      "pitch": -5.0,
      "yaw": 45.0
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
    "visible": true,
    "config": {
      "fusion_method": "icp_registration",
      "distance_threshold": 0.05,
      "max_iterations": 100
    },
    "pose": null,
    "x": 300.0,
    "y": 200.0
  }
]
```

---

### 3.2 `GET /nodes/{node_id}` — Get Single Node

**Path Parameter:** `node_id: string`

**Response: `200 OK`** — same shape as single item from list above.

**Response: `404 Not Found`**
```json
{"detail": "Node not found"}
```

---

### 3.3 `POST /nodes` — Create or Update Node (Upsert)

Creates a new node or updates an existing one by `id`.

**Request Body:**

```yaml
NodeCreateUpdate:
  type: object
  required: [name, type, category]
  properties:
    id:
      type: string
      nullable: true
      description: "Omit to create new; provide to update existing"
    name:
      type: string
      example: "Rear LiDAR"
    type:
      type: string
      example: "sensor"
    category:
      type: string
      example: "sensor"
    enabled:
      type: boolean
      default: true
    visible:
      type: boolean
      default: true
    config:
      type: object
      description: "Node-type-specific settings. MUST NOT contain x, y, z, roll, pitch, yaw."
    pose:
      $ref: '#/components/schemas/Pose'
      nullable: true
      description: "Sensor pose. Required for sensor-type nodes. Omitting defaults to zero pose."
    x:
      type: number
      format: float
      description: "Canvas position X"
    y:
      type: number
      format: float
      description: "Canvas position Y"
```

**Request Example — Create sensor node with pose:**

```json
{
  "name": "Rear LiDAR",
  "type": "sensor",
  "category": "sensor",
  "enabled": true,
  "visible": true,
  "config": {
    "lidar_type": "multiscan",
    "hostname": "192.168.1.20",
    "udp_receiver_ip": "192.168.1.100",
    "port": 2116,
    "mode": "real",
    "throttle_ms": 0
  },
  "pose": {
    "x": 0.0,
    "y": 0.0,
    "z": 500.0,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 180.0
  },
  "x": 180.0,
  "y": 200.0
}
```

**Request Example — Reset pose to zero:**

```json
{
  "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "name": "Front LiDAR",
  "type": "sensor",
  "category": "sensor",
  "enabled": true,
  "visible": true,
  "config": {
    "lidar_type": "multiscan",
    "hostname": "192.168.1.10",
    "mode": "real"
  },
  "pose": {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0
  }
}
```

**Response: `200 OK`**
```json
{"status": "success", "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"}
```

**Response: `422 Unprocessable Entity` — deprecated flat pose keys in `config`:**
```json
{
  "detail": "Pose fields must be sent in the 'pose' object, not inside 'config'. Found deprecated keys: ['x', 'roll', 'yaw']"
}
```

**Response: `422 Unprocessable Entity` — angle out of range:**
```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["body", "pose", "yaw"],
      "msg": "Input should be less than or equal to 180",
      "input": 270.0
    }
  ]
}
```

---

### 3.4 `GET /nodes/status/all` — All Nodes Runtime Status

Includes pose data embedded in the node status for sensor-type nodes.

**Response: `200 OK`**

```json
{
  "nodes": [
    {
      "node_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "connection_status",
        "value": "connected",
        "color": "green"
      },
      "error_message": null,
      "timestamp": 1742560000.0,
      "name": "Front LiDAR",
      "type": "sensor",
      "category": "sensor",
      "enabled": true,
      "visible": true,
      "topic": "front_lidar_a1b2c3d4",
      "throttle_ms": 0.0,
      "throttled_count": 0
    }
  ]
}
```

> Note: Status endpoint does not embed `pose` (pose is static config, not runtime state).
> Frontend reads pose from `GET /nodes` or `GET /nodes/{id}`.

---

### 3.5 `POST /calibration/{node_id}/trigger` — Trigger Calibration

No change to request body. Response `pose_before` / `pose_after` fields already use the
`Pose` shape. Formally documented here for completeness.

**Response: `200 OK`**
```json
{
  "success": true,
  "results": {
    "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4": {
      "fitness": 0.94,
      "rmse": 0.012,
      "quality": "good",
      "source_sensor_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
      "processing_chain": ["a1b2c3d4", "calib01"],
      "pose_before": {
        "x": 0.0, "y": 0.0, "z": 500.0,
        "roll": 0.0, "pitch": 0.0, "yaw": 0.0
      },
      "pose_after": {
        "x": 2.3, "y": -0.5, "z": 499.1,
        "roll": 0.1, "pitch": -0.2, "yaw": 0.4
      }
    }
  },
  "pending_approval": true,
  "run_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### 3.6 `POST /calibration/{node_id}/accept` — Accept Calibration

Accepting a calibration writes the `pose_after` values into `nodes.pose_json` for the
affected sensor(s) and triggers a DAG reload. No changes to request/response shape.

---

### 3.7 `POST /calibration/rollback/{sensor_id}` — Rollback Pose

Restores a sensor's pose from a historical calibration record.

**Request Body:**
```json
{"timestamp": "2026-03-21T10:00:00+00:00"}
```

**Response: `200 OK`**
```json
{
  "success": true,
  "sensor_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "restored_to": "2026-03-21T10:00:00+00:00"
}
```

After rollback, `GET /nodes/{sensor_id}` will reflect the restored pose.

---

## 4. Validation Error Reference

| Field | Constraint | HTTP Code | Error Type |
|---|---|---|---|
| `pose.roll` | `[-180, 180]` | 422 | `less_than_equal` / `greater_than_equal` |
| `pose.pitch` | `[-180, 180]` | 422 | `less_than_equal` / `greater_than_equal` |
| `pose.yaw` | `[-180, 180]` | 422 | `less_than_equal` / `greater_than_equal` |
| `pose.x/y/z` | Finite float | 422 | `finite_number` |
| `config` contains pose keys | Deprecated | 422 | Custom detail string |

---

## 5. Breaking Changes from Old Contract

> **Storage note:** Pose is now stored as `config["pose"]` (nested inside `config_json` DB field).
> The API surface is identical — `pose` is still a top-level field in all request/response payloads.
> No new DB columns exist.

| Old Format | New Format | Migration |
|---|---|---|
| `config.x: 150.0` | `pose.x: 150.0` | Move to `pose` object |
| `config.y: -25.5` | `pose.y: -25.5` | Move to `pose` object |
| `config.z: 800.0` | `pose.z: 800.0` | Move to `pose` object |
| `config.roll: 0.0` | `pose.roll: 0.0` | Move to `pose` object |
| `config.pitch: -5.0` | `pose.pitch: -5.0` | Move to `pose` object |
| `config.yaw: 45.0` | `pose.yaw: 45.0` | Move to `pose` object |

**Clients sending the old format will receive HTTP 422 with the following detail:**
```
"Pose fields must be sent in the 'pose' object, not inside 'config'. Found deprecated keys: [...]"
```

---

## 6. Frontend Mocking Contract

During parallel development, the frontend MUST mock all API responses using this spec.
A minimal mock implementation:

```typescript
// Mock factory for tests and development
export function mockSensorNode(override?: Partial<NodeConfig>): NodeConfig {
  return {
    id: 'mock-sensor-001',
    name: 'Mock Front LiDAR',
    type: 'sensor',
    category: 'sensor',
    enabled: true,
    visible: true,
    config: {
      lidar_type: 'multiscan',
      hostname: '192.168.1.10',
      mode: 'real',
      throttle_ms: 0,
    },
    pose: { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 },
    x: 120,
    y: 200,
    ...override,
  };
}
```
