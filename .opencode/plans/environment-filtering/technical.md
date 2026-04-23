# Technical Specification: Environment Filtering Node

## 1. Layer Placement

`EnvironmentFilteringNode` is an **Application-layer node** (category `"application"`), NOT a pipeline operation. It lives at:

```
app/modules/application/environment_filtering/
├── __init__.py
├── node.py       # EnvironmentFilteringNode(ModuleNode)
└── registry.py   # schema + @NodeFactory.register("environment_filtering")
```

And is wired in `app/modules/application/registry.py` alongside `hello_world_registry`.

---

## 2. Architecture Summary

```
upstream node
    │ payload (numpy N×14)
    ▼
EnvironmentFilteringNode.on_input()
    │
    ├─ _extract_pcd()            numpy → o3d.t.geometry.PointCloud (tensor)
    │
    ├─ asyncio.to_thread()       ← non-blocking threadpool dispatch
    │       │
    │       └─ _sync_filter()   (pure, CPU-bound)
    │               │
    │               ├─ [STEP 1] _voxel_downsample()
    │               │       if voxel_downsample_size > 0:
    │               │           pcd_ds = pcd_in.voxel_down_sample(size)
    │               │           record stats → downsample_meta
    │               │       else:
    │               │           pcd_ds = pcd_in (pass-through reference)
    │               │
    │               ├─ [STEP 2] _apply_with_boxes(pcd_ds)
    │               │       → (oboxes, labels_ds, points_ds_np)
    │               │       # plane detection on DOWNSAMPLED cloud
    │               │
    │               ├─ [STEP 3] _classify_planes()
    │               │       orientation + position + size checks on oboxes
    │               │       → validated_planes: List[PlaneInfo]
    │               │
    │               ├─ [STEP 4] _map_indices_to_original()
    │               │       KD-tree nearest-neighbor: each downsampled plane
    │               │       point → closest original point index
    │               │       → removal_mask on ORIGINAL cloud (N_orig booleans)
    │               │       (only executed when downsampling is active)
    │               │
    │               └─ [STEP 5] _remove_planes()
    │                       pcd_out = pcd_in.select_by_index(keep_indices)
    │                       # always operates on ORIGINAL resolution cloud
    │
    ├─ _build_payload()          enrich with metadata (incl. downsample stats)
    └─ manager.forward_data()    fire-and-forget → downstream + WebSocket
```

---

## 3. Index-Mapping Strategy Decision

### Problem
When `voxel_downsample_size > 0`, plane segmentation runs on a reduced cloud (`pcd_ds`). The `labels_ds` array is indexed `0..N_ds-1`. We need to determine which points in the **original** cloud (`0..N_orig-1`) belong to a detected plane, so we can remove them.

### Options Evaluated

| Strategy | Speed | Accuracy | Memory | Complexity |
|---|---|---|---|---|
| **KD-tree nearest-neighbor** (chosen) | O(N_orig log N_ds) | High — exact proximity | O(N_ds) for tree | Low |
| Voxel grid inverse map | O(N_orig) | Medium — voxel boundary effects | O(N_ds) | Medium |
| Re-run segmentation on original | O(N_orig × seg) | Perfect | None extra | High, defeats purpose |

### **Decision: KD-tree Nearest-Neighbor**

For each plane detected in `pcd_ds`, build a KD-tree from the plane's downsampled points, then query all original points to find those within `voxel_downsample_size / 2` radius. This is accurate, fast (Open3D KDTreeFlann is C++-backed), and requires no changes to the segmentation operation.

```python
def _map_indices_to_original(
    self,
    plane_points_ds: np.ndarray,   # (M, 3) downsampled plane points
    original_points: np.ndarray,    # (N, 3) full-res points
    radius: float,                  # voxel_downsample_size / 2
) -> np.ndarray:                    # boolean mask length N
    pcd_plane = o3d.geometry.PointCloud()
    pcd_plane.points = o3d.utility.Vector3dVector(plane_points_ds)
    tree = o3d.geometry.KDTreeFlann(pcd_plane)

    mask = np.zeros(len(original_points), dtype=bool)
    for i, pt in enumerate(original_points):
        k, _, _ = tree.search_radius_vector_3d(pt, radius)
        if k > 0:
            mask[i] = True
    return mask
```

**Performance note**: For 100k original points and ~5k downsampled plane points, this runs in ~10-15ms (C++ KD-tree). Vectorized batch search via `scipy.spatial.KDTree.query_ball_point` can replace the Python loop if profiling shows it as a bottleneck.

