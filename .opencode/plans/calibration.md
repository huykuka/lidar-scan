# LiDAR Calibration System - Implementation Plan

## Overview

This document describes the ICP (Iterative Closest Point) calibration system for automatically aligning multiple LiDAR sensors in the lidar-standalone application. The calibration node integrates into the existing DAG architecture, allowing users to perform sensor-to-sensor registration through the Flow Canvas UI.

---

## System Architecture

### Module Structure

```
app/modules/calibration/
├── __init__.py                      # Public API exports
├── registry.py                      # NodeDefinition schema + factory builder
├── calibration_node.py              # CalibrationNode orchestrator class
├── registration/                    # Registration algorithms
│   ├── __init__.py
│   ├── global_registration.py      # FPFH + RANSAC coarse alignment
│   ├── icp_engine.py                # Two-stage ICP refinement
│   └── quality.py                   # Result evaluation metrics
└── history.py                       # Calibration history tracking
```

### Integration Points

1. **Database Layer**: New `calibration_history` table for tracking calibration attempts
2. **API Layer**: New endpoints at `/api/v1/calibration/*` for triggering and managing calibrations
3. **Frontend**: Enhanced node card UI with calibration controls and split-view 3D visualization
4. **DAG System**: Calibration node extends `ModuleNode` and participates in standard data flow

---

## Registration Pipeline

### Two-Stage Approach

The calibration system uses a robust two-stage registration pipeline:

#### Stage 1: Global Registration (Coarse Alignment)

**Algorithm**: Fast Point Feature Histogram (FPFH) + RANSAC

**Purpose**: Establish rough alignment when initial sensor poses are far off (>1m translation, >30° rotation)

**Open3D Legacy API Usage**: Global registration requires the legacy API for FPFH feature computation and RANSAC-based matching

**Process Flow**:
1. Convert numpy arrays to legacy `o3d.geometry.PointCloud` objects
2. Downsample both clouds using voxel grid (default: 0.05m voxel size)
3. Estimate normals for both clouds
4. Compute FPFH features using legacy API: `o3d.pipelines.registration.compute_fpfh_feature()`
5. Run RANSAC matching: `o3d.pipelines.registration.registration_ransac_based_on_feature_matching()`
6. Return coarse transformation matrix

**When to Use**:
- User enables "Global Registration" in node properties
- ICP fails with fitness < 0.3 (automatic fallback)
- Initial sensor poses are identity or very rough estimates

#### Stage 2: ICP Refinement (Fine Alignment)

**Algorithm**: Point-to-Plane or Point-to-Point ICP

**Purpose**: Precise local refinement starting from global alignment result

**Open3D Legacy API Usage**: ICP registration uses legacy API for broader algorithm support and robustness

**Process Flow**:
1. Convert numpy arrays to legacy `o3d.geometry.PointCloud` objects
2. Estimate normals (required for point-to-plane method)
3. Run ICP using legacy API: `o3d.pipelines.registration.registration_icp()`
4. Use transformation from Stage 1 as initial guess
5. Return refined transformation matrix + quality metrics (fitness, RMSE)

**Algorithm Options**:
- **Point-to-Point**: Faster, works with noisy data, less accurate
- **Point-to-Plane** (Recommended): More accurate, requires normals, slightly slower

**Why Legacy API**:
- The Open3D legacy pipeline (`o3d.pipelines.registration.*`) provides more registration algorithms
- Better support for FPFH, RANSAC, and various ICP variants
- More stable and well-documented for production use
- Tensor API has limited registration methods as of Open3D 0.18+

---

## Calibration Workflow

### User Perspective

1. **Setup DAG Pipeline**:
   ```
   LiDAR Front → Downsample → Outlier Removal → Calibration Node
   LiDAR Rear  → Downsample → Outlier Removal → Calibration Node
                                                       ↓
                                                  Fusion Node → Visualization
   ```

2. **Start System**: Both sensors stream data through preprocessing pipeline

