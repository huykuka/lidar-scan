# Multi-LiDAR Type Support — API Specification

> **Status**: Revised — Finalized
> **Author**: @architecture
> **Last Revised**: 2026-03-08
> **References**: `requirements.md`, `technical.md`

---

## Base URL

All endpoints are prefixed with `/api/v1`.

---

## 1. GET `/lidar/profiles`

Returns the full catalog of supported SICK LiDAR device profiles. Called once by the frontend on page load. Fully in-memory — no DB/disk access.

### Response `200 OK`

```json
{
  "profiles": [
    {
      "model_id": "multiscan",
      "display_name": "SICK multiScan",
      "launch_file": "launch/sick_multiscan.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "udp_port",
      "default_port": 2115,
      "has_udp_receiver": true,
      "has_imu_udp_port": true,
      "scan_layers": 16
    },
    {
      "model_id": "tim_5xx",
      "display_name": "SICK TiM5xx",
      "launch_file": "launch/sick_tim_5xx.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "port",
      "default_port": 2112,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 1
    },
    {
      "model_id": "tim_7xx",
      "display_name": "SICK TiM7xx",
      "launch_file": "launch/sick_tim_7xx.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "port",
      "default_port": 2112,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 1
    },
    {
      "model_id": "tim_4xx",
      "display_name": "SICK TiM4xx",
      "launch_file": "launch/sick_tim_4xx.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "port",
      "default_port": 2112,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 1
    },
    {
      "model_id": "tim_2xx",
      "display_name": "SICK TiM2xx",
      "launch_file": "launch/sick_tim_240.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "port",
      "default_port": 2112,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 1
    },
    {
      "model_id": "lms_1xx",
      "display_name": "SICK LMS1xx",
      "launch_file": "launch/sick_lms_1xx.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "",
      "default_port": 0,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 1
    },
    {
      "model_id": "lms_5xx",
      "display_name": "SICK LMS5xx",
      "launch_file": "launch/sick_lms_5xx.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "",
      "default_port": 0,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 1
    },
    {
      "model_id": "lms_4xxx",
      "display_name": "SICK LMS4000",
      "launch_file": "launch/sick_lms_4xxx.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "",
      "default_port": 0,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 1
    },
    {
      "model_id": "mrs_1xxx",
      "display_name": "SICK MRS1000",
      "launch_file": "launch/sick_mrs_1xxx.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "",
      "default_port": 0,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 4
    },
    {
      "model_id": "mrs_6xxx",
      "display_name": "SICK MRS6124",
      "launch_file": "launch/sick_mrs_6xxx.launch",
      "default_hostname": "192.168.0.1",
      "port_arg": "",
      "default_port": 0,
      "has_udp_receiver": false,
      "has_imu_udp_port": false,
      "scan_layers": 24
    }
  ]
}
```

### Error Responses

| Code | Condition |
|---|---|
| `500` | Profiles module failed to load |

---

## 2. POST `/nodes/validate-lidar-config`

Validates a proposed sensor node configuration without persisting it. Called by the frontend on save when `type === "sensor"` and `mode === "real"`.

### Request Body

```json
{
  "lidar_type": "multiscan",
  "hostname": "192.168.0.50",
  "udp_receiver_ip": "192.168.0.10",
  "port": 2115,
  "imu_udp_port": 7503
}
```

#### Field Rules

| Field | Type | Required | Description |
|---|---|---|---|
| `lidar_type` | `string` | Yes | Must match a `model_id` from the profiles catalog |
| `hostname` | `string` | Yes | IP address or hostname of the device |
| `udp_receiver_ip` | `string` | No | Required only when profile `has_udp_receiver = true` (multiScan) |
| `port` | `integer` | No | Range `1024–65535`. Used only when profile `port_arg` is non-empty |
| `imu_udp_port` | `integer` | No | Range `1024–65535`. Warning if absent when profile `has_imu_udp_port = true` |

### Response `200 OK` — Valid

```json
{
  "valid": true,
  "lidar_type": "multiscan",
  "resolved_launch_file": "launch/sick_multiscan.launch",
  "errors": [],
  "warnings": []
}
```

### Response `200 OK` — Invalid (unknown type)

```json
{
  "valid": false,
  "lidar_type": "velodyne_vls128",
  "resolved_launch_file": null,
  "errors": [
    "lidar_type 'velodyne_vls128' is not a recognized SICK model. Valid values: multiscan, tim_2xx, tim_4xx, tim_5xx, tim_7xx, lms_1xx, lms_5xx, lms_4xxx, mrs_1xxx, mrs_6xxx"
  ],
  "warnings": []
}
```

