# Node Status Standardization — API Specification

## Purpose

This document is the **single source of truth** for the status schema contract between backend and frontend.

- `@be-dev` must implement and emit payloads matching this spec exactly.
- `@fe-dev` must mock data matching this spec exactly while backend is being built.
- Schema changes require updating **both this document and both implementations**.

---

## 1. Core Types

### 1.1 Python — Pydantic Models

**File**: `app/schemas/status.py`

```python
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class OperationalState(str, Enum):
    """Lifecycle state of the node process / worker.

    INITIALIZE  – Node is starting up (worker spawning, sensor handshake)
    RUNNING     – Node is actively processing data
    STOPPED     – Node is intentionally stopped or disabled
    ERROR       – Node encountered a fatal / non-recoverable error
    """
    INITIALIZE = "INITIALIZE"
    RUNNING    = "RUNNING"
    STOPPED    = "STOPPED"
    ERROR      = "ERROR"


class ApplicationState(BaseModel):
    """Node-specific runtime state. JSON-serializable only.

    Examples
    --------
    Sensor:      ApplicationState(label="connection_status", value="connected", color="green")
    Calibration: ApplicationState(label="calibrating",       value=True,        color="blue")
    IfCondition: ApplicationState(label="condition",         value="true",      color="green")
    Fusion:      ApplicationState(label="fusing",            value=3,           color="blue")
    """
    label: str           = Field(..., description="Human-readable state identifier")
    value: Any           = Field(..., description="JSON-serializable value (str, bool, int, float)")
    color: Optional[str] = Field(None, description="UI hint: green | blue | orange | red | gray")


class NodeStatusUpdate(BaseModel):
    """Standardised status update for one DAG node.

    This is emitted by ``ModuleNode.emit_status()`` and collected by
    ``StatusAggregator`` before being broadcast on the system_status topic.
    """
    node_id:           str                     = Field(..., description="Unique node identifier")
    operational_state: OperationalState        = Field(..., description="Node lifecycle state")
    application_state: Optional[ApplicationState] = Field(None, description="Node-specific state")
    error_message:     Optional[str]           = Field(None, description="Only set when operational_state=ERROR")
    timestamp:         float                   = Field(default_factory=time.time, description="Unix epoch seconds")

    model_config = {"use_enum_values": True}


class SystemStatusBroadcast(BaseModel):
    """WebSocket payload broadcast on the system_status topic."""
    nodes: list[NodeStatusUpdate] = Field(..., description="All registered node statuses")
```

---

### 1.2 TypeScript — Interfaces & Enums

**File**: `web/src/app/core/models/status.model.ts`

```typescript
/**
 * Node Status Standardization — TypeScript schema
 * Mirrors the Python NodeStatusUpdate / SystemStatusBroadcast Pydantic models.
 */

export enum OperationalState {
  INITIALIZE = 'INITIALIZE',
  RUNNING    = 'RUNNING',
  STOPPED    = 'STOPPED',
  ERROR      = 'ERROR',
}

export interface ApplicationState {
  /** Human-readable state identifier, e.g. "connection_status", "calibrating" */
  label: string;
  /** JSON-serializable value: string | boolean | number */
  value: string | boolean | number;
  /** Optional UI color hint: "green" | "blue" | "orange" | "red" | "gray" */
  color?: 'green' | 'blue' | 'orange' | 'red' | 'gray';
}

export interface NodeStatusUpdate {
  node_id:           string;
  operational_state: OperationalState;
  application_state?: ApplicationState;
  /** Only present when operational_state === ERROR */
  error_message?:    string;
  /** Unix epoch seconds (float) */
  timestamp:         number;
}

export interface SystemStatusBroadcast {
  nodes: NodeStatusUpdate[];
}
```

---

## 2. WebSocket Contract

### 2.1 Endpoint

| Field    | Value                               |
|----------|-------------------------------------|
| Protocol | WebSocket (JSON text frames)        |
| Path     | `/ws/system_status`                 |
| Topic    | `system_status` (existing, reused)  |
| Auth     | None (same as current)              |

### 2.2 Message Direction

Only **server → client** messages are defined here. The client sends no messages on this topic.

### 2.3 Trigger

The server broadcasts a `SystemStatusBroadcast` message **only when node state changes**:
- Node lifecycle event: `start()`, `stop()`, `enable()`, `disable()`
- Internal transition: sensor connects / disconnects, calibration begins / ends, condition evaluates
- Error condition: any uncaught exception captured by a node

**Not** triggered by:
- Periodic polling timers
- Per-frame DAG data flow (100 Hz frames do NOT produce 100 Hz status messages)

### 2.4 Rate Limiting

| Layer               | Limit                        | Mechanism                          |
|---------------------|------------------------------|------------------------------------|
| Per-node (backend)  | ≤ 10 updates / second        | 100 ms minimum interval per node   |
| Global (backend)    | Batch window                 | 100 ms `asyncio.sleep` debounce    |
| UI (frontend)       | ≤ 20 renders / second        | 50 ms RxJS `debounceTime`          |

