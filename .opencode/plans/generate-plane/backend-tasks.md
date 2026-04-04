# Backend Tasks: GeneratePlane Operation

**Feature**: Generate Plane from Segmentation Output  
**Assignee**: @be-dev  
**References**:
- Requirements: `.opencode/plans/generate-plane/requirements.md`
- Technical spec: `.opencode/plans/generate-plane/technical.md`
- API contract: `.opencode/plans/generate-plane/api-spec.md`

**Workflow rule**: Check off each task (`- [x]`) as it is completed. Tasks marked ⚠️ have explicit ordering constraints — do not reorder them.

---

## Phase 0: Pre-Implementation Checks (MANDATORY)

- [x] **0.1** Read `technical.md` in full before writing any code.
- [x] **0.2** Run `gitnexus_impact(target="OperationNode", direction="upstream")` and verify blast radius is LOW (only `registry.py`). Document result in a comment at top of your PR.
- [x] **0.3** Run `gitnexus_impact(target="PipelineOperation", direction="upstream")` — confirm all existing operations still work without modification.
- [x] **0.4** Verify SciPy is available:
  ```bash
  python -c "from scipy.spatial import ConvexHull, Delaunay, QhullError; print('OK')"
  ```
  If it fails, add `scipy>=1.7` to `requirements.txt` / `pyproject.toml` before writing code.
- [x] **0.5** Run the existing pipeline operation tests to establish a green baseline:
  ```bash
  pytest tests/pipeline/operations/ -v
  ```
  All tests MUST pass. Do not proceed if any fail.

---

## Phase 1: TDD — Write Failing Tests First ⚠️

> **RULE**: Write ALL tests in this phase **before** writing any implementation code.  
> Tests MUST fail (red) at this stage. This is the TDD gate.

- [x] **1.1** Create directory structure (if needed):
  ```bash
  mkdir -p tests/pipeline/operations/
  ```
  *(Already exists — just create the test file.)*

- [x] **1.2** Create `tests/pipeline/operations/test_generate_plane.py` with the following test cases (all will fail until implementation exists):

  **Validation tests:**
  - [x] `test_invalid_mode_raises()` — mode="invalid" → `ValueError`
  - [x] `test_invalid_voxel_size_zero()` — voxel_size=0 → `ValueError`
  - [x] `test_invalid_voxel_size_negative()` — voxel_size=-0.1 → `ValueError`
  - [x] `test_invalid_size_zero()` — mode="square", size=0 → `ValueError`
  - [x] `test_invalid_size_negative()` — mode="square", size=-1 → `ValueError`
  - [x] `test_degenerate_plane_model()` — plane_model=[0,0,0,0] → `ValueError`
  - [x] `test_insufficient_points()` — empty PointCloud → `ValueError`
  - [x] `test_two_points_only()` — 2-point PointCloud → `ValueError`
  - [x] `test_unsupported_input_type()` — pass a string → `TypeError`

  **Square mode tests:**
  - [x] `test_square_mode_basic_output_type()` — returns `(o3d.t.geometry.PointCloud, dict)`
  - [x] `test_square_mode_metadata_keys()` — all 7 metadata keys present
  - [x] `test_square_mode_mesh_in_metadata()` — `metadata["mesh"]` is `o3d.t.geometry.TriangleMesh`
  - [x] `test_square_mode_vertex_count()` — `size=1.0, voxel_size=0.05` → `vertex_count == 400`
  - [x] `test_square_mode_triangle_count()` — `size=1.0, voxel_size=0.05` → `triangle_count == 722`
  - [x] `test_square_mode_area()` — `size=2.0` → `area == 4.0` (within 0.001 tolerance)
  - [x] `test_square_mode_plane_model()` — metadata `plane_model == [0.0, 0.0, 1.0, 0.0]`
  - [x] `test_square_mode_vertex_pcd_positions()` — returned PointCloud has `N=vertex_count` positions
  - [x] `test_square_mode_vertex_positions_on_z0()` — all Z values of returned vertices are ≈ 0.0
  - [x] `test_square_mode_vertex_limit_exceeded()` — `size=100, voxel_size=0.001` → `ValueError` (>1M vertices)
  - [x] `test_square_mode_accepts_legacy_pcd()` — `o3d.geometry.PointCloud` input → no error

  **Boundary mode tests:**
  - [x] `test_boundary_mode_basic_output_type()` — returns `(o3d.t.geometry.PointCloud, dict)`
  - [x] `test_boundary_mode_metadata_keys()` — all 7 metadata keys present
  - [x] `test_boundary_mode_mesh_in_metadata()` — `metadata["mesh"]` is `o3d.t.geometry.TriangleMesh`
  - [x] `test_boundary_mode_rectangular_hull()` — 4 corners of 1m×1m square → positive vertex/triangle count
  - [x] `test_boundary_mode_plane_model_echo()` — supplied plane_model echoed in metadata
  - [x] `test_boundary_mode_area_positive()` — area > 0.0
  - [x] `test_boundary_collinear_raises()` — all points on a line → `ValueError` (colinear)
  - [x] `test_boundary_mode_accepts_legacy_pcd()` — `o3d.geometry.PointCloud` input → no error
  - [x] `test_boundary_mode_auto_ransac()` — no `plane_model` supplied, flat input → extracts model and succeeds

  **Integration-style tests (still unit, chaining logic):**
  - [x] `test_chain_segmentation_to_generate_plane()` — run `PlaneSegmentation` on flat cloud → pass result to `GeneratePlane(mode="boundary")` with extracted `plane_model` → succeeds

