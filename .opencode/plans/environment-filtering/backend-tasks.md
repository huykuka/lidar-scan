# Backend Tasks: Environment Filtering Node

References:
- Requirements: `.opencode/plans/environment-filtering/requirements.md`
- Technical: `.opencode/plans/environment-filtering/technical.md`
- API Spec: `.opencode/plans/environment-filtering/api-spec.md`

---

## Phase 1 — Scaffold

- [x] Create directory `app/modules/application/environment_filtering/`
- [x] Create `app/modules/application/environment_filtering/__init__.py` (empty)
- [x] Create `app/modules/application/environment_filtering/node.py` (see Phase 2)
- [x] Create `app/modules/application/environment_filtering/registry.py` (see Phase 3)
- [x] Add import to `app/modules/application/registry.py`:
  ```python
  from .environment_filtering import registry as environment_filtering_registry
  __all__ = ["hello_world_registry", "environment_filtering_registry"]
  ```

---

## Phase 2 — `node.py`: `EnvironmentFilteringNode`

- [x] Import: `ModuleNode`, `PatchPlaneSegmentation`, `PointConverter`, `notify_status_change`, status schemas, `asyncio`, `numpy`, `open3d`
- [x] Define `PlaneInfo` dataclass (or TypedDict): `plane_id`, `plane_type`, `normal`, `centroid_z`, `area`, `point_count`
- [x] Implement `__init__`:
- [x] Implement `_validate_params(self) -> None`:
- [x] Implement `_voxel_downsample(self, pcd_tensor) -> Tuple[Any, Dict]` **(NEW)**:
- [x] Implement `_map_indices_to_original(self, plane_pts_ds, orig_pts, radius) -> np.ndarray` **(NEW)**:
- [x] Implement `_apply_with_boxes(self, legacy_pcd) -> Tuple[List, np.ndarray, np.ndarray]`:
- [x] Implement `_classify_plane(self, obox, labels, points_np, plane_idx) -> Optional[PlaneInfo]`:
- [x] Implement `_sync_filter(self, pcd_in) -> Tuple[Any, Dict]` (blocking, runs in thread):
- [x] Implement `async on_input(self, payload)`:
- [x] Implement `emit_status(self) -> NodeStatusUpdate`:

---

## Phase 3 — `registry.py`

- [x] Register `NodeDefinition` with all `PropertySchema` entries per `api-spec.md § 3` — **14 properties** (includes `voxel_downsample_size` in Group A)
- [x] `voxel_downsample_size` PropertySchema: `type="number"`, `default=0.01`, `min=0.0`, `max=1.0`, `step=0.005`, with full help_text from `api-spec.md`
- [x] Group A help_text includes both `throttle_ms` and `voxel_downsample_size`
- [x] Register `PortSchema` inputs/outputs
- [x] Implement `@NodeFactory.register("environment_filtering")` builder:

---

## Phase 4 — Unit Tests

File: `tests/modules/application/test_environment_filtering.py`

- [x] Fixtures: `mock_manager`, `default_node`, `node_with_config(config)` factory fixture
- [x] `TestInstantiation`: defaults applied (`voxel_downsample_size=0.01`), `PatchPlaneSegmentation` instantiated, `_processing=False`
- [x] `TestParamValidation`: all 7 validation cases including `voxel_downsample_size`
- [x] `TestEmptyInput`: 0-pt cloud → pass-through, `status="warning_pass_through"`, no exception
- [x] `TestNoPlanes`: no horizontal planes → pass-through, `status="no_planes_detected"`
- [x] `TestNoValidPlanes`: planes detected but none pass validation → `status="warning_pass_through"`
- [x] `TestOrientationCheck`: plane at 10°/20° angle tests with 15° tolerance
- [x] `TestPositionCheck`: floor Z=0.1 (pass), Z=1.5 (fail); ceiling Z=2.5 (pass), Z=5.0 (fail)
- [x] `TestSizeCheck`: 10m² passes, 0.3m² fails default `min_plane_area=1.0`
- [x] `TestMultiCriteriaAND`: passes orientation+position but fails size → no removal
- [x] `TestMetadataShape`: verify all keys match `api-spec.md § 5` including all downsampling fields
- [x] `TestEmitStatusError/Warning/Idle` — status badge states
- [x] **`TestDownsamplingDisabled`** (NEW): `voxel_downsample_size=0` → `downsampling_enabled=False`
- [x] **`TestDownsamplingDefault`** (NEW): `voxel_downsample_size=0.01` → `downsampling_enabled=True`
- [x] **`TestDownsamplingAggressive`** (NEW): warning logged, no exception
- [x] **`TestIndexMapping`** (NEW): KD-tree radius search maps correctly
- [x] **`TestOutputAtOriginalResolution`** (NEW): output = input - removed
- [x] **`TestDownsamplingMetadata`** (NEW): fields present in all metadata paths

---

## Phase 5 — Integration Tests

File: `tests/modules/application/test_environment_filtering_integration.py`

- [x] Test config persistence: build node from JSON config with `voxel_downsample_size`, verify all 14 params stored correctly
- [x] Test NodeFactory and schema registration (14 properties, websocket_enabled, ports)
- [x] Test factory builder creates correct instance and handles edge cases
- [x] Test `on_input` end-to-end: payload forwarded, metadata injected, skip-if-busy
- [ ] Test `Downsampling → EnvironmentFiltering → HelloWorld` chain via mock manager
- [ ] Test WebSocket topic registration
- [ ] **Downsampling end-to-end** (NEW): dense synthetic cloud (100k pts), `voxel_downsample_size=0.01` → verify pipeline completes in < 150ms and output is at original resolution

---

## Dependencies / Order of Operations

1. Phase 1 (scaffold) must complete before Phase 2/3
2. Phase 2 (`node.py`) must be complete before Phase 3 (lazy import)
3. Phase 3 must be complete before Phase 4/5 tests import the registry
4. No frontend dependency — backend is self-contained
