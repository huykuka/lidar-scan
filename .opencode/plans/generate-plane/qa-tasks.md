# QA Tasks: GeneratePlane Operation

**Feature**: Generate Plane from Segmentation Output  
**Assignee**: @qa  
**References**:
- Requirements: `.opencode/plans/generate-plane/requirements.md`
- Technical spec: `.opencode/plans/generate-plane/technical.md`
- API contract: `.opencode/plans/generate-plane/api-spec.md`
- Backend tasks: `.opencode/plans/generate-plane/backend-tasks.md`

**Workflow**: Check off each task (`- [x]`) as it is verified. Do not mark a task complete unless the assertion/check explicitly passes.

---

## QA Gate 0: Pre-QA Prerequisites

- [ ] **G0.1** Confirm @be-dev has checked off ALL tasks in `backend-tasks.md` Phases 0–7.
- [ ] **G0.2** Confirm `tests/pipeline/operations/test_generate_plane.py` exists and has a minimum of **10 test functions** (requirement states minimum 10 test cases).
- [ ] **G0.3** Run the baseline pipeline test suite before any QA-specific tests to verify dev left it green:
  ```bash
  pytest tests/pipeline/operations/ -v
  ```
  Expected: ALL tests pass (0 failures). Block QA if any failures exist.
- [ ] **G0.4** Verify `GeneratePlane` is importable from the public operations package:
  ```bash
  python -c "from app.modules.pipeline.operations import GeneratePlane; print('OK')"
  ```
- [ ] **G0.5** Verify factory registration:
  ```bash
  python -c "
  from app.modules.pipeline.factory import OperationFactory
  op = OperationFactory.create('generate_plane', {'mode': 'square', 'size': 1.0, 'voxel_size': 0.05})
  print(type(op).__name__)
  "
  ```
  Expected: `GeneratePlane`

---

## Section 1: Unit Test Execution & Coverage

### 1.1 Run Full New Test File

- [ ] **1.1.1** Execute with verbose output and capture results:
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py -v --tb=short 2>&1 | tee /tmp/qa_generate_plane_unit.txt
  ```
- [ ] **1.1.2** Verify test count meets minimum: count lines matching `PASSED` — must be **≥ 10**.
- [ ] **1.1.3** Confirm **0 FAILED**, **0 ERROR** results.
- [ ] **1.1.4** Attach `/tmp/qa_generate_plane_unit.txt` to the QA report.

### 1.2 Validate Test Coverage

- [ ] **1.2.1** Run coverage analysis on the new operation file:
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py \
    --cov=app.modules.pipeline.operations.generate_plane \
    --cov-report=term-missing \
    --cov-report=html:/tmp/qa_coverage_generate_plane
  ```
- [ ] **1.2.2** Verify statement coverage is **≥ 90%**.
- [ ] **1.2.3** Identify any uncovered branches (shown as `Miss` lines). If critical error paths are uncovered, raise a finding.
- [ ] **1.2.4** Document coverage percentage in `qa-report.md`.

---

## Section 2: Functional Acceptance Criteria

### 2.1 Input Handling (AC: Input Handling)

- [ ] **2.1.1** ✅ **Dual input support — Tensor PointCloud**:
  ```python
  import open3d as o3d, numpy as np
  from app.modules.pipeline.operations.generate_plane import GeneratePlane
  pts = np.random.rand(50, 3).astype(np.float32)
  pts[:, 2] = 0  # flat on Z=0
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(pts)
  gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.1, plane_model=[0,0,1,0])
  result_pcd, meta = gen.apply(pcd)
  assert isinstance(result_pcd, o3d.t.geometry.PointCloud)
  ```

- [ ] **2.1.2** ✅ **Dual input support — Legacy PointCloud**:
  ```python
  pcd_legacy = o3d.geometry.PointCloud()
  pcd_legacy.points = o3d.utility.Vector3dVector(np.random.rand(50, 3))
  gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.1, plane_model=[0,0,1,0])
  result_pcd, meta = gen.apply(pcd_legacy)
  assert isinstance(result_pcd, o3d.t.geometry.PointCloud)
  ```

