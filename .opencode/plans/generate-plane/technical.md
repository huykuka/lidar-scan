# Technical Specification: GeneratePlane Pipeline Operation

**Feature**: Generate Plane from Segmentation Output  
**Status**: Ready for Implementation  
**Architect**: @architecture  
**Date**: 2026-04-04

---

## 1. Architecture Overview

`GeneratePlane` is a new **terminal** `PipelineOperation` that converts segmented point cloud data into an `o3d.t.geometry.TriangleMesh`. It slots into the existing DAG as a leaf node — it accepts a point cloud but its primary output is a `TriangleMesh`, not a filtered point cloud. See §4 for the critical constraint this creates.

### 1.1 Component Placement

```
app/
└── modules/
    └── pipeline/
        ├── base.py                      (PipelineOperation ABC — no changes)
        ├── factory.py                   ← ADD "generate_plane" → GeneratePlane
        ├── registry.py                  ← ADD NodeDefinition + factory alias
        └── operations/
            ├── __init__.py              ← ADD GeneratePlane export
            ├── segmentation.py          (PlaneSegmentation — no changes)
            └── generate_plane.py        ← NEW FILE
tests/
└── pipeline/
    └── operations/
        └── test_generate_plane.py       ← NEW FILE (TDD-first)
```

---

## 2. Critical Architectural Constraint: Mesh Output in OperationNode

### 2.1 The Problem

`OperationNode.on_input()` (in `operation_node.py`, line 73) always calls:

```python
return PointConverter.to_points(pcd_out)
```

`PointConverter.to_points()` is typed and implemented only for `o3d.t.geometry.PointCloud` and `o3d.geometry.PointCloud`. A `TriangleMesh` will fall through all branches and return `np.zeros((0, 3))`, causing the downstream frame to be silently dropped (the `if len(processed_points) == 0: return` guard on line 84).

### 2.2 Design Decision: Mesh-to-Points Vertex Passthrough

Rather than altering the `OperationNode` generic infrastructure (broad blast radius), `GeneratePlane.apply()` returns the mesh **AND** the mesh's vertex positions packed back as a numpy-compatible `o3d.t.geometry.PointCloud`. This maintains:

1. **Full `PointConverter` compatibility** — no changes to `operation_node.py` or `base.py`.
2. **Downstream streaming** — mesh vertices flow as points through the WebSocket LIDR protocol for real-time visualization.
3. **Mesh preservation in metadata** — the full `TriangleMesh` object is stored in the metadata dict so downstream mesh-aware consumers (export nodes, REST API) can retrieve it.

### 2.3 apply() Return Contract

```python
def apply(self, pcd: Any) -> Tuple[o3d.t.geometry.PointCloud, Dict[str, Any]]:
    # Returns vertex positions as a PointCloud (for DAG passthrough compatibility)
    # The full TriangleMesh is embedded in metadata["mesh"]
    return vertex_pcd, {
        "mesh": triangle_mesh,          # o3d.t.geometry.TriangleMesh
        "vertex_count": int,
        "triangle_count": int,
        "area": float,
        "plane_model": List[float],     # [a, b, c, d]
        "mode": str,                    # "square" | "boundary"
        "voxel_size": float,
    }
```

> **Rationale**: This is consistent with how `DebugSave` "re-emits" the original `pcd` unchanged. Here, `GeneratePlane` emits vertex positions so the node stays live in the DAG and the mesh can be accessed by downstream mesh-aware nodes that explicitly check `payload.get("mesh")`.

---

## 3. Algorithm Specification

### 3.1 Shared: Input Normalization

Both modes share the same entry path:

```
Input: pcd (Any)
  ├─ isinstance o3d.t.geometry.PointCloud  → use directly
  ├─ isinstance o3d.geometry.PointCloud    → convert via o3d.t.geometry.PointCloud.from_legacy(pcd)
  └─ anything else                         → raise TypeError("Unsupported input type")

Point count check:
  N = pcd.point.positions.shape[0]
  if N < 3: raise ValueError("Insufficient points for plane generation (minimum 3 required)")
```

### 3.2 Shared: Plane Model Resolution

