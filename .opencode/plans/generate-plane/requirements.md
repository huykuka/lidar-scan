# Feature: Generate Plane from Segmentation Output

## Feature Overview

Add a new backend pipeline operation called `GeneratePlane` that creates a 3D planar mesh from segmented point cloud data. This operation supports two distinct modes:

1. **Square Plane Mode**: Generate a centered square plane mesh of user-specified size at the origin with Z-axis normal
2. **Boundary-Fitted Mode**: Generate a plane mesh that exactly matches the convex hull boundary of the input segmentation

Both modes produce an Open3D TriangleMesh with configurable vertex grid spacing (voxel_size). The operation integrates seamlessly into the existing DAG pipeline as a standard `PipelineOperation`.

**Key Capabilities**:
- Accept either point cloud input OR plane model coefficients [a,b,c,d]
- Generate high-quality triangle meshes suitable for visualization, export, or downstream processing
- Configurable vertex density via voxel_size parameter
- Minimal performance overhead (runs on threadpool like other Open3D operations)

## User Stories

### As a robotics engineer:
- I want to generate a planar mesh from my segmented ground/wall/table point clouds, so I can export it for use in collision detection, path planning, or CAD integration
- I want to control the mesh resolution (via voxel_size) to balance between quality and file size when exporting meshes

### As a quality inspector:
- I want to generate a precise mesh matching the exact boundary of a detected surface (e.g., warehouse floor, conveyor belt), so I can measure surface area, flatness, or defects
- I want to overlay the generated mesh on the original point cloud for visual verification of segmentation accuracy

### As a backend developer:
- I want a simple, reusable operation that accepts the output from `PlaneSegmentation` without manual data extraction, so I can chain operations in the DAG
- I want clear parameter validation and error messages when inputs are invalid (e.g., insufficient points, invalid plane model)

### As a data scientist:
- I want to generate synthetic planar surfaces for augmenting training datasets (square plane mode at origin), so I can create controlled test scenarios
- I want to specify grid resolution independently from segmentation voxel parameters

## Acceptance Criteria

### Functional Requirements

#### Input Handling
- [x] **Dual Input Support**: Operation MUST accept either:
  - **Point Cloud Input**: `o3d.t.geometry.PointCloud` (tensor-based) from segmentation output
  - **Plane Model Input**: 4-element plane coefficients [a,b,c,d] where ax + by + cz + d = 0
- [x] **Auto-Detection**: If input is a PointCloud, extract plane model by fitting (RANSAC) or require it in metadata
- [x] **Validation**: Reject invalid inputs (empty point clouds, degenerate plane models, non-numeric coefficients)

#### Mode 1: Square Plane Generation
- [x] **Parameter**: `mode="square"`, `size: float` (side length in meters)
- [x] **Position**: Plane centered at origin (0, 0, 0)
- [x] **Orientation**: Normal vector aligned with Z-axis (0, 0, 1)
- [x] **Mesh Generation**: Create uniform grid of vertices with spacing = voxel_size
  - Grid dimensions: `ceil(size / voxel_size) x ceil(size / voxel_size)` vertices
  - Triangle topology: Two triangles per grid cell (standard mesh quad subdivision)
- [x] **Output**: `o3d.t.geometry.TriangleMesh` with vertex positions, triangle indices, and optionally vertex normals

#### Mode 2: Boundary-Fitted Plane Generation
- [x] **Parameter**: `mode="boundary"`
- [x] **Boundary Extraction**:
  - Project input point cloud points onto the fitted plane (3D → 2D projection using plane normal)
  - Compute 2D convex hull of projected points
  - Triangulate the convex hull region with vertex spacing = voxel_size
- [x] **Mesh Generation**:
  - Generate uniform grid within the convex hull boundary
  - Vertices lie on the fitted plane surface
  - Triangulate using Delaunay or grid-based method (ensure manifold mesh)
- [x] **Output**: `o3d.t.geometry.TriangleMesh` matching the exact convex hull shape

#### Common Parameters
- [x] **voxel_size** (float, default=0.01): Grid spacing between vertices (in meters)
  - Smaller values = denser mesh, larger file size
  - Larger values = coarser mesh, faster generation
  - Must be > 0 and < size (for square mode) or < min_dimension (for boundary mode)
