# Feature: Environment Filtering (Floor/Ceiling Removal)

## Feature Overview

Add a new semi-automatic application node called `EnvironmentFiltering` that removes floor and ceiling planes from real-time indoor LiDAR scans, producing a filtered point cloud containing only objects of interest (walls, furniture, obstacles). This node leverages the existing `patch_plane_segmentation` operation to detect multiple planar patches, validates them as floor/ceiling candidates using multi-criteria checks (orientation, position, size), and removes matching points from the input cloud.

**Key Capabilities**:
- **Voxel Downsampling Pre-Processing**: Configurable downsampling step BEFORE plane segmentation for handling dense point clouds efficiently (100k+ points)
- Real-time performance optimized for indoor scanning workflows (low-latency, <100ms overhead target)
- User-controlled filtering via advanced parameter exposure (all patch_plane_segmentation parameters + downsampling)
- Multi-criteria validation: orientation tolerance, vertical position thresholds, minimum plane size
- Graceful error handling: flags node status if no planes detected, never crashes the pipeline
- Extensible design: supports future plane types (walls, tables, etc.) via modular validation logic
- Pipeline integration: full DAG application node with WebSocket streaming and config persistence

**Use Case**: Real-time indoor scanning where operators want to focus on room contents (furniture, boxes, equipment) without cluttering visualizations with floor/ceiling data.

## User Stories

### As a warehouse operator:
- I want to scan a storage room and see only shelves, pallets, and boxes (not floor/ceiling), so I can quickly identify inventory and obstacles without visual noise
- I want the filtering to work in real-time as I move through the space, so I can make immediate decisions during scanning
- I want the system to handle extremely dense point clouds (100k+ points) without lag, so high-resolution scans don't slow down my workflow

### As a robotics engineer:
- I want to remove floor/ceiling planes before feeding data to navigation algorithms, so my robot focuses on collision-relevant obstacles
- I want to tune the plane detection sensitivity (normal variance, coplanarity) to handle uneven floors (warehouse with pallet debris, sloped ramps) without over-filtering
- I want control over the speed vs. precision tradeoff when processing dense scans, so I can optimize for real-time performance on resource-constrained platforms

### As a facility inspector:
- I want to isolate wall-mounted equipment and fixtures by removing horizontal surfaces, so I can measure clearances and detect obstructions
- I want the system to flag when no floor/ceiling is detected (e.g., scanning outdoors by mistake), so I know the data may be incomplete

### As a data scientist:
- I want to export filtered point clouds with consistent floor removal across multiple scans, so my downstream analysis (object detection, segmentation) gets clean training data
- I want to adjust the vertical position threshold to handle mezzanines, raised platforms, or drop ceilings without losing valid structural data
- I want the option to reduce point cloud density before filtering to speed up batch processing of large datasets, trading precision for throughput

### As a backend developer:
- I want the filtering node to integrate seamlessly into existing DAG pipelines, so I can chain it with downsampling, outlier removal, and visualization nodes
- I want clear parameter validation and error messages when configurations are invalid (e.g., nonsensical threshold values)

## Acceptance Criteria

### Functional Requirements

#### Input Handling
- [ ] **Point Cloud Input**: Accept `o3d.t.geometry.PointCloud` (tensor-based) from upstream DAG nodes
- [ ] **Validation**: Reject invalid inputs (empty point clouds, missing normals if required by segmentation)
- [ ] **Pass-Through on Empty**: If input has < `min_num_points`, pass through original cloud unchanged and flag warning status

#### Voxel Downsampling (Pre-Processing)
- [ ] **Downsampling Execution**: Apply voxel downsampling to input cloud BEFORE plane segmentation if `voxel_downsample_size > 0`
- [ ] **Parameter**: `voxel_downsample_size` (float, default=0.01, min=0.0, max=1.0, units: meters)
  - Defines the voxel grid cell size for downsampling
  - Default 0.01m (1cm) provides good balance between speed and floor/ceiling detection accuracy for typical indoor scans
  - Set to 0 to disable downsampling (advanced users only, for high-precision requirements)
- [ ] **Downsampling Method**: Use Open3D's `voxel_down_sample()` operation
- [ ] **Performance Impact**: Downsampling MUST complete in < 20ms for 100k points with default voxel size
- [ ] **Quality Preservation**: Downsampled cloud MUST retain sufficient point density for reliable plane detection (minimum 1000 points per plane)
- [ ] **Attribute Handling**: Downsampled cloud preserves point attributes (colors, normals) via averaging within each voxel
- [ ] **Disabled Behavior**: When `voxel_downsample_size = 0`, skip downsampling entirely and pass full-resolution cloud to segmentation
- [ ] **Metadata Tracking**: Record downsampling statistics in output metadata:
  ```python
  {
      "downsampling_enabled": bool,
      "voxel_size": float,           # 0 if disabled
      "points_before_downsample": int,
      "points_after_downsample": int
  }
  ```