---

## 3. Node-by-Node Status Specification

### 3.1 LidarSensor

| Lifecycle event         | `operational_state` | `application_state`                                               | `error_message` |
|-------------------------|---------------------|-------------------------------------------------------------------|-----------------|
| Worker not started      | `STOPPED`           | `{label:"connection_status", value:"disconnected", color:"red"}`  | —               |
| Worker spawned          | `INITIALIZE`        | `{label:"connection_status", value:"starting",     color:"orange"}`| —              |
| Receiving frames        | `RUNNING`           | `{label:"connection_status", value:"connected",    color:"green"}` | —              |
| UDP timeout             | `ERROR`             | `{label:"connection_status", value:"disconnected", color:"red"}`  | `"UDP socket timeout after 5s"` |
| Worker process stopped  | `STOPPED`           | `{label:"connection_status", value:"disconnected", color:"red"}`  | —               |

---

### 3.2 CalibrationNode

| Lifecycle event             | `operational_state` | `application_state`                                    | `error_message` |
|-----------------------------|---------------------|--------------------------------------------------------|-----------------|
| Node disabled               | `STOPPED`           | `{label:"calibrating", value:false, color:"gray"}`     | —               |
| Node enabled, idle          | `RUNNING`           | `{label:"calibrating", value:false, color:"gray"}`     | —               |
| Calibration in progress     | `RUNNING`           | `{label:"calibrating", value:true,  color:"blue"}`     | —               |
| Calibration error           | `ERROR`             | `{label:"calibrating", value:false, color:"red"}`      | `"ICP failed: insufficient correspondences"` |

---

### 3.3 IfConditionNode

| Lifecycle event              | `operational_state` | `application_state`                                    | `error_message` |
|------------------------------|---------------------|--------------------------------------------------------|-----------------|
| No input evaluated yet       | `RUNNING`           | `null`                                                 | —               |
| Condition evaluated → true   | `RUNNING`           | `{label:"condition", value:"true",  color:"green"}`    | —               |
| Condition evaluated → false  | `RUNNING`           | `{label:"condition", value:"false", color:"red"}`      | —               |
| Expression eval error        | `ERROR`             | `null`                                                 | `"NameError: name 'x' is not defined"` |

---

### 3.4 OperationNode (pipeline)

| Lifecycle event              | `operational_state` | `application_state`                                     | `error_message` |
|------------------------------|---------------------|---------------------------------------------------------|-----------------|
| No data received yet         | `RUNNING`           | `{label:"processing", value:false, color:"gray"}`       | —               |
| Data flowing (last frame < 5s)| `RUNNING`          | `{label:"processing", value:true,  color:"blue"}`       | —               |
| Processing error             | `ERROR`             | `{label:"processing", value:false, color:"gray"}`       | `"Open3D: invalid point cloud"` |

---

### 3.5 FusionService

| Lifecycle event              | `operational_state` | `application_state`                                  | `error_message` |
|------------------------------|---------------------|------------------------------------------------------|-----------------|
| Node disabled                | `STOPPED`           | `{label:"fusing", value:0, color:"gray"}`            | —               |
| Node enabled, no inputs      | `RUNNING`           | `{label:"fusing", value:0, color:"gray"}`            | —               |
| Node enabled, n inputs fusing| `RUNNING`           | `{label:"fusing", value:n, color:"blue"}`            | —               |
| Fusion error                 | `ERROR`             | `{label:"fusing", value:0, color:"red"}`             | `"Frame timestamp mismatch"` |

---

## 4. Sample Payloads

### 4.1 Normal operation — mixed node types

```json
{
  "nodes": [
    {
      "node_id": "lidar_sensor_abc12345",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "connection_status",
        "value": "connected",
        "color": "green"
      },
      "error_message": null,
      "timestamp": 1711930000.123
    },
    {
      "node_id": "calibration_node_def67890",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "calibrating",
        "value": false,
        "color": "gray"
      },
      "error_message": null,
      "timestamp": 1711930000.124
    },
    {
      "node_id": "if_condition_ghi11111",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "condition",
        "value": "true",
        "color": "green"
      },
      "error_message": null,
      "timestamp": 1711930000.125
    },
    {
      "node_id": "voxel_downsample_jkl22222",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "processing",
        "value": true,
        "color": "blue"
      },
      "error_message": null,
      "timestamp": 1711930000.126
    },
    {
      "node_id": "fusion_service_mno33333",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "fusing",
        "value": 2,
        "color": "blue"
      },
      "error_message": null,
      "timestamp": 1711930000.127
    }
  ]
}
```

### 4.2 Sensor ERROR state

```json
{
  "nodes": [
    {
      "node_id": "lidar_sensor_abc12345",
      "operational_state": "ERROR",
      "application_state": {
        "label": "connection_status",
        "value": "disconnected",
        "color": "red"
      },
      "error_message": "UDP socket timeout after 5s — host 192.168.1.10 unreachable",
      "timestamp": 1711930045.789
    }
  ]
}
```

