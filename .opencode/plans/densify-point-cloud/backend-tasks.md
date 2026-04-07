# Densify Point Cloud — Backend Development Tasks

**Agent:** `@be-dev`  
**Feature:** `densify-point-cloud`  
**Module:** `app/modules/pipeline/operations/densify.py`  
**References:** `technical.md`, `api-spec.md`, `requirements.md`

> **Before starting:** Read `technical.md` fully. All design decisions are finalized there.
> Check off `[x]` each task as you complete it.

---

## Prerequisites

- [x] Read `technical.md` (all 15 sections)
- [x] Read `api-spec.md` (all 8 sections)
- [x] Run existing test suite to confirm baseline: `pytest tests/pipeline/operations/ -v`
- [x] Confirm `scipy` is available: `python -c "from scipy.spatial import KDTree; print('OK')"`

---

## Phase 1: Module Skeleton & Enums

**File:** `app/modules/pipeline/operations/densify.py`

- [x] Create file with module docstring explaining the 4 algorithms, their use cases, and example config (copy from `technical.md` §3)
- [x] Add `DensifyAlgorithm` string enum: `nearest_neighbor`, `mls`, `poisson`, `statistical`
- [x] Add `DensifyQualityPreset` string enum: `fast`, `medium`, `high`
- [x] Add `DensifyStatus` string enum: `success`, `skipped`, `error`
- [x] Add `DensifyConfig` Pydantic v2 model with all fields and validators (per `api-spec.md` §1.2)
- [x] Add `DensifyMetadata` Pydantic v2 model (per `api-spec.md` §2)
- [x] Define module-level constants:
  - `PRESET_ALGORITHM_MAP: Dict[str, str]` → `{"fast": "nearest_neighbor", "medium": "statistical", "high": "mls"}`
  - `MIN_INPUT_POINTS: int = 10`
  - `MAX_MULTIPLIER: float = 8.0`
- [x] Add module-level logger: `logger = get_logger(__name__)`

---

## Phase 2: `Densify` Class — `__init__` and Validation

- [x] Define `class Densify(PipelineOperation)` with imports from `..base`
- [x] Implement `__init__(self, enabled, algorithm, density_multiplier, target_layer_count, quality_preset, preserve_normals)` with all defaults per `api-spec.md` §4
- [x] Add constructor-level validation:
  - [x] `algorithm` in `{"nearest_neighbor", "mls", "poisson", "statistical"}` → raise `ValueError`
  - [x] `density_multiplier` in `[1.0, 8.0]` → raise `ValueError`
  - [x] `quality_preset` in `{"fast", "medium", "high"}` → raise `ValueError`
- [x] Log algorithm selection at `INFO` level in `__init__`: `"Densify: Initialized with algorithm={algorithm}, multiplier={multiplier}, preset={preset}"`
- [x] Ensure no mutable state is stored that could cause cross-frame contamination (all intermediate arrays must be local to `apply()`)

---

## Phase 3: `apply()` — Entry Point & Control Flow

- [x] Implement `apply(self, pcd: Any) -> Tuple[Any, Dict[str, Any]]` with:
  - [x] `start_time = time.monotonic()` at entry
  - [x] Call `_validate_input(pcd)` → returns `(tensor_pcd, original_count)` or `(original_pcd, 0)` on empty
  - [x] Early return if `enabled=False` → status=skipped, skip_reason="Operation disabled"
  - [x] Early return if `original_count < MIN_INPUT_POINTS` → status=skipped + WARNING log
  - [x] Call `_resolve_effective_algorithm()` → returns resolved algorithm string
  - [x] Call `_compute_target_count(original_count)` → returns `int target_count`
  - [x] Early return if `target_count <= original_count` → status=skipped + INFO log
  - [x] Call `_run_algorithm(tensor_pcd, target_count)` wrapped in `try/except Exception`
  - [x] On exception: log ERROR, return `(original_pcd, error_metadata_dict)`
  - [x] On success: conditionally call `_estimate_normals(result_pcd, tensor_pcd, original_count)`
  - [x] Build and return `(result_pcd, metadata_dict)` with all required keys
  - [x] Log DEBUG: processing time and point counts
- [x] Ensure `processing_time_ms = (time.monotonic() - start_time) * 1000` is computed for ALL return paths

---

## Phase 4: Private Helpers

### `_validate_input()`
- [x] Handle `o3d.t.geometry.PointCloud` → return as-is with count
- [x] Handle `o3d.geometry.PointCloud` (legacy) → wrap with `o3d.t.geometry.PointCloud.from_legacy()` + return count
- [x] Handle empty or None input → return `(original, 0)`
- [x] Use `_tensor_map_keys()` pattern from `base.py` for safe attribute access

### `_resolve_effective_algorithm()`
- [x] Return `self.algorithm` (explicit always wins)
- [x] If the user sets `algorithm` to the default AND changes `quality_preset`, the preset map applies.
  > **Note:** Per `technical.md` §7 — explicit `algorithm` always takes precedence. Since `algorithm` has a default
  > of `"nearest_neighbor"`, if the user explicitly wants preset-based resolution, they should not set `algorithm`
  > or should set it to `None`. Constructor should accept `algorithm=None` as "use preset" mode.
