# QA Tasks: Unified Sensor Pose Entity

**Feature:** `sensor-pose-entity`  
**References:** `requirements.md` · `technical.md` · `api-spec.md` · `backend-tasks.md` · `frontend-tasks.md`  
**QA Agent:** @qa  
**Status:** Not Started

---

## Phase 0 — TDD Preparation (Before Development Starts)

- [ ] **Q-01** Verify failing test skeletons exist for all backend test files listed in `backend-tasks.md` before implementation:
  - `tests/schemas/test_pose.py` — skeleton with `@pytest.mark.xfail` markers
  - `tests/modules/test_sensor_pose.py`
  - `tests/modules/test_build_sensor.py`
  - `tests/api/test_nodes_pose.py`
  - `tests/api/test_calibration_rollback_pose.py`

- [ ] **Q-02** Verify failing test skeletons exist for all frontend test files:
  - `pose-form.component.spec.ts`
  - `sensor-node-editor.component.spec.ts` (updated)
  - `sensor-node-card.component.spec.ts` (updated)
  - `node-recording-controls.spec.ts` (updated)

- [ ] **Q-03** Confirm all new test files fail at start (red baseline). Document in `qa-report.md`.

---

## Phase 1 — Backend Unit Tests

### Pose Model Validation (`tests/schemas/test_pose.py`)

- [ ] **Q-04** `Pose()` defaults all fields to `0.0`
- [ ] **Q-05** `Pose(x=100, y=-50, z=800, roll=0, pitch=-5, yaw=45)` constructs successfully
- [ ] **Q-06** `Pose(roll=180.0)` passes; `Pose(roll=180.001)` raises `ValidationError`
- [ ] **Q-07** `Pose(roll=-180.0)` passes; `Pose(roll=-180.001)` raises `ValidationError`
- [ ] **Q-08** Same boundary checks for `pitch` and `yaw` (6 checks total)
- [ ] **Q-09** `Pose(x=float('nan'))` raises `ValidationError`
- [ ] **Q-10** `Pose(x=float('inf'))` raises `ValidationError`
- [ ] **Q-11** `Pose.zero()` returns `Pose(x=0, y=0, z=0, roll=0, pitch=0, yaw=0)`
- [ ] **Q-12** `pose.to_flat_dict()` returns `{'x': 0.0, 'y': 0.0, 'z': 0.0, 'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0}`
- [ ] **Q-13** Frozen model: `pose.x = 1.0` raises `ValidationError` (immutability)

### LidarSensor Pose (`tests/modules/test_sensor_pose.py`)

- [ ] **Q-14** `sensor.set_pose(Pose(x=100, yaw=45))` updates `transformation` matrix (non-identity)
- [ ] **Q-15** `sensor.get_pose_params()` returns a `Pose` instance with correct values
- [ ] **Q-16** `set_pose(Pose.zero())` produces identity-equivalent transformation

### Build Sensor Factory (`tests/modules/test_build_sensor.py`)

- [ ] **Q-17** `build_sensor(node={"pose": {"x":100, "yaw":45, ...}})` → sensor has correct pose
- [ ] **Q-18** `build_sensor(node={"pose": {}})` → sensor defaults to `Pose.zero()`
- [ ] **Q-19** `build_sensor(node={})` (no pose key) → sensor defaults to `Pose.zero()`

### DB Migration (`tests/modules/test_migration_backfill.py`)

- [ ] **Q-20** Insert node row with flat pose keys (`x`, `y`, `z`, `roll`, `pitch`, `yaw`) at the top level of `config_json`; run `ensure_schema()`; assert `config["pose"]` is a nested dict with correct values and flat keys are removed from the top-level config
- [ ] **Q-21** Run `ensure_schema()` twice on same DB — second run is idempotent (no data corruption; `config["pose"]` is not double-nested)
- [ ] **Q-22** Non-sensor node rows (fusion, calibration) whose `config_json` has no pose keys are untouched by backfill

---

## Phase 2 — Backend Integration Tests

### API Contract Tests (`tests/api/test_nodes_pose.py`)

