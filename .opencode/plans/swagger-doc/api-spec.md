# Swagger API Documentation — API Contract

> **Scope**: REST endpoints only. WebSocket endpoints (`ws://…/ws/{topic}`, `ws://…/logs/ws`)
> are excluded from this specification — they are covered by the LIDR binary protocol docs.
> All paths are prefixed with `/api/v1`.

---

## Global Metadata

```yaml
openapi: "3.1.0"
info:
  title: "LiDAR Standalone API"
  version: "1.3.0"
  description: |
    Real-time point-cloud processing pipeline REST interface.
    Binary streaming is served over the LIDR WebSocket protocol (separate docs).
  contact:
    name: "LiDAR Standalone Team"
  license:
    name: "Proprietary"
servers:
  - url: "http://localhost:8005"
    description: "Local development server"
```

---

## Tag Groups

| Tag             | Description                                                         |
|-----------------|---------------------------------------------------------------------|
| `System`        | Lifecycle control and health checks for the pipeline engine         |
| `Nodes`         | CRUD and runtime status of DAG processing nodes                     |
| `Edges`         | Directed connections defining data-flow topology                    |
| `Configuration` | Full-graph import/export and validation                             |
| `Recordings`    | Start, stop, list, and download point-cloud recordings              |
| `Logs`          | Paginated application log access and download                       |
| `Calibration`   | ICP multi-sensor calibration trigger, accept/reject, rollback       |
| `LiDAR`         | SICK device profiles and configuration pre-flight validation        |
| `Assets`        | Static image assets from the lidar module bundle                    |
| `Topics`        | WebSocket topic introspection and single-frame HTTP capture         |

---

## Shared Schemas

### `StatusResponse`
```json
{ "status": "success" }
```

### `UpsertResponse`
```json
{ "status": "success", "id": "a1b2c3d4e5f6..." }
```

### `ErrorDetail`
```json
{ "detail": "Human-readable error message" }
```

---

## System — `GET /api/v1/status`

**Tag**: `System`  
**Summary**: Get pipeline engine status

### Response `200 OK`

```json
{
  "is_running": true,
  "active_sensors": ["node-uuid-1", "node-uuid-2"],
  "version": "1.3.0"
}
```

| Field            | Type            | Description                           |
|------------------|-----------------|---------------------------------------|
| `is_running`     | `bool`          | Whether the DAG engine is active      |
| `active_sensors` | `list[str]`     | IDs of all running node instances     |
| `version`        | `str`           | Application version string            |

---

## System — `POST /api/v1/start`

**Tag**: `System`  
**Summary**: Start the pipeline engine

### Response `200 OK`

```json
{ "status": "success", "is_running": true }
```

---

## System — `POST /api/v1/stop`

**Tag**: `System`  
**Summary**: Stop the pipeline engine

### Response `200 OK`

```json
{ "status": "success", "is_running": false }
```

---

## Nodes — `GET /api/v1/nodes`

**Tag**: `Nodes`  
**Summary**: List all configured nodes

### Response `200 OK` — `list[NodeRecord]`

```json
[
  {
    "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    "name": "MultiScan Left",
    "type": "sensor",
    "category": "sensor",
    "enabled": true,
    "config": {
      "lidar_type": "multiscan",
      "hostname": "192.168.1.10",
      "udp_receiver_ip": "192.168.1.100"
    },
    "x": 120.0,
    "y": 200.0
  }
]
```

---

## Nodes — `GET /api/v1/nodes/definitions`

**Tag**: `Nodes`  
**Summary**: List all registered node type definitions

### Response `200 OK` — `list[NodeDefinition]`

```json
[
  {
    "type": "sensor",
    "display_name": "SICK LiDAR Sensor",
    "category": "sensor",
    "description": "Real-time SICK LiDAR point-cloud source node",
    "icon": "sensors",
    "properties": [
      {
        "name": "lidar_type",
        "label": "LiDAR Model",
        "type": "select",
        "required": true,
        "options": [{"value": "multiscan", "label": "multiScan"}]
      }
    ],
    "inputs": [],
    "outputs": [{"id": "out", "label": "Point Cloud", "data_type": "pointcloud"}]
  }
]
```