- [ ] **2.1.3** ✅ **Validation — empty PointCloud**:
  ```python
  gen = GeneratePlane(mode="boundary", voxel_size=0.05)
  pcd = o3d.t.geometry.PointCloud()
  try:
      gen.apply(pcd)
      assert False, "Should have raised ValueError"
  except ValueError as e:
      assert "Insufficient points" in str(e)
      assert "minimum 3" in str(e)
  ```

- [ ] **2.1.4** ✅ **Validation — degenerate plane model**:
  ```python
  gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.05, plane_model=[0,0,0,0])
  pcd = # 10-point cloud
  try:
      gen.apply(pcd)
      assert False
  except ValueError as e:
      assert "degenerate normal vector" in str(e)
  ```

### 2.2 Square Mode (AC: Mode 1)

- [ ] **2.2.1** ✅ **Centered at origin**: All vertex X values span symmetrically around 0, all Y values span symmetrically around 0, all Z values ≈ 0.0.
  ```python
  gen = GeneratePlane(mode="square", size=2.0, voxel_size=0.5)
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(np.array([[0,0,0],[1,1,0],[2,2,0]], dtype=np.float32))
  vertex_pcd, meta = gen.apply(pcd)
  verts = meta["mesh"].vertex.positions.numpy()
  assert abs(verts[:, 0].mean()) < 0.01   # X centered
  assert abs(verts[:, 1].mean()) < 0.01   # Y centered
  assert np.allclose(verts[:, 2], 0.0, atol=1e-5)  # Z=0
  ```

- [ ] **2.2.2** ✅ **Vertex count formula**: `n = ceil(size/voxel_size)`, `vertex_count == n²`
  - Test: `size=1.0, voxel_size=0.05` → n=20, vertex_count=400 ✓
  - Test: `size=1.0, voxel_size=0.1` → n=10, vertex_count=100 ✓

- [ ] **2.2.3** ✅ **Triangle count formula**: `triangle_count == 2 × (n-1)²`
  - Test: `size=1.0, voxel_size=0.05` → n=20, triangle_count=722 ✓

- [ ] **2.2.4** ✅ **Area exact**: `area == size²` (within 0.01 tolerance)

- [ ] **2.2.5** ✅ **Output TriangleMesh is valid Open3D object**:
  ```python
  mesh = meta["mesh"]
  assert isinstance(mesh, o3d.t.geometry.TriangleMesh)
  assert mesh.vertex.positions.shape[0] > 0
  assert mesh.triangle.indices.shape[0] > 0
  ```

- [ ] **2.2.6** ✅ **Vertex PointCloud has correct count**:
  ```python
  assert vertex_pcd.point.positions.shape[0] == meta["vertex_count"]
  ```

### 2.3 Boundary Mode (AC: Mode 2)

- [ ] **2.3.1** ✅ **Basic boundary mesh generation** with flat cloud of known shape:
  ```python
  # Rectangle: 2m × 1m floor
  corners = np.array([
      [-1, -0.5, 0], [1, -0.5, 0], [1, 0.5, 0], [-1, 0.5, 0]
  ] + list(np.random.rand(46, 3) * [2, 1, 0] - [1, 0.5, 0]), dtype=np.float32)
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(corners)
  gen = GeneratePlane(mode="boundary", voxel_size=0.1, plane_model=[0,0,1,0])
  vertex_pcd, meta = gen.apply(pcd)
  assert meta["vertex_count"] > 0
  assert meta["area"] > 0.0
  assert meta["area"] < 2.5  # approximately 2.0 m²
  ```

- [ ] **2.3.2** ✅ **Boundary mesh vertices lie on the input plane**: For a z=0 plane, all mesh vertex Z-values ≈ 0.0 (within 1e-4).

- [ ] **2.3.3** ✅ **Collinear points raise correct error**:
  ```python
  # All points on a line (x-axis)
  pts = np.zeros((20, 3), dtype=np.float32)
  pts[:, 0] = np.linspace(0, 1, 20)
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(pts)
  gen = GeneratePlane(mode="boundary", voxel_size=0.05, plane_model=[0,0,1,0])
  try:
      gen.apply(pcd)
      assert False, "Should have raised"
  except ValueError as e:
      assert "colinear" in str(e).lower()
  ```

- [ ] **2.3.4** ✅ **Mesh vertices are interior to convex hull** (spot check):
  Verify at least 80% of mesh vertices are within 0.1m of the bounding box of input point projections.