### 4.3 System startup sequence (3 broadcast events)

**Broadcast 1** — DAG start, all nodes initializing:
```json
{
  "nodes": [
    { "node_id": "lidar_sensor_abc12345",      "operational_state": "INITIALIZE", "application_state": { "label": "connection_status", "value": "starting", "color": "orange" }, "timestamp": 1711930010.001 },
    { "node_id": "voxel_downsample_jkl22222",  "operational_state": "RUNNING",    "application_state": { "label": "processing", "value": false, "color": "gray" },             "timestamp": 1711930010.002 },
    { "node_id": "fusion_service_mno33333",    "operational_state": "RUNNING",    "application_state": { "label": "fusing", "value": 0, "color": "gray" },                     "timestamp": 1711930010.003 }
  ]
}
```

**Broadcast 2** — Sensor connected:
```json
{
  "nodes": [
    { "node_id": "lidar_sensor_abc12345", "operational_state": "RUNNING", "application_state": { "label": "connection_status", "value": "connected", "color": "green" }, "timestamp": 1711930012.456 }
  ]
}
```

**Broadcast 3** — Fusion starts receiving frames:
```json
{
  "nodes": [
    { "node_id": "fusion_service_mno33333", "operational_state": "RUNNING", "application_state": { "label": "fusing", "value": 1, "color": "blue" }, "timestamp": 1711930012.789 }
  ]
}
```

### 4.4 Calibration active

```json
{
  "nodes": [
    {
      "node_id": "calibration_node_def67890",
      "operational_state": "RUNNING",
      "application_state": {
        "label": "calibrating",
        "value": true,
        "color": "blue"
      },
      "error_message": null,
      "timestamp": 1711930050.000
    }
  ]
}
```

### 4.5 Node stopped / disabled

```json
{
  "nodes": [
    {
      "node_id": "voxel_downsample_jkl22222",
      "operational_state": "STOPPED",
      "application_state": {
        "label": "processing",
        "value": false,
        "color": "gray"
      },
      "error_message": null,
      "timestamp": 1711930060.000
    }
  ]
}
```

---

## 5. Frontend Mock Data

`@fe-dev` must use the following mock for local development while backend is building:

**File**: `web/src/app/core/services/status-websocket.service.mock.ts`

```typescript
import { OperationalState, SystemStatusBroadcast } from '../models/status.model';

export const MOCK_SYSTEM_STATUS: SystemStatusBroadcast = {
  nodes: [
    {
      node_id: 'lidar_sensor_abc12345',
      operational_state: OperationalState.RUNNING,
      application_state: { label: 'connection_status', value: 'connected', color: 'green' },
      timestamp: Date.now() / 1000,
    },
    {
      node_id: 'calibration_node_def67890',
      operational_state: OperationalState.RUNNING,
      application_state: { label: 'calibrating', value: false, color: 'gray' },
      timestamp: Date.now() / 1000,
    },
    {
      node_id: 'if_condition_ghi11111',
      operational_state: OperationalState.RUNNING,
      application_state: { label: 'condition', value: 'true', color: 'green' },
      timestamp: Date.now() / 1000,
    },
    {
      node_id: 'voxel_downsample_jkl22222',
      operational_state: OperationalState.ERROR,
      application_state: { label: 'processing', value: false, color: 'gray' },
      error_message: 'Open3D: invalid point cloud — zero points after voxel filter',
      timestamp: Date.now() / 1000,
    },
    {
      node_id: 'fusion_service_mno33333',
      operational_state: OperationalState.RUNNING,
      application_state: { label: 'fusing', value: 2, color: 'blue' },
      timestamp: Date.now() / 1000,
    },
  ],
};
```

---

## 6. Validation Rules

| Field              | Constraint                                                      |
|--------------------|-----------------------------------------------------------------|
| `node_id`          | Non-empty string. Must match an existing node in the DAG        |
| `operational_state`| Must be one of: `INITIALIZE`, `RUNNING`, `STOPPED`, `ERROR`    |
| `application_state.value` | Must be JSON-serializable (no numpy, no bytes)          |
| `application_state.color` | Optional. If present: `green`, `blue`, `orange`, `red`, `gray` |
| `error_message`    | Only set when `operational_state == ERROR`. Null otherwise      |
| `timestamp`        | Unix epoch float. Must be ≤ current time + 1s (no future dates)|

---

## 7. REST API Snapshot Endpoint

For HTTP clients that cannot use WebSocket, the existing `GET /api/v1/nodes/status` endpoint will return the same schema:

**Response** `200 OK`:
```json
{
  "nodes": [/* Array<NodeStatusUpdate> */]
}
```

The response format is **identical** to the WebSocket `SystemStatusBroadcast`. This removes the previous split where REST and WebSocket returned different schemas.

---

## 8. Changelog

| Version | Date       | Change                                                               |
|---------|------------|----------------------------------------------------------------------|
| 1.0     | 2026-03-20 | Initial spec — replaces legacy `get_status()` heterogeneous format  |
