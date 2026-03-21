# Technical Design: Unified Sensor Pose Entity

**Feature:** `sensor-pose-entity`  
**Status:** Design Complete  
**Architect:** @architecture  
**Date:** 2026-03-21

---

## 1. Executive Summary

This document describes the full technical design for unifying all scattered sensor pose fields
(`x`, `y`, `z`, `roll`, `pitch`, `yaw`) into a single canonical `Pose` entity throughout the
entire stack. It covers the Python domain model, database migration strategy, API contract
changes, DAG wiring implications, Angular form refactor, and Synergy UI integration.

---

## 2. Current State Audit

### 2.1 Backend: Scattered Flat Fields

Pose is **not** a first-class entity anywhere today. It exists as:

| Location | Pattern |
|---|---|
| `app/modules/lidar/registry.py` | Six flat `PropertySchema` entries: `x`, `y`, `z`, `roll`, `pitch`, `yaw` inside `config_json` |
| `app/modules/lidar/sensor.py` | `self.pose_params: Dict[str, float]` — ad-hoc dict |
| `app/modules/lidar/sensor.py` | `set_pose(x, y, z, roll, pitch, yaw)` — positional args, no Pydantic |
| `app/modules/lidar/registry.py` | `build_sensor()` — reads `config.get("x", 0)` ... `config.get("yaw", 0)` individually |
| `app/modules/calibration/calibration_node.py` | `config.get("roll", 0.0)` etc. — flat reads on dict |
| `app/api/v1/calibration/service.py` | `"x": pose_after["x"]`, `"roll": pose_after["roll"]` — flat dict keys |
| `app/modules/calibration/history.py` | `pose_before: Dict[str, float]`, `pose_after: Dict[str, float]` — untyped |
| `app/db/models.py` `CalibrationHistoryModel` | `pose_before_json` / `pose_after_json` — JSON string with flat dict |

### 2.2 Frontend: Duplicated Pose Definitions

| Location | Pattern |
|---|---|
| `core/models/lidar.model.ts` | `LidarPose` interface (x, y, z, roll, pitch, yaw) |
| `core/models/calibration.model.ts` | `Pose` interface (x, y, z, roll, pitch, yaw) — duplicate |
| `core/models/recording.model.ts` | Inline anonymous pose type in `RecordingMetadata` — triplicate |
| `plugins/sensor/node/sensor-node-card.component.ts` | Reads flat `config['x']`, `config['roll']` directly |
| `features/settings/.../node-recording-controls.ts` | Reads `config.pose` (treats pose as nested object already in some paths) |

**Critical observation:** `config.pose` is referenced in `node-recording-controls.ts` line 60,
but the backend still stores flat `x`, `y`, `z`, `roll`, `pitch`, `yaw` inside `config_json`.
This inconsistency is a live bug; the recording metadata `pose` key is always `undefined`.

---

## 3. Design Decisions

### Decision 1: Python `Pose` Pydantic Model (Frozen, Validated)

**Decision:** Create `app/schemas/pose.py` containing a frozen Pydantic V2 `Pose` model.

**Rationale:**
- Pydantic V2 frozen models are hashable and safe for use as value objects in DAG payloads.
- Centralizes validation in one place; all callers benefit automatically.
- The `Annotated` validator approach (rather than `@validator`) is idiomatic Pydantic V2.
- `model_config = ConfigDict(frozen=True)` prevents accidental mutation in DAG pipelines.

```python
# app/schemas/pose.py
from __future__ import annotations
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

PoseFloat = Annotated[float, Field(allow_inf_nan=False)]
AngleDeg  = Annotated[float, Field(ge=-180.0, le=180.0, allow_inf_nan=False)]

class Pose(BaseModel):
    """Canonical 6-DOF sensor pose. Position in mm; angles in degrees [-180, +180]."""
    model_config = ConfigDict(frozen=True)

    x:     PoseFloat = 0.0  # mm
    y:     PoseFloat = 0.0  # mm
    z:     PoseFloat = 0.0  # mm
    roll:  AngleDeg  = 0.0  # degrees
    pitch: AngleDeg  = 0.0  # degrees
    yaw:   AngleDeg  = 0.0  # degrees

    @classmethod
    def zero(cls) -> "Pose":
        return cls()

    def to_flat_dict(self) -> dict[str, float]:
        """Returns flat {x, y, z, roll, pitch, yaw} dict for backward-compat uses."""
        return self.model_dump()
```

