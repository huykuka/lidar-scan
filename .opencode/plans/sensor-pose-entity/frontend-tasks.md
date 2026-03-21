# Frontend Tasks: Unified Sensor Pose Entity

**Feature:** `sensor-pose-entity`  
**References:** `requirements.md` · `technical.md` · `api-spec.md`  
**Developer:** @fe-dev  
**Status:** Complete

> 📋 **All work is strictly within `/web/`**. Do not touch backend files.  
> 📋 **Mock first:** While backend is in progress, mock all API responses using `api-spec.md`.  
> 📋 **Angular CLI** must be used for scaffolding all new components and services.

---

## Phase 0 — Canonical Pose Model

- [x] **F-01** Create `web/src/app/core/models/pose.model.ts`:
  - Export `Pose` interface with six typed fields (see `technical.md §Decision 9`).
  - Export `ZERO_POSE: Pose` constant `{ x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0 }`.
  - Add JSDoc comments for all fields (unit: mm for position, degrees for angles).

- [x] **F-02** Update `web/src/app/core/models/index.ts`:
  - Export `Pose` and `ZERO_POSE` from `pose.model.ts`.

- [x] **F-03** Refactor `web/src/app/core/models/lidar.model.ts`:
  - Remove `LidarPose` interface entirely.
  - Import `Pose` from `pose.model.ts`.
  - Change `LidarConfig.pose: LidarPose` → `LidarConfig.pose: Pose`.

- [x] **F-04** Refactor `web/src/app/core/models/calibration.model.ts`:
  - Remove the local `Pose` interface definition.
  - Import `Pose` from `../pose.model`.
  - Verify `CalibrationResult.pose_before`, `pose_after`, `CalibrationHistoryRecord.pose_before`, `pose_after` all use the imported `Pose`.

- [x] **F-05** Refactor `web/src/app/core/models/recording.model.ts`:
  - Replace the inline anonymous pose type in `RecordingMetadata.pose` with `Pose` imported from `pose.model.ts`.

- [x] **F-06** Update `web/src/app/core/models/node.model.ts — NodeConfig`:
  - Add `pose?: Pose` field.
  - Import `Pose` from `pose.model.ts`.

---

## Phase 1 — Scaffold PoseFormComponent

- [x] **F-07** Scaffold with Angular CLI:
  ```bash
  cd web && ng g component plugins/sensor/form/pose-form --standalone
  ```

- [x] **F-08** Implement `pose-form.component.ts`:
  - Signal `input()`: `pose = input<Pose>(ZERO_POSE)`
  - Signal `output()`: `poseChange = output<Pose>()`
  - Internal `FormGroup` (`poseFormGroup`) with 6 `FormControl` entries.
  - `Validators.required` + custom `angleRangeValidator` (min -180, max +180) on roll, pitch, yaw.
  - `effect()` syncs `pose` input signal → patches `poseFormGroup` (only when changed from outside).
  - `onXyzInput(field: 'x'|'y'|'z', event: Event)` — reads numeric input value, patches form.
  - `onRangeInput(field: 'roll'|'pitch'|'yaw', event: Event)` — reads `Number((event.target as any).value)`, patches form, emits `poseChange`.
  - `onRangeChange(field: 'roll'|'pitch'|'yaw', event: Event)` — marks field as dirty (committed).
  - `resetPose()` — patches all six controls to `ZERO_POSE`, emits `poseChange` with zeroed pose.
  - `angleLabelFn = (value: number) => \`${value}°\`` — passed to `syn-range` `tooltipFormatter`.
  - Exposes `get isValid(): boolean` for parent to gate the save button.

