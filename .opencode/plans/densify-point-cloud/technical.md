# Densify Point Cloud — Technical Architecture

**Feature:** `densify-point-cloud`  
**Module Package:** `app/modules/pipeline/operations/density/` (refactored from single-file `densify.py`)  
**Backward-Compat Shim:** `app/modules/pipeline/operations/densify.py` (re-exports all symbols)  
**Status:** ARCHITECTURE COMPLETE — Refactored to modular per-algorithm class structure  
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

### 2.1 Class Structure — Modular Package (Refactored 2026-04)

> **Refactor note:** The original v1.0 design used a single `densify.py` file (~1359 lines) with all four
> algorithms as private methods on a monolithic `Densify` class. This was refactored in April 2026 into a
> modular `density/` package with per-algorithm classes inheriting from a shared `DensityAlgorithmBase`.
> The original design rationale (§2.1 v1.0) is preserved below for historical context.

**Decision: Modular `density/` package with `DensityAlgorithmBase` ABC + per-algorithm classes + `Densify` dispatcher**

**Rationale:**
- The monolithic file grew to ~1359 lines, making it difficult to navigate, review, and test individual algorithms in isolation.
- A shared `DensityAlgorithmBase` abstract class extracts common logic (mean NN distance computation, tangent basis, duplicate filtering) into one place — DRY.
- Each algorithm class (`NearestNeighborDensify`, `MLSDensify`, `PoissonDensify`, `StatisticalDensify`) is a single file with a single responsibility.
- The `Densify` dispatcher class preserves the existing public API — `OperationFactory.create("densify", config)` still returns a `Densify` instance that routes internally to the correct algorithm class.
- A backward-compatibility shim at the old `densify.py` path re-exports all public symbols, so all existing imports work unchanged.

**Previous design (v1.0, historical):**
- A single `Densify` class with four private methods (`_densify_nearest_neighbor`, etc.).
- Strategy pattern via internal dispatch — simple but all 1359 lines in one file.

### 2.2 Package Layout

```
app/modules/pipeline/operations/
├── density/                         ← NEW package (this refactor)
│   ├── __init__.py                  ← Public API: re-exports all classes, enums, models
│   ├── density_base.py              ← DensityAlgorithmBase ABC, enums, param models,
│   │                                   constants, shared utilities (mean_nn_dist,
│   │                                   tangent_basis, filter_too_close)
│   ├── densify.py                   ← Densify dispatcher (PipelineOperation subclass)
│   ├── nearest_neighbor.py          ← NearestNeighborDensify algorithm
│   ├── mls.py                       ← MLSDensify algorithm
│   ├── poisson.py                   ← PoissonDensify algorithm
│   └── statistical.py               ← StatisticalDensify algorithm
│
├── densify.py                       ← Backward-compat SHIM (re-exports from density/)
│
└── __init__.py                      ← Imports Densify from densify.py (unchanged)

tests/pipeline/operations/
└── test_densify.py                  ← 109 non-slow tests (unchanged, all passing)
```

**Files modified during refactor (non-structural, additive only):**
```
app/modules/pipeline/operations/__init__.py   ← No changes (imports from densify.py shim)
app/modules/pipeline/factory.py               ← No changes (imports Densify from operations)
app/modules/pipeline/registry.py              ← No changes (NodeDefinition unchanged)
tests/pipeline/operations/test_densify.py     ← Logger names updated (density → parent logger)
```

### 2.3 Class Hierarchy

```
PipelineOperation (ABC)                        [app.modules.pipeline.base]
    │
    └── Densify (dispatcher)                   [density/densify.py]
            ├── __init__(algorithm, density_multiplier,
            │           quality_preset, preserve_normals, enabled, ...)
            ├── apply(pcd) -> (pcd, metadata)  ← delegates to algorithm class
            ├── _resolve_effective_algorithm()
            ├── _compute_target_count()
            └── _estimate_normals()

DensityAlgorithmBase (ABC)                     [density/density_base.py]
    │   ├── mean_nn_dist(pts) -> float         [static, shared]
    │   ├── tangent_basis(normal) -> (u, v)    [static, shared]
    │   ├── filter_too_close(pts, tree, d)     [static, shared]
    │   └── densify(pcd, n_new, params) -> pcd [abstract]
    │
    ├── NearestNeighborDensify                 [density/nearest_neighbor.py]
    │       └── densify(pcd, n_new, params)
    │
    ├── MLSDensify                             [density/mls.py]
    │       └── densify(pcd, n_new, params)
    │
    ├── PoissonDensify                         [density/poisson.py]
    │       └── densify(pcd, n_new, params)
    │
    └── StatisticalDensify                     [density/statistical.py]
            └── densify(pcd, n_new, params)
```