---

## Nodes — `GET /api/v1/nodes/{node_id}`

**Tag**: `Nodes`  
**Summary**: Get a single node configuration

### Path Parameters

| Name      | Type   | Required | Description           |
|-----------|--------|----------|-----------------------|
| `node_id` | string | yes      | Node UUID or short ID |

### Responses

| Code | Description       |
|------|-------------------|
| `200`| Node record       |
| `404`| Node not found    |

### Response `200 OK` — `NodeRecord` (same shape as list item above)

---

## Nodes — `POST /api/v1/nodes`

**Tag**: `Nodes`  
**Summary**: Create or update a node (upsert)

### Request Body — `NodeCreateUpdate`

```json
{
  "name": "MultiScan Left",
  "type": "sensor",
  "category": "sensor",
  "enabled": true,
  "config": {
    "lidar_type": "multiscan",
    "hostname": "192.168.1.10",
    "udp_receiver_ip": "192.168.1.100",
    "port": 2115
  },
  "x": 120.0,
  "y": 200.0
}
```

| Field      | Type            | Required | Description                              |
|------------|-----------------|----------|------------------------------------------|
| `id`       | `string\|null`  | no       | If omitted, a UUID is auto-generated     |
| `name`     | `string`        | yes      |                                          |
| `type`     | `string`        | yes      | Matches a registered node type           |
| `category` | `string`        | yes      | `"sensor"`, `"fusion"`, `"operation"`    |
| `enabled`  | `boolean`       | no       | Default `true`                           |
| `config`   | `object`        | no       | Type-specific configuration dictionary   |
| `x`        | `number\|null`  | no       | Canvas X position                        |
| `y`        | `number\|null`  | no       | Canvas Y position                        |

### Response `200 OK` — `UpsertResponse`

```json
{ "status": "success", "id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" }
```

---

## Nodes — `PUT /api/v1/nodes/{node_id}/enabled`

**Tag**: `Nodes`  
**Summary**: Toggle node enabled state

### Request Body — `NodeStatusToggle`

```json
{ "enabled": false }
```

### Responses

| Code | Description    |
|------|----------------|
| `200`| Success        |

### Response `200 OK` — `StatusResponse`

---

## Nodes — `DELETE /api/v1/nodes/{node_id}`

**Tag**: `Nodes`  
**Summary**: Delete a node and its connected edges

Removes the node from the live DAG, deletes the database record, and cascades edge deletion.

### Responses

| Code | Description    |
|------|----------------|
| `200`| Deleted        |
| `404`| Node not found |

### Response `200 OK` — `StatusResponse`

---

## Nodes — `POST /api/v1/nodes/reload`

**Tag**: `Nodes`  
**Summary**: Reload entire DAG configuration from database

Stops all nodes, cleans up WebSocket topics (sending `1001 Going Away` to clients), then
rebuilds the DAG from the current database state.

### Responses

| Code | Description                                        |
|------|----------------------------------------------------|
| `200`| Reload complete                                    |
| `409`| Reload already in progress — retry after completion|

### Response `200 OK` — `StatusResponse`

### Response `409 Conflict`

```json
{
  "detail": "A configuration reload is already in progress. Please wait and retry."
}
```

---

## Nodes — `GET /api/v1/nodes/status/all`

**Tag**: `Nodes`  
**Summary**: Get runtime status for all nodes

### Response `200 OK` — `NodesStatusResponse`

```json
{
  "nodes": [
    {
      "id": "a1b2c3d4",
      "name": "MultiScan Left",
      "type": "sensor",
      "category": "sensor",
      "enabled": true,
      "running": true,
      "topic": "multiscan_left_a1b2c3d4",
      "last_frame_at": 1700000000.123,
      "frame_age_seconds": 0.05,
      "last_error": null,
      "throttle_ms": 0.0,
      "throttled_count": 0
    }
  ]
}
```

---

## Edges — `GET /api/v1/edges`

**Tag**: `Edges`  
**Summary**: List all DAG edges