### Response `200 OK` — Valid with warning (multiScan without IMU port)

```json
{
  "valid": true,
  "lidar_type": "multiscan",
  "resolved_launch_file": "launch/sick_multiscan.launch",
  "errors": [],
  "warnings": [
    "lidar_type 'multiscan' supports IMU UDP data but imu_udp_port was not provided. IMU data will be disabled."
  ]
}
```

### Response `422 Unprocessable Entity`

Standard FastAPI/Pydantic validation error when request body is missing required fields (`lidar_type` or `hostname`).

---

## 3. GET `/nodes/definitions` *(Extended)*

Existing endpoint. The `"sensor"` node definition is extended to include:
- `lidar_type` as the first property with `type: "select"` (10 options)
- `depends_on` on network-specific fields
- `port` property renamed from `udp_port` (reflects real launch file arg diversity)

### Response `200 OK` — Sensor definition excerpt

```json
[
  {
    "type": "sensor",
    "display_name": "LiDAR Sensor",
    "category": "sensor",
    "description": "Interface for physical SICK sensors or PCD file simulations",
    "icon": "sensors",
    "properties": [
      {
        "name": "lidar_type",
        "label": "LiDAR Model",
        "type": "select",
        "default": "multiscan",
        "options": [
          { "label": "SICK multiScan",  "value": "multiscan" },
          { "label": "SICK TiM2xx",     "value": "tim_2xx"   },
          { "label": "SICK TiM4xx",     "value": "tim_4xx"   },
          { "label": "SICK TiM5xx",     "value": "tim_5xx"   },
          { "label": "SICK TiM7xx",     "value": "tim_7xx"   },
          { "label": "SICK LMS1xx",     "value": "lms_1xx"   },
          { "label": "SICK LMS5xx",     "value": "lms_5xx"   },
          { "label": "SICK LMS4000",    "value": "lms_4xxx"  },
          { "label": "SICK MRS1000",    "value": "mrs_1xxx"  },
          { "label": "SICK MRS6124",    "value": "mrs_6xxx"  }
        ],
        "required": true,
        "help_text": "Select the SICK LiDAR hardware model for this node",
        "depends_on": null
      },
      {
        "name": "throttle_ms",
        "label": "Throttle (ms)",
        "type": "number",
        "default": 0,
        "min": 0,
        "step": 10,
        "help_text": "Minimum time between processing frames (0 = no limit)",
        "depends_on": null
      },
      {
        "name": "mode",
        "label": "Mode",
        "type": "select",
        "default": "real",
        "options": [
          { "label": "Hardware (Real)",   "value": "real" },
          { "label": "Simulation (PCD)", "value": "sim"  }
        ],
        "depends_on": null
      },
      {
        "name": "hostname",
        "label": "Hostname",
        "type": "string",
        "default": "192.168.0.1",
        "help_text": "LiDAR device IP address",
        "depends_on": { "mode": ["real"] }
      },
      {
        "name": "port",
        "label": "Port",
        "type": "number",
        "default": 2112,
        "help_text": "Communication port (TiM / multiScan devices only)",
        "depends_on": {
          "mode": ["real"],
          "lidar_type": ["multiscan", "tim_2xx", "tim_4xx", "tim_5xx", "tim_7xx"]
        }
      },
      {
        "name": "udp_receiver_ip",
        "label": "UDP Receiver IP",
        "type": "string",
        "default": "",
        "help_text": "Host IP receiving UDP data (multiScan only)",
        "depends_on": { "mode": ["real"], "lidar_type": ["multiscan"] }
      },
      {
        "name": "imu_udp_port",
        "label": "IMU UDP Port",
        "type": "number",
        "default": 7503,
        "help_text": "UDP port for IMU data (multiScan only)",
        "depends_on": { "mode": ["real"], "lidar_type": ["multiscan"] }
      },
      {
        "name": "pcd_path",
        "label": "PCD Path",
        "type": "string",
        "default": "",
        "help_text": "Path to .pcd file (simulation only)",
        "depends_on": { "mode": ["sim"] }
      },
      {
        "name": "x",  "label": "Pos X", "type": "number", "default": 0.0, "step": 0.01, "depends_on": null
      },
      {
        "name": "y",  "label": "Pos Y", "type": "number", "default": 0.0, "step": 0.01, "depends_on": null
      },
      {
        "name": "z",  "label": "Pos Z", "type": "number", "default": 0.0, "step": 0.01, "depends_on": null
      },
      {
        "name": "roll",  "label": "Roll",  "type": "number", "default": 0.0, "step": 0.1, "depends_on": null
      },
      {
        "name": "pitch", "label": "Pitch", "type": "number", "default": 0.0, "step": 0.1, "depends_on": null
      },
      {
        "name": "yaw",   "label": "Yaw",   "type": "number", "default": 0.0, "step": 0.1, "depends_on": null
      }
    ],
    "inputs": [],
    "outputs": [
      { "id": "raw_points",       "label": "Raw Points",       "data_type": "pointcloud", "multiple": false },
      { "id": "processed_points", "label": "Processed Points", "data_type": "pointcloud", "multiple": false }
    ]
  }
]
```