**When downsampling is disabled** (`voxel_downsample_size = 0`): `pcd_ds is pcd_in`, so `labels_ds` indexes the original cloud directly — no mapping step needed.

---

## 4. Class Design: `EnvironmentFilteringNode`

Inherits: `ModuleNode`

### 4.1 Constructor Parameters

| Param | Type | Source |
|---|---|---|
| `manager` | `Any` | injected by factory |
| `node_id` | `str` | injected by factory |
| `name` | `str` | injected by factory |
| `config` | `Dict[str, Any]` | DAG node config |
| `throttle_ms` | `float` | extracted from config by factory |

### 4.2 Internal State

```python
self._op: PatchPlaneSegmentation
self.voxel_downsample_size: float        # NEW
self.input_count: int
self.last_input_at: Optional[float]
self.last_error: Optional[str]
self.last_metadata: Dict[str, Any]
self.processing_time_ms: float
self._processing: bool
```

---

## 5. Core Algorithm: `_sync_filter(pcd_in)`

Runs entirely in threadpool. Returns `(pcd_out, metadata_dict)`.

### Step 1 — Voxel Downsampling (NEW)

```python
def _voxel_downsample(self, pcd_tensor):
    """Returns (pcd_ds, downsample_meta). pcd_ds may be same object as pcd_in."""
    n_orig = len(pcd_tensor.point.positions)
    if self.voxel_downsample_size <= 0:
        return pcd_tensor, {
            "downsampling_enabled": False,
            "voxel_size": 0.0,
            "points_before_downsample": n_orig,
            "points_after_downsample": n_orig,
        }

    pcd_legacy = pcd_tensor.to_legacy()
    pcd_ds_legacy = pcd_legacy.voxel_down_sample(self.voxel_downsample_size)
    n_ds = len(np.asarray(pcd_ds_legacy.points))

    if n_ds < 100:
        logger.warning(
            f"[{self.id}] Voxel size {self.voxel_downsample_size}m too large — "
            f"downsampling reduced cloud to {n_ds} points. "
            "Consider reducing voxel_downsample_size."
        )

    pcd_ds = o3d.t.geometry.PointCloud.from_legacy(pcd_ds_legacy)
    meta = {
        "downsampling_enabled": True,
        "voxel_size": self.voxel_downsample_size,
        "points_before_downsample": n_orig,
        "points_after_downsample": n_ds,
    }
    return pcd_ds, meta
```

**Memory**: `pcd_ds_legacy` is a local variable. After `_sync_filter` returns, the GC reclaims it. No persistent cache.

### Step 2 — Plane Detection (on downsampled cloud)

```python
oboxes, labels_ds, pts_ds_np = self._apply_with_boxes(pcd_ds.to_legacy())
```

`_apply_with_boxes` calls `detect_planar_patches(...)` and returns:
- `oboxes`: `List[o3d.geometry.OrientedBoundingBox]`
- `labels_ds`: `np.ndarray` shape `(N_ds,)` — plane index per point, -1 = unassigned
- `pts_ds_np`: `np.ndarray` shape `(N_ds, 3)` — XYZ of downsampled cloud

### Step 3 — Per-Plane Classification

For each `obox` at index `plane_idx`:

1. **Orientation** — extract normal from `obox.R[:, 2]`, compute angle to `[0,0,1]`.  
   Reject if `angle_deg > vertical_tolerance_deg`.

2. **Position** — `z = obox.center[2]`.  
   Reject if outside both `floor_height_range` and `ceiling_height_range`.

3. **Size** — `area = obox.extent[0] * obox.extent[1]`.  
   Reject if `area < min_plane_area`.  
   **Decision**: OBB-area (fast, ~0ms). ConvexHull deferred — OBB overestimates but is safe for room-scale floors.

All three criteria must pass (AND logic). Returns `PlaneInfo(plane_id, plane_type, normal, centroid_z, area, point_count)`.

### Step 4 — Index Mapping (NEW — only when downsampling active)

```python
if self.voxel_downsample_size > 0:
    pts_orig_np = np.asarray(pcd_in.to_legacy().points)
    removal_mask = np.zeros(len(pts_orig_np), dtype=bool)
    radius = self.voxel_downsample_size / 2.0

    for plane in validated_planes:
        plane_pts_ds = pts_ds_np[labels_ds == plane.plane_id]
        plane_mask = self._map_indices_to_original(plane_pts_ds, pts_orig_np, radius)
        removal_mask |= plane_mask
else:
    # No downsampling: labels_ds indexes original cloud directly
    removal_mask = np.zeros(len(pts_ds_np), dtype=bool)
    for plane in validated_planes:
        removal_mask |= (labels_ds == plane.plane_id)
```