### Response `200 OK` — `list[EdgeRecord]`

```json
[
  {
    "id": "edge-uuid",
    "source_node": "node-uuid-1",
    "source_port": "out",
    "target_node": "node-uuid-2",
    "target_port": "in"
  }
]
```

---

## Edges — `POST /api/v1/edges`

**Tag**: `Edges`  
**Summary**: Create a single edge

### Request Body — `EdgeCreateUpdate`

```json
{
  "source_node": "node-uuid-1",
  "source_port": "out",
  "target_node": "node-uuid-2",
  "target_port": "in"
}
```

### Response `200 OK` — `EdgeRecord`

---

## Edges — `DELETE /api/v1/edges/{edge_id}`

**Tag**: `Edges`  
**Summary**: Delete a single edge by ID

### Responses

| Code | Description     |
|------|-----------------|
| `200`| Deleted         |

### Response `200 OK`

```json
{ "status": "deleted", "id": "edge-uuid" }
```

---

## Edges — `POST /api/v1/edges/bulk`

**Tag**: `Edges`  
**Summary**: Replace all edges (full canvas save)

Replaces the entire edge table with the provided list. Used by the frontend canvas on save.

### Request Body — `list[EdgeCreateUpdate]`

### Response `200 OK` — `StatusResponse`

---

## Configuration — `GET /api/v1/config/export`

**Tag**: `Configuration`  
**Summary**: Export full node/edge configuration as a downloadable JSON file

### Responses

| Code | Description                                                    |
|------|----------------------------------------------------------------|
| `200`| `application/json` file with `Content-Disposition: attachment` |

### Response `200 OK` body shape

```json
{
  "version": "2.0",
  "nodes": [...],
  "edges": [...]
}
```

---

## Configuration — `POST /api/v1/config/import`

**Tag**: `Configuration`  
**Summary**: Import node/edge configuration from JSON

### Request Body — `ConfigurationImport`

```json
{
  "nodes": [
    {
      "name": "Sensor A",
      "type": "sensor",
      "category": "sensor",
      "enabled": true,
      "config": { "lidar_type": "multiscan", "hostname": "192.168.1.10" }
    },
    {
      "name": "Fusion",
      "type": "fusion",
      "category": "fusion",
      "enabled": true,
      "config": {}
    }
  ],
  "edges": [
    { "source_node": "sensor-id", "source_port": "out", "target_node": "fusion-id", "target_port": "in" }
  ],
  "merge": false
}
```

| Field    | Type      | Description                                     |
|----------|-----------|-------------------------------------------------|
| `nodes`  | `list`    | Node configuration objects                      |
| `edges`  | `list`    | Edge connection objects                         |
| `merge`  | `boolean` | `false` = replace all; `true` = merge with existing |

### Responses

| Code | Description               |
|------|---------------------------|
| `200`| Import success summary    |
| `400`| Invalid configuration     |

### Response `200 OK` — `ImportResponse`

```json
{
  "success": true,
  "mode": "replace",
  "imported": { "nodes": 2, "edges": 1 },
  "node_ids": ["uuid-1", "uuid-2"],
  "reloaded": true
}
```

---

## Configuration — `POST /api/v1/config/validate`

**Tag**: `Configuration`  
**Summary**: Validate configuration without importing

### Request Body — same shape as `ConfigurationImport`

### Response `200 OK` — `ValidationResponse`

```json
{
  "valid": true,
  "errors": [],
  "warnings": ["Node 'Sensor A': no lidar_type specified; defaulting to 'multiscan'"],
  "summary": { "nodes": 2, "edges": 1 }
}
```

---

## Recordings — `POST /api/v1/recordings/start`

**Tag**: `Recordings`  
**Summary**: Start recording point-cloud frames from a node

### Request Body — `StartRecordingRequest`

```json
{
  "node_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "name": "outdoor-test-run-01",
  "metadata": { "environment": "outdoor", "weather": "clear" }
}
```