### 2.4 Dispatcher Routing

The `Densify` class (the sole `PipelineOperation` subclass) maps algorithm names to their
corresponding class via an internal dispatch table:

```python
_ALGORITHM_CLASSES = {
    "nearest_neighbor": NearestNeighborDensify,
    "mls":             MLSDensify,
    "poisson":         PoissonDensify,
    "statistical":     StatisticalDensify,
}
```

When `apply()` is called, it resolves the effective algorithm (explicit `algorithm` param or
`PRESET_ALGORITHM_MAP[quality_preset]`), instantiates the corresponding algorithm class, and
delegates the heavy computation to its `densify()` method.

### 2.5 Backward-Compatibility Shim

`app/modules/pipeline/operations/densify.py` is now a thin re-export module:

```python
# Backward-compatibility shim — all public symbols re-exported from density/ package
from app.modules.pipeline.operations.density import (
    Densify,
    DensifyAlgorithm,
    DensifyConfig,
    DensifyLogLevel,
    DensifyNNParams,
    DensifyMLSParams,
    DensifyPoissonParams,
    DensifyStatisticalParams,
    DensityAlgorithmBase,
    NearestNeighborDensify,
    MLSDensify,
    PoissonDensify,
    StatisticalDensify,
    # ... all other public symbols
)
```

This ensures:
- `from app.modules.pipeline.operations.densify import Densify` — works (shim path)
- `from app.modules.pipeline.operations.density import Densify` — works (new direct path)
- `from app.modules.pipeline.operations import Densify` — works (via `__init__.py`)
- `OperationFactory.create("densify", {})` — works (factory imports from operations)

### 2.6 Logger Hierarchy

Each module uses `get_logger(__name__)`, producing the following logger names:

```
app.modules.pipeline.operations.density                  ← package __init__
app.modules.pipeline.operations.density.density_base     ← base class
app.modules.pipeline.operations.density.densify          ← dispatcher
app.modules.pipeline.operations.density.nearest_neighbor ← NN algorithm
app.modules.pipeline.operations.density.mls              ← MLS algorithm
app.modules.pipeline.operations.density.poisson          ← Poisson algorithm
app.modules.pipeline.operations.density.statistical      ← Statistical algorithm
```

Tests capture the parent logger `app.modules.pipeline.operations.density` which propagates
all child module logs. This replaced the previous `app.modules.pipeline.operations.densify`
logger name from the monolithic file.

---

## 3. Algorithm Implementation Specifications

### 3.1 Nearest Neighbor (`nearest_neighbor`) — Fast Mode

**Target latency:** <100ms for 50k–100k points  
**Search API:** `scipy.spatial.KDTree` (global full-cloud search — no per-ring sub-sampling)

> **Refactor note (2026-04):** The original spec referenced `o3d.geometry.KDTreeFlann` with random 100-point
> sampling for mean NN distance computation.  This was replaced with a global `scipy.spatial.KDTree` over ALL
> points to eliminate scanline/ring bias and ensure volumetric (sensor-agnostic) point generation.

**Algorithm:**
1. Extract all point positions as a numpy float64 array `pts` (N × 3).
2. Compute global mean NN distance via `_compute_mean_nn_dist_global(pts)` — builds a `scipy.spatial.KDTree`
   on the full cloud and queries k=2 (self + nearest) for up to 1000 uniformly-random sample points.
   This distance reflects the true 3-D point spacing, not just within-ring XY spacing.
3. For `n_new` synthetic slots, pick a random source point from the full cloud (uniform over all N points).
4. Generate a uniformly random 3-D unit direction vector (no axis restriction).
5. Scale by a random radius in `[0.05, 0.5] × mean_nn_dist` and add to the source point XYZ.
6. Accumulate synthetic points in a pre-allocated `numpy` array (`np.empty((n_new, 3), dtype=np.float32)`).
7. Concatenate original + synthetic positions into a new `o3d.t.geometry.PointCloud`.

**Memory:** Pre-allocate full output array at step 6. Never grow a Python list per point.

**Key parameters:** `displacement_factor ∈ [0.05, 0.5]` (fraction of global mean NN distance).

**Volumetric guarantee:** Because source selection is uniform over the full cloud and the direction is an
isotropic 3-D unit vector, synthetic points are generated in all spatial directions.  Vertical (z-axis)
gap filling occurs when the z-gap is smaller than the within-layer XY spacing, causing the global
mean NN distance to be dominated by cross-layer distances.  No axis-specific logic is used.

