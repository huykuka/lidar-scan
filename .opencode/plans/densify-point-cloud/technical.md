# Densify Point Cloud — Technical Architecture

**Feature:** `densify-point-cloud`  
**Module File:** `app/modules/pipeline/operations/densify.py`  
**Status:** ARCHITECTURE COMPLETE — Ready for `@be-dev`  
**References:** `requirements.md`, `api-spec.md`

---

## 1. Architectural Context & GitNexus Impact Analysis

### 1.1 Integration Surface

GitNexus impact analysis on `PipelineOperation` (base class) reports **HIGH** blast radius with 24 direct dependents.
`densify.py` will be an **additive** change only — it extends `PipelineOperation` without modifying it. The following
files require a purely **additive** touch (no behaviour change to existing code):

| File | Change Type | Risk |
|---|---|---|
| `app/modules/pipeline/operations/__init__.py` | Add `Densify` export | LOW — additive import |
| `app/modules/pipeline/factory.py` | Add `"densify"` to `_OP_MAP` | LOW — additive dict entry |
| `app/modules/pipeline/registry.py` | Add `NodeDefinition` + `_OPERATION_TYPES` entry | LOW — additive |

`OperationFactory` impact was **LOW** (1 direct importer: `operation_node.py`). The factory's `create()` method uses a
dictionary dispatch, so adding a key is zero-risk.

> **CRITICAL**: No existing files are modified structurally. All changes are purely additive. The `OperationNode`
> orchestration loop (`operation_node.py`) already handles `(pcd, metadata)` tuple returns — no changes needed there.

---

## 2. Module Design

### 2.1 Class Structure Decision

**Decision: Unified `Densify` class with Strategy pattern (internal `_AlgorithmStrategy` protocol)**

**Rationale:**
- A single `Densify(**config)` call matches the existing factory pattern (`OperationFactory.create(op_type, config)`).
- All four algorithms share identical `__init__` parameters (multiplier, preset, normals toggle) — no value in separate
  constructor signatures.
- The Strategy pattern is implemented as **four private methods**, not separate classes. This avoids over-engineering
  while keeping each algorithm's logic isolated and independently testable.
- Follows the exact pattern of `StatisticalOutlierRemoval` / `OutlierRemoval` in the codebase.

**Rejected alternative: `DensifyNN`, `DensifyMLS`, `DensifyPoisson`, `DensifyStatistical` separate classes**
- Would require four `_OP_MAP` entries and four `NodeDefinition` registrations.
- The factory already has a `"densify"` key that resolves to one class; the algorithm is a config parameter.
- Violates the "algorithm-agnostic" design principle from requirements.

### 2.2 File Structure

```
app/modules/pipeline/operations/
└── densify.py          ← NEW (this feature)

tests/pipeline/operations/
└── test_densify.py     ← NEW (TDD — written first by @qa)
```

**Modified files (additive only):**
```
app/modules/pipeline/operations/__init__.py   ← add Densify import
app/modules/pipeline/factory.py               ← add "densify" to _OP_MAP
app/modules/pipeline/registry.py             ← add NodeDefinition + type entry
```

### 2.3 Class Architecture Diagram

```
PipelineOperation (ABC)
    └── Densify
            ├── __init__(algorithm, density_multiplier, target_point_count,
            │           quality_preset, preserve_normals, enabled)
            ├── apply(pcd: Any) -> Tuple[Any, Dict[str, Any]]
            │       ├── _validate_input(pcd) -> (o3d.t.PointCloud, int)
            │       ├── _resolve_effective_algorithm() -> str
            │       ├── _compute_target_count(original_count) -> int
            │       ├── _run_algorithm(pcd, target_count) -> o3d.t.PointCloud
            │       │       ├── _densify_nearest_neighbor(pcd, n_new)
            │       │       ├── _densify_mls(pcd, n_new)
            │       │       ├── _densify_poisson(pcd, n_new)
            │       │       └── _densify_statistical(pcd, n_new)
            │       └── _estimate_normals(result_pcd, original_pcd, n_original)
```

---

## 3. Algorithm Implementation Specifications