3. **Trigger Calibration**: User clicks "Run Calibration" button on calibration node card in Flow Canvas

4. **Review Results**: UI displays calibration quality metrics:
   - **Fitness**: Overlap ratio (0.0-1.0, higher is better)
   - **RMSE**: Inlier root mean square error in meters
   - **Quality**: Excellent (≥0.9 fitness) / Good (≥0.7) / Poor (<0.7)
   - **Stages Used**: ["global", "icp"] or ["icp"]

5. **Visualize** (Optional): Click "View in 3D" to see split-view before/after alignment comparison

6. **Decide**:
   - **Accept**: Saves calibration to database, updates sensor pose configs, triggers NodeManager reload
   - **Reject**: Discards results, keeps original sensor poses unchanged

7. **Iterate** (Optional): Re-run calibration to refine alignment

8. **Rollback** (Optional): Restore previous calibration from history

### System Perspective

1. **Buffering Phase**:
   - Calibration node receives point clouds from all connected sensors
   - Stores latest frame from each sensor in memory buffer
   - Determines reference sensor (first sensor by default)

2. **Calibration Trigger** (User Action):
   - Frontend sends `POST /api/v1/calibration/{node_id}/trigger`
   - Backend retrieves buffered point clouds
   - Reads current sensor poses from database

3. **Registration Execution**:
   - For each source sensor (non-reference):
     - Extract numpy points from buffer
     - Build initial transformation matrix from current pose
     - Run Global Registration (if enabled)
     - Run ICP refinement with global result as initial guess
     - Evaluate quality (fitness, RMSE)
     - Extract new pose parameters from transformation matrix

4. **Pose Composition**:
   ```
   T_current = create_transformation_matrix(x, y, z, roll, pitch, yaw)  # From DB config
   T_icp = registration_result.transformation                            # From ICP
   T_new = T_icp @ T_current                                             # Compose transforms
   new_pose = extract_pose_from_matrix(T_new)                            # Back to 6-DOF
   ```

5. **Pending Approval State**:
   - Results stored in node's `_pending_calibration` dictionary
   - User can accept, reject, or visualize
   - No database changes until user accepts

6. **Acceptance & Persistence**:
   - Update sensor node config in `nodes` table with new pose
   - Create calibration record in `calibration_history` table
   - Trigger `NodeManager.reload()` to apply new transforms
   - Clear pending calibration state

---

## Database Schema

### New Table: calibration_history

```sql
CREATE TABLE calibration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,                    -- ISO 8601 UTC timestamp
    sensor_id TEXT NOT NULL,                    -- Source sensor being calibrated
    reference_sensor_id TEXT NOT NULL,          -- Target/reference sensor
    fitness REAL,                               -- Registration fitness score
    rmse REAL,                                  -- Inlier RMSE in meters
    quality TEXT,                               -- "excellent" | "good" | "poor"
    data TEXT,                                  -- JSON blob with full CalibrationRecord
    FOREIGN KEY (sensor_id) REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE INDEX idx_calib_sensor_time ON calibration_history(sensor_id, timestamp DESC);
```

### CalibrationRecord Structure (JSON in data column)

```json
{
  "timestamp": "2024-02-27T10:30:45.123Z",
  "sensor_id": "lidar_rear_abc123",
  "reference_sensor_id": "lidar_front_def456",
  "fitness": 0.947,
  "rmse": 0.0089,
  "quality": "excellent",
  "stages_used": ["global", "icp"],
  "pose_before": {
    "x": 2.0, "y": 0.0, "z": 0.5,
    "roll": 0.0, "pitch": 0.0, "yaw": 180.0
  },
  "pose_after": {
    "x": 2.13, "y": 0.05, "z": 0.48,
    "roll": 0.2, "pitch": -0.1, "yaw": 179.8
  },
  "transformation_matrix": [[...], [...], [...], [...]],  // 4x4 matrix
  "accepted": true,
  "notes": ""
}
```