| Field      | Type            | Required | Description                              |
|------------|-----------------|----------|------------------------------------------|
| `node_id`  | `string`        | yes      | ID of the active node to record          |
| `name`     | `string\|null`  | no       | Human-readable recording label           |
| `metadata` | `object\|null`  | no       | Arbitrary key-value metadata             |

### Responses

| Code | Description                          |
|------|--------------------------------------|
| `200`| Recording started                    |
| `400`| Already recording / invalid request  |
| `404`| Node not found in active graph       |
| `500`| Internal error                       |

### Response `200 OK`

```json
{
  "recording_id": "rec-uuid",
  "file_path": "recordings/rec-uuid.lidr",
  "started_at": "2025-01-01T12:00:00Z"
}
```

---

## Recordings — `POST /api/v1/recordings/{recording_id}/stop`

**Tag**: `Recordings`  
**Summary**: Stop an active recording (async finalization)

Returns immediately with `status: "stopping"`. File compression and database save happen in the
background.

### Responses

| Code | Description               |
|------|---------------------------|
| `200`| Stopping (async)          |
| `404`| Recording ID not found    |
| `500`| Internal error            |

### Response `200 OK`

```json
{
  "recording_id": "rec-uuid",
  "node_id": "a1b2c3d4",
  "status": "stopping",
  "frame_count": 1234,
  "duration_seconds": 41.2,
  "message": "Recording is stopping, finalization in progress..."
}
```

---

## Recordings — `GET /api/v1/recordings`

**Tag**: `Recordings`  
**Summary**: List recordings, optionally filtered by node

### Query Parameters

| Name      | Type            | Description             |
|-----------|-----------------|-------------------------|
| `node_id` | `string\|null`  | Filter by source node ID|

### Response `200 OK` — `ListRecordingsResponse`

```json
{
  "recordings": [
    {
      "id": "rec-uuid",
      "name": "outdoor-test-run-01",
      "node_id": "a1b2c3d4",
      "sensor_id": null,
      "file_path": "recordings/rec-uuid.lidr",
      "file_size_bytes": 10485760,
      "frame_count": 1234,
      "duration_seconds": 41.2,
      "recording_timestamp": "2025-01-01T12:00:00Z",
      "metadata": { "environment": "outdoor" },
      "thumbnail_path": null,
      "created_at": "2025-01-01T12:00:41Z"
    }
  ],
  "active_recordings": [
    {
      "recording_id": "rec-uuid-2",
      "node_id": "b2c3d4e5",
      "frame_count": 45,
      "duration_seconds": 1.5,
      "started_at": "2025-01-01T12:00:00Z",
      "metadata": null,
      "status": "recording"
    }
  ]
}
```

---

## Recordings — `GET /api/v1/recordings/{recording_id}`

**Tag**: `Recordings`  
**Summary**: Get detailed information about a recording

### Responses

| Code | Description       |
|------|-------------------|
| `200`| Recording details |
| `404`| Not found         |

### Response `200 OK` — `RecordingResponse` (same shape as list item)

---

## Recordings — `DELETE /api/v1/recordings/{recording_id}`

**Tag**: `Recordings`  
**Summary**: Delete a recording (file + database entry)

File deletion is asynchronous (background task).

### Responses

| Code | Description    |
|------|----------------|
| `200`| Deletion queued|
| `404`| Not found      |

### Response `200 OK`

```json
{ "message": "Recording rec-uuid deleted successfully" }
```

---

## Recordings — `GET /api/v1/recordings/{recording_id}/download`

**Tag**: `Recordings`  
**Summary**: Download the raw LIDR recording file

### Responses

| Code | Description                          |
|------|--------------------------------------|
| `200`| Binary file (`application/octet-stream`) |
| `404`| Recording or file not found          |

---

## Recordings — `GET /api/v1/recordings/{recording_id}/info`

**Tag**: `Recordings`  
**Summary**: Get recording viewer metadata (frame count, duration)

### Response `200 OK`

```json
{
  "id": "rec-uuid",
  "name": "outdoor-test-run-01",
  "node_id": "a1b2c3d4",
  "frame_count": 1234,
  "duration_seconds": 41.2,
  "metadata": { "environment": "outdoor" },
  "recording_timestamp": "2025-01-01T12:00:00Z"
}
```