### 3.1 Nearest Neighbor (`nearest_neighbor`) — Fast Mode

**Target latency:** <100ms for 50k–100k points  
**Open3D API:** `o3d.geometry.KDTreeFlann` (legacy API — fastest for pure neighbor search)

**Algorithm:**
1. Build `KDTreeFlann` from the `to_legacy()` conversion of the input tensor cloud.
2. For each existing point, compute how many synthetic points to generate: `n_synthetic_per_point = ceil(target_count / original_count)` with jitter.
3. Sample a random unit vector, scale by a random fraction of the mean NN distance (radius ≈ 0.1× mean_nn_dist), and add to the source point XYZ.
4. Accumulate synthetic points in a pre-allocated `numpy` array (`np.empty((n_new, 3), dtype=np.float32)`).
5. Concatenate original + synthetic positions back into a new `o3d.t.geometry.PointCloud`.

**Memory:** Pre-allocate full output array at step 4. Never grow a Python list per point.

**Key parameters:** `search_radius_factor=0.1` (fraction of mean NN distance for jitter spread).

### 3.2 Moving Least Squares (`mls`) — Medium/High Mode

**Target latency:** 200–500ms for 50k–100k points  
**Strategy:** Custom numpy/scipy implementation (Open3D does not expose a public MLS upsampling API in v0.17+).

> **Architecture Decision (BA Q2):** Use `scipy.spatial.KDTree` + local polynomial surface fitting, **not** Open3D's
> internal `surface_reconstruction` which is Poisson-based. Open3D's `estimate_normals` + tangent plane projection
> achieves MLS-quality results with the available API surface.

**Algorithm:**
1. Convert to legacy, build `scipy.spatial.KDTree` for neighbor queries.
2. Estimate normals on the original cloud (`pcd.estimate_normals`, `SearchParamKNN(k=20)`) if not present.
3. For each "gap" slot (positions between existing points based on their neighbors), project a candidate point onto
   the tangent plane of its nearest neighbor (tangent plane = point + span{u, v} where u, v ⊥ normal).
4. Add Gaussian noise in the tangent plane: `new_pt = center + σ_u * u + σ_v * v` where σ ~ `radius / 3`.
5. Reject points that land within `min_dist = radius / 4` of any existing point (avoid duplicates).

**Key parameters:** `k_neighbors=20`, `projection_radius=mean_nn_dist * 0.5`.

### 3.3 Poisson Reconstruction (`poisson`) — High Mode

**Target latency:** 500ms–2s  
**Open3D API:** `o3d.geometry.TriangleMesh.create_from_point_cloud_poisson()` then resample.

> **Architecture Decision (BA Q3):** Hybrid approach — **preserve all original points, then augment with Poisson
> resampled points** up to the target count. Do NOT fully replace the cloud with Poisson resampled points, as that
> loses original sensor data and violates the "non-destructive" design principle.

**Algorithm:**
1. Ensure normals on legacy cloud (`estimate_normals` with `SearchParamKNN(k=30)`).
2. Run Poisson reconstruction: `mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd_legacy, depth=8, width=0, scale=1.1, linear_fit=False)`.
3. Trim low-density vertices: remove mesh vertices where density < `np.quantile(densities, 0.1)`.
4. Sample `n_new = target_count - original_count` points uniformly from the mesh surface using
   `mesh.sample_points_uniformly(number_of_points=n_new)`.
5. Concatenate original (tensor) + sampled (legacy→tensor) positions.

**Memory guard:** Check `n_new <= original_count * 7` (cap at 8x). Log warning and clamp if exceeded.

**Depth parameter:** `depth=8` for Fast/Medium, `depth=9` for High preset Poisson variant (to be tested).

### 3.4 Statistical Upsampling (`statistical`) — Medium Mode

**Target latency:** 100–300ms  
**Strategy:** Custom scipy-based local density estimation.

> **Architecture Decision:** Compute local density variance per point, identify low-density regions, and insert
> synthetic points proportionally. Does not use Open3D primitives directly — pure numpy/scipy.