---

## API Endpoints

### POST /api/v1/calibration/{node_id}/trigger

**Purpose**: Run ICP calibration on buffered sensor data

**Request Body**:
```json
{
  "reference_sensor_id": "lidar_front_abc123",  // Optional: override default
  "source_sensor_ids": ["lidar_rear_def456"],   // Optional: specific sensors
  "sample_frames": 1                             // Future: average N frames
}
```

**Response**:
```json
{
  "success": true,
  "results": {
    "lidar_rear_def456": {
      "fitness": 0.947,
      "rmse": 0.0089,
      "quality": "excellent",
      "stages_used": ["global", "icp"],
      "pose_before": {...},
      "pose_after": {...},
      "auto_saved": false
    }
  },
  "pending_approval": true
}
```

### POST /api/v1/calibration/{node_id}/accept

**Purpose**: Accept pending calibration and save to database

**Request Body**:
```json
{
  "sensor_ids": ["lidar_rear_def456"]  // Optional: specific sensors (null = all)
}
```

**Response**:
```json
{
  "success": true,
  "accepted": ["lidar_rear_def456"]
}
```

### POST /api/v1/calibration/{node_id}/reject

**Purpose**: Reject pending calibration (discard results)

**Response**:
```json
{
  "success": true
}
```

### GET /api/v1/calibration/history/{sensor_id}

**Purpose**: Retrieve calibration history for a sensor

**Query Params**: `?limit=10`

**Response**:
```json
{
  "sensor_id": "lidar_rear_def456",
  "history": [
    {
      "timestamp": "2024-02-27T10:30:45.123Z",
      "fitness": 0.947,
      "rmse": 0.0089,
      "quality": "excellent",
      "pose_after": {...},
      "accepted": true
    },
    ...
  ]
}
```

### POST /api/v1/calibration/rollback/{sensor_id}

**Purpose**: Rollback sensor to a previous calibration state

**Request Body**:
```json
{
  "timestamp": "2024-02-27T10:30:45.123Z"
}
```

**Response**:
```json
{
  "success": true,
  "sensor_id": "lidar_rear_def456",
  "restored_to": "2024-02-27T10:30:45.123Z"
}
```

---

## Node Configuration

### Calibration Node Properties

Exposed in the Angular Flow Canvas property editor:

#### ICP Settings
- **icp_method**: "point_to_plane" | "point_to_point" (default: point_to_plane)
- **icp_threshold**: Max correspondence distance in meters (default: 0.02)
- **icp_iterations**: Max iterations (default: 50)

#### Global Registration Settings
- **enable_global_registration**: Boolean (default: true)
- **global_voxel_size**: Downsample voxel size in meters (default: 0.05)
- **ransac_threshold**: RANSAC distance threshold in meters (default: 0.075)
- **ransac_iterations**: RANSAC max iterations (default: 100000)

#### Quality Control
- **min_fitness**: Minimum fitness threshold for quality gate (default: 0.7)
- **max_rmse**: Maximum RMSE threshold for quality gate (default: 0.05)

#### Save Behavior
- **auto_save**: Automatically save calibration without user approval (default: false)
- **min_fitness_to_save**: Only auto-save if fitness >= this value (default: 0.8)

---

## Frontend Components

### Enhanced Node Card

**Location**: `web/src/app/features/settings/components/node-card/`

**New UI Elements for Calibration Nodes**:

1. **Trigger Button**: "🎯 Run Calibration"
   - Disabled if no buffered frames available
   - Shows loading spinner during calibration

2. **Pending Results Panel**:
   - Quality badges (color-coded: green/yellow/red)
   - Fitness and RMSE metrics
   - Pose delta summary (Δx, Δy, Δz, Δyaw, etc.)
   - Stages used indicator

3. **Action Buttons**:
   - "✓ Accept & Save" (green) - Persists calibration
   - "👁️ View in 3D" (blue) - Opens visualization modal
   - "✗ Reject" (red) - Discards results

