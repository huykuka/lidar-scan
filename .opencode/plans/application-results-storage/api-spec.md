# API Contract: Application Node Results Storage

## Base URL: `/api/v1/results`

All responses use `Content-Type: application/json` unless noted. All timestamps are Unix epoch floats.

---

## Endpoints

### `GET /api/v1/results`

Returns all application nodes that have ≥1 result, merged with active DAG nodes of type `application`.

**Response 200:**
```json
[
  {
    "node_id": "volume_calc_abc123",
    "node_name": "Volume Calculation",
    "node_type": "volume_calculation",
    "result_count": 14,
    "latest_timestamp": 1715000000.123
  },
  {
    "node_id": "vehicle_profiler_def456",
    "node_name": "Vehicle Profiler",
    "node_type": "vehicle_profiler",
    "result_count": 0,
    "latest_timestamp": null
  }
]
```

---

### `GET /api/v1/results/{node_id}`

Lists all results for a node, newest first.

**Query params:** `limit` (int, default 100), `offset` (int, default 0)

**Response 200:**
```json
[
  {
    "result_id": "550e8400-e29b-41d4-a716-446655440000",
    "node_id": "volume_calc_abc123",
    "timestamp": 1715000000.123,
    "status": "success",
    "metadata_summary": {
      "volume_m3": 12.4,
      "icp_valid": true
    },
    "pcd_count": 3
  }
]
```

> `metadata_summary` contains only the **top-level scalar fields** from metadata (no nested objects/arrays). Frontend uses this for the list table.

**Response 404:** `{ "detail": "Node not found" }`

---

### `GET /api/v1/results/{node_id}/{result_id}`

Full result detail.

**Response 200:**
```json
{
  "result_id": "550e8400-e29b-41d4-a716-446655440000",
  "node_id": "volume_calc_abc123",
  "timestamp": 1715000000.123,
  "status": "success",
  "metadata": {
    "volume_m3": 12.4,
    "volume_l": 12400.0,
    "icp_fitness": 0.91,
    "icp_valid": true,
    "cell_count": 2048,
    "grid_res": 0.05,
    "calculation_number": 7
  },
  "pcd_files": [
    { "label": "empty",  "path": "results/volume_calc_abc123/550e8400.../empty.pcd",  "color": "#2196F3" },
    { "label": "loaded", "path": "results/volume_calc_abc123/550e8400.../loaded.pcd", "color": "#F44336" },
    { "label": "merged", "path": "results/volume_calc_abc123/550e8400.../merged.pcd", "color": "#4CAF50" }
  ]
}
```

**Response 404:** `{ "detail": "Result not found" }`

---

### `DELETE /api/v1/results/{node_id}/{result_id}`

Deletes a single result. Admin/debug use.

**Response 200:**
```json
{ "deleted": true, "result_id": "550e8400-e29b-41d4-a716-446655440000" }
```

**Response 404:** `{ "detail": "Result not found" }`

---

## Pydantic Schemas (Backend)

```python
class PcdFileEntry(BaseModel):
    label: str
    path: str  # relative to /data/, e.g. "results/<node_id>/<result_id>/<label>.pcd"
               # Frontend constructs full URL as: /data/${path}
               # Backend NEVER returns absolute URLs or proxy endpoints for PCD files.
    color: str  # hex color derived from label; canonical mapping:
                #   empty="#2196F3" (blue), loaded="#F44336" (red),
                #   merged="#4CAF50" (green), unknown="#9E9E9E" (grey)

class NodeResultSummary(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    result_count: int
    latest_timestamp: Optional[float]

class ResultSummary(BaseModel):
    result_id: str
    node_id: str
    timestamp: float
    status: Literal["success", "warning", "error"]
    metadata_summary: Dict[str, Any]  # scalar fields only
    pcd_count: int

class ResultDetail(BaseModel):
    result_id: str
    node_id: str
    timestamp: float
    status: Literal["success", "warning", "error"]
    metadata: Dict[str, Any]
    pcd_files: List[PcdFileEntry]

class DeleteResultResponse(BaseModel):
    deleted: bool
    result_id: str
```

---

## TypeScript Interfaces (Frontend)

```typescript
export interface PcdFileEntry {
  label: string;
  /**
   * Path relative to the /data/ static mount.
   * e.g. "results/<node_id>/<result_id>/<label>.pcd"
   * Frontend constructs the full URL as: `/data/${path}`
   * The backend NEVER returns absolute URLs or proxy endpoints for PCD files.
   */
  path: string;
  /** Hex color derived from PCD label. Canonical: empty=#2196F3, loaded=#F44336, merged=#4CAF50, unknown=#9E9E9E */
  color: string;
}

export interface ResultSummary {
  result_id: string;
  node_id: string;
  timestamp: number;
  status: 'success' | 'warning' | 'error';
  metadata_summary: Record<string, unknown>;
  pcd_count: number;
}

export interface PcdFileEntry {
  label: string;
  path: string;
  color: string;
}

export interface ResultDetail {
  result_id: string;
  node_id: string;
  timestamp: number;
  status: 'success' | 'warning' | 'error';
  metadata: Record<string, unknown>;
  pcd_files: PcdFileEntry[];
}
```

---

## Error Response Format (all endpoints)

```json
{ "detail": "Human-readable error message" }
```

HTTP status codes: `404` (not found), `500` (server/IO error).

---

## PCD Binary Format Contract

Frontend parser must handle:
- **Header**: ASCII lines terminated by `\n`, ending with `DATA binary\n`
- **Fields**: `x y z r g b` (6 fields)
- **Types**: `F F F U U U` (float32 for xyz, uint8 for rgb)
- **Byte order**: little-endian
- **Point stride**: `4+4+4+1+1+1 = 15 bytes` per point

Frontend extracts:
- Position buffer: `Float32Array[N*3]` → Three.js `position` attribute
- Color buffer: `Float32Array[N*3]` (rgb/255) → Three.js `color` attribute