> **`depends_on` semantics**: A property is visible if and only if **all** keys in `depends_on` have their current form value in the corresponding allowed list. AND relationship across keys. A `null` `depends_on` means always visible.

---

## 4. POST `/nodes` *(Unchanged contract, extended payload)*

Existing endpoint. The `config` object now optionally includes `lidar_type`. No breaking changes.

### Request Body — Sensor node with multiScan

```json
{
  "id": "a1b2c3d4-...",
  "name": "Front LiDAR",
  "type": "sensor",
  "category": "sensor",
  "enabled": true,
  "config": {
    "lidar_type": "multiscan",
    "mode": "real",
    "hostname": "192.168.0.50",
    "udp_receiver_ip": "192.168.0.10",
    "port": 2115,
    "imu_udp_port": 7503,
    "throttle_ms": 0,
    "x": 0.0, "y": 0.0, "z": 0.5,
    "roll": 0.0, "pitch": 0.0, "yaw": 0.0
  },
  "x": 200,
  "y": 100
}
```

### Request Body — Sensor node with TiM7xx

```json
{
  "config": {
    "lidar_type": "tim_7xx",
    "mode": "real",
    "hostname": "192.168.0.100",
    "port": 2112,
    "throttle_ms": 0,
    "x": 0.0, "y": 0.0, "z": 0.0,
    "roll": 0.0, "pitch": 0.0, "yaw": 0.0
  }
}
```

### Response `200 OK`

```json
{ "status": "success", "id": "a1b2c3d4-..." }
```

---

## 5. GET `/nodes/status/all` *(Extended response)*

Each sensor node entry now includes `lidar_type` and `lidar_display_name`.

### Response `200 OK` — Sensor node entry

```json
{
  "nodes": [
    {
      "id": "a1b2c3d4-...",
      "name": "Front LiDAR",
      "type": "sensor",
      "category": "sensor",
      "enabled": true,
      "running": true,
      "connection_status": "connected",
      "last_frame_at": 1741430400.123,
      "frame_age_seconds": 0.05,
      "last_error": null,
      "topic": "front_lidar_a1b2c3d4",
      "lidar_type": "tim_7xx",
      "lidar_display_name": "SICK TiM7xx",
      "mode": "real",
      "throttle_ms": 0,
      "throttled_count": 0
    }
  ]
}
```

---

## 6. GET `/config/export` *(Unchanged, naturally includes `lidar_type`)*

Export already serializes the full `config` JSON blob. `lidar_type` appears automatically in any node where it was set.

---

## 7. POST `/config/validate` *(Extended validation)*

For each node where `type === "sensor"`:
- `config.lidar_type` absent → `warning` (not error); defaults to `"multiscan"`.
- `config.lidar_type` present but not in catalog → `error`.

### Warning example (legacy node)

```json
{
  "valid": true,
  "errors": [],
  "warnings": [
    "Node 'Old Sensor' (id: abc123): no lidar_type specified; defaulting to 'multiscan' for backward compatibility."
  ],
  "summary": { "nodes": 1, "edges": 0 }
}
```

---

## 8. Pydantic Models Reference

### `LidarConfigValidationRequest`
```python
class LidarConfigValidationRequest(BaseModel):
    lidar_type: str
    hostname: str
    udp_receiver_ip: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1024, le=65535)
    imu_udp_port: Optional[int] = Field(default=None, ge=1024, le=65535)
```

### `LidarConfigValidationResponse`
```python
class LidarConfigValidationResponse(BaseModel):
    valid: bool
    lidar_type: str
    resolved_launch_file: Optional[str]
    errors: List[str] = []
    warnings: List[str] = []
```

### `SickLidarProfileResponse`
```python
class SickLidarProfileResponse(BaseModel):
    model_id: str
    display_name: str
    launch_file: str
    default_hostname: str
    port_arg: str           # "port" | "udp_port" | ""
    default_port: int
    has_udp_receiver: bool
    has_imu_udp_port: bool
    scan_layers: int
```

### `ProfilesListResponse`
```python
class ProfilesListResponse(BaseModel):
    profiles: List[SickLidarProfileResponse]
```