4. **History Accordion**:
   - Collapsible list of past calibrations
   - Timestamp, quality, fitness/RMSE
   - "↶ Rollback" button per entry

### Split-View Calibration Visualizer

**New Component**: `calibration-viewer.component.ts`

**Location**: `web/src/app/features/workspaces/components/calibration-viewer/`

**Purpose**: Side-by-side 3D comparison of before/after calibration alignment

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Before Calibration    │    After Calibration           │
├────────────────────────┼────────────────────────────────┤
│  [3D Canvas]           │    [3D Canvas]                 │
│  Reference: Blue ●     │    Reference: Blue ●           │
│  Source: Red ●         │    Aligned: Green ●            │
│  (misaligned)          │    Fitness: 0.947              │
└────────────────────────┴────────────────────────────────┘
```

**Rendering**:
- Three.js BufferGeometry for point clouds
- Synchronized camera controls (orbit, zoom, pan)
- Color coding: Reference (blue), Source before (red), Source after (green)
- Overlay metrics display

**Trigger**: User clicks "View in 3D" button in node card

---

## Open3D Legacy API Integration

### Why Legacy API for Registration

The calibration system uses Open3D's **legacy API** (`o3d.geometry.PointCloud` and `o3d.pipelines.registration.*`) instead of the tensor-based API for the following reasons:

1. **Algorithm Availability**: Legacy pipelines provide more registration algorithms:
   - FPFH feature computation
   - RANSAC-based feature matching
   - Point-to-point and point-to-plane ICP
   - Colored ICP, Generalized ICP
   - Fast Global Registration (FGR)

2. **Stability**: Legacy API is mature, well-tested, and widely used in production

3. **Documentation**: Better documentation and community examples for registration tasks

4. **Performance**: Comparable performance for registration tasks (not compute-bound)

### Conversion Pattern

Throughout the calibration module, the following conversion pattern is used:

**Tensor ↔ Legacy Conversions**:
```
# Tensor → Legacy (for registration algorithms)
pcd_legacy = pcd_tensor.to_legacy()

# Legacy → Tensor (back to pipeline)
pcd_tensor = o3d.t.geometry.PointCloud.from_legacy(pcd_legacy)
```

**Full Pipeline Example**:
```
Numpy → Tensor (PointConverter.to_pcd) 
  → Legacy (to_legacy) 
  → Registration (ICP/RANSAC) 
  → Extract Transform 
  → Legacy → Tensor (from_legacy, optional)
  → Numpy (PointConverter.to_points)
```

**Reference**: The boundary detection operation (`app/modules/pipeline/operations/boundary.py` lines 41, 46) already demonstrates this pattern.

---

## Quality Evaluation

### Fitness Score

**Definition**: Ratio of overlapping points between source and target

**Range**: 0.0 to 1.0

**Interpretation**:
- **≥ 0.9**: Excellent alignment, high overlap
- **≥ 0.7**: Good alignment, acceptable overlap
- **< 0.7**: Poor alignment, low overlap (warning)

**Calculation**: `fitness = num_correspondences / total_source_points`

### Inlier RMSE

**Definition**: Root mean square error of point-to-point distances for inlier correspondences

**Units**: Meters

**Interpretation**:
- **≤ 0.02m**: Excellent precision (2cm error)
- **≤ 0.05m**: Good precision (5cm error)
- **> 0.05m**: Poor precision (warning)

### Quality Classification

Calibration results are automatically classified:

```
if fitness ≥ 0.9 AND rmse ≤ 0.02:
    quality = "excellent"
elif fitness ≥ min_fitness AND rmse ≤ max_rmse:
    quality = "good"
else:
    quality = "poor"
