# Multi-LiDAR Type Support — Technical Architecture

> **Status**: Revised — Ready for Development
> **Author**: @architecture
> **Last Revised**: 2026-03-08
> **References**: `requirements.md`, `api-spec.md`, `backend.md`, `frontend.md`, `protocols.md`

---

## 1. Overview & Design Constraints

This feature extends the existing `sensor` DAG node to carry a **`lidar_type`** discriminator field. All configuration, launch-arg generation, and UI conditional rendering flows from this single field. The LIDR binary WebSocket protocol frame is **unchanged**. Performance overhead is **<1%** (no new per-frame code paths; all overhead is at node instantiation/config load time only).

### Hard Constraints (from user requirements)

| Constraint | Implementation |
|---|---|
| Linux-native sick_scan_xd only | `lidar_worker_process` already uses `libsick_scan_xd_shared_lib.so` only. No Windows/ROS variants. |
| No new DAG node types | Extend `registry.py` and `sensor.py` in-place. `NodeFactory.register("sensor")` remains singular. |
| UI dropdown reflects launch file mapping | Options are built directly from the `_PROFILES` dict in `profiles.py`, keyed on real `.launch` filenames. |
| Per-device field conditioning | `depends_on` mechanism on `PropertySchema` controls visibility of `hostname`, `port`, `udp_receiver_ip`, `imu_udp_port`, `add_transform_xyz_rpy` per device group. |

---

## 2. Real Launch File Inventory

The `/launch/` directory contains the authoritative `.launch` files passed verbatim to `sick_generic_caller`. The plan maps exactly to these on-disk files. No invented filenames.

| `model_id` | Display Name | `.launch` File | Port Arg | `udp_receiver_ip`? | IMU Port Arg |
|---|---|---|---|---|---|
| `multiscan` | SICK multiScan | `launch/sick_multiscan.launch` | `udp_port` (default 2115) | ✅ `udp_receiver_ip` | ✅ `imu_udp_port` (7503) |
| `tim_2xx` | SICK TiM2xx / TiM240 | `launch/sick_tim_240.launch` | `port` (default 2112) | ❌ | ❌ |
| `tim_4xx` | SICK TiM4xx | `launch/sick_tim_4xx.launch` | `port` (default 2112) | ❌ | ❌ |
| `tim_5xx` | SICK TiM5xx | `launch/sick_tim_5xx.launch` | `port` (default 2112) | ❌ | ❌ |
| `tim_7xx` | SICK TiM7xx | `launch/sick_tim_7xx.launch` | `port` (default 2112) | ❌ | ❌ |
| `lms_1xx` | SICK LMS1xx | `launch/sick_lms_1xx.launch` | ❌ (TCP only) | ❌ | ❌ |
| `lms_5xx` | SICK LMS5xx | `launch/sick_lms_5xx.launch` | ❌ (TCP only) | ❌ | ❌ |
| `lms_4xxx` | SICK LMS4000 | `launch/sick_lms_4xxx.launch` | ❌ (TCP only) | ❌ | ❌ |
| `mrs_1xxx` | SICK MRS1000 | `launch/sick_mrs_1xxx.launch` | ❌ (TCP only) | ❌ | ❌ |
| `mrs_6xxx` | SICK MRS6124 | `launch/sick_mrs_6xxx.launch` | ❌ (TCP only) | ❌ | ❌ |

**Critical observations from actual launch files:**
- **`port` vs `udp_port`**: TiM and LMS series use `port:=<value>` as the arg name. Only `multiscan` uses `udp_port:=<value>`.
- **`udp_receiver_ip`**: Only `sick_multiscan.launch` has this arg. All other devices communicate via TCP and do not accept this parameter.
- **`imu_udp_port`**: Only `sick_multiscan.launch` has this arg. `sick_mrs_1xxx.launch` has `imu_enable` and an IMU topic but no dedicated UDP port arg.
- **`add_transform_xyz_rpy`**: All launch files accept this arg. It replaces the current hardcoded `0,0,0,0,0,0` and should be built from the node's pose config (`x, y, z, roll, pitch, yaw`). **This is a correction from the previous plan which ignored it.**

---

## 3. Backend Architecture

### 3.1 New File: `app/modules/lidar/profiles.py`

Pure data module — no I/O, no FastAPI imports. Stdlib `dataclasses` only.