- [ ] **Q-23** `POST /nodes` with valid `pose` object → `200`, round-trip `GET /nodes/{id}` returns same pose values
- [ ] **Q-24** `POST /nodes` with `pose.yaw = 180` → `200` (boundary)
- [ ] **Q-25** `POST /nodes` with `pose.yaw = -180` → `200` (negative boundary)
- [ ] **Q-26** `POST /nodes` with `pose.yaw = 181` → `422` (over boundary)
- [ ] **Q-27** `POST /nodes` with `pose.yaw = -181` → `422` (under boundary)
- [ ] **Q-28** `POST /nodes` with `config.x = 100` (flat pose key in config) → `422` with error detail mentioning deprecated key
- [ ] **Q-29** `POST /nodes` with `config.roll = 45` → `422`
- [ ] **Q-30** `GET /nodes` → sensor node response contains `pose` object with all 6 fields
- [ ] **Q-31** `GET /nodes` → fusion node response contains `"pose": null`
- [ ] **Q-32** `GET /nodes/{id}` returns `pose` object for sensor node
- [ ] **Q-33** `POST /nodes` with `pose: null` for sensor node → defaults to zero pose stored in DB

### Calibration Rollback Pose (`tests/api/test_calibration_rollback_pose.py`)

- [ ] **Q-34** Rollback writes restored pose to `config_json["pose"]` (not to a separate `pose_json` column, not as flat keys in config)
- [ ] **Q-35** After rollback, `GET /nodes/{sensor_id}` reflects restored pose values
- [ ] **Q-36** Calibration accept: `GET /nodes/{sensor_id}` after accept shows `pose_after` values

---

## Phase 3 — Frontend Unit Tests

### PoseFormComponent

- [ ] **Q-37** Renders 3 `syn-input` (x, y, z) and 3 `syn-range` (roll, pitch, yaw) controls
- [ ] **Q-38** `resetPose()` sets all form controls to 0 and emits `poseChange` with `ZERO_POSE`
- [ ] **Q-39** `poseChange` emits correct value when a slider fires `syn-input` event
- [ ] **Q-40** `poseChange` emits correct value when a numeric input changes
- [ ] **Q-41** Validation — roll=181: `angleRange` error visible; control is invalid
- [ ] **Q-42** Validation — roll=180: no error; control is valid
- [ ] **Q-43** Validation — roll=-180: no error; control is valid
- [ ] **Q-44** Validation — roll=-181: `angleRange` error visible
- [ ] **Q-45** Input signal change (`pose` input) propagates to all 6 form controls

### SensorNodeEditorComponent

- [ ] **Q-46** `PoseFormComponent` is rendered in the sensor editor
- [ ] **Q-47** `onSave()` payload includes `pose` field with current form values
- [ ] **Q-48** Save button is disabled when `PoseFormComponent` is invalid (roll=270)
- [ ] **Q-49** Reset Pose action updates `poseValue` signal to `ZERO_POSE`

### SensorNodeCardComponent

- [ ] **Q-50** `pose()` computed reads from `node.data.pose.x`, not `node.data.config['x']`
- [ ] **Q-51** `rotation()` reads from `node.data.pose.roll`, not `node.data.config['roll']`
- [ ] **Q-52** Falls back to `ZERO_POSE` when `node.data.pose` is `null`/`undefined`

### NodeRecordingControls

- [ ] **Q-53** `metadata.pose` is set from `data.pose` (top-level), not `config.pose`
- [ ] **Q-54** `metadata.pose` is no longer `undefined` for sensor nodes

---

## Phase 4 — Frontend Linter & Type Check

- [ ] **Q-55** Run TypeScript compiler check:
  ```bash
  cd web && npx tsc --noEmit
  ```
  Zero errors.

- [ ] **Q-56** Run ESLint:
  ```bash
  cd web && npx ng lint
  ```
  Zero errors (warnings reviewed and documented if acceptable).

---

## Phase 5 — Backend Linter & Type Check

- [ ] **Q-57** Run Ruff linter:
  ```bash
  ruff check app/
  ```
  Zero errors.

- [ ] **Q-58** Run Pyright or mypy type check on affected modules:
  ```bash
  pyright app/schemas/pose.py app/modules/lidar/ app/modules/calibration/ app/api/v1/nodes/
  ```
  No type errors on pose-related paths.

---