### 3.2 Moving Least Squares (`mls`) — Medium/High Mode

**Target latency:** 200–500ms for 50k–100k points  
**Strategy:** Custom numpy/scipy implementation (Open3D does not expose a public MLS upsampling API in v0.17+).

> **Architecture Decision (BA Q2):** Use `scipy.spatial.KDTree` + local polynomial surface fitting, **not** Open3D's
> internal `surface_reconstruction` which is Poisson-based. Open3D's `estimate_normals` + tangent plane projection
> achieves MLS-quality results with the available API surface.

**Algorithm:**
1. Convert to legacy, build `scipy.spatial.KDTree` for global duplicate-filter queries.
2. Estimate normals on the original cloud (`pcd.estimate_normals`, `SearchParamKNN(k=20)`) if not present.
   Normal estimation is performed via a full-cloud KNN search — no per-ring restriction.
3. Compute global mean NN distance via `_compute_mean_nn_dist_global(pts)` (same as NN algorithm).
4. For each synthetic slot, select a random source point from the full cloud and compute its tangent-plane
   basis `{u, v}` from its normal (cross-product with a world axis, falls back if near-parallel).
5. Generate `new_pt = p + σ_u * u + σ_v * v` where `σ ~ Uniform(-projection_radius/3, projection_radius/3)`.
   `projection_radius = mean_nn_dist * 0.5`.
6. Apply light post-filtering: remove synthetic points within `min_dist = mean_nn_dist * 0.05` of any
   existing point (using the global KDTree from step 1).

**Key parameters:** `k_neighbors=20`, `projection_radius=mean_nn_dist * 0.5`.

**Volumetric behaviour:** MLS follows each source point's local tangent plane.  For flat horizontal clouds
the tangent plane is XY, so displacements are horizontal.  For tilted or curved surfaces the tangent plane
spans the z direction and generates points with vertical spread.  This is the correct surface-following
behaviour — no axis restriction is imposed.

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
1. Build `scipy.spatial.KDTree` over ALL input points (global, full-cloud).
2. For each point, query `k=10` nearest neighbors; compute local density = `k / volume_of_sphere(radius=max_dist)`.
3. Normalize densities; points in the bottom 50th percentile are "sparse regions."
4. For sparse-region points, generate `n_extra` synthetic neighbors by:
   a. Interpolating linearly between the point and each of its k neighbors.
   b. Adding slight random perturbation in the direction of the neighbor (α ∈ [0.3, 0.7]).
5. Post-filter with `min_dist = mean_nn_dist * 0.3` to prevent stacking.

**Volumetric guarantee:** Because the KDTree is built on all points and k=10 queries include cross-layer
neighbours when z_gap < within-layer XY spacing, interpolated points land inside 3-D gaps.  For the
common two-layer case the condition is met when layers are sparse (few points per layer), causing the
global mean NN distance to reflect the cross-layer gap size.

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
     a. target_count = int(input_count * density_multiplier)
     b. Clamp: target_count = min(target_count, input_count * 8)
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
| Q6 | Mean NN distance sampling — global or per-ring? | **Global `scipy.spatial.KDTree` over all points (2026-04 refactor).  No random-sampled `KDTreeFlann`.  For N>1000 a uniform random sample of 1000 pts is drawn for speed; the KDTree itself is built on all N points so neighbours are truly global.** |

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
| F2: Density multiplier | §7 — `_compute_target_count()` with `density_multiplier` |
| F3: Quality presets | §7 — `PRESET_ALGORITHM_MAP` + precedence logic |
| F4: Normal preservation | §4 — `_estimate_normals()` private method |
| F5: Fail-safe | §9 — all exceptions caught in `apply()` |
| F6: Config parameters | §11 — `NodeDefinition` + `Densify.__init__` signature |
| F7: Output metadata | §8 — metadata dict contract |
| NF1: Performance | §3 — per-algorithm latency targets |
| NF2: DAG integration | §2, §11, §12 — `PipelineOperation`, registry, factory |
| NF3: Logging | §10, §16 — log levels, message templates, and `DensifyLogLevel` enum |
| NF4: Log spam reduction | §16 — minimal/full/none modes with env-var override |
| NF5: Algorithm param exposure | §17 — per-algorithm Pydantic param models |

---

## 16. Log Level Configuration (v1.1)

### 16.1 Overview