```python
@dataclass
class SickLidarProfile:
    model_id: str            # canonical key, e.g. "tim_5xx"
    display_name: str        # shown in UI dropdown
    launch_file: str         # relative path from repo root, e.g. "launch/sick_tim_5xx.launch"
    default_hostname: str    # default IP for this device family
    port_arg: str            # arg name to use: "port" (TiM/LMS) or "udp_port" (multiScan)
    default_port: int        # default value for the port arg
    has_udp_receiver: bool   # True only for multiscan — controls udp_receiver_ip arg emission
    has_imu_udp_port: bool   # True only for multiscan — controls imu_udp_port arg emission
    scan_layers: int         # informational: 1=2D, >1=multi-layer
```

**Profiles table (derived directly from real launch files):**

| `model_id` | `launch_file` | `port_arg` | `default_port` | `has_udp_receiver` | `has_imu_udp_port` | `scan_layers` |
|---|---|---|---|---|---|---|
| `multiscan` | `launch/sick_multiscan.launch` | `udp_port` | 2115 | ✅ | ✅ | 16 |
| `tim_2xx` | `launch/sick_tim_240.launch` | `port` | 2112 | ❌ | ❌ | 1 |
| `tim_4xx` | `launch/sick_tim_4xx.launch` | `port` | 2112 | ❌ | ❌ | 1 |
| `tim_5xx` | `launch/sick_tim_5xx.launch` | `port` | 2112 | ❌ | ❌ | 1 |
| `tim_7xx` | `launch/sick_tim_7xx.launch` | `port` | 2112 | ❌ | ❌ | 1 |
| `lms_1xx` | `launch/sick_lms_1xx.launch` | — | — | ❌ | ❌ | 1 |
| `lms_5xx` | `launch/sick_lms_5xx.launch` | — | — | ❌ | ❌ | 1 |
| `lms_4xxx` | `launch/sick_lms_4xxx.launch` | — | — | ❌ | ❌ | 1 |
| `mrs_1xxx` | `launch/sick_mrs_1xxx.launch` | — | — | ❌ | ❌ | 4 |
| `mrs_6xxx` | `launch/sick_mrs_6xxx.launch` | — | — | ❌ | ❌ | 24 |

> LMS and MRS devices connect via TCP only; `hostname` is their only required network arg. No `port` arg override is needed (the driver uses the SOPAS/CoLa protocol port internally).

**Public API of `profiles.py`:**

```python
def get_all_profiles() -> List[SickLidarProfile]: ...
def get_profile(model_id: str) -> SickLidarProfile: ...  # raises KeyError if unknown

def build_launch_args(
    model_id: str,
    hostname: str,
    port: Optional[int],          # used only when profile.port_arg is set
    udp_receiver_ip: Optional[str],
    imu_udp_port: Optional[int],
    add_transform_xyz_rpy: str     # pre-formatted "x,y,z,roll,pitch,yaw" string
) -> str: ...
```

`build_launch_args` constructs the full argument string:
1. Always includes: `{launch_file} hostname:={hostname} add_transform_xyz_rpy:={add_transform_xyz_rpy}`
2. If `profile.port_arg` is non-empty and `port` is not None: appends `{profile.port_arg}:={port}`
3. If `profile.has_udp_receiver` and `udp_receiver_ip` is not None: appends `udp_receiver_ip:={udp_receiver_ip}`
4. If `profile.has_imu_udp_port` and `imu_udp_port` is not None: appends `imu_udp_port:={imu_udp_port}`

This replaces the hardcoded line 81 in `registry.py`:
```python
# OLD (removed):
launch_args = f"./launch/sick_multiscan.launch hostname:={hostname} udp_receiver_ip:={udp_receiver_ip} udp_port:={udp_port} imu_udp_port:={imu_udp_port}"
```

---

### 3.2 Schema Changes — `app/services/nodes/schema.py`

Add one optional field to `PropertySchema`:

```python
depends_on: Optional[Dict[str, List[Any]]] = None
# Semantics: property is visible only when ALL key-value pairs are satisfied (AND).
# Example: {"mode": ["real"], "lidar_type": ["multiscan"]}
# means: visible only when mode == "real" AND lidar_type == "multiscan"
```

Fully additive/backward-compatible — all existing `PropertySchema` instances default `depends_on=None` and behave as before.

---

### 3.3 Schema Changes — `app/modules/lidar/registry.py`

**New `lidar_type` property** — prepended as first entry in `properties` list:

```python
PropertySchema(
    name="lidar_type",
    label="LiDAR Model",
    type="select",
    default="multiscan",
    required=True,
    help_text="Select the SICK LiDAR hardware model",
    options=[{"label": p.display_name, "value": p.model_id} for p in get_all_profiles()]
)
```

