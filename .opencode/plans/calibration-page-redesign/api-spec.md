# API Specification: Calibration Page Redesign

**Feature:** `calibration-page-redesign`
**Base URL:** `/api/v1`
**Author:** Architecture

---

## Overview

This document specifies all API endpoints consumed by the calibration page redesign. Changes are clearly marked. The frontend MUST mock all responses from this spec during parallel development.

### Endpoint Index

| # | Endpoint | Method | Status |
|---|---|---|---|
| 1 | `/calibration/{node_id}/status` | GET | **NEW** |
| 2 | `/calibration/{node_id}/trigger` | POST | Modified (sample_frames default) |
| 3 | `/calibration/{node_id}/accept` | POST | Unchanged |
| 4 | `/calibration/{node_id}/reject` | POST | **Modified** (response schema fix) |
| 5 | `/calibration/history/{sensor_id}` | GET | **Modified** (add `run_id` param) |
| 6 | `/calibration/rollback/{sensor_id}` | POST | **Modified** (record_id replaces timestamp) |
| 7 | `/calibration/statistics/{sensor_id}` | GET | Unchanged |
| WS | `/ws/system_status` | WebSocket | Unchanged |

---

## 1. NEW: Get Calibration Node Status

**Endpoint:** `GET /api/v1/calibration/{node_id}/status`

**Purpose:** 2-second polling endpoint for the calibration page. Returns complete workflow state including pending calibration results with pose data, transformation matrix, and quality metrics.

**Called by:** `CalibrationStoreService._fetchStatus(nodeId)` on a 2-second interval.

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `node_id` | `string` | Calibration node ID |

### Response: `200 OK`

```json
{
  "node_id": "abc12345def6",
  "node_name": "ICP Calibration",
  "enabled": true,
  "calibration_state": "pending",
  "quality_good": true,
  "reference_sensor_id": "sensor-ref-uuid-1234",
  "source_sensor_ids": ["sensor-src-uuid-5678"],
  "buffered_frames": {
    "sensor-ref-uuid-1234": 28,
    "sensor-src-uuid-5678": 25
  },
  "last_calibration_time": "2026-03-22T14:30:00.000Z",
  "pending_results": {
    "sensor-src-uuid-5678": {
      "fitness": 0.921,
      "rmse": 0.00312,
      "quality": "excellent",
      "quality_good": true,
      "source_sensor_id": "sensor-src-uuid-5678",
      "processing_chain": ["sensor-src-uuid-5678", "crop-node-id", "abc12345def6"],
      "pose_before": {
        "x": 1500.0,
        "y": -200.0,
        "z": 0.0,
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 45.0
      },
      "pose_after": {
        "x": 1502.3,
        "y": -198.7,
        "z": 1.1,
        "roll": 0.12,
        "pitch": -0.08,
        "yaw": 45.31
      },
      "transformation_matrix": [
        [0.9999, -0.0054, 0.0021, 0.002300],
        [0.0054,  0.9999, 0.0008, 0.001300],
        [-0.0021,-0.0008, 1.0000, 0.000011],
        [0.0,     0.0,    0.0,    1.0     ]
      ]
    }
  }
}
```

### Response Fields

| Field | Type | Unit | Description |
|---|---|---|---|
| `node_id` | `string` | — | Calibration DAG node ID |
| `node_name` | `string` | — | Human-readable node name |
| `enabled` | `boolean` | — | Whether the node is enabled |
| `calibration_state` | `string` | — | `"idle"` or `"pending"` |
| `quality_good` | `boolean \| null` | — | `true` if all pending results pass quality threshold; `null` if no pending |
| `reference_sensor_id` | `string \| null` | — | First-seen sensor (ICP target/reference) |
| `source_sensor_ids` | `string[]` | — | Sensors to be calibrated (ICP source) |
| `buffered_frames` | `Record<string, number>` | frames | Frame count per sensor_id |
| `last_calibration_time` | `string \| null` | ISO-8601 | When last calibration was triggered |
| `pending_results` | `Record<string, PendingCalibrationResult>` | — | Keyed by source_sensor_id |