```
if self.plane_model is not None:
    # User-supplied plane coefficients [a,b,c,d] (e.g., from prior segmentation stored in DAG state)
    [a, b, c, d] = self.plane_model
else:
    # Extract from metadata attached to the pcd (set by PlaneSegmentation upstream)
    # Metadata propagation pattern: pcd carries no metadata; use constructor-time plane_model OR
    # pass plane_model as constructor parameter after PlaneSegmentation sets it in payload metadata.
    # If neither available, run lightweight RANSAC on the input cloud.
    plane_model_tensor, _ = pcd.segment_plane(
        distance_threshold=0.01, ransac_n=3, num_iterations=1000, probability=0.9999
    )
    [a, b, c, d] = plane_model_tensor.cpu().numpy().tolist()

Normal validation:
  normal_len = sqrt(a² + b² + c²)
  if normal_len < 1e-6: raise ValueError("Invalid plane model: degenerate normal vector")
  # Normalize normal for projection math
  n̂ = [a, b, c] / normal_len
```

### 3.3 Mode 1: Square Plane Generation

**Goal**: Uniform grid mesh centered at origin, Z-up, ignoring input point cloud positions.

```
Parameters: size (float), voxel_size (float)

Validation:
  if size <= 0:    raise ValueError("size must be > 0")
  if voxel_size <= 0: raise ValueError("voxel_size must be > 0")
  n_steps = ceil(size / voxel_size)
  if n_steps * n_steps > 1_000_000:
      raise ValueError(f"Vertex count {n_steps**2} exceeds 1M limit. Increase voxel_size.")

Algorithm (pure NumPy):
  1. Generate 1D coordinate arrays:
       xs = np.linspace(-size/2, size/2, n_steps, dtype=np.float64)
       ys = np.linspace(-size/2, size/2, n_steps, dtype=np.float64)
  2. Meshgrid:
       XX, YY = np.meshgrid(xs, ys)          # shape: (n_steps, n_steps)
       ZZ = np.zeros_like(XX)
  3. Vertices:
       vertices = np.column_stack([XX.ravel(), YY.ravel(), ZZ.ravel()])  # (N, 3), float64
  4. Triangles (grid-based, CCW winding for +Z normal):
       For each grid cell (i, j) where i ∈ [0, n_steps-2], j ∈ [0, n_steps-2]:
         top_left     = i * n_steps + j
         top_right    = i * n_steps + j + 1
         bottom_left  = (i+1) * n_steps + j
         bottom_right = (i+1) * n_steps + j + 1
         Triangle 1: [top_left, bottom_left, top_right]      (CCW)
         Triangle 2: [top_right, bottom_left, bottom_right]  (CCW)
  5. Build TriangleMesh:
       mesh = o3d.t.geometry.TriangleMesh()
       mesh.vertex.positions = o3d.core.Tensor(vertices.astype(np.float32))
       mesh.triangle.indices = o3d.core.Tensor(triangles.astype(np.int32))
  6. Area:
       area = size * size  (exact, no Open3D call needed)

  Plane model for output metadata: [0.0, 0.0, 1.0, 0.0]  (Z-aligned, at origin)
```

### 3.4 Mode 2: Boundary-Fitted Plane Generation

**Goal**: Mesh that fills the convex hull of input point cloud, projected onto the fitted plane.