**Unit note:** The requirements spec says "mm" for position. The existing
`create_transformation_matrix` docstring says "meters." The transformation matrix math
uses whatever unit the caller provides — the matrix is dimensionless in terms of unit.
**Decision:** Treat pose units as **millimeters** in the Pydantic layer (matching requirements).
The `create_transformation_matrix` function's docstring is updated to reflect mm, not meters,
since the hardware sensors already operate in mm (SICK SDK default).

### Decision 2: Database — Pose Nested Inside `config_json`

**Options considered:**

| Option | Pros | Cons |
|---|---|---|
| **A. Pose nested inside `config_json`** (chosen) | Zero schema migration; no `ALTER TABLE`; consistent with how all other node config is stored | Pose not independently queryable at DB level (not needed for this use case) |
| **B. 6-column struct** (x, y, z, roll, pitch, yaw as separate `Float` columns) | Queryable, explicit schema | Requires `ALTER TABLE × 6`; spreads pose back into flat columns — defeats the purpose |
| **C. Dedicated `pose_json` column** | Separates pose from other config | Requires `ALTER TABLE nodes ADD COLUMN`; additional ORM complexity |

**Decision: Option A — store pose as a nested object inside `config_json`.**

**Rationale:**
- The `config_json` column already holds all node-type-specific settings as a JSON blob.
  Adding a `"pose"` sub-key keeps all node config in one place with **zero schema migration**.
- No `ALTER TABLE` is required. The `nodes` table schema is unchanged.
- The six previously flat keys (`x`, `y`, `z`, `roll`, `pitch`, `yaw`) at the top level of
  `config_json` are migrated into `config_json["pose"]` by the backfill step in `ensure_schema()`.
- `CalibrationHistoryModel.pose_before_json` / `pose_after_json` columns remain as-is — they
  are already correct JSON dictionaries and there is no benefit to restructuring them.
- **No Alembic. No `ALTER TABLE`.** Only a data-level backfill loop in the existing
  `app/db/migrate.py::ensure_schema()` pattern.

**Migration logic (Python, no SQL DDL):**
```python
# ensure_schema() — backfill only, no DDL change
rows = conn.exec_driver_sql("SELECT id, config FROM nodes").fetchall()
pose_keys = {"x", "y", "z", "roll", "pitch", "yaw"}
for row_id, cfg_str in rows:
    cfg = json.loads(cfg_str) if cfg_str else {}
    if "pose" not in cfg and pose_keys.intersection(cfg.keys()):
        # Migrate flat pose keys → nested pose object
        pose = {k: float(cfg.pop(k, 0.0) or 0.0) for k in pose_keys}
        cfg["pose"] = pose
        conn.execute(
            text("UPDATE nodes SET config=:c WHERE id=:id"),
            {"c": json.dumps(cfg), "id": row_id}
        )
```

The backfill is idempotent: if `cfg["pose"]` already exists, the row is skipped.

### Decision 3: `NodeModel` ORM Update

Since pose is stored inside `config_json`, the `NodeModel` ORM class needs **no new column**.
The `to_dict()` method extracts `pose` from the config dict and surfaces it at the top level
of the returned dict — keeping the API shape unchanged:

```python
# app/db/models.py — NodeModel.to_dict() update
def to_dict(self) -> dict:
    import json
    config = json.loads(self.config_json) if self.config_json else {}
    pose = config.pop("pose", None)   # Extract pose from config; mutate local copy only
    return {
        "id": self.id,
        "name": self.name,
        "type": self.type,
        "category": self.category,
        "enabled": self.enabled,
        "visible": self.visible,
        "config": config,   # pose key removed from config dict in response
        "pose": pose,       # posed surfaced at top level (None for non-sensor nodes)
        "x": self.x,
        "y": self.y,
    }
```