### `PendingCalibrationResult` Fields

| Field | Type | Unit | Description |
|---|---|---|---|
| `fitness` | `number` | 0–1 | ICP fitness score (higher = better) |
| `rmse` | `number` | **meters** | Root mean squared error |
| `quality` | `string` | — | `"excellent"` / `"good"` / `"poor"` |
| `quality_good` | `boolean` | — | `fitness >= min_fitness_to_save` threshold |
| `source_sensor_id` | `string` | — | Canonical leaf LiDAR sensor ID |
| `processing_chain` | `string[]` | — | DAG path: `[sensor, ...intermediate, calibration_node]` |
| `pose_before.x/y/z` | `number` | **millimeters** | Position before calibration |
| `pose_before.roll/pitch/yaw` | `number` | **degrees** | Rotation before calibration |
| `pose_after.x/y/z` | `number` | **millimeters** | Position after calibration |
| `pose_after.roll/pitch/yaw` | `number` | **degrees** | Rotation after calibration |
| `transformation_matrix` | `number[][]` | mixed (see below) | 4×4 homogeneous transform |

**Transformation matrix units:**
- Rows 0–2, Cols 0–2: rotation (dimensionless)
- Rows 0–2, Col 3: translation in **meters** (raw ICP output, NOT converted to mm)

### Errors

| Code | Description |
|---|---|
| `404` | Node not found |
| `400` | Node is not a calibration node |

### Mock Data (Frontend Dev)

```typescript
// calibration-mock.ts
export const MOCK_CALIBRATION_STATUS_IDLE: CalibrationNodeStatusResponse = {
  node_id: 'mock-cal-node-001',
  node_name: 'ICP Calibration',
  enabled: true,
  calibration_state: 'idle',
  quality_good: null,
  reference_sensor_id: 'mock-sensor-ref',
  source_sensor_ids: ['mock-sensor-src'],
  buffered_frames: { 'mock-sensor-ref': 28, 'mock-sensor-src': 25 },
  last_calibration_time: null,
  pending_results: {}
};

export const MOCK_CALIBRATION_STATUS_PENDING: CalibrationNodeStatusResponse = {
  node_id: 'mock-cal-node-001',
  node_name: 'ICP Calibration',
  enabled: true,
  calibration_state: 'pending',
  quality_good: true,
  reference_sensor_id: 'mock-sensor-ref',
  source_sensor_ids: ['mock-sensor-src'],
  buffered_frames: { 'mock-sensor-ref': 28, 'mock-sensor-src': 25 },
  last_calibration_time: '2026-03-22T14:30:00.000Z',
  pending_results: {
    'mock-sensor-src': {
      fitness: 0.921,
      rmse: 0.00312,
      quality: 'excellent',
      quality_good: true,
      source_sensor_id: 'mock-sensor-src',
      processing_chain: ['mock-sensor-src', 'mock-cal-node-001'],
      pose_before: { x: 1500.0, y: -200.0, z: 0.0, roll: 0.0, pitch: 0.0, yaw: 45.0 },
      pose_after:  { x: 1502.3, y: -198.7, z: 1.1, roll: 0.12, pitch: -0.08, yaw: 45.31 },
      transformation_matrix: [
        [0.9999, -0.0054,  0.0021, 0.0023],
        [0.0054,  0.9999,  0.0008, 0.0013],
        [-0.0021, -0.0008, 1.0,    0.0000],
        [0.0,     0.0,     0.0,    1.0   ]
      ]
    }
  }
};
```

---

## 2. Trigger Calibration (Modified: default fix)

**Endpoint:** `POST /api/v1/calibration/{node_id}/trigger`

**Change:** `sample_frames` default corrected from `1` to `5`.

### Request Body

