# API Specification — ICP Flow Alignment

**Feature:** `icp-flow-alignment`
**Author:** @architecture
**Date:** 2026-03-16
**Status:** Approved for Implementation

---

## 1. Contract Notes

- All existing calibration endpoint paths are **unchanged**. No new route prefixes.
- This spec is **additive only**: new fields in requests/responses, new DB columns, no removed fields.
- Point clouds are never sent over JSON. Only metadata, IDs, matrices, and pose scalars travel via REST.
- `source_sensor_id` always refers to the leaf `LidarSensor` node ID (`lidar_id`), not an intermediate processing node.
- `processing_chain` is an ordered `List[str]` of DAG node IDs from leaf sensor to calibration node.
- `run_id` is a short UUID hex string (`uuid4().hex[:12]`) generated once per `trigger_calibration` call, correlating all sensor results within that run.

---

## 2. Request Schemas

### 2.1 `POST /api/v1/calibration/{node_id}/trigger`

```yaml
TriggerCalibrationRequest:
  type: object
  properties:
    reference_sensor_id:
      type: string
      nullable: true
      description: >
        Leaf sensor ID (lidar_id) to use as the fixed reference (target) cloud.
        If omitted, the first sensor seen in the buffer is used.
    source_sensor_ids:
      type: array
      items:
        type: string
      nullable: true
      description: >
        Leaf sensor IDs (lidar_id values) to align toward the reference.
        If omitted, all buffered sensors except the reference are used.
    sample_frames:
      type: integer
      minimum: 1
      default: 5
      description: >
        Number of recent buffered frames to aggregate per sensor before running ICP.
        Higher values produce denser, more robust alignment clouds.
  additionalProperties: false
```

**HTTP Responses:**

| Code | Condition |
|---|---|
| `200` | Registration pipeline completed for all requested sensors |
| `400` | `reference_sensor_id` has no buffered data, or no source sensors available |
| `404` | `node_id` not found in the running DAG, or node is not a `CalibrationNode` |
| `409` | A calibration run is already in progress on this node |
| `500` | Unexpected ICP or Open3D error |

---

### 2.2 `POST /api/v1/calibration/{node_id}/accept`

```yaml
AcceptCalibrationRequest:
  type: object
  properties:
    sensor_ids:
      type: array
      items:
        type: string
      nullable: true
      description: >
        Leaf sensor IDs to accept. Null or omitted means accept all pending.
  additionalProperties: false
```

**HTTP Responses:**

| Code | Condition |
|---|---|
| `200` | Calibration accepted and sensor configs updated; DAG reload triggered |
| `400` | No pending calibration or sensor_ids not found in pending set |
| `404` | node_id not found |

---

### 2.3 `POST /api/v1/calibration/{node_id}/reject`

No request body changes.

---

### 2.4 `GET /api/v1/calibration/history/{sensor_id}`

```yaml
query parameters:
  limit:
    type: integer
    default: 10
  source_sensor_id:
    type: string
    nullable: true
    description: >
      NEW. Filter history records by canonical leaf sensor ID.
      Useful when sensor_id in the path is an intermediate node that
      previously forwarded frames to the calibration node.
  run_id:
    type: string
    nullable: true
    description: >
      NEW. Filter history to a single calibration run (all sensors in that run).
```

---

## 3. Response Schemas

### 3.1 `CalibrationTriggerResponse`

```yaml
CalibrationTriggerResponse:
  type: object
  required: [success, run_id, results, pending_approval]
  properties:
    success:
      type: boolean
    run_id:
      type: string
      description: >
        Short UUID hex string identifying this calibration run.
        All per-sensor results share this run_id.
      example: "a3f8b1c20d44"
    results:
      type: object
      description: >
        Keys are leaf sensor IDs (source_sensor_id / lidar_id values).
      additionalProperties:
        $ref: '#/components/schemas/CalibrationSensorResult'
    pending_approval:
      type: boolean
      description: True unless auto_save is enabled and all sensors exceeded min_fitness.
```

### 3.2 `CalibrationSensorResult`

```yaml
CalibrationSensorResult:
  type: object
  properties:
    fitness:
      type: number
      format: float
      nullable: true
    rmse:
      type: number
      format: float
      nullable: true
    quality:
      type: string
      nullable: true
      enum: [excellent, good, poor]
    stages_used:
      type: array
      items:
        type: string
      description: e.g. ["global", "icp"] or ["icp"]
    pose_before:
      type: object
      nullable: true
      description: Previous 6-DOF pose {x, y, z, roll, pitch, yaw}
      properties:
        x: {type: number}
        y: {type: number}
        z: {type: number}
        roll: {type: number}
        pitch: {type: number}
        yaw: {type: number}
    pose_after:
      type: object
      nullable: true
      description: New calibrated 6-DOF pose {x, y, z, roll, pitch, yaw}
      properties:
        x: {type: number}
        y: {type: number}
        z: {type: number}
        roll: {type: number}
        pitch: {type: number}
        yaw: {type: number}
    # --- NEW traceability fields ---
    source_sensor_id:
      type: string
      nullable: true
      description: >
        Canonical leaf LidarSensor node ID (lidar_id).
        This is always the node whose pose config will be updated on accept.
    processing_chain:
      type: array
      items:
        type: string
      description: >
        Ordered list of DAG node IDs that the source cloud traversed before
        arriving at the calibration node.
        Example: ["sensor-uuid-A", "crop-node-1", "downsample-node-2", "calib-node-1"]
    auto_saved:
      type: boolean
      default: false
```

