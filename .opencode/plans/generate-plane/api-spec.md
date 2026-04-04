# API Specification: GeneratePlane Operation

**Feature**: Generate Plane from Segmentation Output  
**Status**: Ready for Implementation  
**Scope**: Backend operation contract only — this operation has no dedicated REST endpoint.  
It is configured via the standard DAG JSON config mechanism and accessed via the existing DAG API.

---

## Overview

`GeneratePlane` is a **`PipelineOperation`** (not a REST endpoint). Its contract governs:

1. The **constructor inputs** (DAG config parameters)
2. The **`apply()` input type** (incoming point cloud)
3. The **`apply()` output tuple** (vertex `PointCloud` + metadata `dict`)

Frontend developers mocking this data should target the output metadata shape.

---

## 1. Constructor Contract

### Class: `GeneratePlane`

```
Location: app/modules/pipeline/operations/generate_plane.py
Base:     PipelineOperation (app/modules/pipeline/base.py)
```

### Constructor Parameters

| Parameter     | Type                   | Default   | Required | Validation                                                                 |
|---------------|------------------------|-----------|----------|----------------------------------------------------------------------------|
| `mode`        | `str`                  | `"square"`| No       | Must be `"square"` or `"boundary"`. Raises `ValueError` if invalid.       |
| `size`        | `float`                | `1.0`     | No       | Must be `> 0` (used only in `square` mode). Raises `ValueError` if ≤ 0.  |
| `voxel_size`  | `float`                | `0.05`    | No       | Must be `> 0`. Raises `ValueError` if ≤ 0.                                |
| `plane_model` | `Optional[List[float]]`| `None`    | No       | If provided: must be a 4-element list `[a, b, c, d]` where `sqrt(a²+b²+c²) > 1e-6`. |

### DAG JSON Config Shape

```jsonc
// Square mode (no upstream segmentation needed)
{
  "id": "gen_plane_square",
  "type": "generate_plane",
  "name": "Square Plane Generator",
  "config": {
    "op_type": "generate_plane",
    "mode": "square",
    "size": 1.0,
    "voxel_size": 0.05
  }
}

// Boundary mode with explicit plane model (recommended when chaining PlaneSegmentation)
{
  "id": "gen_plane_boundary",
  "type": "generate_plane",
  "name": "Floor Mesh Generator",
  "config": {
    "op_type": "generate_plane",
    "mode": "boundary",
    "voxel_size": 0.05,
    "plane_model": [0.02, -0.01, 0.999, -0.15]
  }
}

// Boundary mode without explicit plane model (auto-RANSAC fallback)
{
  "id": "gen_plane_boundary_auto",
  "type": "generate_plane",
  "name": "Auto Floor Mesh Generator",
  "config": {
    "op_type": "generate_plane",
    "mode": "boundary",
    "voxel_size": 0.05
  }
}
```

---

## 2. `apply()` Input Contract

### Input Type

| Type                            | Handling                                          |
|---------------------------------|---------------------------------------------------|
| `o3d.t.geometry.PointCloud`     | Used directly (primary path)                      |
| `o3d.geometry.PointCloud`       | Converted via `o3d.t.geometry.PointCloud.from_legacy()` |
| Any other type                  | `TypeError("Unsupported input type: expected o3d PointCloud")` |

### Minimum Input Requirements

| Condition          | Error                                                             |
|--------------------|-------------------------------------------------------------------|
| `N < 3` points     | `ValueError("Insufficient points for plane generation (minimum 3 required)")` |

---

## 3. `apply()` Output Contract

### Signature

```python
def apply(self, pcd: Any) -> Tuple[o3d.t.geometry.PointCloud, Dict[str, Any]]
```

### Return Value 1: `vertex_pcd` (`o3d.t.geometry.PointCloud`)

An Open3D tensor PointCloud containing **only vertex positions** of the generated mesh.

| Attribute          | Type                    | Description                         |
|--------------------|-------------------------|-------------------------------------|
| `positions`        | `Tensor[float32, (N,3)]`| XYZ vertex positions of the mesh    |

