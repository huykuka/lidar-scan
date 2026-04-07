# Point Cloud Densification Module - Requirements

## Feature Overview

The **Point Cloud Densification Module** is a new pipeline operation that increases the spatial density of sparse point clouds by intelligently interpolating additional points. This addresses a critical limitation of low-layer LIDAR sensors (e.g., 16-layer units) that produce sparse vertical data, making them unsuitable for high-fidelity applications like sensor fusion, object detection, and digital twin reconstruction.

### Primary Use Case: LIDAR Layer Gap Filling

The user operates a **16-layer LIDAR sensor** that can be mounted at different rotations. The resulting point clouds have significant vertical gaps between scan layers, causing:
- Poor object boundary detection
- Inaccurate surface reconstruction
- Reduced fusion quality with other sensors (cameras, radar, etc.)
- ML model training challenges due to data sparsity

The densification module fills these gaps by generating synthetic points through interpolation, effectively **simulating a higher-resolution LIDAR** (e.g., 32-layer or 64-layer) from the original 16-layer data.

### How It Fits in the DAG

The `densify.py` operation integrates seamlessly into the existing pipeline architecture:

1. **Input**: Accepts any point cloud from upstream nodes (raw sensor data, downsampled clouds, filtered data, etc.)
2. **Processing**: Applies selected densification algorithm with configured parameters
3. **Output**: Returns densified point cloud with preserved/interpolated normals and metadata

**Key Design Principles:**
- **Pluggable**: Works at any position in the DAG pipeline
- **Algorithm-Agnostic**: Supports multiple densification methods with runtime selection
- **Real-Time First**: Defaults to fast algorithms (<100ms) with optional high-quality modes for batch processing
- **Non-Destructive**: Always preserves original point attributes (XYZ, normals)

---

## User Stories

### US1: Real-Time LIDAR Layer Simulation

**As a** robotics engineer using a 16-layer LIDAR,  
**I want to** densify point clouds to simulate a 32-layer or 64-layer sensor in real-time,  
**So that** my object detection and tracking algorithms receive higher-quality input without purchasing expensive hardware.

**Acceptance Criteria:**
- Configure densify node to target 2x density (16→32 layers) using nearest neighbor algorithm
- Processing completes in <100ms for typical frame sizes (50k-100k points)
- Densified output maintains original point positions and normals
- Metadata includes original and final point counts

---

### US2: Multi-Algorithm Selection with Guidance

**As a** data scientist preparing training datasets,  
**I want to** choose between multiple densification algorithms with clear descriptions,  
**So that** I can balance speed vs. quality based on my workflow requirements (real-time vs. batch).

**Acceptance Criteria:**
- Support at least 4 algorithms: Nearest Neighbor, Moving Least Squares (MLS), Poisson Reconstruction, Statistical Upsampling
- Each algorithm includes a description explaining:
  - **Use case** (when to use it)
  - **Speed** (real-time vs. batch)
  - **Quality** (preservation of sharp features, smoothness)
- Configuration UI/API allows runtime algorithm switching
- Default algorithm is Nearest Neighbor (fastest, real-time compatible)

---

### US3: Uniform 3D Densification for Variable LIDAR Mounting

**As a** field engineer mounting LIDAR sensors at different rotations,  
**I want to** densify point clouds uniformly in all 3D directions,  
**So that** the densification adapts to any sensor orientation without manual reconfiguration.

**Acceptance Criteria:**
- Densification is **not** limited to vertical-only interpolation
- Algorithm analyzes local point distribution and fills gaps in all directions
- Works correctly when LIDAR is tilted, rotated, or mounted at non-standard angles
- No axis-specific assumptions in the implementation
- **Implementation note (2026-04):** Enforced via `scipy.spatial.KDTree` built on the full point cloud
  for mean NN distance computation in all algorithms (`_compute_mean_nn_dist_global`).  No random-sampled
  `KDTreeFlann` or per-ring sub-sampling is used anywhere in `densify.py`.

---

### US4: Normal Vector Preservation and Interpolation