### 3.3 `AcceptCalibrationResponse`

```yaml
AcceptCalibrationResponse:
  type: object
  properties:
    success:
      type: boolean
    run_id:
      type: string
      nullable: true
      description: run_id of the accepted calibration batch.
    accepted:
      type: array
      items:
        type: string
      description: Leaf sensor IDs whose poses were updated.
    remaining_pending:
      type: array
      items:
        type: string
      description: Leaf sensor IDs still pending approval after this accept call.
```

### 3.4 `RejectCalibrationResponse`

```yaml
RejectCalibrationResponse:
  type: object
  properties:
    success:
      type: boolean
    rejected:
      type: array
      items:
        type: string
      description: Leaf sensor IDs whose pending results were discarded.
```

### 3.5 `CalibrationHistoryRecord` (extended)

```yaml
CalibrationHistoryRecord:
  type: object
  properties:
    id:
      type: string
    sensor_id:
      type: string
      description: >
        The key used internally (may be a processing node ID for legacy records).
    source_sensor_id:
      type: string
      nullable: true
      description: >
        NEW. Canonical leaf LidarSensor node ID. For records created before
        this feature, this field is null.
    processing_chain:
      type: array
      items:
        type: string
      description: >
        NEW. DAG traversal path for the calibration cloud. Empty list for
        legacy records.
    run_id:
      type: string
      nullable: true
      description: >
        NEW. Groups all sensor records from the same trigger_calibration call.
    reference_sensor_id:
      type: string
    timestamp:
      type: string
      format: date-time
    accepted:
      type: boolean
    fitness:
      type: number
      format: float
      nullable: true
    rmse:
      type: number
      format: float
      nullable: true
    quality:
      type: string
      nullable: true
    stages_used:
      type: array
      items:
        type: string
    pose_before:
      type: object
      additionalProperties: true
    pose_after:
      type: object
      additionalProperties: true
    transformation_matrix:
      type: array
      nullable: true
      items:
        type: array
        items:
          type: number
    notes:
      type: string
```

### 3.6 `CalibrationHistoryResponse`

```yaml
CalibrationHistoryResponse:
  type: object
  properties:
    sensor_id:
      type: string
    history:
      type: array
      items:
        $ref: '#/components/schemas/CalibrationHistoryRecord'
```

### 3.7 `CalibrationStatsResponse` (unchanged)

No change to the statistics response schema.

---

## 4. Node Status Payload (Non-REST, `system_status` WebSocket)

The `CalibrationNode.get_status()` return value is broadcast over the `system_status` topic. After this feature, pending results include traceability fields:

```json
{
  "id": "calib-node-uuid",
  "name": "ICP Calibration",
  "type": "calibration",
  "enabled": true,
  "reference_sensor": "sensor-uuid-B",
  "source_sensors": ["sensor-uuid-A"],
  "buffered_frames": {
    "sensor-uuid-A": 30,
    "sensor-uuid-B": 30
  },
  "last_calibration_time": "2026-03-16T10:42:00.123Z",
  "has_pending": true,
  "pending_results": {
    "sensor-uuid-A": {
      "fitness": 0.93,
      "rmse": 0.012,
      "quality": "excellent",
      "source_sensor_id": "sensor-uuid-A",
      "processing_chain": ["sensor-uuid-A", "crop-node-1", "calib-node-uuid"]
    }
  }
}
```

Note: `buffered_frames` changes from `List[str]` (current) to `Dict[str, int]` (count per sensor ID) so the frontend can show buffer fill levels.

---

## 5. Sample Payloads

### 5.1 Trigger request — minimal (all defaults)

```json
{
  "sample_frames": 5
}
```

### 5.2 Trigger request — explicit sensors

```json
{
  "reference_sensor_id": "sensor-uuid-B",
  "source_sensor_ids": ["sensor-uuid-A"],
  "sample_frames": 10
}
```

### 5.3 Trigger response — direct sensor wiring (no intermediate nodes)

