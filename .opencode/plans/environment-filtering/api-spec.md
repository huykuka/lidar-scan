# API Specification: Environment Filtering Node

## 1. Node Registration

| Field | Value |
|---|---|
| `type` | `"environment_filtering"` |
| `display_name` | `"Environment Filtering"` |
| `category` | `"application"` |
| `websocket_enabled` | `true` |
| `icon` | `"layers_clear"` |

---

## 2. Input / Output Ports

| Port | `id` | `label` | `data_type` |
|---|---|---|---|
| Input | `"in"` | `"Input Point Cloud"` | `"pointcloud"` |
| Output | `"out"` | `"Filtered Point Cloud"` | `"pointcloud"` |

---

## 3. Config Properties (NodeDefinition `properties`)

### Group A — Performance

| `name` | `label` | `type` | `default` | `min` | `max` | `step` |
|---|---|---|---|---|---|---|
| `throttle_ms` | `"Throttle (ms)"` | `number` | `0` | `0` | — | `10` |
| `voxel_downsample_size` | `"Voxel Downsample Size (m)"` | `number` | `0.01` | `0.0` | `1.0` | `0.005` |

`help_text`:
- `throttle_ms`: Minimum milliseconds between processed frames. 0 = no limit. Use 50-100ms for 30Hz LiDAR streams.
- `voxel_downsample_size`: Reduce point cloud density before plane detection to improve performance on dense scans (100k+ points). Smaller = higher precision but slower. Recommended: 0.01m (1cm) for indoor scans. Set to 0 to disable downsampling (advanced users only).

### Group B — Plane Detection (patch_plane_segmentation params)

| `name` | `label` | `type` | `default` | `min` | `max` | `step` |
|---|---|---|---|---|---|---|
| `normal_variance_threshold_deg` | `"Normal Variance (deg)"` | `number` | `60.0` | `1.0` | `90.0` | `1.0` |
| `coplanarity_deg` | `"Coplanarity (deg)"` | `number` | `75.0` | `1.0` | `90.0` | `1.0` |
| `outlier_ratio` | `"Outlier Ratio"` | `number` | `0.75` | `0.0` | `1.0` | `0.05` |
| `min_plane_edge_length` | `"Min Edge Length (m)"` | `number` | `0.0` | `0.0` | — | `0.01` |
| `min_num_points` | `"Min Points"` | `number` | `0` | `0` | — | `1` |
| `knn` | `"KNN"` | `number` | `30` | `5` | `100` | `1` |

`help_text` per param:
- `normal_variance_threshold_deg`: Max spread of point normals vs plane normal. Smaller = stricter, fewer planes. Increase (65-75) for noisy/uneven floors.
- `coplanarity_deg`: Max deviation from planar fit. Smaller = tighter planes. Reduce for smooth surfaces.
- `outlier_ratio`: Max fraction of outlier points before rejecting a plane. Increase (0.8-0.9) for debris-covered floors.
- `min_plane_edge_length`: Minimum OBB edge to qualify as a plane. 0 = auto (1% of cloud bbox).
- `min_num_points`: Minimum points for plane fitting. 0 = auto (0.1% of total). Increase to skip tiny fragments.
- `knn`: Nearest neighbors for plane growing. Higher = better quality but slower. Reduce (15-20) for real-time streaming.

### Group C — Validation

| `name` | `label` | `type` | `default` | `min` | `max` | `step` |
|---|---|---|---|---|---|---|
| `vertical_tolerance_deg` | `"Vertical Tolerance (deg)"` | `number` | `15.0` | `1.0` | `45.0` | `0.5` |
| `floor_height_min` | `"Floor Height Min (m)"` | `number` | `-0.5` | — | — | `0.1` |
| `floor_height_max` | `"Floor Height Max (m)"` | `number` | `0.5` | — | — | `0.1` |
| `ceiling_height_min` | `"Ceiling Height Min (m)"` | `number` | `2.0` | — | — | `0.1` |
| `ceiling_height_max` | `"Ceiling Height Max (m)"` | `number` | `4.0` | — | — | `0.1` |
| `min_plane_area` | `"Min Plane Area (m²)"` | `number` | `1.0` | `0.1` | — | `0.1` |

