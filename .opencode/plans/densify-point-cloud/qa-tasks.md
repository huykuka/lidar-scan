# Densify Point Cloud — QA Tasks & Test Plan

**Agent:** `@qa`  
**Feature:** `densify-point-cloud`  
**Test File:** `tests/pipeline/operations/test_densify.py`  
**References:** `requirements.md`, `technical.md`, `api-spec.md`, `backend-tasks.md`

> **TDD Protocol:** Write ALL tests in `test_densify.py` BEFORE `@be-dev` completes implementation.
> Tests must be runnable (even if failing) from day 1. Check off `[x]` as each test passes.

---

## Phase 0: TDD Preparation

- [ ] Create `tests/pipeline/operations/test_densify.py` with all test stubs
- [ ] Run `pytest tests/pipeline/operations/test_densify.py -v` → confirm all tests are **collected** (even if failing with `ImportError` or `NotImplementedError`)
- [ ] Verify test file imports compile once `densify.py` skeleton exists:
  ```python
  from app.modules.pipeline.operations.densify import Densify
  ```
- [ ] Confirm `@pytest.mark.slow` marker is registered in `tests/conftest.py` (already present — no change needed)

---

## Phase 1: Unit Tests — Class Construction & Validation

### 1.1 Default Configuration

- [ ] **`test_densify_default_init`**: `Densify()` instantiates without error; verify default attributes match spec
  ```python
  op = Densify()
  assert op.density_multiplier == 2.0
  assert op.preserve_normals is True
  assert op.enabled is True
  ```

### 1.2 Invalid Configuration

- [ ] **`test_densify_invalid_algorithm`**: `Densify(algorithm="bilinear")` raises `ValueError`
- [ ] **`test_densify_invalid_multiplier_too_high`**: `Densify(density_multiplier=9.0)` raises `ValueError`
- [ ] **`test_densify_invalid_multiplier_too_low`**: `Densify(density_multiplier=0.5)` raises `ValueError`
- [ ] **`test_densify_invalid_preset`**: `Densify(quality_preset="ultra")` raises `ValueError`

### 1.3 Factory Registration

- [ ] **`test_densify_factory_default`**: `OperationFactory.create("densify", {})` returns a `Densify` instance
- [ ] **`test_densify_factory_with_config`**: `OperationFactory.create("densify", {"algorithm": "poisson", "density_multiplier": 4.0})` returns correct instance
- [ ] **`test_densify_factory_unknown_type`**: `OperationFactory.create("densify_v2", {})` raises `ValueError`

---

## Phase 2: Unit Tests — Fail-Safe Behavior (F5)

### 2.1 Insufficient Points

- [ ] **`test_densify_skip_insufficient_points_legacy`**:
  ```python
  pcd = o3d.geometry.PointCloud()
  pcd.points = o3d.utility.Vector3dVector(np.random.rand(5, 3))
  op = Densify()
  result_pcd, meta = op.apply(pcd)
  assert meta["status"] == "skipped"
  assert meta["original_count"] == 5
  assert meta["densified_count"] == 5
  assert "skip_reason" in meta and meta["skip_reason"] is not None
  ```
- [ ] **`test_densify_skip_insufficient_points_tensor`**: Same test using `o3d.t.geometry.PointCloud`
- [ ] **`test_densify_skip_zero_points`**: Empty cloud → status=skipped, no crash

### 2.2 Already Dense Input

- [ ] **`test_densify_skip_already_dense`**:
  ```python
  # 1000 points with multiplier=0.5 (less than 1.0 min, use multiplier=1.0 effectively meaning same count)
  # Actually: set multiplier=2.0 but input already has target_count
  pcd = make_pcd(10000)  # helper fixture
  op = Densify(density_multiplier=1.0)  # no change
  result_pcd, meta = op.apply(pcd)
  assert meta["status"] == "skipped"
  ```

### 2.3 Disabled Operation

- [ ] **`test_densify_disabled`**:
  ```python
  op = Densify(enabled=False)
  pcd = make_pcd(1000)
  result_pcd, meta = op.apply(pcd)
  assert meta["status"] == "skipped"
  assert meta["densified_count"] == 1000
  assert "disabled" in meta["skip_reason"].lower()
  ```

