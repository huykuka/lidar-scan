# QA Tasks: Environment Filtering Node

References:
- Requirements: `.opencode/plans/environment-filtering/requirements.md`
- Technical: `.opencode/plans/environment-filtering/technical.md`
- API Spec: `.opencode/plans/environment-filtering/api-spec.md`

---

## Phase 1 — TDD Preparation (Before Development)

- [ ] Create `tests/modules/application/test_environment_filtering.py` with all test stubs (failing) before `@be-dev` implements `node.py`
- [ ] Create `tests/modules/application/test_environment_filtering_integration.py` stubs
- [ ] Verify all stubs fail with `ImportError` or `NotImplementedError` (confirm red state)
- [ ] Stubs must include downsampling test cases (see Phase 2) **(NEW)**

---

## Phase 2 — Unit Tests

Coordinate with `@be-dev` `backend-tasks.md Phase 4` completion.

- [ ] `TestInstantiation` — all fixtures pass, `voxel_downsample_size=0.01` default verified
- [ ] `TestParamValidation` — 6 `ValueError` cases verified (4 original + 2 new for `voxel_downsample_size`)
- [ ] `TestEmptyInput` — pass-through confirmed, no exceptions, downsample meta present
- [ ] `TestNoPlanes` — `status="no_planes_detected"`, `planes_detected=0`, downsample meta present
- [ ] `TestNoValidPlanes` — `status="warning_pass_through"`, `planes_filtered=0`
- [ ] `TestOrientationCheck` — boundary at `vertical_tolerance_deg` verified
- [ ] `TestPositionCheck` — floor/ceiling height range boundaries verified
- [ ] `TestSizeCheck` — `min_plane_area` threshold verified
- [ ] `TestMultiCriteriaAND` — 2-of-3 criteria failing causes no removal
- [ ] `TestSuccessfulFiltering` — point count decreases, `planes_filtered >= 1`
- [ ] `TestAttributePreservation` — intensity/normals preserved on remaining points
- [ ] `TestMetadataShape` — all keys from `api-spec.md § 5` present (including all downsample fields) **(UPDATED)**
- [ ] `TestEmitStatus*` — ERROR / WARNING orange / RUNNING blue / idle gray
- [ ] **`TestDownsamplingDisabled`** (NEW) — `voxel_downsample_size=0`: `downsampling_enabled=False`, `points_before == points_after`, output at full resolution
- [ ] **`TestDownsamplingDefault`** (NEW) — `voxel_downsample_size=0.01`: `downsampling_enabled=True`, reduced intermediate cloud, correct plane removal on original
- [ ] **`TestDownsamplingAggressive`** (NEW) — small voxel on sparse cloud → warning logged, no exception, `status="warning_low_point_density"` if < 100 pts
- [ ] **`TestIndexMapping`** (NEW) — removed original points are geometrically within `voxel_size/2` of downsampled plane points
- [ ] **`TestOutputAtOriginalResolution`** (NEW) — output point count = `input_count - removed_count`, NOT downsampled count
- [ ] **`TestDownsamplingMetadata`** (NEW) — `points_before_downsample`, `points_after_downsample`, `voxel_size` correct across all status paths

Minimum: **≥ 20 distinct test cases must pass** (was 15).

---

## Phase 3 — Integration Tests

- [ ] Chain test: `Downsampling → EnvironmentFiltering → HelloWorld` — mock manager receives forwarded payload
- [ ] Config round-trip: serialize node to JSON, reload DAG, verify all **14** params match **(UPDATED)**
- [ ] WebSocket topic registration: `TestRealNodeDefinitions` pattern — add `"environment_filtering"` to real-definition suite
- [ ] Circular import: extend `test_all_module_registries_loaded` to import `environment_filtering_registry`
- [ ] **Dense cloud end-to-end** (NEW): 100k-point cloud with `voxel_downsample_size=0.01` → pipeline < 150ms, output at original resolution

---

## Phase 4 — Performance Tests

- [ ] Benchmark: 10k pts, `voxel_downsample_size=0` → `_sync_filter` < 50ms median **(UPDATED: note no downsampling)**
- [ ] Benchmark: 50k pts, `voxel_downsample_size=0.01` → `_sync_filter` < 100ms median
- [ ] Benchmark: 200k pts, `voxel_downsample_size=0.01` → `_sync_filter` < 200ms median **(UPDATED from 300ms)**
- [ ] **Downsampling step isolation** (NEW): measure `_voxel_downsample()` alone for 100k pts → must complete < 20ms
- [ ] **Speedup verification** (NEW): compare `_sync_filter` with vs. without `voxel_downsample_size=0.01` on 100k pts — verify ≥ 2× speedup for segmentation step
- [ ] **Index mapping overhead** (NEW): measure `_map_indices_to_original()` for 100k original pts, 5k plane pts → < 15ms
- [ ] Throttle test: `throttle_ms=50` + 30Hz input → frames skipped, output count ≤ 20/sec
- [ ] Memory test: peak allocation ≤ 1.5× input size (includes temporary downsampled cloud) **(UPDATED from 2×)**

---

## Phase 5 — Edge Case Validation

- [ ] Outdoor scene (no horizontal planes) → `status="no_planes_detected"`, original full-res cloud returned
- [ ] Sloped floor (20°): fails at `vertical_tolerance_deg=15`, passes at `vertical_tolerance_deg=25`
- [ ] Mezzanine (Z=0 and Z=1.5) → only Z=0 removed with default `floor_height_range=[-0.5, 0.5]`
- [ ] Warehouse ceiling at Z=10m → not removed with default range, removed after `ceiling_height_max=12.0`
- [ ] **Dense scan (200k pts), `voxel_downsample_size=0`** (NEW) → no memory overflow, completes (may be slow)
- [ ] **Sparse scan (5k pts), `voxel_downsample_size=0.05`** (NEW) → warning logged, result still valid
- [ ] **Pass-through always at original resolution** (NEW) → in all error/warning paths, confirm returned cloud matches input point count exactly

---

## Phase 6 — Linter & Pre-PR

- [ ] Run `ruff check app/modules/application/environment_filtering/` — 0 errors
- [ ] Run `mypy app/modules/application/environment_filtering/` — 0 type errors
- [ ] Run full backend test suite: `pytest tests/` — no regressions
- [ ] Verify `@be-dev` has checked off all tasks in `backend-tasks.md`
- [ ] Verify `@fe-dev` has checked off all tasks in `frontend-tasks.md`

---

## Phase 7 — QA Report

- [ ] Complete `qa-report.md` with: test count (≥ 20), pass rate, benchmark measurements (with/without downsampling comparison), index-mapping accuracy results, any deferred items
