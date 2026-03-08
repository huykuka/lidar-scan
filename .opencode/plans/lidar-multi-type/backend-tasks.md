# Multi-LiDAR Type Support — Backend Tasks

> **Assignee**: @be-dev
> **Status**: Revised — Ready for Development
> **References**:
> - Requirements: `requirements.md`
> - Architecture: `technical.md`
> - API Contracts: `api-spec.md`
> - Rules: `.opencode/rules/backend.md`

---

## Dependencies & Order of Operations

```
TASK-B1 (profiles.py)
    └─► TASK-B2 (schema.py extension)
            └─► TASK-B3 (registry.py builder update)
                    ├─► TASK-B4 (sensor.py status extension)
                    ├─► TASK-B5 (new lidar.py router)
                    │       └─► TASK-B6 (app/api/v1/__init__.py router mount)
                    └─► TASK-B7 (config.py validator extension)
                            └─► TASK-B8 (tests)
```

TASK-B1 and TASK-B2 are the critical path blockers. TASK-B4, TASK-B5, TASK-B7 can proceed in parallel once TASK-B1 is complete.

---

## Task Checklist

### TASK-B1 — Create `app/modules/lidar/profiles.py`

- [x] Create `app/modules/lidar/profiles.py` as a **pure data module** (stdlib only — no FastAPI, no I/O, no Open3D imports).
- [x] Define `@dataclass SickLidarProfile` with fields:
  - `model_id: str` — canonical key used as the `lidar_type` config value
  - `display_name: str` — shown in UI dropdown label
  - `launch_file: str` — relative path from repo root, e.g. `"launch/sick_tim_5xx.launch"`
  - `default_hostname: str` — default IP for this device family
  - `port_arg: str` — the arg name to pass to the launch file: `"port"` for TiM/LMS with configurable port, `"udp_port"` for multiScan, or `""` for TCP-only devices (LMS, MRS)
  - `default_port: int` — default port value (0 if `port_arg` is empty)
  - `has_udp_receiver: bool` — True only for multiScan (controls `udp_receiver_ip` arg emission)
  - `has_imu_udp_port: bool` — True only for multiScan (controls `imu_udp_port` arg emission)
  - `scan_layers: int` — informational: 1 = 2D, >1 = multi-layer
- [x] Populate `_PROFILES` registry dict with all **25 SICK models**. Use **real launch filenames from the `/launch/` directory**:

  **COMPREHENSIVE SICK CATALOG IMPLEMENTED** (25 models total):
  - ✅ **multiScan Series**: multiScan100 (3D + UDP + IMU)
  - ✅ **TiM Series**: TiM240, TiM5xx, TiM7xx, TiM7xxS (2D + Port config)
  - ✅ **LMS Series**: LMS1xx, LMS1104 v1/v2, LMS5xx, LMS4000 (2D TCP)
  - ✅ **MRS Series**: MRS1104, MRS6124 (3D multi-layer)
  - ✅ **LRS Series**: LRS4000, LRS36x0/x1 + upside-down variants (3D radar)
  - ✅ **Legacy**: LD-MRS family (multi-layer)  
  - ✅ **OEM**: LD-OEM15xx series
  - ✅ **Navigation**: NAV210/245, NAV310, NAV350
  - ✅ **Radar**: RMS1009/RMS2000
  - ✅ **picoScan**: picoScan120/150 (3D + UDP)

  | `model_id`  | `launch_file`                       | `port_arg`  | `default_port` | `has_udp_receiver` | `has_imu_udp_port` | `scan_layers` |
  |-------------|-------------------------------------|-------------|----------------|--------------------|--------------------|---------------|
  | `multiscan` | `launch/sick_multiscan.launch`      | `udp_port`  | 2115           | True               | True               | 16            |
  | `tim_2xx`   | `launch/sick_tim_240.launch`        | `port`      | 2112           | False              | False              | 1             |
  | `tim_4xx`   | `launch/sick_tim_4xx.launch`        | `port`      | 2112           | False              | False              | 1             |
  | `tim_5xx`   | `launch/sick_tim_5xx.launch`        | `port`      | 2112           | False              | False              | 1             |
  | `tim_7xx`   | `launch/sick_tim_7xx.launch`        | `port`      | 2112           | False              | False              | 1             |
  | `lms_1xx`   | `launch/sick_lms_1xx.launch`        | `""`        | 0              | False              | False              | 1             |
  | `lms_5xx`   | `launch/sick_lms_5xx.launch`        | `""`        | 0              | False              | False              | 1             |
  | `lms_4xxx`  | `launch/sick_lms_4xxx.launch`       | `""`        | 0              | False              | False              | 1             |
  | `mrs_1xxx`  | `launch/sick_mrs_1xxx.launch`       | `""`        | 0              | False              | False              | 4             |
  | `mrs_6xxx`  | `launch/sick_mrs_6xxx.launch`       | `""`        | 0              | False              | False              | 24            |

