# Multi-LiDAR Type Support — Frontend Tasks

> **Assignee**: @fe-dev
> **Status**: Revised — Ready for Development
> **References**:
> - Requirements: `requirements.md`
> - Architecture: `technical.md`
> - API Contracts: `api-spec.md`
> - Rules: `.opencode/rules/frontend.md`

---

## Dependencies & Order of Operations

```
TASK-F1 (model extensions)
    └─► TASK-F2 (LidarProfilesApiService)
            └─► TASK-F3 (DynamicNodeEditor — depends_on logic + validation on save)
                    └─► TASK-F4 (NodeStatus badge in node-card)
                            └─► TASK-F5 (tests)
```

**Backend dependency**: TASK-F2 through TASK-F4 must use **mock data from `api-spec.md`** while backend TASK-B5/B6 are in progress. Mock `GET /api/v1/lidar/profiles` inline in the service during development.

TASK-F1 is a pure model change — no backend dependency, start immediately.
TASK-F3 `depends_on` filtering logic operates on schema returned by `GET /nodes/definitions`, which can be mocked with the schema from `api-spec.md` §3.

---

## Task Checklist

### TASK-F1 — Extend TypeScript Models

> **File**: `web/src/app/core/models/node.model.ts`

- [x] Add `depends_on?: Record<string, any[]>` field to the `PropertySchema` interface (after `hidden?: boolean`).
- [x] Add `lidar_type?: string` to the `NodeStatus` interface.
- [x] Add `lidar_display_name?: string` to the `NodeStatus` interface.

> **File**: `web/src/app/core/models/lidar.model.ts`

- [x] Add `lidar_type?: string` to the `LidarConfig` interface.

> **New File**: `web/src/app/core/models/lidar-profile.model.ts`

- [x] Create the file with:
  ```typescript
  export interface LidarProfile {
    model_id: string;
    display_name: string;
    launch_file: string;
    default_hostname: string;
    port_arg: string;        // "port" | "udp_port" | ""
    default_port: number;
    has_udp_receiver: boolean;
    has_imu_udp_port: boolean;
    scan_layers: number;
  }

  export interface LidarProfilesResponse {
    profiles: LidarProfile[];
  }

  export interface LidarConfigValidationRequest {
    lidar_type: string;
    hostname: string;
    udp_receiver_ip?: string;
    port?: number;
    imu_udp_port?: number;
  }

  export interface LidarConfigValidationResponse {
    valid: boolean;
    lidar_type: string;
    resolved_launch_file: string | null;
    errors: string[];
    warnings: string[];
  }
  ```

---

### TASK-F2 — Create `LidarProfilesApiService`

- [x] Scaffold: `cd web && ng g service core/services/api/lidar-profiles-api`.
- [x] Inject `HttpClient` via `inject(HttpClient)`.
- [x] Declare `profiles = signal<LidarProfile[]>([])`.
- [x] Declare `isLoading = signal<boolean>(false)`.
- [x] Implement `async loadProfiles(): Promise<void>`:
  - Sets `isLoading` to `true`.
  - Calls `GET ${environment.apiUrl}/lidar/profiles` via `firstValueFrom`.
  - On success: `this.profiles.set(data.profiles)`.
  - On error: logs error, sets `profiles` to `[]`.
  - Always resets `isLoading` to `false` in a `finally` block.
- [x] **Mock data for development**: Add `MOCK_LIDAR_PROFILES: LidarProfile[]` constant (matching `api-spec.md` §1 response) and call `this.profiles.set(MOCK_LIDAR_PROFILES)` initially. Remove once backend TASK-B5/B6 are deployed.
- [x] Do NOT inject `HttpClient` directly in feature components — this service is the single point of access.

---

### TASK-F3 — `depends_on` Rendering + Validation in `DynamicNodeEditorComponent`

> **File**: `web/src/app/features/settings/components/dynamic-node-editor/dynamic-node-editor.component.ts`

#### Part A — `depends_on` conditional rendering