**Algorithm:**
1. Build `scipy.spatial.KDTree` for the input cloud.
2. For each point, query `k=10` nearest neighbors; compute local density = `k / volume_of_sphere(radius=max_dist)`.
3. Normalize densities; points in the bottom 50th percentile are "sparse regions."
4. For sparse-region points, generate `n_extra` synthetic neighbors by:
   a. Interpolating linearly between the point and each of its k neighbors.
   b. Adding slight random perturbation in the direction of the neighbor (α ∈ [0.3, 0.7]).
5. Post-filter with `min_dist` to prevent stacking.

**Key parameters:** `k_neighbors=10`, `sparse_percentile=50`, `min_dist=mean_nn_dist * 0.3`.

---

## 4. Normal Estimation Strategy

> **Architecture Decision (BA Q4):** Normal estimation parameters are **partially user-configurable** — `preserve_normals` is the user-facing toggle. The internal k-neighbor count is **hardcoded at k=10** (matching requirements spec F4). Search radius is derived automatically from mean NN distance. This balances usability and correctness.

**Logic:**
1. If `preserve_normals=False` → skip entirely.
2. If input `pcd` has no `'normals'` attribute → log INFO, skip (no error per F4).
3. If input has normals → preserve original point normals unchanged.
4. For synthetic points only: estimate normals using `o3d.geometry.KDTreeSearchParamKNN(knn=10)` against the **original** cloud (NOT the augmented cloud). This prevents synthetic points from contaminating normal estimation.
5. Normal estimation is performed via `o3d.geometry.PointCloud.estimate_normals()` on a legacy cloud,
   then results are transferred back to the tensor cloud.

---

## 5. Threading & Asyncio Constraints

**Rule from `backend.md`:** All heavy Open3D operations MUST run via `await asyncio.to_thread()`.

The `Densify.apply()` method is **purely synchronous** (no `async`, no `await`). This is correct and consistent with
all other `PipelineOperation` subclasses. The `OperationNode._sync_compute()` wrapper in `operation_node.py` already
dispatches via `asyncio.to_thread()` for all non-`visualize` operations.

**Threading safety requirements for each algorithm:**

| Algorithm | GIL Release | Open3D Thread-Safety | Notes |
|---|---|---|---|
| `nearest_neighbor` | Yes (numpy ops) | N/A | Fully safe |
| `mls` | Yes (scipy/numpy) | `estimate_normals` is thread-safe | Safe |
| `poisson` | Yes (Open3D C++) | `create_from_point_cloud_poisson` is thread-safe | Safe |
| `statistical` | Yes (scipy/numpy) | N/A | Safe |

**Do NOT** store any mutable state on the `Densify` instance during `apply()`. The instance is shared across frames.
All intermediate arrays must be local variables inside `apply()` and its helper methods.

---

## 6. Memory Optimization Strategy

> **Architecture Decision (BA Q5):** Chunking/streaming for >1M point clouds is **out of scope for v1**. The
> requirement cap is `density_multiplier <= 8.0` with typical input 50k–100k points, giving a maximum output
> of ~800k points (~30MB float32). This is within a single numpy allocation. The `max_multiplier=8.0` guard in
> validation is the primary memory fence.

**Memory strategy:**

1. **Pre-allocate output arrays:** All algorithms must pre-compute `n_new = target - original` before allocating.
   Use `np.empty((n_new, 3), dtype=np.float32)` — never `np.append()` in loops.
2. **Legacy API conversions:** `pcd.to_legacy()` creates a copy. Assign to a local variable and delete after use
   (`del pcd_legacy` at end of algorithm scope) to free memory promptly.
3. **Poisson mesh intermediate:** The `TriangleMesh` object from Poisson reconstruction can be large. Delete it
   (`del mesh`) immediately after `sample_points_uniformly()`.
4. **Tensor concatenation:** Use `o3d.core.Tensor.append()` or build a single numpy array and wrap once.
   Avoid multiple tensor concatenations in a loop.
5. **Guard on `target_point_count`:** If `target_point_count` implies a multiplier > 8.0, clamp to 8.0 and log a
    warning. Example: 100 input points with `target_point_count=900` → multiplier=9.0 → clamped to 8.0 → output=800.

**Memory footprint table:**