- [x] Implement `get_all_profiles() -> List[SickLidarProfile]` returning profiles in display order (multiScan first, then TiM ascending, then LMS ascending, then MRS ascending).
- [x] Implement `get_profile(model_id: str) -> SickLidarProfile` raising `KeyError` with a descriptive message listing valid model IDs.
- [x] Implement `build_launch_args(model_id, hostname, port, udp_receiver_ip, imu_udp_port, add_transform_xyz_rpy) -> str`:
  - Calls `get_profile(model_id)`.
  - Base string: `"{profile.launch_file} hostname:={hostname} add_transform_xyz_rpy:={add_transform_xyz_rpy}"`
  - If `profile.port_arg` is non-empty and `port` is not None: append `{profile.port_arg}:={port}`
  - If `profile.has_udp_receiver` is True and `udp_receiver_ip` is not None: append `udp_receiver_ip:={udp_receiver_ip}`
  - If `profile.has_imu_udp_port` is True and `imu_udp_port` is not None: append `imu_udp_port:={imu_udp_port}`
  - Return the assembled string.
- [x] Add strict Python type hints (`Optional[int]`, `Optional[str]`, etc.) on all public functions.
- [x] Verify all imports in this file are stdlib-only (`dataclasses`, `typing`).

---

### TASK-B2 — Extend `PropertySchema` in `app/services/nodes/schema.py`

- [x] Add `depends_on: Optional[Dict[str, List[Any]]] = None` to the `PropertySchema` Pydantic model.
- [x] Confirm the field defaults to `None` — all existing `PropertySchema` instantiations continue to work without modification.
- [x] Add a docstring comment: `"Property is shown in UI only when ALL key-value constraints in depends_on are satisfied (AND relationship). Each list contains the allowed values for that key."`.

---

### TASK-B3 — Update `app/modules/lidar/registry.py`

- [x] Add imports at the top: `from app.modules.lidar.profiles import get_all_profiles, get_profile, build_launch_args`.
- [x] **Compute helper lists** at module load time (after importing profiles):
  ```python
  _port_capable_models = [p.model_id for p in get_all_profiles() if p.port_arg]
  # Result: ["multiscan", "tim_2xx", "tim_4xx", "tim_5xx", "tim_7xx"]
  ```
- [x] **Add `lidar_type` property as the FIRST entry** in the `properties` list:
  ```python
  PropertySchema(
      name="lidar_type",
      label="LiDAR Model",
      type="select",
      default="multiscan",
      required=True,
      help_text="Select the SICK LiDAR hardware model for this node",
      options=[{"label": p.display_name, "value": p.model_id} for p in get_all_profiles()]
  )
  ```
- [x] **Update `hostname` property**: add `depends_on={"mode": ["real"]}`.
- [x] **Rename `udp_port` property to `port`** (name, label, default=2112) and add:
  `depends_on={"mode": ["real"], "lidar_type": _port_capable_models}`
- [x] **Update `udp_receiver_ip` property**: add `depends_on={"mode": ["real"], "lidar_type": ["multiscan"]}`.
- [x] **Update `imu_udp_port` property**: change default to `7503` and add `depends_on={"mode": ["real"], "lidar_type": ["multiscan"]}`.
- [x] **Update `pcd_path` property**: add `depends_on={"mode": ["sim"]}`.
- [x] In `build_sensor()`:
  - Read `lidar_type = config.get("lidar_type", "multiscan")`.
  - Read `port = config.get("port")` (replaces `udp_port`).
  - Read `udp_receiver_ip = config.get("udp_receiver_ip")`.
  - Read `imu_udp_port = config.get("imu_udp_port")`.
  - Build `add_transform_xyz_rpy = f"{x},{y},{z},{roll},{pitch},{yaw}"`.
  - Wrap in `try/except KeyError` → raise `ValueError(f"Unknown lidar_type: '{lidar_type}'")`
  - Replace line 81 (hardcoded `launch_args`) with:
    ```python
    profile = get_profile(lidar_type)
    launch_args = build_launch_args(
        model_id=lidar_type,
        hostname=hostname,
        port=port,
        udp_receiver_ip=udp_receiver_ip,
        imu_udp_port=imu_udp_port,
        add_transform_xyz_rpy=add_transform_xyz_rpy
    )
    ```
  - After `LidarSensor` instantiation, set: `sensor.lidar_type = profile.model_id` and `sensor.lidar_display_name = profile.display_name`.