- [x] Revise: `algorithm` should default to `None` (not `"nearest_neighbor"`) in `__init__`; if `None`, fall back to `PRESET_ALGORITHM_MAP[quality_preset]`
- [x] Update `api-spec.md` note: algorithm=None means "use preset" (but this is an implementation detail, not a user-facing null)

### `_compute_target_count()`
- [x] If `target_layer_count` is set: `effective_multiplier = target_layer_count / sqrt(original_count)` (heuristic for ring count estimation)
- [x] Else: `effective_multiplier = self.density_multiplier`
- [x] Clamp: `effective_multiplier = min(max(effective_multiplier, 1.0), MAX_MULTIPLIER)`
- [x] Return `int(original_count * effective_multiplier)`

### `_run_algorithm()`
- [x] Dispatch on resolved algorithm string to the 4 private methods
- [x] Each private method receives `(pcd: o3d.t.geometry.PointCloud, n_new: int)` and returns `o3d.t.geometry.PointCloud`

---

## Phase 5: Algorithm Implementations

### 5A — Nearest Neighbor (`_densify_nearest_neighbor`)
- [x] Convert tensor pcd to legacy: `pcd_legacy = pcd.to_legacy()`
- [x] Build `o3d.geometry.KDTreeFlann(pcd_legacy)`
- [x] Extract positions as numpy array: `pts = np.asarray(pcd_legacy.points)` → shape `(N, 3)` float64
- [x] Compute mean NN distance:
  - Sample 100 random points (or all if N < 100)
  - For each sample, query 2 nearest neighbors (k=2: first is self, second is NN)
  - `mean_nn_dist = mean(distances_to_2nd_neighbor)`
- [x] Pre-allocate synthetic array: `synthetic = np.empty((n_new, 3), dtype=np.float32)`
- [x] Generate synthetic points:
  - `points_per_source = max(1, ceil(n_new / N))`
  - For each source point (up to ceiling), generate a displacement vector:
    - Random unit direction: `d = rng.standard_normal(3); d /= np.linalg.norm(d)`
    - Random radius: `r = rng.uniform(0.05, 0.5) * mean_nn_dist`
    - `synthetic[i] = source_pt + r * d`
  - Stop when `n_new` points are filled
- [x] Concatenate: build new tensor pcd with `positions = np.vstack([original_pts, synthetic])`
- [x] Return new `o3d.t.geometry.PointCloud` with positions set
- [x] `del pcd_legacy` to free memory

### 5B — MLS / Tangent Plane Projection (`_densify_mls`)
- [x] Import `scipy.spatial.KDTree` (lazy import inside method)
- [x] Convert tensor pcd positions to numpy float64 array `pts`
- [x] Ensure normals:
  - If `'normals'` not in pcd.point → estimate via `pcd.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(knn=20))`
  - Extract normals as numpy array `norms`
- [x] Build `KDTree(pts)`
- [x] Compute mean NN distance (same pattern as 5A)
- [x] Compute `projection_radius = mean_nn_dist * 0.5`
- [x] Pre-allocate `synthetic = np.empty((n_new, 3), dtype=np.float32)`
- [x] Generation loop:
  - `points_per_source = max(1, ceil(n_new / N))`
  - For each source point `p` with normal `n`:
    - Build tangent plane basis `{u, v}`: pick world_up, cross with `n` to get `u`, cross `u` with `n` to get `v`
    - For each synthetic slot: `σ_u, σ_v ~ Uniform(-projection_radius/3, projection_radius/3)`
    - `new_pt = p + σ_u * u + σ_v * v`
    - `synthetic[i] = new_pt.astype(float32)`
- [x] Post-filter: remove synthetic points within `min_dist = mean_nn_dist * 0.05` of any existing point
- [x] Concatenate and return tensor pcd

### 5C — Poisson Reconstruction (`_densify_poisson`)
- [x] Convert tensor pcd to legacy
- [x] Ensure normals on legacy (estimate if missing: `pcd_legacy.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(knn=30))`)
- [x] Run Poisson: `mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd_legacy, depth=8, width=0, scale=1.1, linear_fit=False)`
- [x] Trim low-density vertices: `densities_arr = np.asarray(densities); threshold = np.quantile(densities_arr, 0.1); vertices_to_remove = densities_arr < threshold; mesh.remove_vertices_by_mask(vertices_to_remove)`
- [x] Sample `n_new` points from mesh: `sampled = mesh.sample_points_uniformly(number_of_points=n_new)`
- [x] Convert sampled (legacy) to tensor
- [x] Concatenate original tensor + sampled tensor positions
- [x] `del mesh, pcd_legacy` before returning
- [x] Return new tensor pcd