### 2.4 Parameter Validation (AC: Error Handling)

Run each error case as its own assertion check:

- [ ] **2.4.1** `voxel_size=0` → `ValueError("voxel_size must be > 0")`
- [ ] **2.4.2** `voxel_size=-0.01` → `ValueError("voxel_size must be > 0")`
- [ ] **2.4.3** `mode="square", size=0` → `ValueError("size must be > 0")`
- [ ] **2.4.4** `mode="square", size=-5` → `ValueError("size must be > 0")`
- [ ] **2.4.5** `mode="triangle"` (invalid) → `ValueError("mode must be 'square' or 'boundary'")`
- [ ] **2.4.6** Vertex limit: `size=500.0, voxel_size=0.001` → `ValueError` (limit exceeded), message contains "1,000,000"
- [ ] **2.4.7** Non-PointCloud input (e.g., `numpy array`) → `TypeError`

---

## Section 3: Output Format Validation (AC: Output Format)

- [ ] **3.1** ✅ **All 7 metadata keys present on success**:
  Check both `square` and `boundary` modes return all keys:
  `["mesh", "vertex_count", "triangle_count", "area", "plane_model", "mode", "voxel_size"]`

- [ ] **3.2** ✅ **`vertex_count` is a Python `int`** (not numpy int):
  ```python
  assert type(meta["vertex_count"]) is int
  ```

- [ ] **3.3** ✅ **`triangle_count` is a Python `int`**:
  ```python
  assert type(meta["triangle_count"]) is int
  ```

- [ ] **3.4** ✅ **`area` is a Python `float` > 0**:
  ```python
  assert isinstance(meta["area"], float) and meta["area"] > 0
  ```

- [ ] **3.5** ✅ **`plane_model` is a list of 4 floats**:
  ```python
  pm = meta["plane_model"]
  assert isinstance(pm, list) and len(pm) == 4
  assert all(isinstance(x, float) for x in pm)
  ```

- [ ] **3.6** ✅ **`mode` echoes the constructor parameter**:
  ```python
  gen = GeneratePlane(mode="boundary", ...)
  _, meta = gen.apply(pcd)
  assert meta["mode"] == "boundary"
  ```

- [ ] **3.7** ✅ **`voxel_size` echoes the constructor parameter**:
  ```python
  gen = GeneratePlane(voxel_size=0.07, ...)
  _, meta = gen.apply(pcd)
  assert meta["voxel_size"] == 0.07
  ```

- [ ] **3.8** ✅ **`mesh` is `o3d.t.geometry.TriangleMesh`**:
  ```python
  assert isinstance(meta["mesh"], o3d.t.geometry.TriangleMesh)
  ```

- [ ] **3.9** ✅ **Primary return value is `o3d.t.geometry.PointCloud`**:
  ```python
  assert isinstance(vertex_pcd, o3d.t.geometry.PointCloud)
  ```

---

## Section 4: Performance Benchmarks (AC: Performance Requirements)

- [ ] **4.1** ✅ **Square mode < 100ms** (`1m×1m, voxel_size=0.01`):
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py -k "benchmark_square" -v -s -m slow
  ```
  Record actual time in QA report.

- [ ] **4.2** ✅ **Boundary mode < 500ms** (`1000 input points, voxel_size=0.01`):
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py -k "benchmark_boundary" -v -s -m slow
  ```
  Record actual time in QA report.

- [ ] **4.3** ✅ **Memory efficiency — mesh ≤ 10× input cloud footprint**:
  ```python
  import sys
  # 1000 points × 3 × 4 bytes = 12,000 bytes input
  gen = GeneratePlane(mode="boundary", voxel_size=0.05, plane_model=[0,0,1,0])
  vertex_pcd, meta = gen.apply(pcd_1000pts)
  mesh = meta["mesh"]
  vertex_bytes = mesh.vertex.positions.numpy().nbytes
  triangle_bytes = mesh.triangle.indices.numpy().nbytes
  mesh_bytes = vertex_bytes + triangle_bytes
  input_bytes = 1000 * 3 * 4  # float32 XYZ
  assert mesh_bytes <= 10 * input_bytes, f"Mesh {mesh_bytes}B exceeds 10× input {input_bytes}B"
  ```