## Phase 6 — E2E Tests

- [ ] **Q-59** **Create sensor with custom pose:**
  1. Open sensor creation form.
  2. Set X=100, Y=50, Z=200 via `syn-input` controls.
  3. Drag Roll slider to 30° using `syn-range`.
  4. Drag Yaw slider to -90°.
  5. Save sensor.
  6. Verify sensor card shows correct pose values.
  7. Verify `GET /nodes/{id}` returns `pose: {x:100, y:50, z:200, roll:30, pitch:0, yaw:-90}`.

- [ ] **Q-60** **Reset pose:**
  1. Load existing sensor with non-zero pose.
  2. Click "Reset Pose" button.
  3. Verify all 6 controls show 0.
  4. Save.
  5. Verify `GET /nodes/{id}` returns `pose: {x:0, y:0, z:0, roll:0, pitch:0, yaw:0}`.

- [ ] **Q-61** **Angle boundary enforcement:**
  1. Attempt to type 270 into the Roll numeric companion (if editable).
  2. Verify inline validation error appears.
  3. Verify save button is disabled.

- [ ] **Q-62** **DAG reload after pose update:**
  1. Update sensor pose via form.
  2. Trigger `POST /nodes/reload`.
  3. Verify `LidarSensor.get_pose_params()` returns the updated pose in backend runtime.

- [ ] **Q-63** **Legacy flat-key API rejection (regression guard):**
  1. Send `POST /api/v1/nodes` with `config: { x: 100, roll: 45 }` (old format).
  2. Verify HTTP 422 response.
  3. Verify error message mentions deprecated keys.

---

## Phase 7 — Backward Compatibility Verification

- [ ] **Q-64** Verify NO sensor node in the system has flat pose keys (`x`, `y`, `z`, `roll`, `pitch`, `yaw`) at the top level of `config_json` after migration (DB query verification — all pose must be nested under `config["pose"]`).
- [ ] **Q-65** Verify calibration history records (`pose_before_json`, `pose_after_json`) are untouched and still parseable as valid flat-dict JSON after migration.
- [ ] **Q-66** Verify `LidarPose` interface is fully removed from `lidar.model.ts` (no remaining usages via grep).
- [ ] **Q-67** Verify inline anonymous pose type is fully removed from `recording.model.ts`.
- [ ] **Q-68** Verify no `config['x']`, `config['roll']` etc. remain in frontend component code (grep).

---

## Phase 8 — Pre-PR Final Verification

- [ ] **Q-69** All backend unit tests pass: `pytest tests/ -v`
- [ ] **Q-70** All frontend unit tests pass: `cd web && npx ng test --watch=false`
- [ ] **Q-71** TypeScript check passes: `cd web && npx tsc --noEmit`
- [ ] **Q-72** Backend linter clean: `ruff check app/`
- [ ] **Q-73** Frontend linter clean: `cd web && npx ng lint`
- [ ] **Q-74** Application starts without errors: `python main.py` — no import errors, DB migration runs cleanly
- [ ] **Q-75** Swagger UI (`/docs`) shows `Pose` schema with all 6 fields and correct validation annotations

---

## Developer Coordination Checkpoints

- [ ] **Q-76** Backend B-07 (`NodeRecord` schema updated) complete → frontend can switch from mock to real API
- [ ] **Q-77** Backend B-10 (`build_sensor` factory) complete → E2E tests Q-59..Q-62 unblocked
- [ ] **Q-78** Frontend F-09 (`PoseFormComponent` HTML) complete → QA can begin UI validation tests Q-37..Q-45

---

## Known Risk Items (Monitor During QA)

| Item | Risk | Test |
|---|---|---|
| `syn-range` emits string, not number | Component may store string "0" instead of number 0 | Q-39: assert `typeof emittedValue.roll === 'number'` |
| Angle boundaries ±180 at slider edge | `syn-range` may not reach exactly -180 | Q-42, Q-43: use programmatic `patchValue` for boundary test |
| DB backfill skips non-zero default rows | Existing prod sensors with non-zero pose may not migrate | Q-20, Q-21 |
| Canvas `x`/`y` vs pose `x`/`y` naming | Wrong field used in template | Q-50, Q-51 |