**`depends_on` additions to existing properties** (conditioned on device capabilities derived from profiles):

| Property | `depends_on` | Rationale |
|---|---|---|
| `hostname` | `{"mode": ["real"]}` | Hardware-only; irrelevant for sim |
| `port` | `{"mode": ["real"], "lidar_type": [models with port_arg]}` | Only TiM/multiScan devices expose a configurable port; LMS/MRS use TCP on fixed ports |
| `udp_receiver_ip` | `{"mode": ["real"], "lidar_type": ["multiscan"]}` | Only multiScan is UDP-based |
| `imu_udp_port` | `{"mode": ["real"], "lidar_type": ["multiscan"]}` | Only multiScan has an IMU UDP port |
| `pcd_path` | `{"mode": ["sim"]}` | Simulation-only |

> **Note**: `add_transform_xyz_rpy` is now **built programmatically** in `build_sensor()` from the pose `x,y,z,roll,pitch,yaw` config values — it is NOT a user-facing UI field. The existing `x, y, z, roll, pitch, yaw` schema properties remain and serve as the UI input. This was already how pose was handled; we now explicitly format it into the `add_transform_xyz_rpy` launch arg.

**Rename `udp_port` → `port` in schema** to reflect the actual arg name used by TiM/LMS devices. The `build_launch_args` function maps this value to the correct arg name (`port` or `udp_port`) per profile.

**`build_sensor()` update:**

```python
from app.modules.lidar.profiles import build_launch_args, get_profile

lidar_type = config.get("lidar_type", "multiscan")
try:
    profile = get_profile(lidar_type)
except KeyError:
    raise ValueError(f"Unknown lidar_type '{lidar_type}'")

# Build the transform string from pose params (passed to add_transform_xyz_rpy)
add_transform = f"{x},{y},{z},{roll},{pitch},{yaw}"

launch_args = build_launch_args(
    model_id=lidar_type,
    hostname=hostname,
    port=config.get("port"),
    udp_receiver_ip=config.get("udp_receiver_ip"),
    imu_udp_port=config.get("imu_udp_port"),
    add_transform_xyz_rpy=add_transform
)
```

> **Backward compatibility**: Nodes saved before this change have no `lidar_type` in their DB `config` JSON. `config.get("lidar_type", "multiscan")` defaults to `multiscan`, which uses `./launch/sick_multiscan.launch` — identical to the current hardcoded behavior. The `add_transform_xyz_rpy` default of `"0,0,0,0,0,0"` matches the previous implicit zero-pose behavior.

---

### 3.4 `LidarSensor` — `app/modules/lidar/sensor.py`

Two new instance attributes on `LidarSensor`:

```python
self.lidar_type: str = "multiscan"
self.lidar_display_name: str = "SICK multiScan"
```

Set by `build_sensor()` after instantiation:
```python
sensor.lidar_type = profile.model_id
sensor.lidar_display_name = profile.display_name
```

`get_status()` extended:
```python
status["lidar_type"] = self.lidar_type
status["lidar_display_name"] = self.lidar_display_name
```

No changes to `start()`, `stop()`, `handle_data()`, or `on_input()`.

---

### 3.5 New Router: `app/api/v1/lidar.py`

```
GET  /api/v1/lidar/profiles             → ProfilesListResponse  (catalog, ~1 KB, in-memory)
POST /api/v1/nodes/validate-lidar-config → LidarConfigValidationResponse
```

The `validate-lidar-config` endpoint accepts `LidarConfigValidationRequest` (see `api-spec.md` §2) and returns semantic validation results — never raises 422 unless the request body itself is malformed (Pydantic handles that automatically). Validation logic:
1. Calls `get_profile(lidar_type)` — error if `KeyError`.
2. Checks `hostname` is non-empty string.
3. If profile `has_udp_receiver`: checks `udp_receiver_ip` is present and non-empty.
4. If profile `port_arg` is set: checks `port` is in range `[1024, 65535]`.
5. If profile `has_imu_udp_port` and `imu_udp_port` is None: warning (not error).
6. Returns `valid`, `resolved_launch_file`, `errors[]`, `warnings[]`.

**Router mounted in `app/api/v1/__init__.py`** with `prefix="/api/v1"`, tag `"lidar"`.

---

### 3.6 Config Validator Extension — `app/api/v1/config.py`