---

## Recordings — `GET /api/v1/recordings/{recording_id}/frame/{frame_index}`

**Tag**: `Recordings`  
**Summary**: Get a single recording frame as PCD file

### Path Parameters

| Name           | Type      | Description              |
|----------------|-----------|--------------------------|
| `recording_id` | `string`  | Recording UUID           |
| `frame_index`  | `integer` | 0-based frame index      |

### Responses

| Code | Description                                        |
|------|----------------------------------------------------|
| `200`| PCD file (`application/octet-stream`)              |
| `400`| Frame index out of range                           |
| `404`| Recording or file not found                        |
| `500`| Frame read error                                   |

---

## Recordings — `GET /api/v1/recordings/{recording_id}/thumbnail`

**Tag**: `Recordings`  
**Summary**: Get recording thumbnail image (PNG)

Generates thumbnail on-demand if not pre-computed. Returns `404` if generation fails.

### Responses

| Code | Description          |
|------|----------------------|
| `200`| PNG image            |
| `404`| Thumbnail unavailable|

---

## Logs — `GET /api/v1/logs`

**Tag**: `Logs`  
**Summary**: Get paginated application log entries

### Query Parameters

| Name     | Type            | Description                                        | Default |
|----------|-----------------|----------------------------------------------------|---------|
| `level`  | `string\|null`  | Filter: `INFO`, `WARNING`, `ERROR`, `DEBUG`        | _all_   |
| `search` | `string\|null`  | Free-text search in log message                    | _none_  |
| `offset` | `integer`       | Start row from latest entry (0 = most recent)      | `0`     |
| `limit`  | `integer`       | Rows to return (max 500)                           | `100`   |

### Response `200 OK` — `list[LogEntry]`

```json
[
  {
    "timestamp": "2025-01-01 12:00:00",
    "level": "INFO",
    "module": "app.services.nodes.orchestrator",
    "message": "Config reload complete."
  }
]
```

---

## Logs — `GET /api/v1/download`

**Tag**: `Logs`  
**Summary**: Download filtered log entries as a plain-text file

### Query Parameters

| Name     | Type            | Description             |
|----------|-----------------|-------------------------|
| `level`  | `string\|null`  | Log level filter        |
| `search` | `string\|null`  | Message search filter   |

### Responses

| Code | Description                                     |
|------|-------------------------------------------------|
| `200`| `text/plain` streaming download                 |
| `404`| Log file not found on disk                      |

---

## Calibration — `POST /api/v1/calibration/{node_id}/trigger`

**Tag**: `Calibration`  
**Summary**: Trigger ICP calibration on buffered sensor data

### Path Parameters

| Name      | Type     | Description             |
|-----------|----------|-------------------------|
| `node_id` | `string` | Calibration node ID     |

### Request Body — `TriggerCalibrationRequest`

```json
{
  "reference_sensor_id": "sensor-uuid-ref",
  "source_sensor_ids": ["sensor-uuid-a", "sensor-uuid-b"],
  "sample_frames": 5
}
```

| Field                  | Type                | Description                                              |
|------------------------|---------------------|----------------------------------------------------------|
| `reference_sensor_id`  | `string\|null`      | Fixed reference sensor (null = auto-select)             |
| `source_sensor_ids`    | `list[string]\|null`| Sensors to align (null = all inputs)                    |
| `sample_frames`        | `integer`           | Number of frames to average (default `1`)                |

### Responses

| Code | Description                              |
|------|------------------------------------------|
| `200`| Calibration results                      |
| `400`| Invalid parameters or insufficient data  |
| `404`| Node not found                           |
| `500`| Calibration algorithm error              |

### Response `200 OK` — `CalibrationTriggerResponse`

```json
{
  "success": true,
  "results": {
    "sensor-uuid-a": { "fitness": 0.94, "rmse": 0.012, "quality": "good" },
    "sensor-uuid-b": { "fitness": 0.87, "rmse": 0.021, "quality": "acceptable" }
  },
  "pending_approval": true
}
```

---