- [x] **F-09** Implement `pose-form.component.html`:
  - **Position section** (label: "Position (mm)"):
    - 3-column grid (col-span-1 each).
    - `syn-input` for X: `type="number"`, `label="X"`, `size="small"`, prefix slot shows "mm", bound to form control.
    - `syn-input` for Y: same pattern.
    - `syn-input` for Z: same pattern.
  - **Orientation section** (label: "Orientation (°)"):
    - Single-column layout (full width sliders).
    - `syn-range` for Roll: `[label]="'Roll'"`, `[min]="-180"`, `[max]="180"`, `[step]="1"`, `[tooltipFormatter]="angleLabelFn"`, `size="small"`, `(synInputEvent)="onRangeInput('roll', $event)"`, `(synChangeEvent)="onRangeChange('roll', $event)"`.
    - `syn-range` for Pitch: same pattern with `'pitch'`.
    - `syn-range` for Yaw: same pattern with `'yaw'`.
    - Suffix each slider with a small `<span>` showing current value in degrees (e.g. `{{ poseFormGroup.get('roll')?.value }}°`).
  - **Reset Pose button** (bottom of form):
    - `<syn-button variant="outline" size="small" type="button" (click)="resetPose()">`.
    - Add `<syn-icon name="restart_alt" slot="prefix"></syn-icon>` inside button.
    - Full-width, centered.
  - Show inline validation error below each angular field if dirty+invalid: `@if (control.dirty && control.invalid)`.

- [x] **F-10** Add `angleRangeValidator` to a shared validators file or inline in `pose-form.component.ts`:
  ```typescript
  function angleRangeValidator(control: AbstractControl): ValidationErrors | null {
    const v = control.value;
    if (v === null || v === undefined || v === '') return null;
    const n = Number(v);
    if (isNaN(n) || n < -180 || n > 180) {
      return { angleRange: { min: -180, max: 180, actual: v } };
    }
    return null;
  }
  ```

---

## Phase 2 — Integrate PoseFormComponent into SensorNodeEditorComponent

- [x] **F-11** Update `sensor-node-editor.component.ts`:
  - Import `PoseFormComponent`.
  - Add signal `poseValue = signal<Pose>(ZERO_POSE)`.
  - In `initForm()`: read `data.pose` (or `ZERO_POSE` fallback) and set `poseValue`.
  - Add `onPoseChange(pose: Pose)` handler: updates `poseValue` signal.
  - Add `isPoseValid = signal<boolean>(true)` — updated from `PoseFormComponent.isValid` via `@ViewChild` or output.
  - In `onSave()`: include `pose: this.poseValue()` in the payload passed to `facade.saveNode()`.
  - Update save-disabled condition: `form.invalid || configForm.invalid || !isPoseValid() || isSaving()`.

- [x] **F-12** Update `sensor-node-editor.component.html`:
  - Remove any existing `syn-input` controls for `x`, `y`, `z`, `roll`, `pitch`, `yaw` (they previously rendered as generic number inputs from the `visibleProperties()` loop — now the loop skips the `"pose"` type property, and `PoseFormComponent` handles rendering).
  - Add a `<syn-divider>` before the pose section.
  - Add `<app-pose-form [pose]="poseValue()" (poseChange)="onPoseChange($event)" />` after the config property loop.

- [x] **F-13** Update the property loop in `sensor-node-editor.component.html`:
  - Add `@if (prop.type !== 'pose')` guard so the generic loop skips the new `"pose"` type property returned by the backend node definition.

---

## Phase 3 — Update SensorNodeCardComponent (Canvas Preview)

- [x] **F-14** Update `plugins/sensor/node/sensor-node-card.component.ts`:
  - Change `protected pose = computed(...)` to read from `this.node().data.pose` (a `Pose` object) instead of `config['x']`, `config['y']`, `config['z']`.
  - Change `protected rotation = computed(...)` to read from `this.node().data.pose.roll`, `.pitch`, `.yaw`.
  - Add null-safety: `const p = this.node().data.pose ?? ZERO_POSE`.

- [x] **F-15** Update `sensor-node-card.component.html` (if any template references `config['x']` etc.) to use the `pose()` and `rotation()` computed signals.

---

## Phase 4 — Fix Recording Metadata (Bug Fix)