In `validate_configuration()`, after the existing `name`/`type` checks, add for nodes with `type == "sensor"`:
- If `lidar_type` absent → warning: `"Node '<name>': no lidar_type; defaulting to 'multiscan' (backward compat)"`.
- If `lidar_type` present but unknown → error.

---

### 3.7 DAG Data Flow — No Changes

```
[multiprocessing.Process → lidar_worker_process]
        │  (puts binary frames on mp.Queue)
        ▼
[NodeManager.data_dispatch_loop]
        │  (reads queue; calls sensor.handle_data())
        ▼
[LidarSensor.handle_data()]
        │  asyncio.to_thread(transform_points)
        ▼
[manager.forward_data(node_id, payload)]
        │  (WebSocket LIDR binary frame — UNCHANGED)
        ▼
[Downstream DAG nodes / WebSocket clients]
```

`lidar_type` selection affects only which `launch_args` string is built at **node creation/reload time**. It never touches the per-frame hot path.

---

## 4. Frontend Architecture

### 4.1 Zero New Components for the Dropdown

`DynamicNodeEditorComponent` already iterates `def.properties` and renders `<syn-select>` for any `type === 'select'` property. Adding `lidar_type` to the backend schema automatically surfaces the dropdown. **No new Angular component is needed for the dropdown itself.**

### 4.2 `depends_on` Conditional Rendering in `DynamicNodeEditorComponent`

The existing `visibleProperties` computed signal is extended from a simple `hidden` filter to also handle `depends_on`. A `formValues` signal bridges the reactive form to the Angular signal world:

```typescript
private formValues = signal<Record<string, any>>({});

// In initForm(), after configForm is created:
this.configForm.valueChanges.subscribe(v => this.formValues.set(v));
this.formValues.set(this.configForm.getRawValue()); // seed initial state

protected visibleProperties = computed(() => {
  const def = this.definition();
  if (!def) return [];
  const vals = this.formValues();
  return def.properties.filter(prop => {
    if (prop.hidden) return false;
    if (prop.depends_on) {
      return Object.entries(prop.depends_on).every(
        ([key, allowed]) => (allowed as any[]).includes(vals[key])
      );
    }
    return true;
  });
});
```

RxJS `subscribe` on `valueChanges` is acceptable here per `frontend.md` — this is a form stream, not a component state store.

### 4.3 TypeScript Model Extensions

**`web/src/app/core/models/node.model.ts`** — `PropertySchema` interface:
```typescript
depends_on?: Record<string, any[]>;
```

**`web/src/app/core/models/node.model.ts`** — `NodeStatus` interface:
```typescript
lidar_type?: string;
lidar_display_name?: string;
```

**`web/src/app/core/models/lidar.model.ts`** — `LidarConfig` interface:
```typescript
lidar_type?: string;
```

**New file: `web/src/app/core/models/lidar-profile.model.ts`**:
```typescript
export interface LidarProfile {
  model_id: string;
  display_name: string;
  launch_file: string;
  default_hostname: string;
  port_arg: string;       // "port" | "udp_port" | ""
  default_port: number;
  has_udp_receiver: boolean;
  has_imu_udp_port: boolean;
  scan_layers: number;
}

export interface LidarProfilesResponse {
  profiles: LidarProfile[];
}
```

### 4.4 New API Service — `LidarProfilesApiService`

`web/src/app/core/services/api/lidar-profiles-api.service.ts`:

```typescript
@Injectable({ providedIn: 'root' })
export class LidarProfilesApiService {
  private http = inject(HttpClient);
  profiles = signal<LidarProfile[]>([]);
  isLoading = signal<boolean>(false);

  async loadProfiles(): Promise<void> {
    this.isLoading.set(true);
    try {
      const data = await firstValueFrom(
        this.http.get<LidarProfilesResponse>(`${environment.apiUrl}/lidar/profiles`)
      );
      this.profiles.set(data.profiles);
    } catch {
      this.profiles.set([]);
    } finally {
      this.isLoading.set(false);
    }
  }
}
```

The `profiles` signal is informational (pre-fill defaults on model change). The `depends_on` logic operates independently via the schema, not this service.

### 4.5 Node Status Badge in `node-card.component.html`

When `status().lidar_display_name` is present (sensor nodes only), render a badge below the node name:

```html
@if (status()?.lidar_display_name) {
  <span class="text-[10px] text-syn-color-neutral-500 font-medium tracking-wide uppercase">
    {{ status()!.lidar_display_name }}
  </span>
}
```

Tailwind only. No custom CSS.

