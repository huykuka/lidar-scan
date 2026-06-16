# US-001 Plane projection and BEV range image pipeline nodes

## Status

completed

## Lane

normal

## Product Contract

The pipeline DAG must support two new operation node types:

1. **plane_projection** — projects every point in a 3D point cloud onto one of
   the three axis-aligned planes (XY, XZ, or YZ) by zeroing the chosen axis
   coordinate. All extra columns (layer, azimuth, intensity, …) are preserved
   unchanged.

2. **range_image** — generates a Bird's-Eye View (BEV) grayscale image from the
   point cloud and broadcasts it as a binary WebSocket frame on the node's own
   topic. The input point cloud is forwarded unchanged to downstream DAG nodes
   (pass-through). Supported channels: `height` (max Z), `density` (point count),
   and `intensity` (mean intensity per cell).

## Relevant Product Docs

- `docs/product/pipeline-nodes.md`

## Acceptance Criteria

- `plane_projection` node zeroes the chosen axis column; all other columns are
  unchanged; metadata includes `projection_plane`, `projected_axis`,
  `point_count`, `mean_dropped_coord`.
- `plane_projection` accepts `axis` values `x`, `y`, and `z`; invalid values
  raise `ValueError` at construction.
- `range_image` node returns the original input `pcd` object unchanged.
- `range_image` metadata includes `image_width`, `image_height`, `filled_cells`,
  `fill_ratio`, `point_count`, and `channel`.
- `range_image` broadcasts a `BEVI`-framed binary WebSocket message when
  `_ws_topic` is set.
- Both node types are registered in `_OP_MAP`, `operations/__init__.py`, and
  `pipeline/registry.py` so the DAG can instantiate them by name.
- `OperationNode.on_input()` bridges `_ws_topic` from the wrapper node into
  `self.op._ws_topic` before each frame so ops like `RangeImage` can read it.

## Design Notes

- `PlaneProjection`: single numpy slice-assign on `positions`, then copies all
  non-position attributes via `_tensor_map_keys()`. Sub-millisecond overhead.
- `RangeImage`: pure-numpy BEV accumulation with `np.maximum.at` for height
  and `np.add.at` for density/intensity. Uses Pillow for PNG encoding with
  PGM fallback when Pillow is absent. The broadcast uses
  `asyncio.ensure_future` so it does not block the background thread.
- `_ws_topic` bridge in `OperationNode.on_input()`: checks
  `hasattr(self.op, "_ws_topic")` before assignment to avoid polluting ops
  that do not declare it.
- Both ops registered with `websocket_enabled=True` so the orchestrator assigns
  a topic slug at startup.

## Validation

| Layer | Expected proof |
| --- | --- |
| Unit | Import, instantiation, and apply() smoke tests via `uv run python` — passed |
| Integration | Not yet: no automated test file; DAG wiring via live app not verified |
| E2E | Not yet |
| Platform | Not yet |
| Release | Not yet |

## Harness Delta

- Harness was not consulted before implementation began. Retroactive intake,
  story, and trace were recorded after the code was merged.
- Backlog item added: `plane-projection-range-image-harness-first` to capture
  the pre-intake gap as friction.

## Evidence

```
uv run python -c "
from app.modules.pipeline.operations.plane_projection.node import PlaneProjection
from app.modules.pipeline.operations.range_image.node import RangeImage
...
All assertions passed.
"
```