**Important:** The `.pop("pose", None)` operates on a local copy of the parsed dict, never
on the raw `config_json` string. The DB row is not modified by `to_dict()`.

### Decision 4: API Contract — `pose` as Top-Level Nested Object

All `sensor`-type node endpoints expose pose as a top-level `pose` object **alongside** `config`,
not inside `config`. This is consistent with how calibration already surfaces `pose_before` /
`pose_after` in its response payloads.

```json
{
  "id": "abc123",
  "name": "Front LiDAR",
  "type": "sensor",
  "category": "sensor",
  "enabled": true,
  "visible": true,
  "config": {
    "lidar_type": "multiscan",
    "hostname": "192.168.1.10",
    "mode": "real"
  },
  "pose": {
    "x": 100.0,
    "y": 0.0,
    "z": 50.0,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 45.0
  },
  "x": 120.0,
  "y": 200.0
}
```

Note: The canvas-position `x`/`y` fields remain at the top level (they are DAG canvas
coordinates, not sensor pose). There is no naming conflict because pose fields are nested.

### Decision 5: `NodeCreateUpdate` Request DTO Update

The `NodeCreateUpdate` Pydantic model gains an optional `pose` field:

```python
class NodeCreateUpdate(BaseModel):
    id:       Optional[str] = None
    name:     str
    type:     str
    category: str
    enabled:  bool = True
    visible:  bool = True
    config:   Dict[str, Any] = {}
    pose:     Optional[Pose] = None   # NEW — None treated as zero pose for sensor nodes
    x:        Optional[float] = None
    y:        Optional[float] = None
```

The service layer (`upsert_node`) is responsible for:
1. If `node.type == "sensor"` and `pose` is provided → merge into `config_json["pose"]`.
2. If `pose` is `None` → default to `Pose.zero()`, stored as `config["pose"]`.
3. Reject any residual flat pose keys inside `config` with HTTP 422.

### Decision 6: `LidarSensor.set_pose()` — Accept `Pose` Object

```python
# NEW signature in sensor.py
def set_pose(self, pose: Pose) -> "LidarSensor":
    d = pose.to_flat_dict()
    self.transformation = create_transformation_matrix(**d)
    self.pose_params = d
    return self
```

The `build_sensor()` factory in `registry.py` reads `node["pose"]` (not `node["config"]`):
```python
raw_pose = node.get("pose", {})
pose = Pose(**raw_pose)   # validated here
sensor.set_pose(pose)
```

### Decision 7: `NodeSchema` / `PropertySchema` — Remove Flat Pose Properties

The six flat `PropertySchema` entries for `x`, `y`, `z`, `roll`, `pitch`, `yaw` in
`registry.py` are **removed**. A new property type `"pose"` is introduced in
`PropertySchema` type union:

```python
PropertySchema(
    name="pose",
    label="Sensor Pose",
    type="pose",   # NEW type — frontend renders the dedicated PoseFormComponent
    default={"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
)
```

This removes the coupling between the sensor form and the generic node editor's
property-type rendering loop. The frontend `SensorNodeEditorComponent` detects
`prop.type === 'pose'` and renders the dedicated `PoseFormComponent` instead of
six individual number inputs.

### Decision 8: Calibration Node — Consume `Pose` Entity

`calibration_node.py` currently reads `config.get("roll", 0.0)` etc. directly.
After the refactor it reads the resolved `node["pose"]` dict from the repository,
which is pre-validated:

```python
raw_pose = current_config.get("pose") or {}
current_pose = Pose(**raw_pose)
T_current = create_transformation_matrix(**current_pose.to_flat_dict())
```

The `accept_calibration` path that writes `{x: ..., roll: ...}` into node config is
updated to write a `Pose` object into `config_json["pose"]` via `NodeRepository.update_node_pose()`.

### Decision 9: TypeScript `Pose` Interface — Single Source of Truth