```
Algorithm:

STEP 1 — Project 3D points onto the plane's 2D coordinate frame:
  Given plane normal n̂ = [a, b, c] / |[a, b, c]|
  Build orthonormal basis {u, v} perpendicular to n̂:
    If |n̂ × [0,0,1]| > 1e-6:
        u = normalize(n̂ × [0,0,1])   // world-Z cross normal
    Else:
        u = normalize(n̂ × [1,0,0])   // fallback for near-Z-normal planes
    v = normalize(n̂ × u)              // complete right-hand basis
  Plane origin (closest point to world origin):
    P0 = -d * n̂                       // P0 = -d/|n|² * [a,b,c], normalized n so /1
  Project each point X_i:
    X_local = X_i - P0
    u_i = X_local · u
    v_i = X_local · v
  Result: 2D points UV = [[u_0,v_0], [u_1,v_1], ..., [u_N,v_N]]

STEP 2 — Compute 2D convex hull:
  from scipy.spatial import ConvexHull
  hull = ConvexHull(UV)
  if hull collapses (QhullError or only 2 vertices): raise ValueError(
      "Cannot compute convex hull: projected points are colinear"
  )
  hull_vertices_2d = UV[hull.vertices]  # shape: (K, 2)

STEP 3 — Generate uniform grid within hull:
  u_min, u_max = UV[:,0].min(), UV[:,0].max()
  v_min, v_max = UV[:,1].min(), UV[:,1].max()
  
  # Safety check for degenerate (thin) hull
  u_range = u_max - u_min
  v_range = v_max - v_min
  if u_range < voxel_size or v_range < voxel_size:
      raise ValueError("Cannot compute convex hull: projected points are colinear")
  
  n_u = ceil(u_range / voxel_size) + 1
  n_v = ceil(v_range / voxel_size) + 1
  if n_u * n_v > 1_000_000:
      raise ValueError(f"Vertex count exceeds 1M limit. Increase voxel_size.")
  
  grid_us = np.linspace(u_min, u_max, n_u)
  grid_vs = np.linspace(v_min, v_max, n_v)
  GU, GV = np.meshgrid(grid_us, grid_vs)
  grid_2d = np.column_stack([GU.ravel(), GV.ravel()])  # (n_u*n_v, 2)

STEP 4 — Filter grid points to convex hull interior:
  Use scipy.spatial.Delaunay(hull_vertices_2d) for inside-test:
    from scipy.spatial import Delaunay
    hull_delaunay = Delaunay(hull_vertices_2d)
    inside_mask = hull_delaunay.find_simplex(grid_2d) >= 0
    interior_2d = grid_2d[inside_mask]           # (M, 2)
    interior_indices = np.where(inside_mask)[0]  # maps interior→grid flat idx

STEP 5 — Back-project 2D → 3D plane surface:
  interior_3d = P0 + interior_2d[:,0:1] * u + interior_2d[:,1:2] * v  # (M, 3)

STEP 6 — Triangulate interior points:
  Use scipy.spatial.Delaunay on interior_2d (not the hull):
    tri = Delaunay(interior_2d)
    triangles = tri.simplices  # (T, 3), indices into interior_3d

  Note: Delaunay on the 2D plane produces a well-conditioned manifold triangulation.
  Winding order: CCW from the perspective of n̂ (verify post-hoc or rely on Open3D
  compute_vertex_normals to orient consistently).

STEP 7 — Build TriangleMesh:
  mesh = o3d.t.geometry.TriangleMesh()
  mesh.vertex.positions = o3d.core.Tensor(interior_3d.astype(np.float32))
  mesh.triangle.indices = o3d.core.Tensor(triangles.astype(np.int32))

STEP 8 — Area computation:
  area = mesh.get_surface_area()  # or compute from triangles analytically
  # Fallback: approximate as hull area
  #   area_approx = hull.volume  (in 2D, ConvexHull.volume = area)
```

### 3.5 Vertex Normal Computation (Optional, Both Modes)

After mesh construction, if callers want normals:
```python
mesh.compute_vertex_normals()   # Open3D t.geometry API call (in-place)
```
This is **not called by default** to keep the operation within performance budgets (normals are out-of-scope per requirements).

---

## 4. DAG Integration & Node Lifecycle

### 4.1 `factory.py` Addition

```python
from app.modules.pipeline.operations.generate_plane import GeneratePlane

_OP_MAP["generate_plane"] = GeneratePlane
```

### 4.2 `operations/__init__.py` Addition

```python
from .generate_plane import GeneratePlane
```

### 4.3 `registry.py` NodeDefinition

```python
node_schema_registry.register(NodeDefinition(
    type="generate_plane",
    display_name="Generate Plane Mesh",
    category="operation",
    description="Generates a planar triangle mesh from segmented point cloud",
    icon="grid_on",
    websocket_enabled=True,   # Streams mesh vertices as point positions
    properties=[
        PropertySchema(name="throttle_ms", ...),
        PropertySchema(name="mode", label="Mode", type="select",
                       default="square",
                       options=[
                           {"label": "Square (origin-centered)", "value": "square"},
                           {"label": "Boundary-Fitted", "value": "boundary"},
                       ]),
        PropertySchema(name="size", label="Size (m)", type="number",
                       default=1.0, step=0.1, min=0.01,
                       help_text="Side length for square mode (ignored in boundary mode)"),
        PropertySchema(name="voxel_size", label="Vertex Spacing (m)", type="number",
                       default=0.05, step=0.005, min=0.001,
                       help_text="Grid vertex spacing in meters"),
        PropertySchema(name="plane_model", label="Plane Model [a,b,c,d]", type="vec4",
                       default=None,
                       help_text="Optional override plane coefficients. If None, extracted from upstream segmentation."),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Vertices (as points)")]
))
```

Then at the bottom of `registry.py`, add `"generate_plane"` to `_OPERATION_TYPES`.

### 4.4 NodeFactory Alias

```python
# At end of registry.py:
NodeFactory._registry["generate_plane"] = NodeFactory._registry["operation"]
```

### 4.5 DAG JSON Configuration Example