- [x] **mode** (string, default="square"): Generation mode ("square" | "boundary")

#### Output Format
- [x] **Primary Output**: `o3d.t.geometry.TriangleMesh` (tensor-based for consistency with pipeline)
- [x] **Metadata Dictionary** (second return value):
  ```python
  {
      "vertex_count": int,        # Number of vertices in mesh
      "triangle_count": int,      # Number of triangles in mesh
      "area": float,              # Surface area in square meters (if computable)
      "plane_model": [a,b,c,d],   # Plane coefficients used
      "mode": "square" | "boundary",
      "voxel_size": float
  }
  ```

### Error Handling
- [x] **Empty Input**: If point cloud has < 3 points, raise ValueError with message "Insufficient points for plane generation (minimum 3 required)"
- [x] **Invalid Plane Model**: If plane coefficients are degenerate (e.g., normal = [0,0,0]), raise ValueError with message "Invalid plane model: degenerate normal vector"
- [x] **Invalid Parameters**:
  - `voxel_size <= 0`: Raise ValueError "voxel_size must be > 0"
  - `size <= 0` (square mode): Raise ValueError "size must be > 0"
  - `mode not in ["square", "boundary"]`: Raise ValueError "mode must be 'square' or 'boundary'"
- [x] **Convex Hull Failure** (boundary mode): If 2D projection collapses to a line, raise ValueError with message "Cannot compute convex hull: projected points are colinear"

### Performance Requirements
- [x] **Async Execution**: Mesh generation MUST run on threadpool via `await asyncio.to_thread()` to prevent blocking the FastAPI event loop
- [x] **Benchmark Targets**:
  - Square plane (1m x 1m, voxel_size=0.01): < 100ms generation time
  - Boundary-fitted plane (1000 input points, voxel_size=0.01): < 500ms generation time
- [x] **Memory Efficiency**: Generated mesh size MUST NOT exceed 10x the input point cloud memory footprint

### Integration Requirements
- [x] **Pipeline Compatibility**: Implement as subclass of `PipelineOperation` in `app/modules/pipeline/operations/generate_plane.py`
- [x] **Signature**: Follow existing pattern:
  ```python
  def apply(self, pcd: Any) -> Tuple[o3d.t.geometry.TriangleMesh, Dict[str, Any]]:
      """Generates a plane mesh from point cloud or plane model."""
      pass
  ```
- [x] **Registry**: No registration needed (operations are dynamically loaded, not registered like modules)
- [x] **Type Compatibility**: Support both Tensor-based (`o3d.t.geometry.PointCloud`) and legacy (`o3d.geometry.PointCloud`) input with automatic conversion if needed

### Validation & Testing
- [x] **Unit Tests** (in `tests/modules/pipeline/operations/test_generate_plane.py`):
  - Test square mode with various sizes and voxel_sizes
  - Test boundary mode with different segmentation shapes (rectangular, circular, irregular)
  - Test input validation (empty clouds, invalid parameters)
  - Test plane model extraction from metadata
  - Test output mesh properties (vertex count, triangle count, manifoldness)
- [x] **Integration Tests**:
  - Chain `PlaneSegmentation` → `GeneratePlane` in DAG
  - Verify mesh can be exported to OBJ/PLY/STL formats
  - Verify mesh can be visualized in downstream operations
- [x] **Edge Cases**:
  - Very small voxel_size (e.g., 0.001) → verify memory limits
  - Very large size/boundary → verify generation time limits
  - Degenerate inputs (coplanar points, single-line clusters) → verify graceful error handling

## Out of Scope