**Decision:** Replace `LidarPose` (lidar.model.ts) and the anonymous pose type in
`recording.model.ts` with a single canonical `Pose` interface exported from
`core/models/pose.model.ts`. `calibration.model.ts` already defines `Pose` correctly;
that becomes the source of truth and is re-exported from the new file.

```typescript
// web/src/app/core/models/pose.model.ts  (NEW file)
/** Canonical 6-DOF sensor pose. Position in mm; angles in degrees [-180, +180]. */
export interface Pose {
  x:     number;  // mm
  y:     number;  // mm
  z:     number;  // mm
  roll:  number;  // degrees [-180, +180]
  pitch: number;  // degrees [-180, +180]
  yaw:   number;  // degrees [-180, +180]
}

export const ZERO_POSE: Pose = { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 };
```

All other model files import from `pose.model.ts`.

### Decision 10: Angular Form — Separate `PoseFormComponent` (Dumb Component)

Rather than hard-coding pose controls inside `SensorNodeEditorComponent`, a dedicated
standalone dumb component is created:

```
web/src/app/plugins/sensor/form/pose-form/
  pose-form.component.ts
  pose-form.component.html
```

**Interface:**
- `Input` (signal): `pose: Pose` — current pose value
- `Output` (signal): `poseChange: OutputEmitterRef<Pose>` — emits on any change
- Internal `FormGroup` with 6 controls; syncs with `pose` input via `effect()`
- Exposes `resetPose()` method called by Reset button binding in the parent or internally

**Why a separate component?**  
Keeps `SensorNodeEditorComponent` at reasonable size, enables reuse (e.g., in calibration
rollback confirmation dialog), and isolates the Synergy `syn-range` bindings for easier testing.

### Decision 11: `syn-range` Binding Strategy for Angles

`syn-range` exposes a `value` property (string, space-separated for multi-thumb) and emits
`syn-change` and `syn-input` events. In Angular, the Synergy wrapper emits `valueChange`
for two-way binding:

```html
<syn-range
  [label]="'Roll'"
  [min]="-180"
  [max]="180"
  [step]="1"
  [value]="poseForm.get('roll')?.value?.toString()"
  [tooltipFormatter]="angleLabelFn"
  size="small"
  (synInputEvent)="onRangeInput('roll', $event)"
/>
```

**Important:** `syn-range.value` is a string. The component must parse `Number(event.target.value)`
or read `nativeElement.value` after a `syn-input` event. The `tooltipFormatter` function
formats the value as `"45°"`.

**`syn-input` vs `syn-change`:** Use `syn-input` for live reactive feedback (updates the
Angular form on every drag), but only mark the form as dirty on `syn-change` (committed
value). This gives smooth UX without excessive form-dirty noise.

### Decision 12: Reset Pose Button

The Reset Pose button is placed in `PoseFormComponent`. It calls a method that patches the
internal form group with `ZERO_POSE` and emits the zeroed pose upward:

```typescript
resetPose(): void {
  this.poseFormGroup.patchValue(ZERO_POSE);
  this.poseChange.emit({ ...ZERO_POSE });
}
```

Button markup uses `syn-button` with `variant="outline"` and a reset icon:

```html
<syn-button variant="outline" size="small" (click)="resetPose()">
  <syn-icon name="restart_alt" slot="prefix"></syn-icon>
  Reset Pose
</syn-button>
```

---

## 4. Migration Plan

### 4.1 Database Migration (No Alembic, No DDL)

The `ensure_schema()` function in `app/db/migrate.py` is extended with a **data-only backfill**
— no `ALTER TABLE` is needed because the `nodes` table schema is unchanged.

