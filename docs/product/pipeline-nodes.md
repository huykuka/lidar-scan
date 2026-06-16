# Pipeline Nodes

The pipeline is a DAG of operation nodes. Each node receives a point cloud
frame, applies a transformation, and forwards the result to downstream nodes.
Nodes are registered by type name and instantiated with a config dict.

## Node Types

### Sensor Nodes

Receive frames from LiDAR hardware or PCD file injection.

### Operation Nodes

Apply a single point cloud transformation. All operation nodes:
- Accept an `o3d.t.geometry.PointCloud` via `apply(pcd)`.
- Return `(pcd_out, metadata_dict)`.
- Are registered in `app/modules/pipeline/operation_node.py:_OP_MAP`.

Current operation types:

| Type | Description |
| --- | --- |
| `crop` | Bounding-box filter |
| `downsample` | Voxel downsampling |
| `uniform_downsample` | Uniform random downsampling |
| `statistical_outlier_removal` | Statistical outlier filter |
| `radius_outlier_removal` | Radius-based outlier filter |
| `plane_segmentation` | RANSAC plane segmentation |
| `patch_plane_segmentation` | Patch-based plane segmentation |
| `clustering` | DBSCAN clustering |
| `filter` | Field range filter |
| `filter_by_key` | Filter by named field |
| `boundary_detection` | Boundary point detection |
| `debug_save` | Save frame to disk for debugging |
| `generate_plane` | Generate a planar mesh from segmented cloud |
| `densify` | Point cloud densification |
| `surface_reconstruction` | Alpha/BPR/Poisson surface mesh |
| `centroid_calculation` | Centroid computation |
| `coordinate_transform` | Rigid coordinate frame transform |
| `edge_detection` | Edge feature extraction |
| `plane_projection` | Axis-aligned orthographic projection (see below) |
| `range_image` | Bird's-Eye View range image generator (see below) |

---

## `plane_projection`

Projects every point onto an axis-aligned plane by zeroing one coordinate.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `axis` | `"x"` \| `"y"` \| `"z"` | `"z"` | The axis coordinate to set to zero |

Plane mapping:

| `axis` | Zeroed column | Projection plane |
| --- | --- | --- |
| `z` | Z → 0 | XY (top-down / floor) |
| `y` | Y → 0 | XZ (front view) |
| `x` | X → 0 | YZ (side view) |

All columns beyond XYZ (layer, azimuth, intensity, …) are preserved unchanged.

**Metadata keys:** `projected_axis`, `projection_plane`, `point_count`,
`mean_dropped_coord`

---

## `range_image`

Generates a Bird's-Eye View (BEV) grayscale image from the point cloud and
broadcasts it as a binary WebSocket frame on the node's own topic.

The input point cloud is forwarded to downstream DAG nodes **unchanged**
(pass-through). This node is a side-effect-only image producer.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `resolution` | float | `0.1` | Grid cell size in metres (m/pixel) |
| `x_min` | float | `-25.0` | Left edge of the BEV ROI in metres |
| `x_max` | float | `25.0` | Right edge of the BEV ROI in metres |
| `y_min` | float | `-25.0` | Bottom edge of the BEV ROI in metres |
| `y_max` | float | `25.0` | Top edge of the BEV ROI in metres |
| `channel` | `"height"` \| `"density"` \| `"intensity"` | `"height"` | Signal encoded as pixel brightness |

**Channel descriptions:**

| Channel | Accumulation rule |
| --- | --- |
| `height` | Maximum Z value of all points in the cell |
| `density` | Count of points in the cell |
| `intensity` | Mean intensity of all points in the cell (falls back to density if no intensity column) |

**WebSocket wire format:**

Binary frame: `BEVI` (4 bytes) + header length (uint32 LE) + JSON header + PNG bytes.

JSON header fields: `type`, `channel`, `resolution`, `x_min`, `x_max`,
`y_min`, `y_max`, `width`, `height`, `timestamp`, `point_count`,
`filled_cells`.

**Metadata keys:** `channel`, `resolution_m`, `image_width`, `image_height`,
`point_count`, `filled_cells`, `fill_ratio`

---

## Adding a New Operation Node

1. Create `app/modules/pipeline/operations/<type>/node.py` — subclass
   `PipelineOperation`, implement `apply(pcd) -> (pcd_out, metadata)`.
2. Create `__init__.py` re-exporting the class.
3. Create `registry.py` — `NodeDefinition` schema + `@NodeFactory.register`.
4. Add the import to `operations/__init__.py`.
5. Add the `"type_name": ClassName` entry to `_OP_MAP` in
   `operation_node.py`.
6. Add the registry import to `pipeline/registry.py` and `__all__`.