#### Plane Detection & Validation
- [ ] **Detection**: Use `patch_plane_segmentation` operation internally to detect multiple planar patches from downsampled cloud (if enabled) OR original input
- [ ] **Orientation Validation**: For each detected plane, check if normal vector is approximately vertical (up/down)
  - Parameter: `vertical_tolerance_deg` (float, default=15.0, range 1-45°)
  - Logic: Plane normal must be within tolerance of [0, 0, ±1] (Z-axis in world frame)
  - Edge case: Handle any orientation (floor/ceiling may not align with Z-axis in tilted scanner frames)
- [ ] **Position Validation**: Check if plane is at expected floor or ceiling height
  - Parameter: `floor_height_range` (tuple[float, float], default=[-0.5, 0.5] meters) - min/max Z of plane centroid for floor detection
  - Parameter: `ceiling_height_range` (tuple[float, float], default=[2.0, 4.0] meters) - min/max Z of plane centroid for ceiling detection
  - Logic: Plane centroid Z-coordinate must fall within specified range
- [ ] **Size Validation**: Reject planes that are too small to be room surfaces
  - Parameter: `min_plane_area` (float, default=1.0 square meters) - minimum plane area to consider as floor/ceiling
  - Logic: Compute plane area from convex hull of segmented points, reject if below threshold
- [ ] **Multi-Criteria AND Logic**: A plane is classified as floor/ceiling ONLY if ALL three validations pass (orientation + position + size)

#### Filtering & Output
- [ ] **Point Removal**: Remove all points belonging to validated floor/ceiling planes from ORIGINAL input cloud (NOT downsampled cloud)
  - Critical: Plane indices from downsampled segmentation MUST be mapped back to original cloud indices
  - Implementation: Use boolean indexing on point cloud indices (do NOT modify original cloud)
  - Preserve point attributes (colors, normals, intensities) for remaining points
- [ ] **Primary Output**: `o3d.t.geometry.PointCloud` containing only non-floor/ceiling points at ORIGINAL resolution
- [ ] **Metadata Dictionary** (second return value):
  ```python
  {
      "input_point_count": int,       # Original cloud size (before downsampling)
      "output_point_count": int,      # Filtered cloud size (at original resolution)
      "removed_point_count": int,     # Points removed
      "downsampling_enabled": bool,   # Whether voxel downsampling was applied
      "voxel_size": float,            # Voxel size used (0 if disabled)
      "points_before_downsample": int,
      "points_after_downsample": int,
      "planes_detected": int,         # Total planes found by segmentation
      "planes_filtered": int,         # Planes classified as floor/ceiling
      "plane_details": [              # Per-plane metadata
          {
              "plane_id": int,
              "plane_type": "floor" | "ceiling",
              "normal": [float, float, float],
              "centroid_z": float,
              "area": float,
              "point_count": int
          }
      ],
      "status": "success" | "no_planes_detected" | "warning_pass_through"
  }
  ```

#### User-Exposed Parameters (from patch_plane_segmentation)
All parameters from `patch_plane_segmentation/registry.py` MUST be exposed to users for advanced tuning:

- [ ] **throttle_ms** (int, default=0, min=0): Minimum time between processing frames (0 = no limit)
- [ ] **normal_variance_threshold_deg** (float, default=60.0, range 1-90°): Max spread of point normals vs plane normal. Smaller = fewer, higher quality planes
- [ ] **coplanarity_deg** (float, default=75.0, range 1-90°): Max spread of point-to-plane distances. Larger = tighter fit
- [ ] **outlier_ratio** (float, default=0.75, range 0-1): Max fraction of outliers before rejecting a plane
- [ ] **min_plane_edge_length** (float, default=0.0 meters, min=0): Min largest-edge for a patch. 0 = 1% of cloud dimension
- [ ] **min_num_points** (int, default=0, min=0): Min points for plane fitting. 0 = 0.1% of total points
- [ ] **knn** (int, default=30, range 5-100): Nearest neighbors for growing/merging. Larger = better quality, slower

Additional environment-filtering-specific parameters:

- [ ] **voxel_downsample_size** (float, default=0.01, min=0.0, max=1.0, units: meters): Voxel grid size for downsampling BEFORE plane segmentation
  - **0**: Disables downsampling (advanced users only - use for high-precision requirements)
  - **0.005-0.01m** (5-10mm): Recommended for dense indoor scans (100k+ points)
  - **0.02-0.05m** (2-5cm): Fast processing for real-time visualization (trade precision for speed)
  - **>0.1m**: Not recommended (degrades plane detection quality)
  - **Help Text**: "Reduce point cloud density before plane detection. Smaller = higher precision but slower. Set to 0 to disable (advanced users only)."
- [ ] **vertical_tolerance_deg** (float, default=15.0, range 1-45°): Orientation tolerance for floor/ceiling detection
- [ ] **floor_height_range** (tuple[float, float], default=[-0.5, 0.5]): Min/max Z for floor centroid (meters)
- [ ] **ceiling_height_range** (tuple[float, float], default=[2.0, 4.0]): Min/max Z for ceiling centroid (meters)
- [ ] **min_plane_area** (float, default=1.0, min=0.1): Minimum plane area (square meters) to consider as floor/ceiling

### Error Handling & Edge Cases
- [ ] **No Planes Detected**: If `patch_plane_segmentation` finds 0 planes:
  - Return original input cloud unchanged (at full resolution, NOT downsampled)
  - Set metadata status to `"no_planes_detected"`
  - Flag node status in DAG as WARNING (not ERROR - pipeline continues)
  - Log info-level message: "No planar surfaces detected, passing through original cloud"