```python
# app/db/migrate.py — backfill: flat pose keys → config["pose"] nested object
def _backfill_pose_into_config(conn) -> None:
    """Migrate flat pose keys in config_json into config_json['pose'] nested object.
    Idempotent: rows that already have config['pose'] are skipped.
    """
    pose_keys = {"x", "y", "z", "roll", "pitch", "yaw"}
    rows = conn.exec_driver_sql("SELECT id, config FROM nodes").fetchall()
    for row_id, cfg_str in rows:
        try:
            cfg = json.loads(cfg_str) if cfg_str else {}
        except json.JSONDecodeError:
            cfg = {}
        # Skip rows that already have nested pose
        if "pose" in cfg:
            continue
        flat_pose_keys = pose_keys.intersection(cfg.keys())
        if flat_pose_keys:
            pose = {k: float(cfg.pop(k, 0.0) or 0.0) for k in pose_keys}
            cfg["pose"] = pose
            conn.execute(
                text("UPDATE nodes SET config=:c WHERE id=:id"),
                {"c": json.dumps(cfg), "id": row_id}
            )
```

Called at the end of `ensure_schema()` after existing DDL checks.

### 4.2 No Backward Compatibility

Per requirements, no legacy flat pose fields in API requests are accepted post-migration.
Any `NodeCreateUpdate` payload containing `config.x`, `config.roll`, etc. will:
1. Have those keys ignored if `pose` is also present, OR
2. Return HTTP 422 with detail: `"Pose fields must be sent in the 'pose' object, not inside 'config'. Found deprecated keys: x, roll"`

This is enforced in the `upsert_node` service function with an explicit validator.

### 4.3 `config_json` Cleanup

After backfill, all sensor nodes will have `config_json` free of pose keys. Non-sensor nodes
(fusion, calibration, etc.) never had pose in config, so they are unaffected.

---

## 5. DAG Wiring Impacts

| Component | Change Required |
|---|---|
| `app/modules/lidar/sensor.py` | `set_pose()` accepts `Pose`; `get_pose_params()` returns `Pose` |
| `app/modules/lidar/registry.py` | `build_sensor()` reads `node["pose"]`; 6 flat properties → 1 `"pose"` property |
| `app/modules/lidar/core/transformations.py` | `create_transformation_matrix(**pose.to_flat_dict())` — no internal change needed |
| `app/modules/calibration/calibration_node.py` | Reads `node["pose"]`; writes updated pose back via `NodeRepository.update_node_config_pose()` |
| `app/modules/calibration/history.py` | `pose_before: Pose`, `pose_after: Pose` (typed) |
| `app/repositories/node_orm.py` | New `update_node_pose(node_id, pose: Pose)` method writes `config["pose"]` inside `config_json` |
| `app/api/v1/nodes/service.py` | Validates no flat pose keys in `config`; reads/writes `config["pose"]` |
| `app/api/v1/calibration/service.py` | `rollback_calibration` writes `Pose` to `config["pose"]` via `update_node_pose()` |

---

## 6. Frontend Component DAG

```
SensorNodeEditorComponent (Smart, plugin root)
├── NodeEditorHeaderComponent (Dumb, save/cancel buttons)
├── [form] name input (syn-input)
├── [configForm] generic property loop (string, number, boolean, select)
└── PoseFormComponent (Dumb, NEW)
    ├── syn-input × 3 (x, y, z — numeric, mm)
    ├── syn-range × 3 (roll, pitch, yaw — -180..180°)
    └── syn-button "Reset Pose"
```

```
SensorNodeCardComponent (Dumb, canvas card preview)
└── reads node().data.pose.x, .y, .z, .roll, .pitch, .yaw
    (was: node().data.config['x'], config['roll'])
```

```
NodeRecordingControls
└── metadata.pose = node().data.pose  (was: config.pose — was broken)
```

---

## 7. Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| `syn-range` emits string values | Medium | Parse `Number()` in `onRangeInput`; add unit test for NaN guard |
| Calibration backfill of `pose_after` dict uses flat keys (6 individual writes in `accept_calibration`) | High | Update all 6 flat write sites to use `NodeRepository.update_node_pose(id, Pose(**new_pose))` |
| `CalibrationHistoryModel.pose_before_json` / `pose_after_json` store flat dict | Low | These are read-only history records — no schema change needed; Python callers are updated to use `Pose` for in-memory construction only |
| Recording metadata `pose` key was silently undefined | Low | Fixed by reading from `node.data.pose` (top-level) instead of `config.pose` |
| Canvas-position `x`/`y` conflict with pose `x`/`y` naming | Low | Canvas coords live at `NodeRecord.x`/`y` (top-level); sensor pose lives in `NodeRecord.pose.x`/`y` — no collision |
| `node-store.service.ts` `NodeConfig.config` spread | Medium | `NodeConfig` model updated to include `pose: Pose`; store patches preserve pose separately |