### 2.4 No Exception Propagation

- [ ] **`test_densify_no_exception_on_corrupt_input`**: Pass a plain Python dict as pcd → must NOT raise; must return (something, metadata) with status=error or skipped
- [ ] **`test_densify_no_exception_on_none`**: `op.apply(None)` → does not raise; returns tuple

### 2.5 Error Recovery

- [ ] **`test_densify_error_returns_original`**: Mock `_run_algorithm` to raise `RuntimeError("simulated failure")`; verify:
  - Return value is original pcd (not None)
  - `meta["status"] == "error"`
  - `meta["error_message"]` contains the error text
  - `meta["densified_count"] == original_count`

---

## Phase 3: Unit Tests — Nearest Neighbor Algorithm (F1, US1)

All tests use `o3d.geometry.PointCloud` (legacy) and `o3d.t.geometry.PointCloud` (tensor) variants.

- [ ] **`test_nn_increases_point_count_legacy`**:
  ```python
  pcd = make_pcd(1000)  # helper: random points
  op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
  result_pcd, meta = op.apply(pcd)
  assert meta["status"] == "success"
  assert meta["densified_count"] >= 1500   # at least 1.5x (allows some post-filter loss)
  assert meta["densified_count"] <= 2500   # not more than 2.5x
  assert meta["original_count"] == 1000
  ```
- [ ] **`test_nn_increases_point_count_tensor`**: Same with tensor pcd
- [ ] **`test_nn_preserves_original_positions`**:
  ```python
  # Original positions must all be present in result (NN adds, never removes)
  original_pts = np.asarray(pcd_legacy.points)
  result_pts = np.asarray(result_legacy.points)
  # Check all original points are in result (within float32 tolerance)
  for pt in original_pts:
      assert np.any(np.linalg.norm(result_pts - pt, axis=1) < 1e-4)
  ```
- [ ] **`test_nn_metadata_fields_complete`**: Assert all 7 metadata keys are present in `meta`
- [ ] **`test_nn_density_ratio_correct`**: `meta["density_ratio"] == meta["densified_count"] / meta["original_count"]`
- [ ] **`test_nn_processing_time_recorded`**: `meta["processing_time_ms"] > 0.0`
- [ ] **`@pytest.mark.slow` `test_nn_performance_fast_mode`**: 100k points → processing_time_ms < 100
  ```python
  pcd = make_pcd(100_000)
  op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
  result_pcd, meta = op.apply(pcd)
  assert meta["processing_time_ms"] < 100.0, f"Too slow: {meta['processing_time_ms']:.1f}ms"
  ```

---

## Phase 4: Unit Tests — Statistical Upsampling Algorithm (F1)

- [ ] **`test_statistical_increases_point_count`**: 1000 pts, 2× → count between 1500 and 2500
- [ ] **`test_statistical_metadata_correct`**: status=success, all keys present
- [ ] **`test_statistical_no_duplicate_stacking`**: Result should not have points within `1e-5` of each other in clusters (min-dist filter check)
  ```python
  from scipy.spatial import KDTree
  result_pts = get_positions(result_pcd)
  kd = KDTree(result_pts)
  pairs = kd.query_pairs(r=1e-5)
  assert len(pairs) == 0, f"{len(pairs)} near-duplicate points found"
  ```
- [ ] **`@pytest.mark.slow` `test_statistical_performance_medium_mode`**: 100k points → < 300ms

---

## Phase 5: Unit Tests — MLS Algorithm (F1)