```json
{
  "id": "gen_plane_1",
  "type": "generate_plane",
  "name": "Floor Mesh Generator",
  "config": {
    "op_type": "generate_plane",
    "mode": "boundary",
    "voxel_size": 0.05
  }
}
```

> Note: `op_type` must be set in `config` because `build_operation()` in `registry.py` reads `config.get("op_type") or node.get("type")`. Both paths resolve to `"generate_plane"`.

---

## 5. Async & Threadpool Strategy

`GeneratePlane.apply()` is a **synchronous method** (per `PipelineOperation` contract). The `OperationNode.on_input()` wraps all non-`visualize` operations with `await asyncio.to_thread(_sync_compute)`. This applies automatically — no changes to `OperationNode`.

The heavy numpy/scipy work in `apply()` must **not** use asyncio primitives. It runs entirely synchronously inside `_sync_compute()`.

---

## 6. Memory Safety

```
Vertex count safety gate (shared, both modes):
  max_dim = ceil(max(u_range, v_range, size) / voxel_size)
  if max_dim ** 2 > 1_000_000:
      raise ValueError(
          f"Requested mesh would produce ~{max_dim**2:,} vertices "
          f"(limit: 1,000,000). Increase voxel_size."
      )
```

This check is performed **before** any allocation. For boundary mode, a pre-check on the bounding box extents is sufficient. Exact interior point count is always ≤ bbox vertex count.

---

## 7. Input: `plane_model` Parameter Handling

The `PlaneSegmentation.apply()` returns `plane_model` in the **metadata dict**, not on the point cloud object itself. However, `OperationNode.on_input()` discards metadata from upstream operations — it only forwards `payload["points"]` (numpy array) through `PointConverter`.

This means `GeneratePlane` **cannot automatically receive** `plane_model` from a chained `PlaneSegmentation` unless:

### Resolution (v1): Constructor Parameter

The user explicitly provides `plane_model` as a constructor parameter in the DAG config:

```json
{
  "config": {
    "op_type": "generate_plane",
    "mode": "boundary",
    "voxel_size": 0.05,
    "plane_model": [0.02, -0.01, 0.999, -0.15]
  }
}
```

If `plane_model` is `None` (default), `GeneratePlane` runs a lightweight RANSAC on the incoming point cloud to extract it. This adds ~50-200ms overhead but requires no pipeline changes.

### Resolution (v2 — future): Metadata Propagation

Extend `OperationNode.on_input()` to propagate metadata from upstream operations in `payload`. This is a broader change affecting all operations and is **deferred** to a future architectural ticket.

### Constructor signature:

```python
def __init__(
    self,
    mode: str = "square",
    size: float = 1.0,
    voxel_size: float = 0.05,
    plane_model: Optional[List[float]] = None
):
```

---

## 8. Type Signatures & Contracts

```python
# app/modules/pipeline/operations/generate_plane.py

from __future__ import annotations

import math
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull, Delaunay, QhullError

from ..base import PipelineOperation

logger = logging.getLogger(__name__)

MAX_VERTICES: int = 1_000_000
MIN_POINTS: int = 3

class GeneratePlane(PipelineOperation):
    """
    Generates a planar TriangleMesh from a segmented point cloud.

    Returns vertex positions as a PointCloud for DAG/WebSocket compatibility,
    with the full TriangleMesh embedded in metadata["mesh"].

    Args:
        mode:         "square" | "boundary"
        size:         Side length in meters (square mode only)
        voxel_size:   Vertex grid spacing in meters
        plane_model:  Optional [a,b,c,d] plane coefficients.
                      If None, fitted via RANSAC from input.
    """

    def __init__(
        self,
        mode: str = "square",
        size: float = 1.0,
        voxel_size: float = 0.05,
        plane_model: Optional[List[float]] = None,
    ) -> None: ...

    def apply(self, pcd: Any) -> Tuple[o3d.t.geometry.PointCloud, Dict[str, Any]]:
        """
        Returns:
            (vertex_pcd, metadata)

            vertex_pcd: o3d.t.geometry.PointCloud of mesh vertex positions
            metadata: {
                "mesh":           o3d.t.geometry.TriangleMesh,
                "vertex_count":   int,
                "triangle_count": int,
                "area":           float,
                "plane_model":    List[float],  # [a, b, c, d]
                "mode":           str,
                "voxel_size":     float,
            }
        """
        ...

    # Private helpers
    def _resolve_plane_model(self, pcd: o3d.t.geometry.PointCloud) -> np.ndarray: ...
    def _generate_square(self, plane_model: np.ndarray) -> Tuple[np.ndarray, np.ndarray]: ...
    def _generate_boundary(
        self, pcd: o3d.t.geometry.PointCloud, plane_model: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]: ...
    def _build_mesh(
        self, vertices: np.ndarray, triangles: np.ndarray
    ) -> o3d.t.geometry.TriangleMesh: ...
    def _vertices_to_pcd(
        self, vertices: np.ndarray
    ) -> o3d.t.geometry.PointCloud: ...
```