```

**User Action Based on Quality**:
- **Excellent/Good**: Safe to accept
- **Poor**: Review parameters, add preprocessing, or improve initial poses

---

## Calibration History & Rollback

### History Tracking

Every calibration attempt (accepted or rejected) is stored in the `calibration_history` table with:
- Timestamp
- Quality metrics (fitness, RMSE)
- Pose before and after
- Transformation matrix
- Acceptance status

**Benefits**:
- Audit trail of calibration attempts
- Ability to revert to previous calibrations
- Track calibration quality over time
- Debug calibration issues

### Rollback Mechanism

Users can restore a sensor to a previous calibration state:

1. View calibration history in node card accordion
2. Click "↶ Rollback" on desired historical entry
3. System reads `pose_after` from that calibration record
4. Updates sensor config in database
5. Triggers `NodeManager.reload()` to apply

**Use Cases**:
- Accidentally accepted poor calibration
- Want to compare different calibration attempts
- Revert to factory/manual calibration after testing auto-calibration

---

## Multi-Sensor Calibration Strategy

### Sequential Calibration (Implemented)

For systems with 3+ LiDAR sensors, each sensor is calibrated independently to a single reference sensor:

```
Reference: LiDAR Front
Sources:
  - LiDAR Rear  → calibrated to Front
  - LiDAR Left  → calibrated to Front
  - LiDAR Right → calibrated to Front