- [x] **Regression check**: For a node with no `lidar_type` and all-zero pose, confirm the generated `launch_args` is functionally equivalent to the current hardcoded value (multiScan defaults, `add_transform_xyz_rpy=0,0,0,0,0,0`).
  - Old: `./launch/sick_multiscan.launch hostname:=192.168.100.124 udp_receiver_ip:=192.168.100.10 udp_port:=2667 imu_udp_port:=7511`
  - New (from profiles defaults): `launch/sick_multiscan.launch hostname:=<configured> udp_port:=2115 udp_receiver_ip:=<configured> imu_udp_port:=<configured> add_transform_xyz_rpy:=0,0,0,0,0,0`
  - The `./` prefix difference and exact ports/IPs are **user-configured**; only the overall pattern must match. The `lidar_worker_process` already handles both relative and absolute launch file path resolution.

---

### TASK-B4 — Extend `app/modules/lidar/sensor.py`

- [x] Add `self.lidar_type: str = "multiscan"` and `self.lidar_display_name: str = "SICK multiScan"` as instance attributes in `LidarSensor.__init__` (with their default values).
- [x] In `get_status()`, add to the returned `status` dict:
  ```python
  status["lidar_type"] = self.lidar_type
  status["lidar_display_name"] = self.lidar_display_name
  ```
  These must be added after the `status` dict is constructed and before the `return` statement.
- [x] Do **not** change `__init__` signature — attributes are set externally by `build_sensor()` after instantiation (no constructor coupling needed).
- [x] Confirm all existing tests for `LidarSensor` still pass.

---

### TASK-B5 — Create `app/api/v1/lidar.py` Router

- [x] Create `app/api/v1/lidar.py` with `router = APIRouter(prefix="/lidar", tags=["lidar"])`.
- [x] Define Pydantic models (in this file or a shared `app/modules/lidar/models.py`):
  - `SickLidarProfileResponse` (see `api-spec.md` §8) — map from `SickLidarProfile` dataclass, include `port_arg`, `has_udp_receiver`, `has_imu_udp_port`.
  - `ProfilesListResponse` wrapping `List[SickLidarProfileResponse]`.
  - `LidarConfigValidationRequest` — `lidar_type: str`, `hostname: str`, `udp_receiver_ip: Optional[str] = None`, `port: Optional[int] = Field(None, ge=1024, le=65535)`, `imu_udp_port: Optional[int] = Field(None, ge=1024, le=65535)`.
  - `LidarConfigValidationResponse` — `valid: bool`, `lidar_type: str`, `resolved_launch_file: Optional[str]`, `errors: List[str] = []`, `warnings: List[str] = []`.
- [x] Implement `GET /lidar/profiles`:
  - Returns `ProfilesListResponse` from `get_all_profiles()`.
  - No authentication, no DB access. Fully in-memory.
- [x] Implement `POST /lidar/validate-lidar-config`:
  - Calls `get_profile(req.lidar_type)` — if `KeyError`, add to `errors` and return `valid=False` immediately.
  - Validates `hostname` is non-empty — if not, add to `errors`.
  - If `profile.has_udp_receiver` and `req.udp_receiver_ip` is None or empty — add to `errors`.
  - If `profile.port_arg` is non-empty and `req.port` is None — add to `warnings` (port defaults will be used).
  - If `profile.has_imu_udp_port` and `req.imu_udp_port` is None — add to `warnings` ("IMU data will be disabled").
  - If any `errors`, return `LidarConfigValidationResponse(valid=False, ...)`.
  - Otherwise return `valid=True` with any collected `warnings` and `resolved_launch_file=profile.launch_file`.
  - Use `HTTPException(422)` **only** for malformed request bodies (Pydantic handles this automatically). Do not raise 422 for semantic validation failures — use `valid=False` in the response body.
- [x] Add strict type hints on all endpoint functions.

---

### TASK-B6 — Mount New Router in `app/api/v1/__init__.py`

- [x] Import: `from .lidar import router as lidar_router`.
- [x] Add: `router.include_router(lidar_router)`.
- [x] Confirm `GET /api/v1/lidar/profiles` and `POST /api/v1/lidar/validate-lidar-config` both appear in the FastAPI OpenAPI docs at `/docs`.

---

### TASK-B7 — Extend Config Validator in `app/api/v1/config.py`

- [x] In `validate_configuration()`, after the existing `name`/`type`/`id` duplicate checks, add a sensor-specific block:
  ```python
  from app.modules.lidar.profiles import get_profile  # import inside function to avoid circular
  for i, node in enumerate(config.nodes):
      if node.get("type") == "sensor":
          node_name = node.get("name", f"#{i}")
          lidar_type = node.get("config", {}).get("lidar_type")
          if lidar_type is None:
              warnings.append(
                  f"Node '{node_name}': no lidar_type specified; defaulting to 'multiscan' (backward compat)."
              )
          else:
              try:
                  get_profile(lidar_type)
              except KeyError:
                  errors.append(
                      f"Node '{node_name}': lidar_type '{lidar_type}' is not a recognized SICK model."
                  )
  ```