```json
{
  "success": true,
  "run_id": "a3f8b1c20d44",
  "results": {
    "sensor-uuid-A": {
      "fitness": 0.91,
      "rmse": 0.018,
      "quality": "good",
      "stages_used": ["global", "icp"],
      "pose_before": {"x": 0.0, "y": 0.0, "z": 0.5, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
      "pose_after":  {"x": 0.3, "y": 0.1, "z": 0.5, "roll": 0.2, "pitch": 0.0, "yaw": 1.5},
      "source_sensor_id": "sensor-uuid-A",
      "processing_chain": ["sensor-uuid-A", "calib-node-uuid"],
      "auto_saved": false
    }
  },
  "pending_approval": true
}
```

### 5.4 Trigger response — sensor behind crop + downsample nodes

```json
{
  "success": true,
  "run_id": "b7d2e9a01f55",
  "results": {
    "sensor-uuid-A": {
      "fitness": 0.95,
      "rmse": 0.009,
      "quality": "excellent",
      "stages_used": ["icp"],
      "pose_before": {"x": 0.0, "y": 0.0, "z": 0.5, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
      "pose_after":  {"x": 0.28, "y": 0.05, "z": 0.5, "roll": 0.1, "pitch": 0.0, "yaw": 1.4},
      "source_sensor_id": "sensor-uuid-A",
      "processing_chain": ["sensor-uuid-A", "crop-node-1", "downsample-node-2", "calib-node-uuid"],
      "auto_saved": false
    }
  },
  "pending_approval": true
}
```

### 5.5 Accept response

```json
{
  "success": true,
  "run_id": "b7d2e9a01f55",
  "accepted": ["sensor-uuid-A"],
  "remaining_pending": []
}
```

### 5.6 History record — new format

```json
{
  "id": "rec-uuid-001",
  "sensor_id": "sensor-uuid-A",
  "source_sensor_id": "sensor-uuid-A",
  "processing_chain": ["sensor-uuid-A", "crop-node-1", "downsample-node-2", "calib-node-uuid"],
  "run_id": "b7d2e9a01f55",
  "reference_sensor_id": "sensor-uuid-B",
  "timestamp": "2026-03-16T10:42:00.123Z",
  "accepted": true,
  "fitness": 0.95,
  "rmse": 0.009,
  "quality": "excellent",
  "stages_used": ["icp"],
  "pose_before": {"x": 0.0, "y": 0.0, "z": 0.5, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
  "pose_after":  {"x": 0.28, "y": 0.05, "z": 0.5, "roll": 0.1, "pitch": 0.0, "yaw": 1.4},
  "transformation_matrix": [
    [0.999, -0.025, 0.002, 0.28],
    [0.025,  0.999, 0.001, 0.05],
    [-0.002, -0.001, 1.000, 0.00],
    [0.000,  0.000, 0.000, 1.00]
  ],
  "notes": ""
}
```

### 5.7 History record — legacy format (pre-feature, backward compat)

```json
{
  "id": "rec-uuid-legacy",
  "sensor_id": "sensor-uuid-A",
  "source_sensor_id": null,
  "processing_chain": [],
  "run_id": null,
  "reference_sensor_id": "sensor-uuid-B",
  "timestamp": "2026-01-01T08:00:00.000Z",
  "accepted": true,
  "fitness": 0.87,
  "rmse": 0.031,
  "quality": "good",
  "stages_used": ["global", "icp"],
  "pose_before": {"x": 0.0, "y": 0.0, "z": 0.5, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
  "pose_after":  {"x": 0.25, "y": 0.08, "z": 0.5, "roll": 0.1, "pitch": 0.0, "yaw": 1.3},
  "transformation_matrix": null,
  "notes": ""
}
```

---

## 6. Payload Key Reference for DAG Nodes

All DAG nodes forwarding data through the pipeline MUST pass these keys unchanged unless they are the originating sensor:

| Key | Mutated by | Rule |
|---|---|---|
| `lidar_id` | Source worker only | Never overwritten by intermediate nodes |
| `node_id` | Each forwarding node | Set to `self.id` before calling `forward_data` |
| `points` | Any processing node | May be transformed/filtered; shape must remain `(N, 3+)` |
| `timestamp` | Source worker only | Never changed downstream |
| `processing_chain` | Each forwarding node | Append `self.id`; do not replace the list |

---

## 7. Error Details

| HTTP Code | `detail` string pattern | Cause |
|---|---|---|
| `400` | `"Reference sensor {id} has no buffered data"` | Node has not received frames from the reference sensor |
| `400` | `"No source sensors to calibrate"` | Only one sensor is buffered or source list is empty |
| `400` | `"Source sensor {id} has no buffered data"` | Explicit sensor_id given but not in buffer |
| `404` | `"Node {id} not found"` | node_id not in `node_manager.nodes` |
| `400` | `"Node {id} is not a calibration node (type: …)"` | node_id points to wrong node type |
| `409` | `"Calibration already running on node {id}"` | Concurrent trigger call guard (if implemented) |
| `500` | `"Calibration failed: {detail}"` | Unexpected exception from Open3D or numpy |