`help_text` per param:
- `vertical_tolerance_deg`: How close to vertical the plane normal must be (0° = perfectly horizontal). 15° covers typical scanner tilt. Increase (20-30°) for sloped floors/ramps.
- `floor_height_min/max`: Z-coordinate range for the floor centroid (world frame, Z-up). Adjust for multi-level environments or raised platforms.
- `ceiling_height_min/max`: Z-coordinate range for the ceiling centroid. Increase max for warehouses (8-12m). Adjust min if drop ceilings exist.
- `min_plane_area`: Minimum plane area in m² to classify as floor/ceiling. Prevents shelves or table tops from being removed. Increase (3-10m²) for open warehouse scans.

> **Note on `floor_height_range` / `ceiling_height_range` serialization**: The internal Python API uses `tuple[float, float]`. The DAG JSON config and PropertySchema expose them as flat `floor_height_min`, `floor_height_max`, `ceiling_height_min`, `ceiling_height_max` scalars. The factory builder converts these to tuples. This avoids needing a `"list"` type property in the schema, consistent with other nodes.

---

## 4. DAG Config JSON Shape

```json
{
  "node_id": "env_filter_1",
  "type": "environment_filtering",
  "name": "Remove Floor/Ceiling",
  "config": {
    "throttle_ms": 0,
    "voxel_downsample_size": 0.01,
    "normal_variance_threshold_deg": 60.0,
    "coplanarity_deg": 75.0,
    "outlier_ratio": 0.75,
    "min_plane_edge_length": 0.0,
    "min_num_points": 0,
    "knn": 30,
    "vertical_tolerance_deg": 15.0,
    "floor_height_min": -0.5,
    "floor_height_max": 0.5,
    "ceiling_height_min": 2.0,
    "ceiling_height_max": 4.0,
    "min_plane_area": 1.0
  }
}
```

---

## 5. Payload Metadata (injected into `payload["metadata"]`)

Emitted downstream and accessible to `IfConditionNode` via top-level keys:

```json
{
  "downsampling_enabled": true,
  "voxel_size": 0.01,
  "points_before_downsample": 50000,
  "points_after_downsample": 25000,
  "input_point_count": 50000,
  "output_point_count": 35000,
  "removed_point_count": 15000,
  "planes_detected": 3,
  "planes_filtered": 2,
  "plane_details": [
    {
      "plane_id": 0,
      "plane_type": "floor",
      "normal": [0.02, -0.01, 0.999],
      "centroid_z": 0.05,
      "area": 25.3,
      "point_count": 8000
    }
  ],
  "status": "success"
}
```

`status` values: `"success"` | `"no_planes_detected"` | `"warning_pass_through"` | `"warning_low_point_density"`

> **When downsampling is disabled** (`voxel_downsample_size = 0`): `downsampling_enabled = false`, `voxel_size = 0.0`, `points_before_downsample == points_after_downsample == input_point_count`.

---

## 6. Node Status (`emit_status`)

| Condition | `operational_state` | `application_state.label` | `application_state.value` | `color` |
|---|---|---|---|---|
| Error / invalid params | `ERROR` | `"error"` | error message string | `"red"` |
| Warning (no planes / no valid / low density) | `RUNNING` | `"planes_filtered"` | `0` | `"orange"` |
| Recently active, planes found | `RUNNING` | `"planes_filtered"` | `N` (int) | `"blue"` |
| Idle (no recent input) | `RUNNING` | `"processing"` | `false` | `"gray"` |

---

## 7. REST API

No dedicated REST endpoints. Node is managed entirely via the existing DAG management endpoints:

- `GET  /api/v1/nodes/schema` — returns `NodeDefinition` for `"environment_filtering"`
- `POST /api/v1/canvas` — create/update DAG including `environment_filtering` nodes
- `GET  /api/v1/nodes/status` — returns `NodeStatusUpdate` for all nodes

---

## 8. WebSocket

Node uses the standard LIDR binary protocol. Topic: `{slugified_name}_{node_id_prefix}`.

Binary frame format per `protocols.md`:
```
[LIDR magic 4B][version 4B][timestamp 8B][point_count 4B][points N×12B]
```

Metadata (downsampling stats, plane_details, status etc.) is NOT streamed over WebSocket. It is included in the DAG payload dict for downstream nodes only.

> **Total property count**: 14 (was 13). Added `voxel_downsample_size` to Group A — Performance.