---

## 8. Files to Create / Modify

### Backend (New Files)
- `app/schemas/pose.py` — `Pose` Pydantic model (canonical)

### Backend (Modified Files)
- `app/db/models.py` — Update `NodeModel.to_dict()` to extract `pose` from `config_json` (no new column)
- `app/db/migrate.py` — Add `_backfill_pose_into_config()` backfill (data-only, no DDL)
- `app/modules/lidar/sensor.py` — `set_pose(pose: Pose)`, `get_pose_params() -> Pose`
- `app/modules/lidar/registry.py` — Remove 6 flat `PropertySchema`; add `"pose"` type; `build_sensor()` reads `node["pose"]`
- `app/modules/calibration/calibration_node.py` — Read/write via `Pose`
- `app/modules/calibration/history.py` — Type `pose_before`/`pose_after` as `Pose`
- `app/repositories/node_orm.py` — Add `update_node_pose()`
- `app/api/v1/nodes/service.py` — `NodeCreateUpdate.pose`, flat-key rejection guard
- `app/api/v1/nodes/handler.py` — No route changes; response model updates
- `app/api/v1/calibration/service.py` — `rollback_calibration` writes `Pose` into `config["pose"]` via `update_node_pose()`
- `app/api/v1/schemas/nodes.py` — `NodeRecord.pose: Pose`

### Frontend (New Files)
- `web/src/app/core/models/pose.model.ts` — `Pose` interface, `ZERO_POSE` constant
- `web/src/app/plugins/sensor/form/pose-form/pose-form.component.ts`
- `web/src/app/plugins/sensor/form/pose-form/pose-form.component.html`

### Frontend (Modified Files)
- `web/src/app/core/models/lidar.model.ts` — Remove `LidarPose`; import `Pose` from `pose.model.ts`; `LidarConfig.pose: Pose`
- `web/src/app/core/models/calibration.model.ts` — Remove local `Pose`; import from `pose.model.ts`
- `web/src/app/core/models/recording.model.ts` — Replace anonymous pose type with `Pose`
- `web/src/app/core/models/node.model.ts` — `NodeConfig` gains `pose?: Pose`
- `web/src/app/core/models/index.ts` — Export `Pose`, `ZERO_POSE`
- `web/src/app/plugins/sensor/form/sensor-node-editor.component.ts` — Integrate `PoseFormComponent`
- `web/src/app/plugins/sensor/form/sensor-node-editor.component.html` — Add pose section
- `web/src/app/plugins/sensor/node/sensor-node-card.component.ts` — Read `node().data.pose.*`
- `web/src/app/features/settings/components/flow-canvas/node/node-recording-controls/node-recording-controls.ts` — Fix `metadata.pose = data.pose`
- `web/src/app/core/services/stores/lidar-store.service.ts` — Update `LidarState.selectedLidar` pose typing
- `web/src/app/core/services/api/nodes-api.service.ts` — `upsertNode` sends `pose` field

---

## 9. Testing Strategy (Summary — detail in qa-tasks.md)

- **Unit:** `Pose` model validation (boundary values ±180, NaN rejection, missing fields)
- **Unit:** `build_sensor()` factory with `node["pose"]` dict
- **Unit:** `PoseFormComponent` — reset, slider event parsing, form validity
- **Integration:** `POST /nodes` with `pose` object — round-trip via API
- **Integration:** DB migration backfill (flat pose keys in config_json → nested `config["pose"]`)
- **Integration:** Calibration accept → `config_json["pose"]` updated correctly
- **E2E:** Create sensor → set pose via sliders → reset → save → verify DB