The `Densify` module historically emitted a `DEBUG` log for every `apply()` call, which in a streaming pipeline
running at 10–30 FPS produced hundreds of log lines per second. The v1.1 update introduces a configurable
`log_level` that reduces this to a single summary message per call (or complete silence) without losing ERROR
visibility.

### 16.2 `DensifyLogLevel` Enum

```python
class DensifyLogLevel(str, Enum):
    MINIMAL = "minimal"   # Single summary DEBUG/INFO/WARNING per apply() — DEFAULT
    FULL    = "full"      # Original per-step DEBUG logging (useful for debugging)
    NONE    = "none"      # Complete silence; only ERROR messages are always emitted
```

### 16.3 Behaviour Matrix

| `log_level` | On success | On skip | On error |
|---|---|---|---|
| `minimal` | 1× `DEBUG` summary (orig→final pts, ms) | 1× `INFO` or `WARNING` with reason | Always `ERROR` |
| `full` | Original multi-step `DEBUG` per algorithm | `INFO`/`WARNING` with reason | Always `ERROR` |
| `none` | Silent | Silent | Always `ERROR` |

> **ERROR messages are always logged regardless of `log_level`** to guarantee operational visibility of failures.

### 16.4 Resolution Precedence

```
1. Explicit log_level= constructor argument (highest priority)
2. DENSIFY_LOG_LEVEL environment variable (str value: "minimal" | "full" | "none")
3. Default: "minimal"
```

The `_resolve_log_level()` helper method implements this:

```python
def _resolve_log_level(self, explicit_arg: str | None) -> str:
    if explicit_arg is not None:
        return explicit_arg
    return os.environ.get("DENSIFY_LOG_LEVEL", "minimal")
```

### 16.5 Invalid Values

An invalid `log_level` string raises `ValueError` at `__init__` time:
```
ValueError: "invalid_level" is not a valid DensifyLogLevel.
            Valid values are: minimal, full, none
```

---

## 17. Per-Algorithm Parameter Exposure (v1.1)

### 17.1 Motivation

Previously all four algorithms had fully hardcoded tuning parameters (e.g., `displacement range [0.05, 0.5]`
for NN, `k_neighbors=20` for MLS). Power users running batch jobs or custom pipelines had no way to adjust
these without modifying source code. v1.1 exposes these as optional Pydantic sub-dicts on `DensifyConfig`
and as kwargs on `Densify.__init__`.

### 17.2 Parameter Models

| Model | Algorithm | Key Parameters |
|---|---|---|
| `DensifyNNParams` | `nearest_neighbor` | `displacement_min`, `displacement_max` |
| `DensifyMLSParams` | `mls` | `k_neighbors`, `projection_radius_factor`, `min_dist_factor` |
| `DensifyStatisticalParams` | `statistical` | `k_neighbors`, `sparse_percentile`, `min_dist_factor` |
| `DensifyPoissonParams` | `poisson` | `depth`, `density_threshold_quantile` |

See `api-spec.md §1.3` for full field definitions and validation constraints.

### 17.3 Backward Compatibility

All `*_params` kwargs default to `None`. When `None`, the original hardcoded production values apply:

| Algorithm | Production defaults (when params=None) |
|---|---|
| NN | `displacement_min=0.05`, `displacement_max=0.5` × mean_nn_dist |
| MLS | `k_neighbors=20`, `projection_radius=0.5×`, `min_dist=0.05×` mean_nn_dist |
| Statistical | `k_neighbors=10`, `sparse_percentile=50`, `min_dist=0.3×` mean_nn_dist |
| Poisson | `depth=8`, `density_threshold_quantile=0.1` |

This ensures **100% backward compatibility** — all existing DAG configs and factory calls work unchanged.

### 17.4 Dict Coercion

The `_coerce_params()` helper automatically converts a plain `dict` to the typed Pydantic model:

```python
def _coerce_params(self, value, model_cls):
    if value is None:
        return None
    if isinstance(value, dict):
        return model_cls(**value)
    return value  # already a model instance
```

This means callers can pass either `nn_params={"displacement_min": 0.1}` or
`nn_params=DensifyNNParams(displacement_min=0.1)` — both work identically.

### 17.5 Log Output in `full` Mode

When `log_level="full"` and custom params are in use, the algorithm methods emit an additional `DEBUG` line:

```
Densify: [nn] using custom params: displacement=[0.1, 0.3] × mean_nn_dist
Densify: [mls] using custom params: k=15, radius=0.4× mean_nn_dist, min_dist=0.03×
Densify: [statistical] using custom params: k=15, sparse_pct=40.0, min_dist=0.2×
Densify: [poisson] using custom params: depth=9, density_q=0.05
```