### 4.6 `NodesApiService` — Validation Method

Add to `web/src/app/core/services/api/nodes-api.service.ts`:

```typescript
async validateLidarConfig(
  request: LidarConfigValidationRequest
): Promise<LidarConfigValidationResponse> {
  return await firstValueFrom(
    this.http.post<LidarConfigValidationResponse>(
      `${environment.apiUrl}/nodes/validate-lidar-config`, request
    )
  );
}
```

In `DynamicNodeEditorComponent.onSave()`, for `def.type === 'sensor'` with `mode === 'real'`: call `validateLidarConfig` before `upsertNode`. Abort save and show toast on `valid === false`.

---

## 5. API Contract Summary

See `api-spec.md` for full request/response schemas.

| Method | Path | Change |
|---|---|---|
| `GET` | `/api/v1/lidar/profiles` | **New** — full device catalog |
| `POST` | `/api/v1/nodes/validate-lidar-config` | **New** — pre-save validation |
| `GET` | `/api/v1/nodes/definitions` | **Extended** — sensor definition gains `lidar_type` select, `depends_on` on network fields |
| `POST` | `/api/v1/nodes` | **Unchanged contract** — `config.lidar_type` persisted as-is |
| `GET` | `/api/v1/nodes/status/all` | **Extended** — sensor status includes `lidar_type`, `lidar_display_name` |
| `POST` | `/api/v1/config/validate` | **Extended** — warns on missing `lidar_type` for sensor nodes |

---

## 6. Performance Analysis

| Concern | Impact | Mitigation |
|---|---|---|
| Profile dict lookup in `build_sensor()` | O(1), once at node build/reload time | In-memory dict, no I/O |
| `build_launch_args` | Pure string formatting, once at node start | Negligible |
| `depends_on` filter in Angular | O(N) on ~12 props, re-runs on form value changes | `computed()` memoizes; no DOM interaction |
| `/lidar/profiles` endpoint | Called once on page load, cached in signal | ~500 bytes response, no polling |
| `lidar_type` in status response | One extra string field per sensor node | Negligible |

**Conclusion**: No per-frame code paths touched. Overhead well under <1% constraint.

---

## 7. Backward Compatibility Matrix

| Scenario | Behavior |
|---|---|
| Saved node with no `lidar_type` in DB | `config.get("lidar_type", "multiscan")` → uses multiScan profile |
| Existing `sick_multiscan.launch` path | `multiscan` profile points to same file |
| Existing nodes with `x,y,z,roll,pitch,yaw` all zero | `add_transform_xyz_rpy` = `"0,0,0,0,0,0"` — identical to former hardcoded default |
| `PropertySchema` without `depends_on` | Always visible (unchanged behavior) |
| Frontend receiving status without `lidar_type` | Both fields optional in `NodeStatus`; badge simply hidden |

---

## 8. File Change Surface

### Backend — Files Created
- `app/modules/lidar/profiles.py` — device profiles table + `build_launch_args`
- `app/api/v1/lidar.py` — new router with `/profiles` + `/validate-lidar-config`

### Backend — Files Modified
- `app/services/nodes/schema.py` — add `depends_on` to `PropertySchema`
- `app/modules/lidar/registry.py` — add `lidar_type` property, `depends_on` on network fields, replace hardcoded `launch_args`, rename `udp_port` → `port` in schema
- `app/modules/lidar/sensor.py` — add `lidar_type`/`lidar_display_name` attributes and `get_status()` output
- `app/api/v1/config.py` — extend `validate_configuration()` for sensor `lidar_type` check
- `app/api/v1/__init__.py` — mount new lidar router

### Frontend — Files Created
- `web/src/app/core/models/lidar-profile.model.ts` — `LidarProfile` interface
- `web/src/app/core/services/api/lidar-profiles-api.service.ts` — profiles catalog service

### Frontend — Files Modified
- `web/src/app/core/models/node.model.ts` — `depends_on` on `PropertySchema`; `lidar_type`/`lidar_display_name` on `NodeStatus`
- `web/src/app/core/models/lidar.model.ts` — `lidar_type` on `LidarConfig`
- `web/src/app/core/services/api/nodes-api.service.ts` — add `validateLidarConfig` method
- `web/src/app/features/settings/components/dynamic-node-editor/dynamic-node-editor.component.ts` — `formValues` signal, `depends_on` filtering, validation on save
- `web/src/app/features/settings/components/node-card/node-card.component.html` — `lidar_display_name` badge