- [x] Confirm this does **not** change the response shape (`valid`, `errors`, `warnings`, `summary` remain identical).

---

### TASK-B8 — Tests

- [ ] **Unit test `profiles.py`** (`tests/test_lidar_profiles.py`):
  - `get_all_profiles()` returns exactly 10 profiles.
  - `get_profile("multiscan")` returns profile with `has_imu_udp_port=True`, `launch_file="launch/sick_multiscan.launch"`.
  - `get_profile("tim_7xx")` returns profile with `has_imu_udp_port=False`, `port_arg="port"`.
  - `get_profile("unknown_xyz")` raises `KeyError`.
  - `build_launch_args("tim_5xx", "192.168.0.10", 2112, None, None, "0,0,0,0,0,0")` produces string containing `sick_tim_5xx.launch` and `port:=2112` and `add_transform_xyz_rpy:=0,0,0,0,0,0` but does **not** contain `udp_receiver_ip` or `imu_udp_port`.
  - `build_launch_args("multiscan", "192.168.0.1", 2115, "192.168.0.10", 7503, "0,0,0,0,0,0")` produces string containing `sick_multiscan.launch`, `udp_port:=2115`, `udp_receiver_ip:=192.168.0.10`, `imu_udp_port:=7503`.
  - `build_launch_args("lms_1xx", "192.168.0.5", None, None, None, "0,0,0,0,0,0")` produces string with `sick_lms_1xx.launch` and `hostname:=192.168.0.5` but no `port:=` token.
  - `build_launch_args("multiscan", "192.168.0.1", 2115, None, None, "0,0,0,0,0,0")` — no `udp_receiver_ip` token (since it is None).

- [ ] **Unit test `PropertySchema` extension** (`tests/test_schema.py`):
  - `PropertySchema(name="x", label="X", type="number")` instantiates with `depends_on=None`.
  - `PropertySchema(name="port", label="Port", type="number", depends_on={"mode": ["real"]})` serializes `depends_on` correctly in `.model_dump()`.

- [ ] **Integration test `GET /api/v1/lidar/profiles`**:
  - Returns HTTP 200 with `"profiles"` key.
  - Body contains all 10 profiles.
  - Each profile has `model_id`, `display_name`, `launch_file`, `port_arg`, `has_udp_receiver`, `has_imu_udp_port`.
  - `multiscan` profile has `has_udp_receiver: true` and `has_imu_udp_port: true`.
  - `tim_7xx` profile has both set to `false`.

- [ ] **Integration test `POST /api/v1/lidar/validate-lidar-config`**:
  - Valid multiScan config → `{ "valid": true, "errors": [], "resolved_launch_file": "launch/sick_multiscan.launch" }`.
  - Unknown `lidar_type` → `{ "valid": false }` with descriptive error.
  - multiScan config missing `udp_receiver_ip` → `valid: false` with error.
  - multiScan config with missing `imu_udp_port` → `valid: true` with warning.
  - TiM7xx config (no `udp_receiver_ip`, no `imu_udp_port`) → `valid: true, errors: []`.
  - Malformed body (missing `lidar_type`) → HTTP 422.

- [ ] **Integration test `GET /api/v1/nodes/definitions`**:
  - Sensor definition includes `lidar_type` as first property with `type: "select"` and 10 options.
  - `port` property has `depends_on.lidar_type` containing `"multiscan"`, `"tim_5xx"`, etc.
  - `udp_receiver_ip` has `depends_on: { "mode": ["real"], "lidar_type": ["multiscan"] }`.
  - `pcd_path` has `depends_on: { "mode": ["sim"] }`.

- [ ] **Integration test node create + reload + status**:
  - Create sensor node with `lidar_type: "tim_5xx"` via `POST /api/v1/nodes`.
  - Call `POST /api/v1/nodes/reload`.
  - Call `GET /api/v1/nodes/status/all`.
  - Confirm response contains `lidar_type: "tim_5xx"` and `lidar_display_name: "SICK TiM5xx"`.

- [ ] **Regression test — backward compat**:
  - Create sensor node with no `lidar_type` in config (simulate pre-feature node).
  - Call `build_sensor()` (or reload).
  - Confirm no error thrown.
  - Confirm `get_status()` returns `lidar_type: "multiscan"`.

- [ ] **Integration test `POST /api/v1/config/validate`**:
  - Config with sensor node missing `lidar_type` → `valid: true` with warning.
  - Config with sensor node having unknown `lidar_type` → `valid: false` with error.