## Calibration — `POST /api/v1/calibration/{node_id}/accept`

**Tag**: `Calibration`  
**Summary**: Accept pending calibration results

### Request Body — `AcceptCalibrationRequest`

```json
{ "sensor_ids": ["sensor-uuid-a"] }
```

| Field        | Type                | Description                                 |
|--------------|---------------------|---------------------------------------------|
| `sensor_ids` | `list[string]\|null`| Specific sensors to accept (null = all)     |

### Responses

| Code | Description       |
|------|-------------------|
| `200`| Accepted          |
| `400`| Invalid request   |
| `404`| Node not found    |

### Response `200 OK`

```json
{ "success": true, "accepted": ["sensor-uuid-a"] }
```

---

## Calibration — `POST /api/v1/calibration/{node_id}/reject`

**Tag**: `Calibration`  
**Summary**: Reject pending calibration (discards results)

### Responses

| Code | Description       |
|------|-------------------|
| `200`| Rejected          |
| `404`| Node not found    |

### Response `200 OK` — `StatusResponse`

---

## Calibration — `GET /api/v1/calibration/history/{sensor_id}`

**Tag**: `Calibration`  
**Summary**: Get calibration history for a sensor

### Path Parameters

| Name        | Type     | Description    |
|-------------|----------|----------------|
| `sensor_id` | `string` | Sensor node ID |

### Query Parameters

| Name    | Type      | Description                       | Default |
|---------|-----------|-----------------------------------|---------|
| `limit` | `integer` | Maximum records to return         | `10`    |

### Response `200 OK` — `CalibrationHistoryResponse`

```json
{
  "sensor_id": "sensor-uuid-a",
  "history": [
    {
      "id": "cal-uuid",
      "sensor_id": "sensor-uuid-a",
      "timestamp": "2025-01-01T12:00:00Z",
      "accepted": true,
      "fitness": 0.94,
      "rmse": 0.012
    }
  ]
}
```

---

## Calibration — `POST /api/v1/calibration/rollback/{sensor_id}`

**Tag**: `Calibration`  
**Summary**: Rollback sensor to a previous accepted calibration state

### Request Body — `RollbackRequest`

```json
{ "timestamp": "2025-01-01T12:00:00Z" }
```

### Responses

| Code | Description                                   |
|------|-----------------------------------------------|
| `200`| Rollback applied                              |
| `400`| Target calibration was not accepted           |
| `404`| Calibration record or sensor not found        |
| `500`| Rollback execution error                      |

### Response `200 OK` — `RollbackResponse`

```json
{
  "success": true,
  "sensor_id": "sensor-uuid-a",
  "restored_to": "2025-01-01T12:00:00Z"
}
```

---

## Calibration — `GET /api/v1/calibration/statistics/{sensor_id}`

**Tag**: `Calibration`  
**Summary**: Get statistical summary of calibration attempts

### Response `200 OK` — `CalibrationStatsResponse`

```json
{
  "sensor_id": "sensor-uuid-a",
  "total_attempts": 12,
  "accepted_count": 8,
  "avg_fitness": 0.91,
  "avg_rmse": 0.018
}
```

---

## LiDAR — `GET /api/v1/lidar/profiles`

**Tag**: `LiDAR`  
**Summary**: List all enabled SICK LiDAR device profiles

Pure in-memory operation. No database or file I/O.

### Response `200 OK` — `ProfilesListResponse`

```json
{
  "profiles": [
    {
      "model_id": "multiscan",
      "display_name": "SICK multiScan",
      "launch_file": "./launch/sick_multiscan.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "port",
      "default_port": 2115,
      "has_udp_receiver": true,
      "has_imu_udp_port": false,
      "scan_layers": 16,
      "thumbnail_url": "/api/v1/assets/lidar/multiscan.png",
      "icon_name": "sensors",
      "icon_color": "#FF6B35"
    }
  ]
}
```

---

## LiDAR — `POST /api/v1/lidar/validate-lidar-config`

**Tag**: `LiDAR`  
**Summary**: Validate a proposed LiDAR sensor configuration