- [x] **F-16** Update `features/settings/components/.../node-recording-controls.ts`:
  - Change `metadata.pose = config.pose` (line 60) → `metadata.pose = data.pose` (reads from the top-level `NodeConfig.pose` field, not `config.pose`).
  - This fixes the silent undefined bug identified in `technical.md §2.1`.

---

## Phase 5 — API Service Updates

- [x] **F-17** Update `core/services/api/nodes-api.service.ts — upsertNode()`:
  - Ensure the `Partial<NodeConfig>` passed to `POST /nodes` includes the `pose` field.
  - No change to HTTP method or URL.

- [x] **F-18** Update `core/services/stores/lidar-store.service.ts`:
  - `LidarState.selectedLidar: Partial<LidarConfig>` — `LidarConfig.pose: Pose` is now properly typed (carried by F-03). No store logic changes needed, but verify `setState({selectedLidar: ...})` calls propagate `pose`.

- [x] **F-19** Update `core/services/api/lidar-api.service.ts — getLidars()`:
  - The mapping `...n.config` spread currently copies pose keys from `config` into the LidarConfig object. After the backend refactor, pose is in `n.pose` (top-level), not `n.config`.
  - Update mapping to: `pose: n.pose ?? ZERO_POSE`.

---

## Phase 6 — Tests

- [x] **F-20** Unit tests for `PoseFormComponent` (`pose-form.component.spec.ts`):
  - Renders 3 `syn-input` controls (x, y, z) and 3 `syn-range` controls (roll, pitch, yaw).
  - `resetPose()` sets all 6 form values to 0 and emits `poseChange` with `ZERO_POSE`.
  - `poseChange` emits correct value when slider fires `syn-input` event.
  - Validation: roll=181 → `angleRange` error; roll=180 → no error; roll=-180 → no error.
  - Input signal change propagates to form controls.

- [x] **F-21** Unit tests for `SensorNodeEditorComponent` (`sensor-node-editor.component.spec.ts`):
  - `PoseFormComponent` is rendered inside the editor.
  - `onSave()` passes `pose` field in payload when form is valid.
  - Save button is disabled when pose is invalid (e.g., roll=270).
  - Reset Pose action propagates to `poseValue` signal.

- [x] **F-22** Unit tests for `SensorNodeCardComponent` (`sensor-node-card.component.spec.ts`):
  - `pose()` computed reads from `node.data.pose.x` (not `config['x']`).
  - `rotation()` computed reads from `node.data.pose.roll` (not `config['roll']`).
  - Graceful fallback to `ZERO_POSE` when `node.data.pose` is undefined.

- [x] **F-23** Unit tests for `NodeRecordingControls` (`node-recording-controls.spec.ts`):
  - `metadata.pose` is set from `data.pose` (top-level), not `config.pose`.

- [x] **F-24** Type-check verification:
  ```bash
  cd web && npx tsc --noEmit
  ```
  Must pass with zero errors after all changes.

---

## Phase 7 — Linter

- [x] **F-25** Run Angular ESLint:
  ```bash
  cd web && npx ng lint
  ```
  Resolve all lint errors/warnings introduced by this feature.

---

## Dependencies

```
F-01..F-06 (Model layer — no component deps)
  → F-07..F-10 (PoseFormComponent scaffold)
    → F-11..F-13 (SensorNodeEditor integration)
    → F-14..F-15 (SensorNodeCard update)
  → F-16 (Recording bug fix — independent)
  → F-17..F-19 (API/Store updates)
→ F-20..F-23 (Tests — can be written TDD-first)
→ F-24, F-25 (Linter/TypeCheck — final gate)
```

**Backend Dependency:**  
Frontend can develop against mocked API (per `api-spec.md`) until backend B-07 is complete.
Once the backend is deployed, remove mocks and verify against real API.

**Synergy UI Dependency:**  
Confirm `syn-range` and `syn-button` are present in the project's Synergy version:
```bash
cd web && grep "@synergy-design-system" package.json
```
`syn-range` and `syn-icon` must be available. No version upgrades expected.