- [x] **1.3** Confirm all tests fail (ImportError or ModuleNotFoundError is acceptable at this stage):
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py -v 2>&1 | head -50
  ```
  Expected: `FAILED` / `ERROR` for every test. If any test passes, fix the test logic.

---

## Phase 2: Core Implementation ⚠️

> Implement in order. Do not skip to Phase 3 until all tests pass.

- [x] **2.1** Create `app/modules/pipeline/operations/generate_plane.py`:

  Structure to implement (follow `technical.md` §8 exactly):
  - [x] Module-level constants: `MAX_VERTICES = 1_000_000`, `MIN_POINTS = 3`
  - [x] `class GeneratePlane(PipelineOperation)`:
    - [x] `__init__()` with parameter validation (validate `mode`, `voxel_size`). Do NOT validate `size` here — that belongs in `_generate_square()`.
    - [x] `apply()` — main dispatch method
    - [x] `_resolve_plane_model()` — extract from constructor arg or RANSAC fallback
    - [x] `_generate_square()` — returns `(vertices: np.ndarray, triangles: np.ndarray)`
    - [x] `_generate_boundary()` — returns `(vertices: np.ndarray, triangles: np.ndarray)`
    - [x] `_build_mesh()` — assembles `o3d.t.geometry.TriangleMesh` from numpy arrays
    - [x] `_vertices_to_pcd()` — wraps vertex numpy array into `o3d.t.geometry.PointCloud`

  **Critical implementation rules**:
  - `apply()` return type MUST be `Tuple[o3d.t.geometry.PointCloud, Dict[str, Any]]` — not `TriangleMesh`.
  - `metadata["mesh"]` contains the full `TriangleMesh` (Python object).
  - Internal math uses `np.float64`; final tensors cast to `np.float32`.
  - Vertex count gate (`MAX_VERTICES`) MUST be enforced BEFORE array allocation.
  - RANSAC fallback in `_resolve_plane_model()` uses: `distance_threshold=0.01, ransac_n=3, num_iterations=1000, probability=0.9999`.
  - Follow CCW winding for square mode (see `technical.md` §3.3, Step 4).
  - Use `scipy.spatial.ConvexHull` + `scipy.spatial.Delaunay` for boundary mode.

- [x] **2.2** Run tests after each private method is implemented to get incremental green:
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py -v -x  # stop on first failure
  ```