### Request Body — `LidarConfigValidationRequest`

```json
{
  "lidar_type": "multiscan",
  "hostname": "192.168.1.10",
  "udp_receiver_ip": "192.168.1.100",
  "port": 2115,
  "imu_udp_port": null
}
```

| Field               | Type             | Constraints      | Description                          |
|---------------------|------------------|------------------|--------------------------------------|
| `lidar_type`        | `string`         | required         | Must match a registered profile ID   |
| `hostname`          | `string`         | required         | Device IP or hostname                |
| `udp_receiver_ip`   | `string\|null`   | —                | Required for multiScan               |
| `port`              | `integer\|null`  | 1024–65535       | Override device port                 |
| `imu_udp_port`      | `integer\|null`  | 1024–65535       | IMU receiver port                    |

### Response `200 OK` — `LidarConfigValidationResponse`

```json
{
  "valid": true,
  "lidar_type": "multiscan",
  "resolved_launch_file": "./launch/sick_multiscan.launch",
  "errors": [],
  "warnings": ["IMU UDP port not specified; IMU data will be disabled"]
}
```

---

## Assets — `GET /api/v1/assets/lidar/`

**Tag**: `Assets`  
**Summary**: List available LiDAR thumbnail image files

### Response `200 OK`

```json
{
  "thumbnails": [
    {
      "filename": "multiscan.png",
      "url": "/api/v1/assets/lidar/multiscan.png",
      "size": 32768
    }
  ],
  "count": 1,
  "assets_dir": "/app/modules/lidar/assets"
}
```

### Responses

| Code | Description          |
|------|----------------------|
| `200`| Thumbnail list       |
| `500`| Directory read error |

---

## Assets — `GET /api/v1/assets/lidar/{filename}`

**Tag**: `Assets`  
**Summary**: Serve a LiDAR device thumbnail image

### Path Parameters

| Name       | Type     | Description                         |
|------------|----------|-------------------------------------|
| `filename` | `string` | Thumbnail filename (e.g. `multiscan.png`) |

### Responses

| Code | Description                                   |
|------|-----------------------------------------------|
| `200`| Image file (`image/png`, `image/jpeg`, etc.) |
| `400`| Unsupported extension or path traversal attempt |
| `404`| File not found                                |

---

## Topics — `GET /api/v1/topics`

**Tag**: `Topics`  
**Summary**: List active WebSocket topics (excludes system topics)

### Response `200 OK`

```json
{
  "topics": ["multiscan_left_a1b2c3d4", "fusion_output_b2c3d4e5"],
  "description": {
    "raw_points": "Stream of raw point cloud data (sub-sampled for performance)",
    "processed_points": "Stream of preprocessed data with algorithm results"
  }
}
```

---

## Topics — `GET /api/v1/topics/capture`

**Tag**: `Topics`  
**Summary**: Capture a single frame from a WebSocket topic via HTTP

Blocks up to 5 seconds waiting for the next broadcast on the specified topic.
Useful for testing and single-shot integrations that cannot maintain a WebSocket.

### Query Parameters

| Name    | Type     | Required | Description                        |
|---------|----------|----------|------------------------------------|
| `topic` | `string` | yes      | WebSocket topic name to capture from |

### Responses

| Code | Description                                           |
|------|-------------------------------------------------------|
| `200`| Binary LIDR frame (`application/octet-stream`)        |
| `503`| Topic was removed while waiting — retry               |
| `504`| Timeout — no frame arrived within 5 seconds           |

---

## Common Error Responses

All endpoints that raise `HTTPException` follow this error body shape:

```json
{ "detail": "Human-readable error description" }
```

| HTTP Code | Typical trigger                                              |
|-----------|--------------------------------------------------------------|
| `400`     | Invalid request parameters or business rule violation        |
| `404`     | Requested resource (node, recording, calibration) not found  |
| `409`     | Concurrent conflict (e.g. reload already in progress)        |
| `500`     | Unexpected server-side error                                 |
| `503`     | Service unavailable (topic removed during capture wait)      |
| `504`     | Gateway timeout (frame capture timeout)                      |