**Purpose**: Enables the `OperationNode` → `PointConverter.to_points()` passthrough for WebSocket streaming and downstream DAG forwarding.

### Return Value 2: `metadata` (`Dict[str, Any]`)

```jsonc
{
  // Required keys — always present on success
  "mesh":           "<o3d.t.geometry.TriangleMesh object>",   // Python object, not serializable
  "vertex_count":   2500,                                      // integer ≥ 3
  "triangle_count": 4802,                                      // integer ≥ 1
  "area":           1.0,                                       // float, square meters
  "plane_model":    [0.0, 0.0, 1.0, 0.0],                    // [a, b, c, d]
  "mode":           "square",                                  // "square" | "boundary"
  "voxel_size":     0.05                                       // float, meters
}
```

| Key              | Type                      | Notes                                                                                  |
|------------------|---------------------------|----------------------------------------------------------------------------------------|
| `mesh`           | `o3d.t.geometry.TriangleMesh` | Not JSON-serializable. Only for in-process use by downstream mesh-aware nodes.    |
| `vertex_count`   | `int`                     | Equals `mesh.vertex.positions.shape[0]`                                                |
| `triangle_count` | `int`                     | Equals `mesh.triangle.indices.shape[0]`                                                |
| `area`           | `float`                   | Square mode: exact `size²`. Boundary mode: `mesh.get_surface_area()` or ConvexHull area. |
| `plane_model`    | `List[float]` (len=4)     | `[a, b, c, d]` — the plane equation used. Square mode: `[0, 0, 1, 0]`. Boundary mode: fitted or user-supplied. |
| `mode`           | `str`                     | Echo of input `mode` parameter for downstream tracing.                                 |
| `voxel_size`     | `float`                   | Echo of input `voxel_size` parameter.                                                  |

---

## 4. Error Responses

All errors are `ValueError` or `TypeError` raised synchronously inside `apply()`. They propagate to `OperationNode.on_input()` where they are:

1. Stored in `self.last_error: str`
2. Logged via `logger.error()`
3. Broadcasted via `notify_status_change(self.id)` → visible in the Angular status dashboard

### Error Catalogue

```jsonc
// Empty / insufficient input
ValueError: "Insufficient points for plane generation (minimum 3 required)"

// Degenerate plane model (zero normal vector)
ValueError: "Invalid plane model: degenerate normal vector"

// Bad voxel_size
ValueError: "voxel_size must be > 0"

// Bad size (square mode only)
ValueError: "size must be > 0"

// Unknown mode string
ValueError: "mode must be 'square' or 'boundary'"

// Collinear projected points (boundary mode)
ValueError: "Cannot compute convex hull: projected points are colinear"

// Vertex count safety limit exceeded
ValueError: "Requested mesh would produce ~N vertices (limit: 1,000,000). Increase voxel_size."

// Wrong input type
TypeError: "Unsupported input type: expected o3d PointCloud"
```

---

## 5. Concrete Examples

### Example 1: Square Mode Output

**Input Config**:
```json
{ "mode": "square", "size": 1.0, "voxel_size": 0.05 }
```

**Output Metadata**:
```json
{
  "vertex_count": 400,
  "triangle_count": 722,
  "area": 1.0,
  "plane_model": [0.0, 0.0, 1.0, 0.0],
  "mode": "square",
  "voxel_size": 0.05
}
```
*`mesh` key is present as a Python object (omitted from JSON representation).*

> Calculation: `ceil(1.0 / 0.05) = 20` → `20×20 = 400` vertices, `19×19×2 = 722` triangles.

---

### Example 2: Square Mode Output (High Resolution)

**Input Config**:
```json
{ "mode": "square", "size": 1.0, "voxel_size": 0.02 }
```

**Output Metadata**:
```json
{
  "vertex_count": 2500,
  "triangle_count": 4802,
  "area": 1.0,
  "plane_model": [0.0, 0.0, 1.0, 0.0],
  "mode": "square",
  "voxel_size": 0.02
}
```

> Calculation: `ceil(1.0 / 0.02) = 50` → `50×50 = 2500` vertices, `49×49×2 = 4802` triangles.