### Not Included in This Feature
- **Texture Mapping**: No UV coordinates or texture images. Generated meshes are geometry-only
- **Color/Intensity Transfer**: Mesh vertices do NOT inherit colors or intensity values from input points (future enhancement)
- **Normals Computation**: Vertex normals are auto-computed by Open3D if needed, but not explicitly calculated or smoothed
- **Mesh Smoothing/Subdivision**: No Laplacian smoothing, Catmull-Clark subdivision, or other post-processing. Output is a raw grid-based mesh
- **Non-Planar Surfaces**: This operation only generates planar meshes. Curved surface fitting (NURBS, splines) is out of scope
- **Multi-Plane Generation**: Generates only one plane per operation call. For multiple planes, chain multiple operations in the DAG
- **Hole Filling**: For boundary mode, if convex hull has concave regions, they are NOT filled (convex hull always convex by definition)
- **Frontend Visualization**: This is a backend-only feature. Frontend mesh rendering enhancements are a separate task
- **Export Functionality**: Mesh export to file formats (OBJ/STL/PLY) is handled by existing output nodes, not this operation
- **Plane Alignment to Gravity/World Frame**: No automatic alignment to world Z-axis or gravity vector. Use calibration/transform nodes for that

## Technical Constraints

### Open3D Compatibility
- **Primary API**: Use Tensor-based API (`o3d.t.geometry.*`) for consistency with modern pipeline
- **Legacy Fallback**: If input is legacy `o3d.geometry.PointCloud`, convert to tensor, process, and convert back if needed
- **Version Compatibility**: Target Open3D >= 0.13.0 (tensor API stable)

### Performance
- **Threadpool Execution**: All mesh generation code MUST run in `asyncio.to_thread()` to avoid blocking
- **Mesh Size Limits**: Cap maximum vertex count at 1 million vertices (safety limit to prevent OOM errors)
  - If `ceil(size/voxel_size)^2 > 1_000_000`, raise ValueError with suggestion to increase voxel_size
- **Convex Hull Algorithm**: Use Open3D or Scipy's Delaunay/ConvexHull (whichever is faster)

### Data Integrity
- **Manifold Meshes**: Generated meshes SHOULD be manifold (no holes, no duplicate vertices), but not strictly required for this v1
- **Plane Model Precision**: Use float64 for plane coefficients during computation, convert to float32 for output if needed

### Pipeline Architecture
- **Stateless Operation**: No internal state between `apply()` calls (pure function)
- **No Direct Orchestrator Coupling**: Operation MUST NOT import or reference the DAG orchestrator
- **Metadata Propagation**: Plane model coefficients from segmentation metadata SHOULD be preserved in output metadata

## Dependencies

### Existing Systems
- **PipelineOperation Base Class**: `app/modules/pipeline/base.py` - Defines `apply()` interface
- **PlaneSegmentation Operation**: `app/modules/pipeline/operations/segmentation.py` - Provides input data (point cloud + plane_model metadata)
- **PointConverter Utility**: `app/modules/pipeline/base.py` - For converting between numpy/Open3D formats if needed

### External Libraries
- **Open3D**: Already installed, used for TriangleMesh, PointCloud, and geometry algorithms
- **NumPy**: Already installed, used for plane projection math and array operations
- **SciPy** (optional): If Open3D's convex hull is insufficient, SciPy's `scipy.spatial.ConvexHull` can be used

### Backend Rules
- Follow type hinting rules from `.opencode/rules/backend.md`
- Use Pydantic models if exposing parameters via REST API (though operations are typically configured via JSON in DAG definitions)

## Success Metrics

### Quantitative
- [x] 100% of unit tests pass (minimum 10 test cases covering both modes)
- [x] Integration test: PlaneSegmentation → GeneratePlane chain completes in < 1 second for typical scan (10k points, voxel_size=0.01)
- [x] Memory usage: Generated mesh < 10MB for typical use cases
- [x] Performance: Square mode < 100ms, Boundary mode < 500ms (measured on dev machine)

### Qualitative
- [x] Backend developers can add `GeneratePlane` to DAG JSON configs without reading documentation (self-explanatory parameters)
- [ ] Generated meshes can be exported and opened in MeshLab/Blender without errors
- [x] Error messages are clear and actionable (users understand how to fix invalid inputs)
- [x] Code follows existing operation patterns (easy to review and maintain)

## Open Questions

### To Be Decided During Implementation
- **Mesh Topology**: Grid-based triangulation vs Delaunay triangulation for boundary mode? (Recommend grid-based for speed)
- **Normal Direction**: Should mesh normals always point "up" (positive Z for square mode)? Or follow plane model orientation?
- **Metadata Format**: Should `plane_model` metadata follow a strict schema (Pydantic model) or just be a list?
- **Edge Cases**: How to handle extremely thin/elongated convex hulls in boundary mode (aspect ratio > 100:1)?