- [x] Add a private `formValues = signal<Record<string, any>>({})` field to the class.
- [x] In `initForm()`, immediately after `this.configForm = this.fb.group(configGroup)`, add:
  ```typescript
  this.configForm.valueChanges.subscribe(v => this.formValues.set(v));
  this.formValues.set(this.configForm.getRawValue()); // seed initial state
  ```
  Store the subscription for cleanup: `private formValuesSub?: Subscription`.
- [x] In `ngOnDestroy()` (implement `OnDestroy` if not already): call `this.formValuesSub?.unsubscribe()`.
- [x] Replace the existing `visibleProperties` computed signal:
  ```typescript
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
- [x] Confirm the `@for (prop of visibleProperties(); ...)` loop in `dynamic-node-editor.component.html` is unchanged — the template does not need edits.
- [x] Confirm `onSelectChange` already handles `lidar_type` without changes (it uses the generic `configForm.get(propName)?.setValue(value)` pattern).
- [x] Guard against uninitialized form: ensure `this.formValues()` is called only when `this.configForm` exists. The seeding step in `initForm()` guarantees this order.

#### Part B — Validation on save for sensor nodes in real mode

- [x] Inject `LidarProfilesApiService` (or use `NodesApiService.validateLidarConfig` — see TASK-F3 Part C).
- [x] In `onSave()`, add a validation gate before the `upsertNode` call:
  ```typescript
  // Only validate real-mode sensor nodes
  if (def.type === 'sensor' && configRaw['mode'] === 'real') {
    const validationReq: LidarConfigValidationRequest = {
      lidar_type: configRaw['lidar_type'],
      hostname: configRaw['hostname'],
      udp_receiver_ip: configRaw['udp_receiver_ip'] || undefined,
      port: configRaw['port'] || undefined,
      imu_udp_port: configRaw['imu_udp_port'] || undefined,
    };
    try {
      const result = await this.nodesApi.validateLidarConfig(validationReq);
      if (!result.valid) {
        this.toast.danger(result.errors[0] ?? 'Invalid LiDAR configuration.');
        this.isSaving.set(false);
        return;
      }
      if (result.warnings.length > 0) {
        this.toast.warning(result.warnings[0]);
        // Do not abort save on warnings — proceed.
      }
    } catch {
      // If validation endpoint is unavailable, proceed with save (graceful degradation).
    }
  }
  ```
- [x] Ensure `isSaving.set(false)` is called in all early-return branches.

#### Part C — `validateLidarConfig` on `NodesApiService`

> **File**: `web/src/app/core/services/api/nodes-api.service.ts`

- [x] Add imports for `LidarConfigValidationRequest` and `LidarConfigValidationResponse` from `lidar-profile.model.ts`.
- [x] Add method:
  ```typescript
  async validateLidarConfig(
    request: LidarConfigValidationRequest
  ): Promise<LidarConfigValidationResponse> {
    return await firstValueFrom(
      this.http.post<LidarConfigValidationResponse>(
        `${environment.apiUrl}/lidar/validate-lidar-config`,
        request
      )
    );
  }
  ```
- [x] **Mock for development** (until backend TASK-B5 is deployed): make the method immediately return `{ valid: true, lidar_type: request.lidar_type, resolved_launch_file: null, errors: [], warnings: [] }`. Remove mock once backend is live.

---

### TASK-F4 — `lidar_display_name` Badge in Node Card

> **File**: `web/src/app/features/settings/components/node-card/node-card.component.html`

- [x] Read the existing template to locate where the node name is rendered.
- [x] Immediately below the node name, add:
  ```html
  @if (status()?.lidar_display_name) {
    <span class="block text-[10px] text-syn-color-neutral-500 font-medium tracking-wide uppercase leading-tight">
      {{ status()!.lidar_display_name }}
    </span>
  }
  ```
- [x] Use Tailwind CSS only. No custom CSS, no `.scss` modifications.
- [x] Confirm `node-card.component.ts` does **not** need changes — `status` is already typed as `NodeStatus | null` which now includes the optional `lidar_display_name` field (after TASK-F1).
- [x] Confirm this is a dumb/presentational component — do not add any API calls here.

---

### TASK-F5 — Tests

> Follow the pattern of existing `.spec.ts` files alongside their component/service files.

**`LidarProfilesApiService`** (`lidar-profiles-api.service.spec.ts`):
- [ ] `loadProfiles()` calls `GET /lidar/profiles` and populates `profiles` signal from the response.
- [ ] `loadProfiles()` on HTTP error leaves `profiles` as `[]` and does not throw.
- [ ] `isLoading` signal goes `false → true → false` across a successful call.
- [ ] Use `HttpClientTestingModule` and `HttpTestingController`.

**`DynamicNodeEditorComponent` — `depends_on` filtering**:
- [ ] Provide a mock `NodeStoreService` returning a sensor `NodeDefinition` matching `api-spec.md` §3 (with `depends_on` populated on `hostname`, `port`, `udp_receiver_ip`, `imu_udp_port`, `pcd_path`).
- [ ] When `configForm` value is `{ mode: "sim", lidar_type: "multiscan" }`, `visibleProperties()` does NOT include `hostname`, `port`, `udp_receiver_ip`, `imu_udp_port`.
- [ ] When `configForm` value is `{ mode: "real", lidar_type: "tim_7xx" }`, `hostname` IS included, `udp_receiver_ip` is NOT, `imu_udp_port` is NOT.
- [ ] When `configForm` value is `{ mode: "real", lidar_type: "multiscan" }`, `hostname`, `port`, `udp_receiver_ip`, `imu_udp_port` are ALL included.
- [ ] When `configForm` value is `{ mode: "real", lidar_type: "lms_1xx" }`, `port` is NOT included (lms_1xx has empty `port_arg`).
- [ ] `pcd_path` is included only when `mode === "sim"`.

**`NodesApiService.validateLidarConfig`**:
- [ ] Method posts to correct URL `/lidar/validate-lidar-config`.
- [ ] Returns parsed `LidarConfigValidationResponse`.
- [ ] Use `HttpClientTestingModule`.

**`node-card.component` badge rendering**:
- [ ] When `status` has `lidar_display_name: "SICK TiM7xx"`, the badge text appears in the rendered template.
- [ ] When `status` has no `lidar_display_name` (or is null), no badge element is rendered.

---

### Manual Integration Smoke Test (non-automated checklist)

- [ ] Open node editor for a `sensor` node. Confirm `LiDAR Model` dropdown is the **first** property.
- [ ] Default selection is `SICK multiScan`.
- [ ] Switch `Mode` to `Simulation (PCD)`: `Hostname`, `Port`, `UDP Receiver IP`, `IMU UDP Port` all disappear; `PCD Path` appears.
- [ ] Switch `Mode` back to `Hardware (Real)`: `Hostname` reappears. With `SICK multiScan` selected: `Port`, `UDP Receiver IP`, `IMU UDP Port` all appear.
- [ ] Select `SICK TiM7xx`: `UDP Receiver IP` and `IMU UDP Port` disappear; `Port` remains.
- [ ] Select `SICK LMS1xx`: `Port` also disappears (only `Hostname` visible among network fields).
- [ ] Save a node with `lidar_type = "tim_5xx"`. Reload the page. Reopen the node editor. Confirm `LiDAR Model` dropdown shows `SICK TiM5xx` selected.
- [ ] After saving, the node card shows `SICK TiM5xx` as a small badge under the node name.
- [ ] Attempt to save a `real` mode multiScan node without `udp_receiver_ip`. Confirm a toast error is shown and save is aborted (requires backend to be live).
- [ ] Open an existing workspace with a legacy sensor node (no `lidar_type` in stored config). Confirm it opens without error and defaults to `SICK multiScan`.
- [ ] Confirm Three.js point cloud visualization renders without regressions on a `sim` mode node.