**As a** surface reconstruction developer,  
**I want to** preserve or interpolate surface normals for newly created points,  
**So that** downstream meshing and rendering operations produce correct shading and geometry.

**Acceptance Criteria:**
- Original point normals are preserved unchanged
- Newly interpolated points estimate normals from neighboring original points
- Normal estimation uses local neighborhood geometry (k-nearest neighbors)
- If input cloud lacks normals, operation continues without error (spatial XYZ only)

---

### US5: Fail-Safe Operation with Pipeline Continuity

**As a** system integrator running 24/7 production pipelines,  
**I want to** the densify module to gracefully handle errors without crashing the DAG,  
**So that** sensor failures or invalid configurations don't halt the entire system.

**Acceptance Criteria:**
- If densification algorithm fails → pass through original cloud unchanged, log error
- If input has insufficient points (<10) → skip processing, log warning
- If input density already exceeds target → skip processing, log info message
- Metadata includes operation status: `success`, `skipped`, or `error`

---

## Acceptance Criteria

### Functional Requirements

#### F1: Multiple Densification Algorithms

- [x] **Nearest Neighbor (NN)**: Fast, preserves original attributes, suitable for real-time (<100ms)
  - Description: "Interpolates points by copying attributes from the nearest original point. Best for real-time pipelines requiring <100ms latency. Preserves sharp features but may create blocky artifacts."
  
- [x] **Moving Least Squares (MLS)**: Medium quality, smooth surfaces, moderate speed
  - Description: "Fits smooth polynomial surfaces to local neighborhoods. Best for batch processing where surface smoothness is critical. Processing time: 200-500ms for typical clouds."
  
- [x] **Poisson Reconstruction**: High quality, watertight surfaces, slowest
  - Description: "Reconstructs implicit surface function and resamples. Best for mesh generation and CAD workflows. Processing time: 500ms-2s. May smooth out fine details."
  
- [x] **Statistical Upsampling**: Balances speed and quality, adaptive
  - Description: "Adds points based on local density statistics. Best for general-purpose densification with moderate speed requirements. Processing time: 100-300ms."

- [x] Default algorithm: Nearest Neighbor
- [x] Algorithm selection is runtime-configurable via `algorithm` parameter

---

#### F2: Density Target Specification

- [x] Primary mode: **Density Multiplier** (e.g., 2x, 4x, 8x)
- [x] Secondary mode: **Target Point Count** (absolute output point count)
  - Example: 10,000 input points with `target_point_count=20000` → 2x densification
  - Example: 10,000 input points with `target_point_count=80000` → 8x densification (max)
- [x] Configuration accepts `density_multiplier` (float, default: 2.0)
- [x] Configuration optionally accepts `target_point_count` (int, overrides multiplier if provided)
- [x] Minimum multiplier: 1.0 (no change)
- [x] Maximum multiplier: 8.0 (prevents excessive memory usage)

---

#### F3: Quality Preset System

- [x] Three presets: `fast`, `medium`, `high`
- [x] **Fast** (default):
  - Algorithm: Nearest Neighbor
  - Target latency: <100ms
  - Best for real-time sensor feeds
  
- [x] **Medium**:
  - Algorithm: Statistical Upsampling or MLS
  - Target latency: <300ms
  - Best for interactive applications
  
- [x] **High**:
  - Algorithm: MLS or Poisson
  - Target latency: <2s
  - Best for batch processing, dataset preparation

- [x] Preset selection is runtime-configurable via `quality_preset` parameter
- [x] Manual `algorithm` setting overrides preset if both are provided

---

#### F4: Normal Vector Handling

- [x] Original point normals are preserved unchanged
- [x] Newly interpolated points estimate normals from k-nearest neighbors (k=10 default)
- [x] Normal estimation uses original point cloud for reference (not synthetic points)
- [x] If input cloud lacks `normals` attribute → skip normal estimation, log info
- [x] Configurable via `preserve_normals` boolean (default: `true`)

---

#### F5: Error Handling and Fail-Safe Modes