### Step 5 — Point Removal (always on original resolution)

```python
keep_indices = np.where(~removal_mask)[0]
pcd_out = pcd_in.select_by_index(keep_indices)   # index-based slice, no full copy
```

---

## 6. Full Metadata Contract

```python
{
    # Downsampling stats (NEW)
    "downsampling_enabled": bool,
    "voxel_size": float,               # 0.0 if disabled
    "points_before_downsample": int,
    "points_after_downsample": int,
    # Filtering results
    "input_point_count": int,          # = points_before_downsample
    "output_point_count": int,
    "removed_point_count": int,
    "planes_detected": int,
    "planes_filtered": int,
    "plane_details": List[PlaneInfo],
    "status": str,                     # see §7
}
```

---

## 7. Error Handling Matrix

| Condition | Behaviour | `operational_state` | `status` |
|---|---|---|---|
| Empty input (0 pts) | return original | WARNING badge | `"warning_pass_through"` |
| `< min_num_points` | pass-through | WARNING badge | `"warning_pass_through"` |
| Downsampling → < 100 pts | proceed + log | WARNING badge | `"warning_low_point_density"` |
| 0 planes detected | pass-through | WARNING badge | `"no_planes_detected"` |
| Planes detected, none valid | pass-through | WARNING badge | `"warning_pass_through"` |
| `voxel_downsample_size` < 0 or > 1 | raise `ValueError` at init | `ERROR` | N/A |
| `vertical_tolerance_deg` out of range | raise `ValueError` at init | `ERROR` | N/A |
| `min_plane_area < 0.1` | raise `ValueError` at init | `ERROR` | N/A |
| height range `max <= min` | raise `ValueError` at init | `ERROR` | N/A |
| Malformed input (TypeError) | `last_error` set | `ERROR` | N/A |
| Unexpected exception | `last_error` set + log | `ERROR` | N/A |

> WARNING → `OperationalState.RUNNING` with `color="orange"`. ERROR → `OperationalState.ERROR`.  
> In all pass-through cases, return ORIGINAL full-resolution cloud (NOT downsampled).

---

## 8. Parameter Validation (at construction)

```python
def _validate_params(self) -> None:
    if not (0.0 <= self.voxel_downsample_size <= 1.0):         # NEW
        raise ValueError("voxel_downsample_size must be between 0.0 and 1.0 meters")
    if not (1 <= self.vertical_tolerance_deg <= 45):
        raise ValueError("vertical_tolerance_deg must be between 1 and 45 degrees")
    if self.min_plane_area < 0.1:
        raise ValueError("min_plane_area must be >= 0.1 square meters")
    if self.floor_height_range[0] >= self.floor_height_range[1]:
        raise ValueError("floor_height_range must have max > min")
    if self.ceiling_height_range[0] >= self.ceiling_height_range[1]:
        raise ValueError("ceiling_height_range must have max > min")
```

---

## 9. Async Execution Pattern

```python
async def on_input(self, payload: Dict[str, Any]) -> None:
    if self._processing:
        logger.debug(f"[{self.id}] Dropping frame — still processing")
        return
    self._processing = True
    try:
        pcd_in = _extract_pcd(payload["points"])
        pcd_out, metadata = await asyncio.to_thread(self._sync_filter, pcd_in)
        new_payload = payload.copy()
        new_payload["points"] = PointConverter.to_points(pcd_out)
        new_payload["node_id"] = self.id
        new_payload["metadata"] = metadata
        new_payload.update(metadata)
        notify_status_change(self.id)
        asyncio.create_task(self.manager.forward_data(self.id, new_payload))
    except Exception as exc:
        self.last_error = str(exc)
        notify_status_change(self.id)
        logger.error(f"[{self.id}] {exc}", exc_info=True)
    finally:
        self._processing = False
```

---

## 10. Registry Pattern

`registry.py` follows `hello_world/registry.py` exactly:

```python
node_schema_registry.register(NodeDefinition(
    type="environment_filtering",
    category="application",
    ...
))

@NodeFactory.register("environment_filtering")
def build_environment_filtering(node, service_context, edges):
    from app.modules.application.environment_filtering.node import EnvironmentFilteringNode
    config = node.get("config") or {}
    throttle_ms = float(config.get("throttle_ms", 0) or 0)
    return EnvironmentFilteringNode(
        manager=service_context,
        node_id=node["id"],
        name=node.get("name") or "Environment Filtering",
        config=config,
        throttle_ms=throttle_ms,
    )
```