- [x] **2.3** Achieve full green test suite for the new test file:
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py -v
  ```
  All tests MUST pass before proceeding to Phase 3.

---

## Phase 3: Pipeline Integration ⚠️

> Only begin after Phase 2 tests are green.

- [x] **3.1** Add `GeneratePlane` to `app/modules/pipeline/operations/__init__.py`:
  ```python
  from .generate_plane import GeneratePlane
  ```

- [x] **3.2** Register in `app/modules/pipeline/factory.py`:
  - Add import: `from app.modules.pipeline.operations.generate_plane import GeneratePlane`
  - *(Or rely on the `__init__.py` wildcard — check existing import pattern in `factory.py`.)*
  - Add to `_OP_MAP`:
    ```python
    "generate_plane": GeneratePlane,
    ```

- [x] **3.3** Register `NodeDefinition` in `app/modules/pipeline/registry.py`:
  - Add full `NodeDefinition` block (see `api-spec.md` §7 for exact schema).
  - Add `"generate_plane"` to `_OPERATION_TYPES` list at the bottom.
  - Add factory alias: `NodeFactory._registry["generate_plane"] = NodeFactory._registry["operation"]`

- [x] **3.4** Verify registry integration with a quick smoke test:
  ```bash
  python -c "
  from app.modules.pipeline.factory import OperationFactory
  op = OperationFactory.create('generate_plane', {'mode': 'square', 'size': 1.0, 'voxel_size': 0.05})
  print(type(op))
  "
  ```
  Expected output: `<class 'app.modules.pipeline.operations.generate_plane.GeneratePlane'>`

- [x] **3.5** Verify `OperationFactory` error for unknown type still works:
  ```bash
  python -c "
  from app.modules.pipeline.factory import OperationFactory
  OperationFactory.create('nonexistent', {})
  " 2>&1 | grep "Unknown operation"
  ```

---

## Phase 4: Integration Test

- [x] **4.1** Write a standalone integration test that chains `PlaneSegmentation → GeneratePlane`:

  ```python
  # tests/pipeline/operations/test_generate_plane.py (add to existing file)
  
  def test_integration_segmentation_chain():
      """PlaneSegmentation output → GeneratePlane boundary mode."""
      import open3d as o3d
      import numpy as np
      from app.modules.pipeline.operations.segmentation import PlaneSegmentation
      from app.modules.pipeline.operations.generate_plane import GeneratePlane
  
      # Create a flat floor cloud (z ≈ 0) with 200 points
      rng = np.random.default_rng(42)
      xy = rng.uniform(-2, 2, (200, 2))
      z = rng.normal(0, 0.005, (200, 1))  # slight noise
      pts = np.hstack([xy, z]).astype(np.float32)
  
      pcd = o3d.t.geometry.PointCloud()
      pcd.point.positions = o3d.core.Tensor(pts)
  
      seg = PlaneSegmentation(distance_threshold=0.02, ransac_n=3, num_iterations=500)
      seg_pcd, seg_meta = seg.apply(pcd)
  
      plane_model = seg_meta["plane_model"]  # [a, b, c, d]
  
      gen = GeneratePlane(mode="boundary", voxel_size=0.1, plane_model=plane_model)
      vertex_pcd, mesh_meta = gen.apply(seg_pcd)
  
      assert mesh_meta["vertex_count"] > 0
      assert mesh_meta["triangle_count"] > 0
      assert mesh_meta["area"] > 0.0
      assert isinstance(mesh_meta["mesh"], o3d.t.geometry.TriangleMesh)
  ```

- [x] **4.2** Run the integration test:
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py::test_integration_segmentation_chain -v
  ```

---

## Phase 5: Performance Benchmarks

- [x] **5.1** Add performance benchmark tests (can be skipped in CI with `@pytest.mark.slow`):

  ```python
  @pytest.mark.slow
  def test_benchmark_square_1m_voxel_01():
      """Square 1m×1m, voxel=0.01 must complete in < 100ms."""
      import time
      gen = GeneratePlane(mode="square", size=1.0, voxel_size=0.01)
      pcd = o3d.t.geometry.PointCloud()
      pcd.point.positions = o3d.core.Tensor(
          np.random.rand(100, 3).astype(np.float32)
      )
      start = time.perf_counter()
      gen.apply(pcd)
      elapsed_ms = (time.perf_counter() - start) * 1000
      assert elapsed_ms < 100, f"Square mode took {elapsed_ms:.1f}ms (limit: 100ms)"
  
  @pytest.mark.slow
  def test_benchmark_boundary_1k_pts_voxel_01():
      """Boundary 1k pts, voxel=0.01 must complete in < 500ms."""
      import time
      rng = np.random.default_rng(0)
      pts = rng.uniform(-1, 1, (1000, 2))
      z = np.zeros((1000, 1))
      pts3d = np.hstack([pts, z]).astype(np.float32)
      pcd = o3d.t.geometry.PointCloud()
      pcd.point.positions = o3d.core.Tensor(pts3d)
  
      gen = GeneratePlane(mode="boundary", voxel_size=0.01, plane_model=[0, 0, 1, 0])
      start = time.perf_counter()
      gen.apply(pcd)
      elapsed_ms = (time.perf_counter() - start) * 1000
      assert elapsed_ms < 500, f"Boundary mode took {elapsed_ms:.1f}ms (limit: 500ms)"
  ```