- [x] **Algorithm failure** → pass through original cloud unchanged, log error, metadata: `status=error`
- [x] **Insufficient points** (count < 10) → skip processing, log warning, metadata: `status=skipped`
- [x] **Over-dense input** (current density > target) → skip processing, log info, metadata: `status=skipped`
- [x] **Missing attributes** → continue with available data (e.g., skip normals if not present)
- [x] No exceptions propagate to DAG orchestrator (all errors caught internally)

---

#### F6: Configuration Parameters

- [x] `enabled` (bool): Enable/disable toggle (default: `true`)
- [x] `algorithm` (enum): Algorithm selection (default: `"nearest_neighbor"`)
  - Valid values: `"nearest_neighbor"`, `"mls"`, `"poisson"`, `"statistical"`
- [x] `density_multiplier` (float): Density increase factor (default: `2.0`, range: `1.0-8.0`)
- [x] `target_point_count` (int, optional): Override multiplier with an absolute target point count
- [x] `quality_preset` (enum): Preset selection (default: `"fast"`)
  - Valid values: `"fast"`, `"medium"`, `"high"`
- [x] `preserve_normals` (bool): Interpolate normals for new points (default: `true`)

Example configuration:
```json
{
  "type": "densify",
  "config": {
    "enabled": true,
    "algorithm": "nearest_neighbor",
    "density_multiplier": 2.0,
    "quality_preset": "fast",
    "preserve_normals": true
  }
}
```

---

#### F7: Output Metadata

- [x] `densified_count` (int): Final point count after densification
- [x] `original_count` (int): Input point count before processing
- [x] `density_ratio` (float): Achieved density increase (densified_count / original_count)
- [x] `algorithm_used` (string): Algorithm that was applied
- [x] `processing_time_ms` (float): Execution time in milliseconds
- [x] `status` (enum): Operation status
  - Values: `"success"`, `"skipped"`, `"error"`
- [x] `skip_reason` (string, optional): Explanation if status is `"skipped"`
- [x] `error_message` (string, optional): Error details if status is `"error"`

Example output metadata:
```json
{
  "densified_count": 128000,
  "original_count": 64000,
  "density_ratio": 2.0,
  "algorithm_used": "nearest_neighbor",
  "processing_time_ms": 45.3,
  "status": "success"
}
```

---

### Non-Functional Requirements

#### NF1: Performance

- [ ] **Fast mode** processing time <100ms for 50k-100k point clouds
- [ ] **Medium mode** processing time <300ms for 50k-100k point clouds
- [ ] **High mode** processing time <2s for 50k-100k point clouds
- [ ] Heavy Open3D operations offloaded to threadpool via `await asyncio.to_thread()`
- [ ] Does not block the FastAPI async event loop
- [ ] Memory footprint: <4x input cloud size (e.g., 100k input → max 400k output → ~50MB RAM)

---

#### NF2: DAG Integration

- [x] Module file: `app/modules/pipeline/operations/densify.py`
- [x] Inherits from `PipelineOperation` base class
- [x] Implements `apply(pcd) -> (pcd, metadata)` method signature
- [x] Compatible with both legacy (`o3d.geometry.PointCloud`) and tensor (`o3d.t.geometry.PointCloud`) point cloud types
- [x] Works at any position in the DAG (accepts any upstream point cloud)
- [x] Registered via existing `app/modules/pipeline/operations/__init__.py`

---

#### NF3: Logging & Observability

- [x] Logs algorithm selection at INFO level: `"Densify: Using nearest_neighbor algorithm with 2.0x multiplier"`
- [x] Logs performance metrics at DEBUG level: `"Densify: Processed 64000→128000 points in 45.3ms"`
- [x] Logs warnings for skipped operations: `"Densify: Skipping - input already denser than target (ratio: 0.8)"`
- [x] Logs errors with full context: `"Densify: MLS algorithm failed - {error_details}. Passing through original cloud."`
- [x] All logs include node instance ID for multi-node DAG debugging

---

#### NF4: API Documentation

- [ ] Algorithm descriptions embedded in module docstrings
- [ ] Configuration parameters documented with type hints and default values
- [ ] Example configurations provided in module header comments
- [ ] Integration with existing Swagger API docs (if exposed via REST endpoints)

---

## Out of Scope