Wire-up in `app/modules/application/registry.py`:
```python
from .environment_filtering import registry as environment_filtering_registry
__all__ = ["hello_world_registry", "environment_filtering_registry"]
```

---

## 11. Extensibility Design

```python
# Modular validation — adding wall filtering requires only:
def _validate_as_wall(self, obox) -> Optional[PlaneInfo]:
    """Future: check normal is horizontal, position is at perimeter."""
    ...

# Configurable pre-processing — swap voxel downsampling for SOR:
def _preprocess(self, pcd) -> Tuple[Any, Dict]:
    """Currently: voxel_down_sample. Future: statistical_outlier_removal."""
    ...

# Pluggable segmentation — current entry point is _apply_with_boxes()
def _apply_with_boxes(self, legacy_pcd) -> Tuple[List, np.ndarray, np.ndarray]:
    ...
```

---

## 12. Performance Tradeoff Guide

| Scenario | `voxel_downsample_size` | Expected latency | Notes |
|---|---|---|---|
| Sparse scan (< 20k pts) | `0` (disabled) | < 50ms | No benefit from downsampling |
| Dense indoor (50k pts) | `0.01` (1cm) | < 100ms | **Default — recommended** |
| High-density (100k pts) | `0.01` | < 150ms | 2-3× speedup vs. no downsampling |
| Very dense (200k pts) | `0.015` (1.5cm) | < 200ms | Real-time capable |
| Precision mode | `0` (disabled) | < 400ms | Offline processing, max accuracy |
| Fastest mode | `0.03–0.05` | < 100ms | Coarse floor removal only |

**When to disable downsampling**: critical measurements, architectural docs, sparse clouds where downsampling would eliminate plane points.

---

## 13. Example DAG Configs

**Default indoor room**
```json
{
  "node_id": "ef_default",
  "type": "environment_filtering",
  "config": {
    "voxel_downsample_size": 0.01,
    "normal_variance_threshold_deg": 60.0,
    "coplanarity_deg": 75.0,
    "outlier_ratio": 0.75,
    "knn": 30,
    "vertical_tolerance_deg": 15.0,
    "floor_height_min": -0.5, "floor_height_max": 0.5,
    "ceiling_height_min": 2.0, "ceiling_height_max": 4.0,
    "min_plane_area": 1.0
  }
}
```

**Uneven warehouse floor (loose tolerances)**
```json
{
  "node_id": "ef_warehouse",
  "type": "environment_filtering",
  "config": {
    "voxel_downsample_size": 0.02,
    "normal_variance_threshold_deg": 70.0,
    "coplanarity_deg": 65.0,
    "outlier_ratio": 0.85,
    "vertical_tolerance_deg": 25.0,
    "floor_height_min": -0.8, "floor_height_max": 0.8,
    "ceiling_height_min": 8.0, "ceiling_height_max": 12.0,
    "min_plane_area": 5.0,
    "knn": 20
  }
}
```

**High-ceiling space**
```json
{
  "node_id": "ef_highceil",
  "type": "environment_filtering",
  "config": {
    "voxel_downsample_size": 0.01,
    "vertical_tolerance_deg": 15.0,
    "floor_height_min": -0.5, "floor_height_max": 0.5,
    "ceiling_height_min": 7.0, "ceiling_height_max": 15.0,
    "min_plane_area": 10.0
  }
}
```

**Dense scan optimization (100k+ pts)**
```json
{
  "node_id": "ef_dense",
  "type": "environment_filtering",
  "config": {
    "voxel_downsample_size": 0.015,
    "knn": 30,
    "vertical_tolerance_deg": 15.0,
    "min_plane_area": 1.0
  }
}
```

**High-precision mode (downsampling disabled)**
```json
{
  "node_id": "ef_precision",
  "type": "environment_filtering",
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

---

## 14. Open Question Resolutions

| Question | Decision |
|---|---|
| Plane area calculation | OBB-based (fast, no scipy dep). ConvexHull deferred. |
| Multi-floor in single pass | Yes — detect both floor AND ceiling in one `_sync_filter` call. |
| Coordinate frame assumption | Trust user config; document Z-up in `help_text`. |
| WebSocket metadata | `plane_details` in `payload["metadata"]` only (no dedicated WS stream). |
| Threadpool sizing | `asyncio.to_thread()` (shared pool). Isolated executor deferred. |
| **Downsampling index mapping** | **KD-tree nearest-neighbor** (radius = `voxel_size / 2`). Fast C++ backed, high accuracy. |
| **Downsampling attribute averaging** | Open3D `voxel_down_sample()` averages attributes natively — no custom logic needed. |