- [ ] **4.4** ✅ **Threadpool execution — does not block event loop**:
  Write an asyncio test confirming `asyncio.to_thread()` can wrap `apply()` successfully:
  ```python
  import asyncio, open3d as o3d, numpy as np
  from app.modules.pipeline.operations.generate_plane import GeneratePlane
  
  async def test_async():
      gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.1, plane_model=[0,0,1,0])
      pts = np.random.rand(10, 3).astype(np.float32)
      pcd = o3d.t.geometry.PointCloud()
      pcd.point.positions = o3d.core.Tensor(pts)
      result = await asyncio.to_thread(gen.apply, pcd)
      assert result is not None
  
  asyncio.run(test_async())
  ```
  Expected: Returns without error or deadlock.

---

## Section 5: Integration & Pipeline Tests (AC: Integration Requirements)

- [ ] **5.1** ✅ **PlaneSegmentation → GeneratePlane chain**:
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py::test_integration_segmentation_chain -v
  ```

- [ ] **5.2** ✅ **Factory-created operation works end-to-end**:
  ```python
  from app.modules.pipeline.factory import OperationFactory
  op = OperationFactory.create("generate_plane", {
      "mode": "boundary",
      "voxel_size": 0.1,
      "plane_model": [0, 0, 1, 0]
  })
  # Apply to a flat cloud
  pts = np.random.rand(50, 3).astype(np.float32)
  pts[:, 2] = 0
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(pts)
  vertex_pcd, meta = op.apply(pcd)
  assert meta["vertex_count"] > 0
  ```

- [ ] **5.3** ✅ **Mesh exportable to PLY format** (verifies mesh is MeshLab/Blender compatible):
  ```python
  import tempfile, os
  mesh = meta["mesh"]
  with tempfile.NamedTemporaryFile(suffix=".ply", delete=False) as f:
      tmp_path = f.name
  o3d.t.io.write_triangle_mesh(tmp_path, mesh)
  assert os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0
  # Reload and verify
  loaded = o3d.t.io.read_triangle_mesh(tmp_path)
  assert loaded.vertex.positions.shape[0] == meta["vertex_count"]
  os.unlink(tmp_path)
  ```

- [ ] **5.4** ✅ **NodeDefinition registered correctly**:
  ```python
  from app.services.nodes.schema import node_schema_registry
  schema = node_schema_registry.get("generate_plane")  # or equivalent lookup
  assert schema is not None
  assert schema.display_name == "Generate Plane Mesh"
  assert len(schema.properties) >= 4   # throttle_ms, mode, size, voxel_size
  ```
  *(Adjust the registry lookup method if the API differs — check `registry.py` for the lookup pattern.)*

---

## Section 6: Edge Cases

- [ ] **6.1** ✅ **Very small voxel_size** (`0.001`, `size=0.5`) — completes without memory error:
  ```python
  gen = GeneratePlane(mode="square", size=0.5, voxel_size=0.001)
  # ceil(0.5/0.001) = 500 → 500² = 250,000 vertices — within 1M limit
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(np.random.rand(10, 3).astype(np.float32))
  vertex_pcd, meta = gen.apply(pcd)
  assert meta["vertex_count"] == 250000
  ```

- [ ] **6.2** ✅ **Exactly 3 input points** — boundary mode minimum case:
  ```python
  pts = np.array([[0,0,0],[1,0,0],[0.5,1,0]], dtype=np.float32)
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(pts)
  gen = GeneratePlane(mode="boundary", voxel_size=0.1, plane_model=[0,0,1,0])
  vertex_pcd, meta = gen.apply(pcd)
  assert meta["vertex_count"] > 0
  ```

- [ ] **6.3** ✅ **Near-degenerate normal (near-horizontal plane)** — `plane_model=[0.999, 0.001, 0.001, 0]` — does not crash (basis vector fallback path):
  ```python
  gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.1, plane_model=[0.999, 0.001, 0.001, 0])
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(np.random.rand(10, 3).astype(np.float32))
  vertex_pcd, meta = gen.apply(pcd)
  assert meta["vertex_count"] > 0
  ```

- [ ] **6.4** ✅ **Highly elongated input** (1000:1 aspect ratio) — boundary mode must either succeed or raise the colinear error, NOT crash with unhandled exception:
  ```python
  pts = np.zeros((50, 3), dtype=np.float32)
  pts[:, 0] = np.linspace(0, 100, 50)  # 100m long, 0m wide
  pts[:, 1] = np.random.normal(0, 0.001, 50)  # near-zero width
  pcd = o3d.t.geometry.PointCloud()
  pcd.point.positions = o3d.core.Tensor(pts)
  gen = GeneratePlane(mode="boundary", voxel_size=0.5, plane_model=[0,0,1,0])
  try:
      gen.apply(pcd)
  except ValueError as e:
      assert "colinear" in str(e).lower()  # Expected for near-degenerate hull
  except Exception as e:
      assert False, f"Unexpected exception type: {type(e).__name__}: {e}"
  ```

- [ ] **6.5** ✅ **Stateless between calls** — two consecutive `apply()` calls on same instance return independent results:
  ```python
  gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.1, plane_model=[0,0,1,0])
  _, meta1 = gen.apply(pcd_a)
  _, meta2 = gen.apply(pcd_b)
  # Mesh objects must be independent
  assert meta1["mesh"] is not meta2["mesh"]
  ```

---

## Section 7: Regression Tests (Existing Operations Unaffected)

- [ ] **7.1** ✅ **All pre-existing pipeline operation tests still pass**:
  ```bash
  pytest tests/pipeline/operations/ -v --ignore=tests/pipeline/operations/test_generate_plane.py
  ```
  Expected: 0 failures.

- [ ] **7.2** ✅ **`OperationFactory` still raises for unknown ops**:
  ```python
  from app.modules.pipeline.factory import OperationFactory
  try:
      OperationFactory.create("nonexistent", {})
      assert False
  except ValueError:
      pass
  ```

- [ ] **7.3** ✅ **Existing module imports not broken**:
  ```bash
  python -c "from app.modules.pipeline.operations import Crop, Downsample, PlaneSegmentation, GeneratePlane; print('All OK')"
  ```

---

## Section 8: Linter & Type Check

- [ ] **8.1** Run flake8 on the new file (0 errors expected):
  ```bash
  flake8 app/modules/pipeline/operations/generate_plane.py --max-line-length=120
  ```

- [ ] **8.2** Run mypy on the new file (0 errors expected, or only missing-import warnings for scipy):
  ```bash
  mypy app/modules/pipeline/operations/generate_plane.py --ignore-missing-imports
  ```

- [ ] **8.3** Verify no bare `except` clauses in the new file:
  ```bash
  grep -n "except:" app/modules/pipeline/operations/generate_plane.py
  ```
  Expected: no output.

---

## Section 9: QA Report Preparation

- [ ] **9.1** Create `qa-report.md` in `.opencode/plans/generate-plane/` documenting:
  - Total tests executed
  - Pass/fail counts
  - Coverage percentage
  - Benchmark results (actual ms timings)
  - Any deviations from acceptance criteria
  - Any findings/bugs discovered

- [ ] **9.2** If any acceptance criteria are NOT met, create a bug report issue and block the PR.

- [ ] **9.3** Confirm all items in the **Quantitative Success Metrics** section of `requirements.md` are met:
  - [ ] ≥ 10 test cases in unit tests
  - [ ] PlaneSegmentation → GeneratePlane chain < 1s for 10k points, voxel=0.01
  - [ ] Square mode < 100ms
  - [ ] Boundary mode < 500ms
  - [ ] Mesh size < 10MB for typical use

---

## QA Acceptance Checklist Summary

| Section | Key Check | Pass Criteria |
|---------|-----------|---------------|
| 1 — Unit Tests        | ≥ 10 tests pass, 0 fail | 100% pass |
| 1 — Coverage          | Statement coverage       | ≥ 90%     |
| 2 — Functional        | All AC verified manually | All ✅     |
| 3 — Output Format     | All 7 metadata keys      | All ✅     |
| 4 — Performance       | Square < 100ms           | ✅         |
| 4 — Performance       | Boundary < 500ms         | ✅         |
| 5 — Integration       | Chain + export test      | ✅         |
| 6 — Edge Cases        | 5 edge case checks       | No uncaught exceptions |
| 7 — Regression        | Pre-existing tests       | 0 failures |
| 8 — Linter            | flake8 + mypy            | 0 errors   |
