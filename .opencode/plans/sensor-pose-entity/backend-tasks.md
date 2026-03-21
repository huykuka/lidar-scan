# Backend Tasks: Unified Sensor Pose Entity

**Feature:** `sensor-pose-entity`  
**References:** `requirements.md` · `technical.md` · `api-spec.md`  
**Developer:** @be-dev  
**Status:** Not Started

> ⚠️ **Breaking Change.** All flat pose fields (`x`, `y`, `z`, `roll`, `pitch`, `yaw`) are removed
> from `config_json`. This refactor touches the DB schema, ORM layer, DAG registry, calibration
> pipeline, and all API schemas. Follow tasks in order.

---

## Phase 0 — Foundation

- [ ] **B-01** Create `app/schemas/pose.py`:
  - Define frozen Pydantic V2 `Pose` model with six fields.
  - `x`, `y`, `z`: `Annotated[float, Field(allow_inf_nan=False)]`
  - `roll`, `pitch`, `yaw`: `Annotated[float, Field(ge=-180.0, le=180.0, allow_inf_nan=False)]`
  - Add `model_config = ConfigDict(frozen=True)`
  - Add `Pose.zero() -> Pose` classmethod
  - Add `Pose.to_flat_dict() -> dict[str, float]` method
  - Add `__init__.py` export in `app/schemas/__init__.py`

- [ ] **B-02** Add `Pose` to `app/schemas/__init__.py` so it is importable as `from app.schemas import Pose`.

---

## Phase 1 — Database Migration (Data-Only, No DDL)

- [ ] **B-03** Update `app/db/models.py — NodeModel.to_dict()`:
  - **No new column is added.** The `nodes` table schema is unchanged.
  - Update `to_dict()` to parse `config_json`, pop the `"pose"` sub-key out of the config dict, and return it at the top level:
    ```python
    config = json.loads(self.config_json) if self.config_json else {}
    pose = config.pop("pose", None)   # local mutation only — does not touch the DB row
    return { ..., "config": config, "pose": pose, ... }
    ```
  - Ensure canvas `x`/`y` remain at top-level (no naming conflict with pose).

- [ ] **B-04** Update `app/db/migrate.py — ensure_schema()`:
  - Add `_backfill_pose_into_config(conn)` helper function (no DDL — data-only backfill):
    - Reads all `nodes` rows.
    - Skips rows that already have `config["pose"]`.
    - For rows with flat pose keys (`x`, `y`, `z`, `roll`, `pitch`, `yaw`) at the top level of `config_json`, migrates them into a nested `config["pose"]` dict and removes the flat keys.
    - Writes updated `config_json` back to the row.
  - Must be idempotent: running `ensure_schema()` twice produces no data corruption.
  - Call `_backfill_pose_into_config(conn)` at the end of `ensure_schema()`.

- [ ] **B-05** Verify migration runs cleanly against existing `config/data.db` (if present). Write a migration smoke test in `tests/modules/` that creates a fake node with flat pose keys in `config_json`, runs `ensure_schema()`, and asserts that `config["pose"]` is populated and flat keys are removed from `config`.

---

## Phase 2 — Repository Layer

- [ ] **B-06** Update `app/repositories/node_orm.py — NodeRepository`:
  - `upsert()` method: accept `"pose"` key from payload dict and serialize it into `config_json["pose"]` (merge into config blob); reject flat pose keys inside `"config"` dict (raise `ValueError` — service layer catches and raises HTTP 422).
  - Add `update_node_pose(node_id: str, pose: Pose) -> None` method:
    - Reads current `config_json`, deserializes, updates `config["pose"]` with `pose.to_flat_dict()`, and writes back to `config_json`. Faster targeted update for calibration accept/rollback paths.
  - `get_by_id()` / `list()` return dicts via `NodeModel.to_dict()` — pose is already surfaced at top-level by B-03.

---

## Phase 3 — Schema / API Layer

- [ ] **B-07** Update `app/api/v1/schemas/nodes.py — NodeRecord`:
  - Add `pose: Optional[Pose] = None` field
  - Import `Pose` from `app.schemas.pose`
  - Update `json_schema_extra` example to include `"pose"` object (see `api-spec.md §3.1`)

- [ ] **B-08** Update `app/api/v1/nodes/service.py — NodeCreateUpdate`:
  - Add `pose: Optional[Pose] = None` field
  - In `upsert_node()`: detect flat pose keys in `req.config` and raise `HTTPException(422, detail=...)`
  - Pass `pose: req.pose or Pose.zero()` as a top-level key to the repository `upsert()` call, which stores it inside `config_json["pose"]`

---

## Phase 4 — DAG / Module Layer

- [ ] **B-09** Update `app/modules/lidar/sensor.py — LidarSensor`:
  - Change `set_pose(x, y, z, roll, pitch, yaw)` → `set_pose(pose: Pose) -> LidarSensor`
  - `self.pose_params` is now typed as `Pose` (not `Dict[str, float]`)
  - Update `get_pose_params() -> Pose` return type
  - Update internal `pose_params` initialization to `Pose.zero()`