### Deferred to Technical Specification
- Exact algorithm for 2D projection (choose orthogonal projection basis vectors)
- Mesh vertex ordering (CCW vs CW winding for normals)
- Whether to support Open3D's TriangleMesh.create_from_point_cloud_poisson() for smoother meshes (future enhancement)

## Example Usage

### Example 1: Square Plane at Origin
```python
# DAG Configuration (JSON)
{
  "node_id": "plane_gen_1",
  "type": "pipeline",
  "operation": "GeneratePlane",
  "params": {
    "mode": "square",
    "size": 1.0,          # 1 meter x 1 meter
    "voxel_size": 0.02    # 5cm vertex spacing → 50x50 = 2500 vertices
  }
}

# Expected Output Metadata:
{
  "vertex_count": 2500,
  "triangle_count": 4802,  # ~2 triangles per grid cell
  "area": 1.0,
  "plane_model": [0, 0, 1, 0],  # Z-aligned plane through origin
  "mode": "square",
  "voxel_size": 0.02
}
```

### Example 2: Boundary-Fitted Plane from Segmentation
```python
# DAG Configuration (chained operations)
{
  "nodes": [
    {
      "node_id": "segment_floor",
      "type": "pipeline",
      "operation": "PlaneSegmentation",
      "params": {
        "distance_threshold": 0.01,
        "ransac_n": 3,
        "num_iterations": 1000
      }
    },
    {
      "node_id": "generate_floor_mesh",
      "type": "pipeline",
      "operation": "GeneratePlane",
      "params": {
        "mode": "boundary",
        "voxel_size": 0.01   # 1cm resolution
      }
    }
  ],
  "edges": [
    {"from": "segment_floor", "to": "generate_floor_mesh"}
  ]
}

# Expected Output Metadata (example):
{
  "vertex_count": 15234,
  "triangle_count": 30102,
  "area": 12.5,            # ~12.5 square meters floor area
  "plane_model": [0.02, -0.01, 0.999, -0.15],  # Fitted plane coefficients
  "mode": "boundary",
  "voxel_size": 0.01
}
```

### Example 3: Error Case - Invalid Input
```python
# Empty point cloud input
pcd = o3d.t.geometry.PointCloud()
gen = GeneratePlane(mode="boundary", voxel_size=0.01)
result = gen.apply(pcd)  # Raises: ValueError("Insufficient points for plane generation (minimum 3 required)")
```

## References

### Code Locations
- New operation file: `app/modules/pipeline/operations/generate_plane.py`
- Base class: `app/modules/pipeline/base.py` (PipelineOperation)
- Related operations:
  - PlaneSegmentation: `app/modules/pipeline/operations/segmentation.py`
  - BoundaryDetection: `app/modules/pipeline/operations/boundary.py`
  - Crop: `app/modules/pipeline/operations/crop.py`
- Test file: `tests/modules/pipeline/operations/test_generate_plane.py`

### Related Features
- None (this is a net-new feature, not building on existing plans)

### Architecture Rules
- Backend: `.opencode/rules/backend.md`
- Pipeline architecture: See `app/modules/pipeline/README.md` (if exists)

### External Documentation
- Open3D TriangleMesh API: http://www.open3d.org/docs/latest/python_api/open3d.t.geometry.TriangleMesh.html
- Open3D Plane Segmentation: http://www.open3d.org/docs/latest/python_api/open3d.t.geometry.PointCloud.html#open3d.t.geometry.PointCloud.segment_plane

---

**Document Status**: ✅ Complete - Ready for @architecture to define technical implementation in `technical.md`

**Next Steps**:
1. @architecture: Review requirements and create `technical.md` with algorithm details (projection math, triangulation approach, mesh topology)
2. @architecture: Define API contract in `api-spec.md` (if this operation exposes REST endpoints, though likely not needed)
3. @be-dev: Implement `GeneratePlane` operation in `app/modules/pipeline/operations/generate_plane.py`
4. @be-dev: Write unit tests covering all acceptance criteria
5. @qa: Validate mesh output quality, performance benchmarks, and error handling