```

**Advantages**:
- Simple and deterministic
- Scales to any number of sensors
- Easy to understand and debug

**Limitations**:
- No global optimization (errors don't distribute evenly)
- Reference sensor must have good overlap with all sources

### Future: Pairwise + Global Optimization

For more complex scenarios, a pairwise approach with pose graph optimization could be implemented:

1. Run ICP between all sensor pairs with overlap
2. Build pose graph with transformation edges
3. Run global optimization to minimize total error
4. Distribute errors evenly across all sensors

**When Needed**: 4+ sensors with complex spatial arrangements

---

## Preprocessing Recommendations

### Why Preprocessing Before Calibration

Raw LiDAR data often contains noise, outliers, and excessive point density that can degrade ICP performance. Preprocessing improves:
- **Speed**: Fewer points = faster ICP
- **Accuracy**: Removing noise reduces false correspondences
- **Robustness**: Cleaner data helps convergence

### Recommended Pipeline

Insert these pipeline nodes **before** the calibration node:

1. **Downsample (Voxel Grid)**:
   - Voxel size: 0.02m - 0.05m
   - Reduces point count by 80-95%
   - Preserves geometric structure

2. **Statistical Outlier Removal**:
   - Neighbors: 20-30
   - Std ratio: 2.0
   - Removes isolated noise points

3. **Crop (Optional)**:
   - Define bounding box of overlap region
   - Focuses ICP on shared area
   - Improves speed and accuracy

**Example DAG**:
```
LiDAR → Downsample(0.03m) → Outlier Removal → Crop → Calibration
```

---

## Parameter Tuning Guide

### When ICP Fails to Converge

**Symptoms**: Fitness < 0.3, RMSE very high, quality = "poor"

**Solutions**:
1. Enable global registration (`enable_global_registration: true`)
2. Increase ICP threshold (try 0.05m instead of 0.02m)
3. Improve initial sensor poses manually
4. Add more preprocessing (downsample, outlier removal)
5. Ensure sensors have sufficient overlap (>30% of FOV)

### When Calibration is Slow

**Symptoms**: Calibration takes >10 seconds

**Solutions**:
1. Increase downsample voxel size (reduce point count)
2. Decrease ICP max iterations (50 → 30)
3. Decrease RANSAC iterations for global registration
4. Crop to smaller overlap region

### When Fitness is High but Alignment Looks Wrong

**Symptoms**: Fitness > 0.9 but visual inspection shows misalignment

**Solutions**:
1. Check if point clouds are too similar (symmetry issues)
2. Add distinctive features to environment (calibration targets)
3. Use point-to-plane instead of point-to-point
4. Verify sensor timestamps are synchronized

---

## Testing Strategy

### Unit Tests

1. **Global Registration**:
   - Test with identical clouds (expect ~identity transform)
   - Test with known transform (should recover within tolerance)
   - Test with insufficient overlap (should fail gracefully)

2. **ICP Engine**:
   - Test point-to-point vs point-to-plane methods
   - Test two-stage pipeline (global → ICP)
   - Test quality evaluation classification

3. **Pose Composition**:
   - Test transformation matrix composition
   - Test pose extraction (matrix → 6-DOF)
   - Test edge cases (identity, 180° rotation, etc.)

4. **History Management**:
   - Test save and retrieve calibration records
   - Test rollback to previous calibration
   - Test database constraints and foreign keys

### Integration Tests

1. **Full Calibration Workflow**:
   - Create 2 sensor nodes + calibration node
   - Send mock point clouds (known transform)
   - Trigger calibration via API
   - Verify database update
   - Verify NodeManager reload

2. **Multi-Sensor Calibration**:
   - Test with 3+ sensors
   - Verify sequential calibration to reference

3. **API Endpoints**:
   - Test trigger, accept, reject, history, rollback
   - Test error handling (missing nodes, no data, etc.)

### Manual Testing with Real Data

1. **Two LiDAR Setup**:
   - Position sensors with ~50% overlap
   - Run system with approximate manual poses
   - Trigger calibration
   - Verify alignment in 3D workspace

2. **Preprocessing Pipeline**:
   - Test with/without downsample
   - Test with/without outlier removal
   - Measure impact on fitness and RMSE

3. **Edge Cases**:
   - Test with minimal overlap (< 20%)
   - Test with very noisy data
   - Test with dynamic scenes (moving objects)

---

## Implementation Checklist

### Phase 1: Backend Core (Registration Algorithms)

- [ ] Create module structure: `app/modules/calibration/`
- [ ] Implement `registration/global_registration.py`:
  - [ ] FPFH feature computation (legacy API)
  - [ ] RANSAC-based matching (legacy API)
  - [ ] Quality metrics extraction
- [ ] Implement `registration/icp_engine.py`:
  - [ ] Point-to-point ICP (legacy API)
  - [ ] Point-to-plane ICP (legacy API)
  - [ ] Two-stage pipeline (global → ICP)
  - [ ] Quality evaluation logic
- [ ] Implement `registration/quality.py`:
  - [ ] Fitness/RMSE calculation
  - [ ] Quality classification (excellent/good/poor)
- [ ] Implement `history.py`:
  - [ ] CalibrationRecord dataclass
  - [ ] Save/retrieve history from database
  - [ ] Rollback functionality

### Phase 2: Backend Node & Orchestration

- [ ] Implement `calibration_node.py`:
  - [ ] CalibrationNode class (extends ModuleNode)
  - [ ] Input buffering (`on_input` method)
  - [ ] Trigger calibration logic
  - [ ] Pending approval state management
  - [ ] Accept/reject methods
  - [ ] Status reporting
- [ ] Implement `registry.py`:
  - [ ] NodeDefinition schema with all properties
  - [ ] Factory builder function
  - [ ] Register with node_schema_registry
  - [ ] Register with NodeFactory

### Phase 3: Database & Persistence

- [ ] Create database migration:
  - [ ] `calibration_history` table schema
  - [ ] Indexes for performance
  - [ ] Foreign key constraints
- [ ] Implement `app/repositories/calibration_orm.py`:
  - [ ] save_calibration_record()
  - [ ] get_calibration_history()
  - [ ] Rollback support functions

### Phase 4: API Layer

- [ ] Create `app/api/v1/calibration.py`:
  - [ ] POST /calibration/{node_id}/trigger
  - [ ] POST /calibration/{node_id}/accept
  - [ ] POST /calibration/{node_id}/reject
  - [ ] GET /calibration/history/{sensor_id}
  - [ ] POST /calibration/rollback/{sensor_id}
- [ ] Register router in main FastAPI app
- [ ] Add Pydantic request/response models

### Phase 5: Frontend - Node Card

- [ ] Update `node-card.component.ts`:
  - [ ] Detect calibration node type
  - [ ] Add "Run Calibration" button
  - [ ] Display pending results panel
  - [ ] Add accept/reject/view actions
  - [ ] Add history accordion
- [ ] Update `node-card.component.html`:
  - [ ] Calibration controls template
  - [ ] Quality badge styling (color-coded)
  - [ ] Metrics display
  - [ ] History list template
- [ ] Update `node-card.component.scss`:
  - [ ] Styling for calibration-specific UI

### Phase 6: Frontend - API Service

- [ ] Create `CalibrationApiService`:
  - [ ] triggerCalibration()
  - [ ] acceptCalibration()
  - [ ] rejectCalibration()
  - [ ] getCalibrationHistory()
  - [ ] rollbackCalibration()
- [ ] Add TypeScript interfaces for request/response types

### Phase 7: Frontend - 3D Visualization

- [ ] Create `calibration-viewer.component.ts`:
  - [ ] Split-view layout (before/after)
  - [ ] Two Three.js scenes (synchronized cameras)
  - [ ] Point cloud rendering (BufferGeometry)
  - [ ] Color coding (blue/red/green)
  - [ ] Metrics overlay
- [ ] Create modal/dialog wrapper for viewer
- [ ] Wire "View in 3D" button to open modal

### Phase 8: Testing

- [ ] Write unit tests:
  - [ ] Global registration tests
  - [ ] ICP engine tests
  - [ ] Pose composition tests
  - [ ] History management tests
- [ ] Write integration tests:
  - [ ] Full calibration workflow
  - [ ] Multi-sensor calibration
  - [ ] API endpoint tests
- [ ] Manual testing with real sensor data

### Phase 9: Documentation

- [ ] Update `AGENTS.md`:
  - [ ] Add calibration module to architecture section
  - [ ] Document node type and capabilities
- [ ] Create user guide:
  - [ ] How to set up calibration pipeline
  - [ ] Parameter tuning recommendations
  - [ ] Troubleshooting common issues
- [ ] Add inline code documentation (docstrings)

---

## Known Limitations & Future Enhancements

### Current Limitations

1. **Single-frame calibration**: Only uses latest buffered frame (no multi-frame averaging)
2. **Sequential calibration**: No global pose graph optimization
3. **Static scenes**: Assumes static environment during calibration
4. **Manual trigger**: No automatic re-calibration on drift detection

### Future Enhancements

1. **Multi-frame averaging**: Average N frames before calibration for noise reduction
2. **Pairwise + global optimization**: Distribute errors evenly across all sensors
3. **Automatic drift detection**: Monitor alignment quality and trigger re-calibration
4. **Calibration targets**: Detect and use fiducial markers for improved accuracy
5. **Colored ICP**: Use intensity data for better convergence
6. **Export calibration**: Save/load calibration configs as JSON files

---

## References

- Open3D Registration Tutorial: https://www.open3d.org/docs/release/tutorial/pipelines/index.html
- ICP Registration: https://www.open3d.org/docs/release/tutorial/pipelines/icp_registration.html
- Global Registration: https://www.open3d.org/docs/release/tutorial/pipelines/global_registration.html
- FPFH Features: https://www.open3d.org/docs/release/python_api/open3d.pipelines.registration.compute_fpfh_feature.html

---

## Summary

This calibration system provides a production-ready solution for automatic LiDAR sensor alignment with:

✅ **Robust two-stage registration** (global + ICP)  
✅ **Legacy API integration** for maximum algorithm support  
✅ **User approval workflow** with quality gates  
✅ **Calibration history** with rollback capability  
✅ **DAG integration** allowing preprocessing pipelines  
✅ **3D visualization** for verification  
✅ **Sequential multi-sensor** support  

The system is designed to be intuitive for users while providing the flexibility and robustness needed for real-world LiDAR calibration scenarios.