### Explicitly NOT Included in This Feature

- **Attribute Interpolation Beyond Normals**: Color (RGB), intensity, and custom attributes are **not** interpolated. Only XYZ positions and normals.
- **Adaptive/Automatic Density Selection**: The system does **not** analyze input geometry to auto-select optimal density. User must specify target.
- **Region-of-Interest (ROI) Densification**: No spatial masking or bounding box selection. Entire input cloud is processed uniformly.
- **Conditional/Masked Densification**: No per-point filtering (e.g., "densify only ground points"). All points contribute equally.
- **Mesh Generation**: This module produces point clouds, not triangle meshes. Poisson reconstruction generates intermediate meshes but resamples back to points.
- **Sharp Feature Preservation Tuning**: No advanced edge-detection or crease-angle parameters. Feature preservation is algorithm-dependent.
- **Custom Algorithm Plugins**: Only the 4 specified algorithms are supported. No user-defined densification functions.
- **Downsampling Logic**: This module only increases density. For decreasing density, use existing `downsample.py` module.
- **Persistent Quality Metrics**: No comparison against ground-truth high-resolution scans. Quality assessment is user-subjective.

---

## Success Metrics

- [ ] Densify module successfully processes 16-layer LIDAR data to 2x density in <100ms (fast mode)
- [x] Algorithm switching validated across all 4 methods in automated tests
- [x] Integration test: Densify → Downsample → Compare produces geometrically consistent results
- [x] Zero DAG crashes due to densification errors in 1000-frame stress test
- [x] Normal interpolation produces visually plausible results in rendering tests
- [ ] Documentation includes algorithm selection flowchart and use case recommendations

---

## Dependencies & Prerequisites

- **Backend**: Python 3.10+, FastAPI, Open3D 0.17+
- **DAG Framework**: Existing `PipelineOperation` base class in `app/modules/pipeline/base.py`
- **Concurrency**: `asyncio.to_thread()` for Open3D threadpool offloading
- **Point Cloud Types**: Support for both `o3d.geometry.PointCloud` and `o3d.t.geometry.PointCloud`
- **Open3D Algorithms**:
  - Nearest neighbor search: `o3d.geometry.KDTreeFlann`
  - MLS: May require custom implementation or third-party library
  - Poisson: `o3d.geometry.TriangleMesh.create_from_point_cloud_poisson()`
  - Statistical upsampling: Custom implementation based on local density estimation

---

## Open Questions for Architecture Review

1. **Q:** Should class structure be single `Densify` class with algorithm parameter, or separate classes (`DensifyNN`, `DensifyMLS`, etc.)?  
   **A:** Deferred to Architect (@architecture)

2. **Q:** MLS implementation strategy - use Open3D's surface reconstruction or custom scipy-based approach?  
   **A:** Deferred to Architect (@architecture)

3. **Q:** Should Poisson reconstruction preserve original points or fully resample?  
   **A:** Deferred to Architect (@architecture)

4. **Q:** Normal estimation parameters (k-neighbors, search radius) - user-configurable or hardcoded defaults?  
   **A:** Deferred to Architect (@architecture)

5. **Q:** Memory management for large clouds (>1M points) - streaming/chunking needed?  
   **A:** Deferred to Architect (@architecture)

---

## Next Steps for Architecture & Planning

1. **@architecture**: Design class structure (`Densify` unified vs. per-algorithm classes) in `technical.md`
2. **@architecture**: Specify Open3D API usage for each algorithm (MLS approach, Poisson resampling strategy)
3. **@architecture**: Define normal estimation parameters and memory optimization strategies
4. **@architecture**: Document threading model (which operations run on threadpool vs. async loop)
5. **@architecture**: Create API contract in `api-spec.md` (configuration schema, metadata format)
6. **@be-dev**: Review `backend-tasks.md` for implementation breakdown
7. **@qa**: Define test scenarios in `qa-tasks.md` (algorithm accuracy, performance benchmarks, error cases)

---

**Document Status:** ✅ READY FOR ARCHITECTURE REVIEW  
**Next Phase:** Architecture to produce `technical.md` and `api-spec.md`