| Input Points | Max Multiplier | Output Points | RAM (float32 XYZ) |
|---|---|---|---|
| 50,000 | 8× | 400,000 | ~4.7 MB |
| 100,000 | 8× | 800,000 | ~9.5 MB |
| 200,000 | 8× | 1,600,000 | ~19 MB |

These are well within the <50MB requirement from NF1.

---

## 7. Configuration Resolution Logic

The `apply()` method implements the following precedence rules at runtime (not at `__init__`):

```
1. If enabled=False → return original, status=skipped
2. If input_count < 10 → return original, status=skipped (log WARNING)
3. Resolve effective_algorithm:
     a. If algorithm is explicitly set (not None) → use algorithm
     b. Else → use preset_algorithm_map[quality_preset]
4. Compute target_count:
     a. If target_point_count is set → effective_multiplier = target_point_count / original_count
     b. Else → target_count = int(input_count * density_multiplier)
     c. Clamp: target_count = min(target_count, input_count * 8)
5. If target_count <= input_count → return original, status=skipped (log INFO)
6. Run algorithm → if exception → return original, status=error (log ERROR)
7. If preserve_normals → estimate normals for synthetic points
8. Return densified_pcd, metadata dict
```

**Preset Algorithm Map:**
```python
PRESET_ALGORITHM_MAP = {
    "fast":   "nearest_neighbor",
    "medium": "statistical",
    "high":   "mls",
}
```

Note: `"poisson"` is available only through explicit `algorithm` override (not a default preset algorithm),
due to its 500ms–2s latency being too slow for any default preset. The High preset defaults to MLS.

---

## 8. Metadata Contract

`apply()` always returns a 2-tuple `(pcd, metadata_dict)`. The `metadata_dict` has the following guaranteed keys:

```python
{
    # Always present
    "status":             str,       # "success" | "skipped" | "error"
    "original_count":     int,
    "densified_count":    int,       # == original_count on skip/error
    "density_ratio":      float,     # densified_count / original_count
    "algorithm_used":     str,       # e.g. "nearest_neighbor", "skipped", "error"
    "processing_time_ms": float,

    # Conditional
    "skip_reason":        str | None,   # set on status=skipped
    "error_message":      str | None,   # set on status=error
}
```

---

## 9. Error Handling Contract

All exceptions from algorithm execution are caught inside `apply()`:

```python
try:
    result_pcd = self._run_algorithm(pcd_tensor, target_count)
except Exception as e:
    logger.error(
        f"[{node_id}] Densify: {self.algorithm} algorithm failed — {e}. "
        f"Passing through original cloud."
    )
    return original_pcd, {
        "status": "error",
        "error_message": str(e),
        ...
    }
```

**No exceptions propagate out of `apply()`**. The DAG orchestrator (`OperationNode`) remains unaffected.

---

## 10. Logging Specification

All log calls include the instance's `node_id` (passed via the `_node_id` attribute set during
`OperationNode.__init__` → but since `PipelineOperation` does not receive `node_id`, use module-level logger
with a `[Densify]` prefix. Operations that need node context should use `self._debug_prefix` if set, else `"[Densify]"`).

> **Implementation note:** The existing codebase does not pass `node_id` into `PipelineOperation.apply()`.
> Use `get_logger(__name__)` (matching `operation_node.py` pattern) and prefix messages with `"Densify:"`.

| Level | Message template |
|---|---|
| `INFO` | `"Densify: Using {algorithm} with {multiplier}x multiplier"` |
| `DEBUG` | `"Densify: Processed {orig}→{final} points in {ms:.1f}ms"` |
| `WARNING` | `"Densify: Skipping — {reason}"` |
| `ERROR` | `"Densify: {algorithm} failed — {error}. Passing through original cloud."` |

---

## 11. DAG Registration (registry.py Changes)

The new node schema for the Angular flow-canvas UI:

```python
node_schema_registry.register(NodeDefinition(
    type="densify",
    display_name="Point Cloud Densify",
    category="operation",
    description="Increases point cloud density by interpolating synthetic points",
    icon="blur_circular",
    websocket_enabled=True,
    properties=[
        PropertySchema(name="throttle_ms", ...),
        PropertySchema(
            name="algorithm", label="Algorithm", type="select",
            default="nearest_neighbor",
            options=[
                {"label": "Nearest Neighbor (Real-time, <100ms)",   "value": "nearest_neighbor"},
                {"label": "Statistical Upsampling (Balanced, <300ms)", "value": "statistical"},
                {"label": "Moving Least Squares (High Quality, <500ms)", "value": "mls"},
                {"label": "Poisson Reconstruction (Best Quality, <2s)", "value": "poisson"},
            ],
            help_text="Densification algorithm. Overrides quality_preset if set."
        ),
        PropertySchema(
            name="density_multiplier", label="Density Multiplier", type="number",
            default=2.0, min=1.0, max=8.0, step=0.5,
            help_text="Target density increase factor (e.g. 2.0 = 2× input points)"
        ),
        PropertySchema(
            name="target_point_count", label="Target Point Count (optional)", type="number",
            default=None, min=1, step=1,
            help_text="Override multiplier: absolute output point count (e.g. 20000 for 2× a 10k cloud)"
        ),
        PropertySchema(
            name="quality_preset", label="Quality Preset", type="select",
            default="fast",
            options=[
                {"label": "Fast (<100ms, real-time)",   "value": "fast"},
                {"label": "Medium (<300ms, interactive)", "value": "medium"},
                {"label": "High (<2s, batch)",          "value": "high"},
            ],
            help_text="Preset. Manual algorithm selection takes precedence."
        ),
        PropertySchema(
            name="preserve_normals", label="Preserve Normals", type="boolean",
            default=True,
            help_text="Interpolate surface normals for new synthetic points"
        ),
    ],
    inputs=[PortSchema(id="in", label="Input")],
    outputs=[PortSchema(id="out", label="Output")]
))
```

---

## 12. Factory Registration (factory.py Changes)

```python
# In _OP_MAP dict:
"densify": Densify,

# In imports:
from app.modules.pipeline.operations import Densify
```

---

## 13. Open Questions (Resolved)

| # | Question | Resolution |
|---|---|---|
| Q1 | Single class vs. per-algorithm classes? | **Single `Densify` class with Strategy pattern (4 private methods)** |
| Q2 | MLS implementation strategy? | **Custom scipy + tangent plane projection** (no Open3D MLS API available in v0.17+) |
| Q3 | Poisson: preserve originals or fully resample? | **Hybrid: preserve all originals + augment with Poisson-sampled synthetic points** |
| Q4 | Normal estimation parameters — configurable? | **`preserve_normals` bool is user-facing; `k=10` is hardcoded per spec F4** |
| Q5 | Memory management for >1M points? | **Chunking out of scope v1; `max_multiplier=8.0` is the memory guard; pre-allocate numpy arrays** |

---

## 14. Dependency Map

```
densify.py
├── Standard library: time, logging, math
├── numpy (already in requirements)
├── open3d (already in requirements)
├── scipy.spatial.KDTree (already used by generate_plane.py)
└── app.modules.pipeline.base (PipelineOperation, _tensor_map_keys)
```

No new third-party dependencies are introduced.

---

## 15. Acceptance Criteria Cross-Reference

| Req | Technical Implementation |
|---|---|
| F1: 4 algorithms | §3 — `_densify_nearest_neighbor`, `_densify_mls`, `_densify_poisson`, `_densify_statistical` |
| F2: Density multiplier + target point count | §7 — `_compute_target_count()` with both modes |
| F3: Quality presets | §7 — `PRESET_ALGORITHM_MAP` + precedence logic |
| F4: Normal preservation | §4 — `_estimate_normals()` private method |
| F5: Fail-safe | §9 — all exceptions caught in `apply()` |
| F6: Config parameters | §11 — `NodeDefinition` + `Densify.__init__` signature |
| F7: Output metadata | §8 — metadata dict contract |
| NF1: Performance | §3 — per-algorithm latency targets |
| NF2: DAG integration | §2, §11, §12 — `PipelineOperation`, registry, factory |
| NF3: Logging | §10 — log levels and message templates |