- [ ] **`test_mls_increases_point_count`**: 1000 pts, 2× → count in expected range
- [ ] **`test_mls_metadata_correct`**: status=success, all keys present
- [ ] **`test_mls_result_is_point_cloud`**: result is `o3d.t.geometry.PointCloud` regardless of input type
- [ ] **`@pytest.mark.slow` `test_mls_performance_medium_mode`**: 10k points → < 500ms (smaller cloud for CI speed)
- [ ] **`test_mls_tangent_plane_accuracy`**: For a known planar input (all points on z=0 plane), verify synthetic points remain near z=0 (±tolerance based on radius)
  ```python
  pts = np.column_stack([np.random.rand(500, 2) * 10.0, np.zeros(500)])
  pcd = make_tensor_pcd(pts)
  op = Densify(algorithm="mls", density_multiplier=2.0)
  result_pcd, meta = op.apply(pcd)
  result_pts = get_positions(result_pcd)
  assert np.abs(result_pts[:, 2]).max() < 0.05, "MLS points deviated too far from source plane"
  ```

---

## Phase 6: Unit Tests — Poisson Algorithm (F1)

- [ ] **`test_poisson_increases_point_count`**: 500 pts (sphere surface), 2× → count in range
- [ ] **`test_poisson_metadata_correct`**: status=success, algorithm_used="poisson"
- [ ] **`test_poisson_preserves_originals`**: All N original points present in output
  ```python
  n_original = get_count(result_pcd)
  # First N points should match original positions
  result_pts = get_positions(result_pcd)[:n_original]
  original_pts = get_positions(input_pcd)
  np.testing.assert_allclose(result_pts, original_pts, atol=1e-4)
  ```
- [ ] **`@pytest.mark.slow` `test_poisson_performance_high_mode`**: 5k points on sphere → < 2000ms

---

## Phase 7: Unit Tests — Quality Preset System (F3)

- [ ] **`test_preset_fast_uses_nn`**: `Densify(quality_preset="fast")` → `meta["algorithm_used"] == "nearest_neighbor"`
- [ ] **`test_preset_medium_uses_statistical`**: `Densify(quality_preset="medium")` → `meta["algorithm_used"] == "statistical"`
- [ ] **`test_preset_high_uses_mls`**: `Densify(quality_preset="high")` → `meta["algorithm_used"] == "mls"`
- [ ] **`test_explicit_algorithm_overrides_preset`**: `Densify(algorithm="poisson", quality_preset="fast")` → `meta["algorithm_used"] == "poisson"`

---

## Phase 8: Unit Tests — Density Target (F2)

- [ ] **`test_multiplier_2x`**: 1000 pts → result ~2000 pts (±15% tolerance for stochastic algorithms)
- [ ] **`test_multiplier_4x`**: 500 pts → result ~2000 pts (±15%)
- [ ] **`test_multiplier_8x_max`**: 1000 pts, multiplier=8.0 → result ~8000 pts (±15%)
- [ ] **`test_density_multiplier_is_the_only_density_control`**:
  ```python
  op = Densify(density_multiplier=2.0)
  pcd = make_pcd(1000)
  result_pcd, meta = op.apply(pcd)
  # density_multiplier=2.0 with 1000 pts → ~2000 pts
  assert meta["status"] in ("success", "skipped")
  assert meta["densified_count"] >= 1000
  ```
- [ ] **`test_multiplier_clamped_at_8x`**: Verify that `density_multiplier=8.0` is enforced as maximum
  ```python
  op = Densify(density_multiplier=8.0)
  pcd = make_pcd(100)
  result_pcd, meta = op.apply(pcd)
  assert meta["densified_count"] <= 100 * 8 + 5  # max 8x with small tolerance
  ```

---

## Phase 9: Unit Tests — Normal Estimation (F4)

- [ ] **`test_normals_preserved_for_original_points`**:
  ```python
  pcd_legacy = make_pcd_with_normals(500)  # helper: pcd with pre-computed normals
  op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0, preserve_normals=True)
  result_pcd, meta = op.apply(pcd_legacy)
  # Verify 'normals' attribute exists in result
  assert 'normals' in result_pcd.point
  ```
- [ ] **`test_normals_estimated_for_synthetic_points`**:
  ```python
  # Synthetic points (indices n_original..) must have non-zero normals
  n_original = 500
  result_norms = result_pcd.point['normals'].numpy()
  synthetic_norms = result_norms[n_original:]
  norms_mag = np.linalg.norm(synthetic_norms, axis=1)
  assert np.all(norms_mag > 0.9), "Synthetic normals must be unit length"
  ```