### 5D — Statistical Upsampling (`_densify_statistical`)
- [x] Import `scipy.spatial.KDTree` (lazy import)
- [x] Extract positions as numpy float64 array
- [x] Build `KDTree(pts)`, query `k=10` nearest neighbors for all points: `dists, idxs = kd.query(pts, k=11)` (first col is self)
- [x] `dists = dists[:, 1:]`, `idxs = idxs[:, 1:]` (exclude self)
- [x] Compute local density per point: `local_density = 10 / ((4/3) * π * max_dist^3)` where `max_dist = dists[:, -1]`
- [x] Find sparse-region points: `sparse_mask = local_density < np.percentile(local_density, 50)`
- [x] For sparse points, generate interpolated neighbors:
  - For each sparse point `p[i]` and its neighbor `p[j]`:
    - `α = rng.uniform(0.3, 0.7)`
    - `new_pt = (1 - α) * p[i] + α * p[j]`
  - Budget `n_new` points total across all sparse sources
- [x] Post-filter with `min_dist = mean_nn_dist * 0.3` (same as MLS)
- [x] Concatenate and return tensor pcd

---

## Phase 6: Normal Estimation (`_estimate_normals`)

- [x] Signature: `_estimate_normals(self, result_pcd: o3d.t.geometry.PointCloud, original_pcd: o3d.t.geometry.PointCloud, n_original: int) -> o3d.t.geometry.PointCloud`
- [x] Check if `'normals'` in `result_pcd.point` already (they would have come from the original points)
- [x] If `preserve_normals=False` or input had no normals → return `result_pcd` unchanged
- [x] Extract positions of synthetic-only points (slice from index `n_original` onward)
- [x] For synthetic positions, query k=10 neighbors in original_pcd positions using `KDTreeFlann`
- [x] Compute normal for each synthetic point = mean of neighbor normals, then normalize to unit length
- [x] Set `result_pcd.point['normals']` tensor (all N+M points) by combining:
  - Original normals (indices `0..n_original-1`) from `original_pcd.point['normals']`
  - Computed normals (indices `n_original..end`) from step above
- [x] Return updated `result_pcd`

---

## Phase 7: Wire Up to Pipeline

### `operations/__init__.py`
- [x] Add: `from .densify import Densify`

### `factory.py`
- [x] Add import: `from app.modules.pipeline.operations import Densify` (or update the existing import block)
- [x] Add to `_OP_MAP`: `"densify": Densify,`

### `registry.py`
- [x] Add full `NodeDefinition` for `"densify"` per `technical.md` §11
  - type, display_name, category, description, icon, websocket_enabled=True
  - All 6 `PropertySchema` entries (throttle_ms, algorithm, density_multiplier, target_layer_count, quality_preset, preserve_normals)
  - 1 input port, 1 output port
- [x] Add `"densify"` to `_OPERATION_TYPES` list at the bottom of the file

---

## Phase 8: Logging & Observability

- [x] Verify all log messages match the templates in `technical.md` §10
- [x] Confirm INFO log fires once per `__init__` (not per frame)
- [x] Confirm DEBUG log fires per successful `apply()` call
- [x] Confirm WARNING fires for each skip (not rate-limited — per frame is acceptable for debugging)
- [x] Confirm ERROR fires with full exception context (`exc_info=False` — message is already descriptive)

---

## Phase 9: Self-Review Checklist

Before handing off to `@qa`:

- [x] Run full test suite: `pytest tests/ -v` — ensure no regressions
- [x] Run module-level smoke test: import and instantiate `Densify()` with default args
- [x] Verify `OperationFactory.create("densify", {})` succeeds (default config)
- [x] Verify `OperationFactory.create("densify", {"algorithm": "poisson", "density_multiplier": 4.0})` succeeds
- [x] Verify invalid config raises `ValueError`: `Densify(algorithm="invalid")`, `Densify(density_multiplier=20.0)`
- [x] Verify the fail-safe: pass a cloud with 5 points → assert `status=skipped` in metadata
- [x] Verify the fail-safe: pass an already-dense cloud (no `target_layer_count`, high existing count) → assert `status=skipped`
- [x] Check for any import of `from __future__ import annotations` if using `|` union type syntax (Python 3.10+)
- [x] Confirm no `async def` anywhere in `densify.py` (operations are synchronous)
- [x] Confirm `apply()` never raises an unhandled exception (fuzz test with None, empty array, 1-point cloud)

---

## Dependencies & Order-of-Operations

```
Phase 1 (Skeleton)
    → Phase 2 (Init)
        → Phase 3 (apply)
            → Phase 4 (Helpers)
                → Phase 5 (Algorithms) ← can be done in parallel per algorithm
                → Phase 6 (Normals)
            → Phase 7 (Wire Up) ← requires Phase 5 complete
        → Phase 8 (Logging) ← can verify throughout Phase 3-6
    → Phase 9 (Self-review) ← final gate before @qa handoff
```

**Blocked by:** Nothing. `@qa` is writing `test_densify.py` in parallel (TDD). Ensure your implementation satisfies
all test contracts defined in `qa-tasks.md`.