```json
{
  "reference_sensor_id": null,
  "source_sensor_ids": null,
  "sample_frames": 5
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `reference_sensor_id` | `string \| null` | `null` | Override reference sensor. `null` = first-seen sensor |
| `source_sensor_ids` | `string[] \| null` | `null` | Sensors to calibrate. `null` = all non-reference sensors |
| `sample_frames` | `number` | **`5`** | Frames to aggregate per sensor (was `1`, now `5`) |

### Response: `200 OK`

```json
{
  "success": true,
  "run_id": "a1b2c3d4e5f6",
  "results": {
    "sensor-src-uuid-5678": {
      "fitness": 0.921,
      "rmse": 0.00312,
      "quality": "excellent",
      "source_sensor_id": "sensor-src-uuid-5678",
      "processing_chain": ["sensor-src-uuid-5678", "abc12345def6"]
    }
  },
  "pending_approval": true
}
```

### Errors

| Code | Description |
|---|---|
| `400` | No reference sensor data buffered / no source sensors |
| `404` | Node not found |
| `500` | ICP algorithm failure |

---

## 3. Accept Calibration (Unchanged)

**Endpoint:** `POST /api/v1/calibration/{node_id}/accept`

### Request Body

```json
{
  "sensor_ids": null
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `sensor_ids` | `string[] \| null` | `null` | Specific sensors to accept. `null` = all pending |

### Response: `200 OK`

```json
{
  "success": true,
  "accepted": ["sensor-src-uuid-5678"]
}
```

### Errors

| Code | Description |
|---|---|
| `400` | No pending calibration |
| `404` | Node not found |

---

## 4. MODIFIED: Reject Calibration (Response Schema Fix)

**Endpoint:** `POST /api/v1/calibration/{node_id}/reject`

**Change:** Response was `{"status": "success"}`. Now returns `{"success": bool, "rejected": string[]}` to match the frontend `CalibrationRejectResponse` interface.

### Request Body

No request body required (empty JSON `{}` or no body).

### Response: `200 OK` (CHANGED)

```json
{
  "success": true,
  "rejected": ["sensor-src-uuid-5678"]
}
```

| Field | Type | Description |
|---|---|---|
| `success` | `boolean` | Always `true` on 200 |
| `rejected` | `string[]` | Leaf sensor IDs whose pending results were discarded |

### Errors

| Code | Description |
|---|---|
| `404` | Node not found |
| `400` | Node is not a calibration node |

---

## 5. MODIFIED: Get Calibration History (Add `run_id` Filter)

**Endpoint:** `GET /api/v1/calibration/history/{sensor_id}`

**Change:** Added `run_id` query parameter for filtering.

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `sensor_id` | `string` | Calibration node ID (used as sensor_id for legacy compat) |

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | `number` | `10` | Max records to return |
| `source_sensor_id` | `string \| null` | `null` | Filter by leaf sensor ID |
| `run_id` | `string \| null` | `null` | **NEW** — Filter by calibration run ID |

### Response: `200 OK`

```json
{
  "sensor_id": "abc12345def6",
  "history": [
    {
      "id": "record-uuid-hex-001",
      "sensor_id": "sensor-src-uuid-5678",
      "reference_sensor_id": "sensor-ref-uuid-1234",
      "timestamp": "2026-03-22T14:30:00.000Z",
      "accepted": true,
      "accepted_at": "2026-03-22T14:32:15.000Z",
      "accepted_by": null,
      "fitness": 0.921,
      "rmse": 0.00312,
      "quality": "excellent",
      "stages_used": ["global", "icp"],
      "pose_before": {
        "x": 1500.0, "y": -200.0, "z": 0.0,
        "roll": 0.0, "pitch": 0.0, "yaw": 45.0
      },
      "pose_after": {
        "x": 1502.3, "y": -198.7, "z": 1.1,
        "roll": 0.12, "pitch": -0.08, "yaw": 45.31
      },
      "transformation_matrix": [
        [0.9999, -0.0054,  0.0021, 0.0023],
        [0.0054,  0.9999,  0.0008, 0.0013],
        [-0.0021, -0.0008, 1.0,    0.0000],
        [0.0,     0.0,     0.0,    1.0   ]
      ],
      "notes": "",
      "source_sensor_id": "sensor-src-uuid-5678",
      "processing_chain": ["sensor-src-uuid-5678", "abc12345def6"],
      "run_id": "a1b2c3d4e5f6",
      "node_id": "abc12345def6",
      "rollback_source_id": null,
      "registration_method": {
        "method": "icp",
        "stages": ["global", "icp"]
      }
    }
  ]
}
```

### History Record Fields

| Field | Type | Unit | Description |
|---|---|---|---|
| `id` | `string` | — | UUID hex primary key |
| `sensor_id` | `string` | — | Sensor that was calibrated |
| `reference_sensor_id` | `string` | — | Reference sensor |
| `timestamp` | `string` | ISO-8601 | When calibration was triggered |
| `accepted` | `boolean` | — | Whether user accepted |
| `accepted_at` | `string \| null` | ISO-8601 | When user accepted (**new field**) |
| `accepted_by` | `string \| null` | — | Reserved for auth (**new field**) |
| `fitness` | `number` | 0–1 | ICP fitness |
| `rmse` | `number` | **meters** | ICP RMSE |
| `quality` | `string` | — | `"excellent"` / `"good"` / `"poor"` |
| `stages_used` | `string[]` | — | Registration stages |
| `pose_before.x/y/z` | `number` | **mm** | Pre-calibration position |
| `pose_before.roll/pitch/yaw` | `number` | **°** | Pre-calibration rotation |
| `pose_after.x/y/z` | `number` | **mm** | Post-calibration position |
| `pose_after.roll/pitch/yaw` | `number` | **°** | Post-calibration rotation |
| `transformation_matrix` | `number[][]` | mixed | 4×4 matrix (translation in **meters**) |
| `source_sensor_id` | `string \| null` | — | Canonical leaf sensor ID |
| `processing_chain` | `string[]` | — | DAG path |
| `run_id` | `string \| null` | — | Correlates multi-sensor runs |
| `node_id` | `string \| null` | — | Calibration node ID (**new field**) |
| `rollback_source_id` | `string \| null` | — | ID of record that was rolled back (**new field**) |
| `registration_method` | `object \| null` | — | `{method, stages}` (**new field**) |

### Errors

| Code | Description |
|---|---|
| `500` | Database error |

---

## 6. MODIFIED: Rollback Calibration (Record ID replaces Timestamp)

**Endpoint:** `POST /api/v1/calibration/rollback/{sensor_id}`

**Change:** Request body was `{"timestamp": "..."}`. Now uses `{"record_id": "..."}` for reliable PK-based lookup.

**Rationale:** Timestamps are string-based and could collide. `record_id` is a UUID hex (globally unique PK).

**Rollback semantics:** Works for ANY accepted history entry, not just the most recent. A new history record is created to record the rollback action (`rollback_source_id` is set). DAG reload is triggered.

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `sensor_id` | `string` | Sensor node ID to rollback |

### Request Body (CHANGED)

```json
{
  "record_id": "record-uuid-hex-001"
}
```

| Field | Type | Description |
|---|---|---|
| `record_id` | `string` | ID (PK) of the accepted history record to restore. Must be an accepted record (`accepted === true`). |

### Response: `200 OK`

```json
{
  "success": true,
  "sensor_id": "sensor-src-uuid-5678",
  "restored_to": "2026-03-22T14:30:00.000Z",
  "new_record_id": "rollback-record-uuid-hex"
}
```

| Field | Type | Description |
|---|---|---|
| `success` | `boolean` | Always `true` on 200 |
| `sensor_id` | `string` | Sensor that was rolled back |
| `restored_to` | `string` | ISO-8601 timestamp of the source record |
| `new_record_id` | `string` | ID of the new rollback history record created |

### Errors

| Code | Description |
|---|---|
| `404` | Sensor or record not found |
| `400` | Record is not accepted (cannot rollback to unaccepted calibration) |
| `500` | Rollback operation failed |

---

## 7. Get Calibration Statistics (Unchanged)

**Endpoint:** `GET /api/v1/calibration/statistics/{sensor_id}`

### Response: `200 OK`

```json
{
  "sensor_id": "abc12345def6",
  "total_attempts": 12,
  "accepted_count": 8,
  "avg_fitness": 0.887,
  "avg_rmse": 0.00421,
  "best_fitness": 0.961,
  "best_rmse": 0.00198
}
```

---

## 8. WebSocket: System Status (Unchanged)

**Endpoint:** `WS /api/v1/ws/system_status`

**Used by:** `StatusWebSocketService` → `CalibrationComponent` (status badge), `NodeCalibrationControls` (status badge only)

### Message Format (JSON)

```json
{
  "nodes": [
    {
      "node_id": "abc12345def6",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "calibrating",
        "value": true,
        "color": "blue"
      },
      "timestamp": 1711118400.0
    }
  ]
}
```

### Calibration-Specific `application_state` Values

| `label` | `value` | `color` | Meaning |
|---|---|---|---|
| `"calibrating"` | `false` | `"gray"` | Node running, no pending calibration |
| `"calibrating"` | `true` | `"blue"` | Calibration pending approval |

**Note:** `operational_state` is `"STOPPED"` when the node is disabled. The `application_state` field is absent or `null` in that case.

---

## 9. Polling Strategy

The frontend uses two parallel data streams:

### Stream 1: WebSocket Status (passive, always-on)
```
Endpoint: WS /ws/system_status
Consumer: StatusWebSocketService
Cadence: Push (server-initiated on any status change)
Used for: Lightweight status badges in CalibrationComponent list cards and NodeCalibrationControls
Data: operational_state + calibrating boolean
```

### Stream 2: HTTP Polling (active, page-scoped)
```
Endpoint: GET /api/v1/calibration/{node_id}/status
Consumer: CalibrationStoreService
Cadence: Every 2000ms via setInterval
Start: When CalibrationViewerComponent or CalibrationComponent activates a node
Stop: When component is destroyed (ngOnDestroy) or user navigates away
Used for: Full workflow state in CalibrationViewerComponent and CalibrationComponent detail
Data: calibration_state, pending_results (with poses + matrix), buffered_frames
```

### Polling Lifecycle

```
CalibrationViewerComponent.ngOnInit / constructor effect
  → calibrationStore.startPolling(nodeId)
    → immediate fetch + setInterval(2000)

CalibrationViewerComponent.ngOnDestroy
  → calibrationStore.stopPolling()
    → clearInterval

CalibrationComponent (list page)
  → startPolling for EACH calibration node in the list
  → stopPolling for all on destroy
```

### Request Ordering (Initial Page Load)

```
1. GET /api/v1/calibration/{node_id}/status   ← immediate on enter
2. GET /api/v1/calibration/history/{id}?limit=50  ← eager load for history accordion
3. setInterval → repeat (1) every 2s
```

### Stale Data Handling

- If a polling request fails (network error), **silently ignore** and retain last known state
- Show a "Last updated" timestamp from `last_calibration_time` to indicate data freshness
- WebSocket status badge remains authoritative for operational state

---

## 10. Frontend Mock Service

During backend development, the frontend must inject a mock for `CalibrationApiService.getNodeStatus()`:

```typescript
// In CalibrationApiService (or a test double):
async getNodeStatus(nodeId: string): Promise<CalibrationNodeStatusResponse> {
  // Return MOCK_CALIBRATION_STATUS_PENDING after 1 trigger, then MOCK_CALIBRATION_STATUS_IDLE
  return MOCK_CALIBRATION_STATUS_IDLE;
}
```

For rollback, the mock must accept `record_id` (not `timestamp`):
```typescript
async rollback(sensorId: string, request: { record_id: string }): Promise<CalibrationRollbackResponse> {
  return { success: true, sensor_id: sensorId, restored_to: new Date().toISOString(), new_record_id: 'mock-rollback-id' };
}
```