- [ ] **`test_normals_skipped_when_input_has_none`**:
  ```python
  pcd = make_pcd(500)  # no normals
  op = Densify(preserve_normals=True)
  result_pcd, meta = op.apply(pcd)
  assert meta["status"] == "success"
  # Should NOT crash; normals either absent or silently skipped
  ```
- [ ] **`test_normals_disabled`**:
  ```python
  pcd = make_pcd_with_normals(500)
  op = Densify(preserve_normals=False)
  result_pcd, meta = op.apply(pcd)
  assert meta["status"] == "success"
  # normals attribute should NOT be added to result
  ```

---

## Phase 10: Unit Tests — Metadata Schema (F7)

- [ ] **`test_metadata_all_keys_present_on_success`**: Assert all 7 mandatory keys in meta dict on success path
- [ ] **`test_metadata_all_keys_present_on_skip`**: Assert all keys on skip path; `skip_reason` is not None
- [ ] **`test_metadata_all_keys_present_on_error`**: Assert all keys on error path; `error_message` is not None
- [ ] **`test_metadata_density_ratio_calculation`**: `density_ratio = densified_count / original_count` exactly
- [ ] **`test_metadata_algorithm_used_matches_config`**: When `algorithm="mls"`, `meta["algorithm_used"] == "mls"`

---

## Phase 11: Integration Tests — DAG Pipeline

- [ ] **`test_densify_accepts_tensor_pcd_from_upstream`**:
  ```python
  # Simulate PointConverter.to_pcd() → Densify → PointConverter.to_points() pipeline
  from app.modules.pipeline.base import PointConverter
  points_in = np.random.rand(1000, 14).astype(np.float32)
  pcd = PointConverter.to_pcd(points_in)
  op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
  result_pcd, meta = op.apply(pcd)
  points_out = PointConverter.to_points(result_pcd)
  assert points_out.shape[0] >= 1500
  assert points_out.shape[1] == 14  # structural columns preserved
  ```

- [ ] **`test_densify_followed_by_downsample_consistency`**:
  ```python
  # Densify → Downsample roundtrip should not lose original geometry
  from app.modules.pipeline.operations.downsample import Downsample
  pcd = make_pcd(1000)
  densify_op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
  downsample_op = Downsample(voxel_size=0.05)
  dense_pcd, _ = densify_op.apply(pcd)
  sampled_pcd, _ = downsample_op.apply(dense_pcd)
  # After up+down, should have reasonable point count
  count = get_count(sampled_pcd)
  assert count > 0
  ```

- [ ] **`test_densify_in_pipeline_chain`**:
  ```python
  # Crop → Densify → StatisticalOutlierRemoval chain
  from app.modules.pipeline.operations.crop import Crop
  from app.modules.pipeline.operations.outliers import StatisticalOutlierRemoval
  pcd = make_pcd(5000)
  crop_op = Crop(min_bound=[-5,-5,-5], max_bound=[5,5,5])
  densify_op = Densify()
  outlier_op = StatisticalOutlierRemoval()
  pcd, _ = crop_op.apply(pcd)
  pcd, _ = densify_op.apply(pcd)
  pcd, _ = outlier_op.apply(pcd)
  assert get_count(pcd) > 0
  ```

---

## Phase 12: Stress / Robustness Tests

- [ ] **`@pytest.mark.slow` `test_stress_1000_frames_no_crash`**:
  ```python
  op = Densify(algorithm="nearest_neighbor", density_multiplier=2.0)
  for i in range(1000):
      pcd = make_pcd(np.random.randint(10, 5000))
      result_pcd, meta = op.apply(pcd)
      assert meta["status"] in ("success", "skipped")
  # Must complete without any exception
  ```

- [ ] **`@pytest.mark.slow` `test_memory_not_growing`**:
  ```python
  # Run 100 frames, check RSS memory doesn't grow unboundedly
  import tracemalloc
  tracemalloc.start()
  op = Densify()
  for _ in range(100):
      pcd = make_pcd(10000)
      op.apply(pcd)
  current, peak = tracemalloc.get_traced_memory()
  tracemalloc.stop()
  assert peak < 200 * 1024 * 1024  # peak < 200MB for 100 frames of 10k pts
  ```