---

### Example 3: Boundary Mode Output

**Input**: Segmented floor point cloud (1000 points), `plane_model=[0.02, -0.01, 0.999, -0.15]`, `voxel_size=0.05`

**Output Metadata** (approximate values):
```json
{
  "vertex_count": 1243,
  "triangle_count": 2318,
  "area": 4.2,
  "plane_model": [0.02, -0.01, 0.999, -0.15],
  "mode": "boundary",
  "voxel_size": 0.05
}
```

---

### Example 4: Error Response

**Input**: Empty PointCloud (`N=0 points`), `mode="boundary"`

**Raised**: `ValueError("Insufficient points for plane generation (minimum 3 required)")`

**OperationNode status** (via WebSocket status channel):
```json
{
  "node_id": "gen_plane_1",
  "operational_state": "ERROR",
  "application_state": { "label": "processing", "value": false, "color": "gray" },
  "error_message": "Insufficient points for plane generation (minimum 3 required)"
}
```

---

## 6. DAG Topology Constraints

| Constraint          | Rule                                                                                       |
|---------------------|--------------------------------------------------------------------------------------------|
| Input node type     | Any point cloud source (sensor, crop, segmentation, clustering, etc.)                     |
| Output compatibility| Vertex positions streamed as LIDR point data. The `TriangleMesh` object is **NOT** forwarded to downstream DAG nodes in v1. |
| Terminal node usage | `GeneratePlane` can be used as a leaf/terminal node OR mid-chain if downstream operations accept vertex-only point clouds. |
| ChainWith           | Best chained after `PlaneSegmentation` (supplies plane inlier points + plane model).       |

---

## 7. NodeDefinition Schema (for Angular Flow-Canvas)

```python
NodeDefinition(
    type="generate_plane",
    display_name="Generate Plane Mesh",
    category="operation",
    description="Generates a planar triangle mesh from segmented point cloud",
    icon="grid_on",
    websocket_enabled=True,
    properties=[
        PropertySchema(
            name="throttle_ms", label="Throttle (ms)", type="number",
            default=0, min=0, step=10,
            help_text="Minimum time between frames (0 = no limit)"
        ),
        PropertySchema(
            name="mode", label="Mode", type="select", default="square",
            options=[
                {"label": "Square (origin-centered)", "value": "square"},
                {"label": "Boundary-Fitted",           "value": "boundary"},
            ],
            help_text="Mesh generation mode"
        ),
        PropertySchema(
            name="size", label="Size (m)", type="number",
            default=1.0, step=0.1, min=0.01,
            help_text="Side length in meters (square mode only)"
        ),
        PropertySchema(
            name="voxel_size", label="Vertex Spacing (m)", type="number",
            default=0.05, step=0.005, min=0.001,
            help_text="Grid vertex spacing in meters"
        ),
        PropertySchema(
            name="plane_model", label="Plane Model [a,b,c,d]", type="vec4",
            default=None,
            help_text="Optional override: plane coefficients. If None, auto-fitted via RANSAC."
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Vertices (as points)")]
)
```

---

## 8. Mock Data for Frontend (Until Backend is Implemented)

Frontend nodes that display mesh metadata from `payload` can use this mock response when stubbing the operation:

```typescript
// Mock payload metadata from GeneratePlane (boundary mode)
const mockGeneratePlaneMeta = {
  vertex_count: 1243,
  triangle_count: 2318,
  area: 4.2,
  plane_model: [0.02, -0.01, 0.999, -0.15],
  mode: "boundary",
  voxel_size: 0.05,
  // Note: "mesh" key is NOT serializable — never present in JSON payloads
};

// Mock payload metadata (square mode)
const mockGeneratePlaneMetaSquare = {
  vertex_count: 2500,
  triangle_count: 4802,
  area: 1.0,
  plane_model: [0.0, 0.0, 1.0, 0.0],
  mode: "square",
  voxel_size: 0.02,
};
```

---

*This specification covers the full internal API contract for `GeneratePlane`. No new REST endpoints are introduced by this feature.*