- [ ] **No Valid Floor/Ceiling**: If planes are detected but none pass validation:
  - Return original input cloud unchanged (at full resolution, NOT downsampled)
  - Set metadata status to `"warning_pass_through"`
  - Flag node status as WARNING
  - Log info-level message: "Detected N planes, but none matched floor/ceiling criteria"
- [ ] **Downsampling Too Aggressive**: If `voxel_downsample_size` reduces cloud to < 100 points:
  - Log warning: "Voxel size {voxel_downsample_size}m too large - downsampling reduced cloud to {point_count} points. Consider reducing voxel_downsample_size."
  - Proceed with downsampled cloud (don't fail - user may intentionally want coarse filtering)
  - Set metadata status to `"warning_low_point_density"`
- [ ] **Invalid Parameters**:
  - If `voxel_downsample_size` < 0 or > 1.0, raise ValueError with message "voxel_downsample_size must be between 0.0 and 1.0 meters"
  - If `vertical_tolerance_deg` < 1 or > 45, raise ValueError with message "vertical_tolerance_deg must be between 1 and 45 degrees"
  - If `min_plane_area` < 0.1, raise ValueError with message "min_plane_area must be >= 0.1 square meters"
  - If `floor_height_range` max <= min, raise ValueError with message "floor_height_range must have max > min"
  - Same for `ceiling_height_range`
- [ ] **Empty Input Cloud**: If input point cloud has 0 points:
  - Return empty cloud
  - Set metadata status to `"warning_pass_through"`
  - Flag node status as WARNING
  - Log warning: "Received empty point cloud, skipping filtering"
- [ ] **Malformed Input**: If input lacks required geometry (e.g., points attribute):
  - Raise TypeError with message "Input must be o3d.t.geometry.PointCloud with valid points"
  - Node status set to ERROR (this is a pipeline configuration issue, not a data issue)

### Performance Requirements
- [ ] **Real-Time Target**: Total processing time MUST be < 100ms for typical indoor scan (50k points, default parameters)
- [ ] **Downsampling Overhead**: Voxel downsampling step MUST complete in < 20ms for 100k points with default voxel size (0.01m)
- [ ] **Performance Benefit**: For dense scans (100k+ points):
  - WITH downsampling (0.01m voxel): Total time < 150ms
  - WITHOUT downsampling: Total time may exceed 300ms
  - Net speedup: 2-3x for plane segmentation step
- [ ] **Async Execution**: Plane segmentation and validation logic MUST run on threadpool via `await asyncio.to_thread()` to prevent blocking FastAPI event loop
- [ ] **Benchmark Targets**:
  - Small scan (10k points, no downsampling): < 50ms end-to-end
  - Medium scan (50k points, no downsampling): < 100ms end-to-end
  - Large scan (200k points, WITH 0.01m downsampling): < 200ms end-to-end
  - Large scan (200k points, WITHOUT downsampling): < 400ms end-to-end (acceptable for offline processing)
- [ ] **Low Latency**: Throttle parameter (`throttle_ms`) MUST be respected to prevent backpressure in high-frequency streaming (e.g., 30Hz LiDAR)
- [ ] **Memory Efficiency**: Filtered cloud MUST NOT create unnecessary copies (use index-based slicing, not full cloud duplication)
- [ ] **Downsampling Memory**: Downsampled temporary cloud memory MUST be released immediately after segmentation (no persistent cache)

### Integration Requirements
- [x] **Application Node**: Implement as DAG application node (NOT a bare operation) in `app/modules/pipeline/nodes/environment_filtering/`
- [x] **Node Type**: Register as `type="environment_filtering"` in node schema registry
- [x] **WebSocket Enabled**: Set `websocket_enabled=True` in node definition for real-time streaming support
- [x] **Config Persistence**: All user-exposed parameters MUST be stored in backend DAG node config (persisted across sessions)
- [x] **Node Factory**: Implement builder function in `app/modules/pipeline/nodes/environment_filtering/registry.py` following existing patterns (see `patch_plane_segmentation/registry.py`)
- [x] **Schema Definition**: Define `NodeDefinition` with all parameters exposed via `PropertySchema` objects
  - Each parameter MUST have: name, label, type, default, min/max (where applicable), help_text
  - Group parameters logically: "Plane Detection" (segmentation params), "Validation" (orientation/position/size), "Performance" (throttle)
- [x] **Ports**: Define standard DAG ports:
  - Input port: `id="in"`, `label="Input Point Cloud"`
  - Output port: `id="out"`, `label="Filtered Point Cloud"`
- [x] **Status Reporting**: Node MUST report status via DAG status API:
  - `"running"`: Processing active
  - `"success"`: Filtered N points, found M floor/ceiling planes
  - `"warning"`: No planes detected or no valid planes (see Error Handling section)
  - `"error"`: Invalid parameters or malformed input

### Validation & Testing
- [ ] **Unit Tests** (in `tests/modules/pipeline/nodes/test_environment_filtering.py`):
  - Test plane detection with synthetic horizontal planes (floor at Z=0, ceiling at Z=3)
  - Test orientation validation edge cases (tilted planes at 10°, 20°, 30° angles)
  - Test position validation with planes at various heights
  - Test size validation with small/large planes
  - Test multi-criteria logic (plane passes 2/3 criteria but not all 3)
  - Test parameter validation (invalid ranges, negative values)
  - Test empty input, no planes detected, no valid planes scenarios
  - Test point attribute preservation (colors, normals, intensities)
  - **Downsampling Tests**:
    - Test voxel_downsample_size = 0 (disabled) → full-resolution processing
    - Test voxel_downsample_size = 0.01 (default) → verify point reduction and plane detection accuracy
    - Test voxel_downsample_size = 0.05 (aggressive) → verify handling of low point density
    - Test voxel_downsample_size > 1.0 (invalid) → verify parameter validation error
    - Test downsampled plane indices correctly map back to original cloud
    - Test filtered output is at original resolution (not downsampled)
    - Test metadata includes correct downsampling statistics
- [ ] **Integration Tests**:
  - Chain `Downsampling` → `EnvironmentFiltering` → `Visualization` in DAG
  - Test WebSocket streaming with high-frequency point cloud updates (10Hz, 30Hz)
  - Test config persistence: save DAG with custom parameters, reload, verify parameters match
  - Test node status reporting: verify WARNING status appears in DAG UI when no planes detected
  - **Downsampling Integration**:
    - Test end-to-end latency with dense clouds (100k+ points) WITH and WITHOUT downsampling
    - Verify downsampling metadata appears in WebSocket stream
- [ ] **Performance Tests**:
  - Benchmark with real indoor scan data (10k, 50k, 200k points)
  - Verify <100ms target for 50k points with default parameters
  - Measure throttle_ms effectiveness: verify frames are skipped correctly at 10ms, 50ms, 100ms intervals
  - **Downsampling Performance**:
    - Benchmark downsampling overhead: measure voxel_down_sample() time for 100k, 200k points
    - Verify 2-3x speedup for plane segmentation with 0.01m downsampling on 100k+ point clouds
    - Measure total latency reduction: compare full pipeline time WITH vs WITHOUT downsampling
- [ ] **Edge Cases**:
  - Scan with no floor/ceiling (outdoor scene by mistake) → verify pass-through behavior
  - Scan with sloped floor (ramp, stairs) → verify orientation tolerance works
  - Scan with mezzanine (intermediate floor at Z=1.5m) → verify position ranges handle multiple horizontal surfaces
  - Scan with ceiling at unusual height (10m warehouse) → verify ceiling_height_range is adjustable
  - **Downsampling Edge Cases**:
    - Dense scan (200k points) with voxel_downsample_size = 0 → verify no memory overflow
    - Sparse scan (5k points) with voxel_downsample_size = 0.05 → verify warning for low point density
    - Extremely dense scan (500k+ points) → verify downsampling prevents timeout

### Documentation Requirements
- [ ] **Parameter Help Text**: Each `PropertySchema` MUST include clear, concise `help_text` explaining:
  - What the parameter controls
  - Recommended default for typical use cases
  - Effect of increasing/decreasing the value
  - **voxel_downsample_size-specific help text**: "Reduce point cloud density before plane detection to improve performance on dense scans (100k+ points). Smaller values = higher precision but slower processing. Recommended: 0.01m (1cm) for indoor scans. Set to 0 to disable downsampling (advanced users only)."
- [ ] **Node Description**: `NodeDefinition.description` MUST explain:
  - What the node does (removes floor/ceiling from indoor scans)
  - Primary use case (real-time scanning for object isolation)
  - When to use it vs. manual segmentation
  - **Downsampling behavior**: "For dense point clouds (>50k points), automatic voxel downsampling improves performance while maintaining filtering accuracy. Output is always at original resolution."
- [ ] **Error Messages**: All error/warning messages MUST be actionable:
  - Example: "No planes detected. Try reducing normal_variance_threshold_deg or min_plane_area if your scan has noisy or sparse floor/ceiling data."
  - **Downsampling warning**: "Voxel size {size}m reduced cloud to {count} points. Consider decreasing voxel_downsample_size for better plane detection quality."
- [ ] **Example Config**: Include example DAG JSON snippet in `technical.md` showing typical parameter values for:
  - Smooth concrete floor (tight tolerances)
  - Uneven warehouse floor with debris (loose tolerances)
  - High-ceiling space (adjusted height ranges)
  - **Dense scan optimization** (100k+ points with downsampling enabled)
  - **High-precision mode** (downsampling disabled for critical measurements)
- [ ] **Performance Tradeoff Documentation**: Explain speed vs. precision tradeoff in `technical.md`:
  - When to enable downsampling (dense scans, real-time visualization)
  - When to disable downsampling (high-precision measurements, sparse scans)
  - Impact on latency and filtering accuracy (quantitative benchmarks)

## Out of Scope

### Not Included in This Feature
- **Wall Detection/Removal**: This feature ONLY handles horizontal surfaces (floor/ceiling). Vertical plane filtering (walls) is a future enhancement
- **Table/Desk Detection**: No semantic classification beyond floor/ceiling. Object-level segmentation (furniture) is out of scope
- **Manual Plane Selection**: Users CANNOT manually select which planes to remove via UI. All filtering is automatic based on validation criteria
- **Plane Model Export**: Generated plane models (coefficients, boundaries) are NOT exported or saved. Only point cloud filtering is performed
- **Frontend Visualization of Planes**: No UI overlay showing detected planes. Visualization is limited to filtered point cloud output
- **Adaptive Height Estimation**: No automatic estimation of floor/ceiling heights from scene context. Users MUST configure height ranges manually
- **Multi-Room Handling**: If scanning multiple rooms with different floor heights (e.g., split-level home), single height range applies globally. Room-specific filtering is out of scope
- **Orientation Auto-Calibration**: No automatic detection of scanner tilt or gravity vector. Users MUST ensure scanner is approximately level OR adjust `vertical_tolerance_deg`
- **Mesh Generation**: Detected planes are NOT converted to meshes. This node outputs filtered point clouds only (use separate `GeneratePlane` node for mesh generation)
- **Color-Based Filtering**: No use of point colors/intensities for floor/ceiling detection. Validation is purely geometry-based
- **Temporal Filtering**: No frame-to-frame consistency checks (e.g., tracking same floor across multiple scans). Each frame is processed independently
- **Adaptive Downsampling**: Voxel size is fixed per configuration. No automatic adjustment based on input cloud density or performance targets. Users MUST manually tune `voxel_downsample_size`
- **Downsampled Output Option**: Output is ALWAYS at original resolution. No option to output downsampled cloud (use separate Downsampling node if needed)

### Explicitly Out of Scope (Architectural Boundaries)
- **Frontend Parameter UI**: Parameter tuning is backend-only via DAG JSON config. A dedicated frontend control panel for environment filtering is a separate feature
- **Real-Time Parameter Adjustment**: Changing parameters requires DAG reinitialization (full pipeline reload). Live parameter tweaking during scanning is not supported
- **Undo/History**: No undo mechanism for filtered data. If filtering is too aggressive, users must adjust parameters and re-scan
- **Export Integration**: Exporting filtered point clouds to file formats (PCD, PLY, LAS) is handled by existing output nodes, not this node

## Technical Constraints

### Pipeline Architecture
- **Node Type**: Application node (not a bare operation) - wraps `patch_plane_segmentation` operation + voxel downsampling + validation logic
- **Stateless Execution**: No internal state between node executions (pure function per frame)
- **No Direct Orchestrator Coupling**: Node MUST NOT import or reference the DAG orchestrator directly
- **Operation Reuse**: MUST use existing `patch_plane_segmentation` operation via standard operation invocation (do NOT duplicate segmentation code)
- **Downsampling Integration**: Use Open3D's built-in `voxel_down_sample()` method (do NOT implement custom voxel grid logic)

### Performance
- **Threadpool Execution**: Heavy computation (voxel downsampling, plane segmentation, area calculation) MUST run in `asyncio.to_thread()` to avoid blocking event loop
- **Memory Limits**: Filtered cloud MUST NOT exceed 2x the input cloud memory footprint (avoid temporary copies)
- **Downsampling Memory**: Downsampled cloud is temporary and MUST be garbage collected immediately after segmentation
- **WebSocket Efficiency**: When `websocket_enabled=True`, filtered cloud MUST be serialized efficiently (use binary format, not JSON, per LIDR protocol)

### Data Integrity
- **Point Attribute Preservation**: Filtered cloud MUST preserve all point attributes from ORIGINAL input (positions, colors, normals, intensities)
- **Index Consistency**: If input cloud has explicit point indices, filtered cloud indices MUST remain valid (no renumbering)
- **Coordinate Frame**: Filtering logic assumes input is in scanner/world frame with Z-axis as "up" direction. No coordinate transforms are applied
- **Downsampling Index Mapping**: Plane indices from downsampled segmentation MUST be accurately mapped back to original cloud indices for filtering

### Extensibility Design
- **Modular Validation**: Plane validation logic SHOULD be structured to easily add new plane types (walls, tables) in future:
  - Suggest: `_validate_floor_ceiling()`, `_validate_walls()` as separate methods
  - Validation criteria should be configurable per plane type
- **Pluggable Segmentation**: If future versions support alternative segmentation algorithms (region growing, clustering), switching should require minimal code changes
  - Suggest: Abstract segmentation call behind interface: `_detect_planes(cloud, params) -> List[Plane]`
- **Configurable Pre-Processing**: Downsampling step SHOULD be structured to support alternative pre-processing methods (statistical outlier removal, radius filtering) in future

### Open3D Compatibility
- **Primary API**: Use Tensor-based API (`o3d.t.geometry.PointCloud`) for consistency with modern pipeline
- **Legacy Fallback**: If input is legacy `o3d.geometry.PointCloud`, convert to tensor, process, and return legacy format (maintain type compatibility)
- **Version Compatibility**: Target Open3D >= 0.13.0 (tensor API stable)

### Error Recovery
- **Graceful Degradation**: NEVER crash the pipeline. If filtering fails (exception in segmentation), return original cloud + ERROR status
- **Logging**: All warnings/errors MUST be logged with context (frame number, parameter values, point count) for debugging
- **Status Propagation**: Node status MUST be queryable via DAG status API for frontend display

## Dependencies

### Existing Systems
- **PipelineOperation**: `app/modules/pipeline/base.py` - Base class for operations (if wrapping segmentation as operation)
- **OperationNode**: `app/modules/pipeline/operation_node.py` - Base class for application nodes wrapping operations
- **patch_plane_segmentation**: `app/modules/pipeline/operations/patch_plane_segmentation/` - Segmentation operation to reuse
- **NodeFactory**: `app/services/nodes/node_factory.py` - Node registration system
- **NodeDefinition Schema**: `app/services/nodes/schema.py` - Schema for node registration (PropertySchema, PortSchema)

### External Libraries
- **Open3D**: Already installed, used for PointCloud manipulation and geometry operations
- **NumPy**: Already installed, used for plane normal vector math, centroid calculation, area computation
- **Asyncio**: Python standard library, used for threadpool execution

### Backend Rules
- Follow type hinting rules from `.opencode/rules/backend.md`
- Follow DAG node patterns from existing nodes (e.g., `app/modules/pipeline/nodes/*/`)
- Follow WebSocket streaming protocol from `.opencode/rules/protocols.md` (LIDR binary format)

## Success Metrics

### Quantitative
- [ ] 100% of unit tests pass (minimum 20 test cases covering detection, validation, error handling, downsampling)
- [ ] Integration test: Full pipeline with EnvironmentFiltering node completes in < 200ms for 50k point scan
- [ ] Performance: 95th percentile latency < 100ms for 50k points with default parameters (measured over 100 frames)
- [ ] **Downsampling Performance**: For 100k point scans with 0.01m voxel size:
  - Downsampling step < 20ms
  - Total pipeline time < 150ms (vs >300ms without downsampling)
  - Net speedup: 2-3x for plane segmentation
- [ ] Real-time capable: Sustains 10Hz throughput (100ms per frame) without dropped frames or backpressure warnings
- [ ] Memory efficiency: Peak memory usage < 1.5x input cloud size during filtering (including temporary downsampled cloud)

### Qualitative
- [ ] Backend developers can add `EnvironmentFiltering` node to DAG JSON configs using only parameter `help_text` (no documentation lookup needed)
- [ ] Users can tune parameters via JSON config and immediately see effect in filtered output (no "magic" behavior)
- [ ] Error messages are clear and actionable: Users understand WHY filtering failed and HOW to fix it
- [ ] Code follows existing node patterns: New developers can understand implementation by comparing to `patch_plane_segmentation` node
- [ ] Extensibility validated: Architecture review confirms adding wall filtering would require < 50 lines of new code
- [ ] **Downsampling Clarity**: Users understand the speed vs. precision tradeoff from parameter help text and example configs
- [ ] **Performance Predictability**: Benchmarks clearly demonstrate when to enable/disable downsampling based on point cloud density

## Open Questions

### To Be Decided During Architecture Phase
- **Plane Area Calculation**: Use convex hull area (fast but overestimates for irregular shapes) OR actual segmented point extent (slower but accurate)?
- **Multi-Floor Handling**: Should node support detecting BOTH floor AND ceiling in single pass (current design assumes yes), or separate passes for each?
- **Coordinate Frame Assumption**: Should node validate that Z-axis is "up" (via gravity check), or trust user configuration?
- **WebSocket Metadata**: Should plane_details metadata be streamed via WebSocket (for frontend visualization), or only returned in operation output?
- **Downsampling Index Mapping Strategy**: Use nearest-neighbor search to map plane indices from downsampled cloud back to original cloud, OR use voxel grid inverse mapping (faster but requires storing voxel metadata)?
- **Downsampling Point Attribute Averaging**: For downsampled cloud, average point attributes (colors, normals) within each voxel, OR use centroid point attributes only?

### Deferred to Technical Specification
- Exact algorithm for plane area calculation (convex hull vs bounding box vs OBB)
- Whether to use Open3D's built-in plane model extraction or custom fitting
- Thread pool sizing for async execution (fixed pool vs dynamic)
- Validation order optimization (check size first to short-circuit expensive orientation checks?)
- Downsampling index mapping implementation (nearest-neighbor vs voxel grid inverse)
- Memory management strategy for temporary downsampled cloud (explicit cleanup vs garbage collection)
- Optimal voxel size calculation heuristics (if adaptive downsampling is added in future)

## Example Usage

### Example 1: Default Configuration (Typical Indoor Room)
```json
{
  "node_id": "env_filter_1",
  "type": "environment_filtering",
  "name": "Remove Floor/Ceiling",
  "config": {
    "voxel_downsample_size": 0.01,
    "throttle_ms": 0,
    "normal_variance_threshold_deg": 60.0,
    "coplanarity_deg": 75.0,
    "outlier_ratio": 0.75,
    "min_plane_edge_length": 0.0,
    "min_num_points": 0,
    "knn": 30,
    "vertical_tolerance_deg": 15.0,
    "floor_height_range": [-0.5, 0.5],
    "ceiling_height_range": [2.0, 4.0],
    "min_plane_area": 1.0
  }
}
```

**Expected Behavior**: 
- Downsample 50k point scan to ~25k points with 1cm voxel grid
- Detects floor at ~Z=0 and ceiling at ~Z=3m from downsampled cloud
- Removes both planes from ORIGINAL full-resolution cloud
- Returns filtered cloud with furniture, walls, equipment at original resolution

**Expected Metadata**:
```json
{
  "input_point_count": 50000,
  "output_point_count": 35000,
  "removed_point_count": 15000,
  "downsampling_enabled": true,
  "voxel_size": 0.01,
  "points_before_downsample": 50000,
  "points_after_downsample": 25000,
  "planes_detected": 3,
  "planes_filtered": 2,
  "plane_details": [
    {
      "plane_id": 0,
      "plane_type": "floor",
      "normal": [0.02, -0.01, 0.999],
      "centroid_z": 0.05,
      "area": 25.3,
      "point_count": 8000
    },
    {
      "plane_id": 1,
      "plane_type": "ceiling",
      "normal": [0.01, 0.03, -0.998],
      "centroid_z": 2.85,
      "area": 24.8,
      "point_count": 7000
    }
  ],
  "status": "success"
}
```

### Example 2: Warehouse with Uneven Floor (Adjusted Tolerances)
```json
{
  "node_id": "env_filter_warehouse",
  "type": "environment_filtering",
  "name": "Warehouse Floor Filter",
  "config": {
    "voxel_downsample_size": 0.02,
    "normal_variance_threshold_deg": 70.0,
    "coplanarity_deg": 65.0,
    "outlier_ratio": 0.85,
    "vertical_tolerance_deg": 25.0,
    "floor_height_range": [-0.8, 0.8],
    "ceiling_height_range": [8.0, 12.0],
    "min_plane_area": 5.0
  }
}
```

**Rationale**:
- Larger `voxel_downsample_size` (2cm): Faster processing for large warehouse scans, acceptable loss of precision
- Higher `normal_variance_threshold_deg` and `outlier_ratio`: Tolerates debris, pallet edges on floor
- Larger `vertical_tolerance_deg`: Handles sloped sections, loading docks
- Expanded `floor_height_range`: Accounts for forklift ramps, drainage slopes
- Higher `ceiling_height_range`: Typical warehouse ceiling height
- Larger `min_plane_area`: Filters out small horizontal surfaces (shelves, table tops)

### Example 3: Error Case - Outdoor Scan (No Planes Detected)
**Input**: Point cloud of outdoor parking lot (no large horizontal surfaces)

**Output Metadata**:
```json
{
  "input_point_count": 30000,
  "output_point_count": 30000,
  "removed_point_count": 0,
  "downsampling_enabled": true,
  "voxel_size": 0.01,
  "points_before_downsample": 30000,
  "points_after_downsample": 15000,
  "planes_detected": 0,
  "planes_filtered": 0,
  "plane_details": [],
  "status": "no_planes_detected"
}
```

**Node Status**: WARNING
**Log Message**: "No planar surfaces detected, passing through original cloud"
**Note**: Original full-resolution cloud is returned (not downsampled)

### Example 4: High-Frequency Streaming (30Hz LiDAR)
```json
{
  "node_id": "env_filter_realtime",
  "type": "environment_filtering",
  "name": "Real-Time Filter",
  "config": {
    "voxel_downsample_size": 0.01,
    "throttle_ms": 50,
    "knn": 20,
    "min_plane_area": 2.0
  }
}
```

**Behavior**:
- Processes max 20 frames/second (1 frame per 50ms minimum)
- Skips intermediate frames if processing takes longer than throttle interval
- Downsampling enabled for performance (1cm voxel)
- Lower `knn` for faster segmentation
- Higher `min_plane_area` to reduce false positives on small surfaces

### Example 5: High-Precision Mode (Dense Scans, No Downsampling)
```json
{
  "node_id": "env_filter_precision",
  "type": "environment_filtering",
  "name": "High-Precision Filter",
  "config": {
    "voxel_downsample_size": 0.0,
    "normal_variance_threshold_deg": 50.0,
    "coplanarity_deg": 80.0,
    "outlier_ratio": 0.7,
    "knn": 50,
    "vertical_tolerance_deg": 10.0,
    "min_plane_area": 0.5
  }
}
```

**Rationale**:
- `voxel_downsample_size = 0`: Disabled for maximum precision (advanced users only)
- Tighter tolerances (`normal_variance_threshold_deg`, `coplanarity_deg`, `vertical_tolerance_deg`): Higher quality plane detection
- Higher `knn` (50): Better plane estimation quality at cost of speed
- Smaller `min_plane_area` (0.5m²): Detect smaller floor patches
- **Use Case**: Critical measurements, offline batch processing, architectural documentation where precision > speed

### Example 6: Dense Scan Optimization (100k+ Points)
```json
{
  "node_id": "env_filter_dense",
  "type": "environment_filtering",
  "name": "Dense Scan Filter",
  "config": {
    "voxel_downsample_size": 0.015,
    "throttle_ms": 0,
    "normal_variance_threshold_deg": 60.0,
    "knn": 30,
    "vertical_tolerance_deg": 15.0,
    "floor_height_range": [-0.5, 0.5],
    "ceiling_height_range": [2.0, 4.0],
    "min_plane_area": 1.0
  }
}
```

**Rationale**:
- `voxel_downsample_size = 0.015` (1.5cm): Aggressive downsampling for 100k+ point clouds
- Expected performance: 100k points → ~40k downsampled → <150ms total processing
- Maintains floor/ceiling detection accuracy while achieving real-time performance
- **Use Case**: High-resolution LiDAR scanners (Velodyne, Ouster) in real-time applications

## References

### Code Locations
- New node directory: `app/modules/pipeline/nodes/environment_filtering/`
- Registry file: `app/modules/pipeline/nodes/environment_filtering/registry.py`
- Node implementation: `app/modules/pipeline/nodes/environment_filtering/node.py`
- Reused operation: `app/modules/pipeline/operations/patch_plane_segmentation/`
- Base classes:
  - `app/modules/pipeline/operation_node.py` (OperationNode)
  - `app/services/nodes/node_factory.py` (NodeFactory)
  - `app/services/nodes/schema.py` (NodeDefinition, PropertySchema, PortSchema)
- Test file: `tests/modules/pipeline/nodes/test_environment_filtering.py`

### Related Features
- **Generate Plane**: `.opencode/plans/generate-plane/` - Complementary feature for mesh generation from detected planes (not directly used, but similar validation logic)

### Architecture Rules
- Backend: `.opencode/rules/backend.md`
- Protocols: `.opencode/rules/protocols.md` (LIDR WebSocket format)
- Pipeline architecture: `AGENTS.md` (DAG orchestration section)

### External Documentation
- Open3D PointCloud API: http://www.open3d.org/docs/latest/python_api/open3d.t.geometry.PointCloud.html
- Open3D Plane Segmentation: http://www.open3d.org/docs/latest/python_api/open3d.t.geometry.PointCloud.html#open3d.t.geometry.PointCloud.segment_plane
- FastAPI Background Tasks: https://fastapi.tiangolo.com/tutorial/background-tasks/ (for async execution patterns)

---

**Document Status**: ✅ Complete - **UPDATED WITH VOXEL DOWNSAMPLING** - Ready for @architecture to define technical implementation in `technical.md`

**Next Steps**:
1. @architecture: Review updated requirements and update `technical.md` with:
   - Voxel downsampling workflow (when to apply, index mapping strategy)
   - Detailed validation algorithm (multi-criteria AND logic)
   - Plane area calculation method (convex hull vs bounding box)
   - WebSocket streaming integration (LIDR protocol format)
   - Node lifecycle management (init, execute, cleanup)
   - Error handling flow diagram
   - Performance benchmarks and optimization strategies
2. @architecture: Update API contract in `api-spec.md` with new downsampling metadata fields
3. @be-dev: Implement `EnvironmentFiltering` node following `backend-tasks.md` (to be updated)
4. @be-dev: Write unit tests covering all acceptance criteria including downsampling scenarios
5. @qa: Validate filtering accuracy, performance benchmarks (with/without downsampling), and real-time streaming behavior

---

## Change Summary (Voxel Downsampling Update)

### Key Changes
1. **New Pre-Processing Step**: Added configurable voxel downsampling BEFORE plane segmentation
2. **New Parameter**: `voxel_downsample_size` (float, 0.0-1.0 meters, default=0.01m)
3. **Performance Optimization**: 2-3x speedup for dense scans (100k+ points) with minimal accuracy loss
4. **Output Guarantee**: Filtered cloud is ALWAYS at original resolution (plane detection uses downsampled cloud, filtering applies to original)

### Updated Sections
- **Feature Overview**: Added downsampling as key capability
- **User Stories**: Added stories for dense scan handling and speed/precision tradeoff control
- **Input Handling**: New "Voxel Downsampling (Pre-Processing)" subsection with full specifications
- **Plane Detection**: Updated to specify detection runs on downsampled cloud
- **Filtering & Output**: Updated to clarify filtering applies to ORIGINAL cloud with index mapping
- **User-Exposed Parameters**: Added `voxel_downsample_size` with detailed help text and value recommendations
- **Error Handling**: Added "Downsampling Too Aggressive" edge case
- **Performance Requirements**: Added downsampling-specific benchmarks and memory constraints
- **Validation & Testing**: Expanded test cases to cover downsampling scenarios
- **Documentation Requirements**: Added downsampling-specific help text and tradeoff documentation
- **Out of Scope**: Added "Adaptive Downsampling" and "Downsampled Output Option" exclusions
- **Technical Constraints**: Updated pipeline architecture, performance, data integrity, extensibility sections
- **Success Metrics**: Added quantitative downsampling performance targets
- **Open Questions**: Added downsampling index mapping strategy and point attribute averaging questions
- **Example Usage**: Updated all examples to include `voxel_downsample_size`, added Examples 5 & 6 for high-precision and dense scan modes

### Impact on Downstream Tasks
- **Architecture (@architecture)**: Must design index mapping strategy from downsampled to original cloud
- **Backend (@be-dev)**: Must implement voxel downsampling step and index mapping logic
- **QA (@qa)**: Must validate performance improvement and accuracy preservation with downsampling enabled
- **Frontend**: No impact (filtering is backend-only, output format unchanged)

**Ready for Architecture Review** ✅