- [x] **5.2** Run benchmarks and record results in a comment in your PR:
  ```bash
  pytest tests/pipeline/operations/test_generate_plane.py -m slow -v -s
  ```

---

## Phase 6: Full Regression Check ⚠️

- [x] **6.1** Run the FULL pipeline operations test suite (not just the new file):
  ```bash
  pytest tests/pipeline/ -v
  ```
  All pre-existing tests MUST still pass.

- [x] **6.2** Run `gitnexus_detect_changes(scope="all")` and confirm only these files were changed:
  - `app/modules/pipeline/operations/generate_plane.py` (NEW)
  - `app/modules/pipeline/operations/__init__.py` (modified)
  - `app/modules/pipeline/factory.py` (modified)
  - `app/modules/pipeline/registry.py` (modified)
  - `tests/pipeline/operations/test_generate_plane.py` (NEW)
  - Optionally: `requirements.txt` / `pyproject.toml` (if scipy was missing)

- [x] **6.3** Confirm no type errors with mypy (if configured):
  ```bash
  mypy app/modules/pipeline/operations/generate_plane.py --ignore-missing-imports
  ```

---

## Phase 7: Documentation & Handoff

- [x] **7.1** Ensure the module docstring in `generate_plane.py` documents:
  - The DAG-terminal nature (mesh in metadata, vertices as PointCloud output).
  - The `plane_model` parameter limitation (not auto-threaded from upstream).
  - Valid parameter ranges and performance characteristics.

- [x] **7.2** Verify the `GeneratePlane` constructor docstring matches `api-spec.md` §1.

- [x] **7.3** Notify @qa that implementation is complete and tests are green.

---

## Checklist Summary

| Phase | Task Count | Critical Notes |
|-------|-----------|----------------|
| 0 — Pre-checks    | 5 tasks  | MUST run gitnexus impact checks |
| 1 — TDD Tests     | 33 tasks | Write tests before code |
| 2 — Implementation| 12 tasks | apply() returns PointCloud, mesh in metadata |
| 3 — Integration   | 5 tasks  | Update factory.py, __init__.py, registry.py |
| 4 — Integration test | 2 tasks | Chain PlaneSegmentation → GeneratePlane |
| 5 — Benchmarks    | 2 tasks  | Mark as `@pytest.mark.slow` |
| 6 — Regression    | 3 tasks  | No pre-existing tests may break |
| 7 — Docs          | 3 tasks  | Docstrings + handoff |

**Total: ~65 tasks**

---

## Non-Obvious Rules to Follow

1. **`apply()` MUST return `PointCloud`, not `TriangleMesh`**. The `OperationNode._sync_compute()` method calls `PointConverter.to_points(pcd_out)` unconditionally. If you return a `TriangleMesh`, the output is silently dropped (returns empty array). See `technical.md` §2 for full explanation.

2. **Do NOT modify `operation_node.py` or `base.py`**. The mesh-as-metadata pattern is the intentional v1 design. Modifying those files has a HIGH blast radius across the entire pipeline.

3. **`plane_model` is NOT automatically propagated from `PlaneSegmentation`**. The DAG strips metadata between nodes. See `technical.md` §7 for the full explanation and the RANSAC fallback behavior.

4. **Vertex count safety gate before allocation**. Check `n_steps² > MAX_VERTICES` BEFORE calling `np.meshgrid()`. This prevents OOM errors on misconfigured DAG nodes.

5. **Import scipy defensively**: Wrap the import in a `try/except ImportError` at the top of `generate_plane.py` with a clear error message if it's missing.

6. **Float64 for math, Float32 for tensors**. Numpy projection math (plane basis, hull computation) uses `float64`. The final `o3d.core.Tensor(vertices.astype(np.float32))` casting happens in `_build_mesh()` only.