---

## Phase 13: Linter & Type Verification

- [ ] Run `ruff check app/modules/pipeline/operations/densify.py` → 0 errors
- [ ] Run `mypy app/modules/pipeline/operations/densify.py --strict` (or project's mypy config) → 0 errors
- [ ] Run `ruff check tests/pipeline/operations/test_densify.py` → 0 errors
- [ ] Confirm `densify.py` has no `from __future__ import annotations` needed (Python 3.10+ is the target; use `Optional[int]` style)

---

## Phase 14: Pre-PR Verification

- [ ] Run full test suite: `pytest tests/ -v -m "not slow"` → 0 failures
- [ ] Run slow tests: `pytest tests/ -v -m "slow"` → 0 failures, all performance tests within bounds
- [ ] Confirm `tests/pipeline/operations/test_densify.py` has `__init__.py` in its directory (already exists)
- [ ] Confirm no existing tests were broken by additive changes to `__init__.py`, `factory.py`, `registry.py`
- [ ] Final check: `pytest tests/pipeline/operations/ -v` → all pipeline operation tests pass
- [ ] Final check: `pytest tests/modules/test_node_definitions.py -v` → densify node appears in registry

---

## Test Fixtures Reference

The following helpers should be defined at the top of `test_densify.py` (or in a `conftest.py` under `tests/pipeline/`):

```python
import numpy as np
import open3d as o3d
from typing import Optional

def make_pcd(n: int, seed: int = 42) -> o3d.geometry.PointCloud:
    """Create a legacy PointCloud with n random points."""
    rng = np.random.default_rng(seed)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(rng.random((n, 3)).astype(np.float64))
    return pcd

def make_tensor_pcd(pts: Optional[np.ndarray] = None, n: int = 1000) -> o3d.t.geometry.PointCloud:
    """Create a tensor PointCloud."""
    if pts is None:
        pts = np.random.rand(n, 3).astype(np.float32)
    pcd = o3d.t.geometry.PointCloud()
    pcd.point.positions = o3d.core.Tensor(pts.astype(np.float32))
    return pcd

def make_pcd_with_normals(n: int) -> o3d.geometry.PointCloud:
    """Create a PointCloud with pre-estimated normals (sphere surface)."""
    pcd = o3d.geometry.PointCloud()
    pts = np.random.randn(n, 3)
    pts /= np.linalg.norm(pts, axis=1, keepdims=True)  # unit sphere
    pcd.points = o3d.utility.Vector3dVector(pts)
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(knn=10))
    return pcd

def get_count(pcd) -> int:
    """Get point count from either legacy or tensor pcd."""
    if isinstance(pcd, o3d.t.geometry.PointCloud):
        return pcd.point.positions.shape[0] if 'positions' in pcd.point else 0
    return len(pcd.points)

def get_positions(pcd) -> np.ndarray:
    """Extract positions as numpy array from either pcd type."""
    if isinstance(pcd, o3d.t.geometry.PointCloud):
        return pcd.point.positions.numpy()
    return np.asarray(pcd.points)
```

---

## Test Coverage Targets

| Category | Target Coverage |
|---|---|
| `Densify.__init__` validation | 100% |
| `apply()` control flow (all skip/error/success branches) | 100% |
| All 4 algorithm methods | ≥90% line coverage |
| Normal estimation | ≥85% line coverage |
| Metadata keys completeness | 100% |
| DAG integration (factory + registry) | 100% |

---

## Completion Gate

All items below must be `[x]` before `@qa` signs off:

- [ ] All Phase 1–10 tests passing (non-slow)
- [ ] All Phase 11 integration tests passing
- [ ] All Phase 12 slow/stress tests passing
- [ ] All Phase 13 linter checks passing
- [ ] All Phase 14 pre-PR checks passing
- [ ] `qa-report.md` written with test run output and coverage summary