---

## 9. Error Handling Matrix

| Condition                                 | Exception            | Message                                                                                   |
|-------------------------------------------|----------------------|-------------------------------------------------------------------------------------------|
| `N < 3`                                   | `ValueError`         | `"Insufficient points for plane generation (minimum 3 required)"`                        |
| `normal = [0,0,0]`                        | `ValueError`         | `"Invalid plane model: degenerate normal vector"`                                         |
| `voxel_size <= 0`                         | `ValueError`         | `"voxel_size must be > 0"`                                                                |
| `size <= 0` (square mode)                 | `ValueError`         | `"size must be > 0"`                                                                      |
| `mode ∉ {"square","boundary"}`            | `ValueError`         | `"mode must be 'square' or 'boundary'"`                                                   |
| Projected points colinear (boundary mode) | `ValueError`         | `"Cannot compute convex hull: projected points are colinear"`                             |
| Vertex count > 1M                         | `ValueError`         | `"Requested mesh would produce ~N vertices (limit: 1,000,000). Increase voxel_size."`    |
| Unsupported input type                    | `TypeError`          | `"Unsupported input type: expected o3d PointCloud"`                                       |

All errors propagate naturally to `OperationNode.on_input()` where they are caught, logged to `self.last_error`, and reported via `notify_status_change()`.

---

## 10. Performance Analysis

| Scenario                              | Complexity         | Expected time |
|---------------------------------------|--------------------|---------------|
| Square 1m×1m, voxel=0.01 (10k verts) | O(n²) meshgrid     | < 50ms        |
| Square 5m×5m, voxel=0.01 (250k verts)| O(n²)              | < 300ms       |
| Boundary 1k pts, voxel=0.05          | O(N log N) Delaunay| < 200ms       |
| Boundary 10k pts, voxel=0.01         | O(N log N)         | < 500ms       |

The O(N log N) SciPy Delaunay and ConvexHull algorithms are the bottleneck for boundary mode with large voxel grids. The 1M vertex cap and threadpool execution ensure the FastAPI event loop is never blocked.

---

## 11. Dependencies

| Library    | Version  | Usage                                    |
|------------|----------|------------------------------------------|
| `open3d`   | ≥ 0.13   | TriangleMesh, PointCloud, Tensor APIs    |
| `numpy`    | ≥ 1.21   | meshgrid, linspace, array ops            |
| `scipy`    | ≥ 1.7    | ConvexHull, Delaunay, QhullError         |

SciPy is listed as optional in requirements but **must be available**. The developer should verify it is already in `requirements.txt` / `pyproject.toml`. If not, it must be added.

---

## 12. Non-Obvious Design Constraints Summary

1. **`GeneratePlane` is DAG-terminal for mesh operations**: Its return is vertex positions as a `PointCloud`, not the mesh object. The mesh lives in `metadata["mesh"]`. Downstream nodes that want the mesh must consume `payload["metadata"]["mesh"]` — but no such nodes exist today. This is the expected v1 behaviour.

2. **`plane_model` is NOT automatically threaded from `PlaneSegmentation`**: `OperationNode` strips metadata between nodes. Users MUST either supply `plane_model` in the DAG config OR accept RANSAC overhead.

3. **CCW winding convention**: Square mode uses CCW winding as viewed from +Z (normal is [0,0,1]). Boundary mode winding follows SciPy Delaunay's simplex order, which may not be consistently CCW from the plane normal direction. Downstream mesh tools (MeshLab, Blender) handle both.

4. **Float32 vs Float64**: Internal projection math uses `float64` for numerical stability. Final mesh vertices are cast to `float32` before the Open3D Tensor (matching LIDR protocol and point cloud convention).

5. **SciPy Delaunay for boundary interior**: The boundary hull defines the interior region; a second Delaunay call on the *interior grid points* (not the hull) generates the actual triangulation. This ensures all triangles are interior to the hull.

6. **`websocket_enabled=True` in NodeDefinition**: Even though the primary product is a mesh, vertex positions are streamed as point data. This allows real-time preview in the frontend without any frontend changes.