- [ ] **B-10** Update `app/modules/lidar/registry.py`:
  - Remove 6 flat `PropertySchema` entries (`x`, `y`, `z`, `roll`, `pitch`, `yaw`)
  - Add a single `PropertySchema(name="pose", label="Sensor Pose", type="pose", default={...})`
  - Update `build_sensor()` factory:
    - Read `node["pose"]` (dict) instead of individual `config.get("x", 0)` etc.
    - Construct `pose = Pose(**node.get("pose", {}))` — validated
    - Call `sensor.set_pose(pose)` with the new signature
    - Remove the 6 individual `float(config.get(...))` lines

- [ ] **B-11** Update `app/modules/calibration/calibration_node.py`:
  - Import `Pose` from `app.schemas.pose`
  - In `trigger_calibration()`: read current pose as `Pose(**node_config.get("pose", {}))` (via the repo `node["pose"]` key)
  - After ICP: construct `new_pose = Pose(**extract_pose_from_matrix(T_new))` — validate here
  - Replace 6-key flat write in `accept_calibration()` with `repo.update_node_pose(sensor_id, Pose(**record.pose_after))`; this writes into `config_json["pose"]`
  - `pose_before`, `pose_after` in result dicts use `Pose.to_flat_dict()` for serialization to history records

- [ ] **B-12** Update `app/modules/calibration/history.py`:
  - `CalibrationAttempt.pose_before: Pose` (typed, not `Dict[str, float]`)
  - `CalibrationAttempt.pose_after: Pose`
  - Update all callers that construct `CalibrationAttempt` to pass `Pose` objects

---

## Phase 5 — Calibration API Rollback Path

- [ ] **B-13** Update `app/api/v1/calibration/service.py — rollback_calibration()`:
  - Replace the 6-key flat `repo.update_node_config(sensor_id, {**existing_config, "x": ..., "roll": ...})` block
  - Use: `pose = Pose(**json.loads(record.pose_after_json)); repo.update_node_pose(sensor_id, pose)`
  - `update_node_pose` will write the pose into `config_json["pose"]` (not a separate column)

---

## Phase 6 — Node Definition / Schema Registry

- [ ] **B-14** Update `app/services/nodes/schema.py — PropertySchema`:
  - Add `"pose"` to the `type` literal union: `type: Literal['string', 'number', 'boolean', 'select', 'vec3', 'list', 'pose']`

---

## Phase 7 — Tests

- [ ] **B-15** Unit tests `tests/schemas/test_pose.py`:
  - Valid construction: all six fields
  - Default construction: `Pose()` → all zeros
  - Boundary: `roll=180.0` passes; `roll=180.001` raises `ValidationError`
  - Boundary: `roll=-180.0` passes; `roll=-180.001` raises `ValidationError`
  - `Pose.zero()` returns correct instance
  - `to_flat_dict()` returns expected dict
  - Frozen: assigning `pose.x = 1.0` raises `ValidationError` (frozen model)
  - NaN rejected: `Pose(x=float('nan'))` raises `ValidationError`

- [ ] **B-16** Unit tests `tests/modules/test_sensor_pose.py`:
  - `LidarSensor.set_pose(Pose(x=100, yaw=45))` produces correct `transformation` matrix
  - `LidarSensor.get_pose_params()` returns `Pose` instance

- [ ] **B-17** Unit tests `tests/modules/test_build_sensor.py`:
  - `build_sensor()` with `node["pose"] = {"x": 100, "yaw": 45, ...}` produces sensor with correct pose
  - `build_sensor()` with empty `node["pose"] = {}` defaults to `Pose.zero()`

- [ ] **B-18** Integration tests `tests/api/test_nodes_pose.py`:
  - `POST /nodes` with `pose` object → `200` and round-trip `GET /nodes/{id}` returns same pose
  - `POST /nodes` with `config.x = 100` (flat key) → `422` with correct error message
  - `POST /nodes` with `pose.yaw = 270` → `422` (angle out of range)
  - `POST /nodes` with `pose.yaw = 180` → `200` (boundary passes)
  - `POST /nodes` with `pose.yaw = -180` → `200` (negative boundary passes)
  - `GET /nodes` → all sensor nodes have `pose` field; non-sensor nodes have `pose: null`

- [ ] **B-19** Integration test — DB migration backfill:
  - Create node row with flat pose keys (`x`, `y`, `z`, `roll`, `pitch`, `yaw`) in `config_json` at the top level.
  - Run `ensure_schema()`.
  - Assert `config["pose"]` is populated as a nested dict.
  - Assert flat pose keys are gone from the top level of `config_json`.
  - Run `ensure_schema()` again — assert idempotency (data unchanged).

- [ ] **B-20** Integration test `tests/api/test_calibration_rollback_pose.py`:
  - Rollback applies `pose_after` correctly to `config_json["pose"]` (not as flat keys)
  - After rollback, `GET /nodes/{sensor_id}` reflects restored pose

---

## Dependencies & Order

```
B-01, B-02 (Pose model)
  → B-03, B-04 (DB layer — to_dict() + backfill migration, no DDL)
    → B-06 (Repository — update_node_pose writes into config_json["pose"])
      → B-07, B-08 (API schemas/service)
        → B-09, B-10 (DAG sensor module)
        → B-11, B-12 (Calibration module)
        → B-13 (Rollback path)
  → B-14 (PropertySchema type)
→ B-15..B-20 (Tests — can be written TDD-first before implementation)
```

**Frontend Unblocked At:** B-07 complete (NodeRecord schema updated) — frontend can begin
mocking from `api-spec.md` immediately.
