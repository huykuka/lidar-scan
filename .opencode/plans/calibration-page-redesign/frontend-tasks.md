# Frontend Tasks: Calibration Page Redesign

**Feature:** `calibration-page-redesign`
**References:** `technical.md`, `api-spec.md`, `requirements.md`
**Developer:** `@fe-dev`

> **Ordering rule:** Complete task groups in numbered order. Groups 1–3 (models, API service, store) must be complete
> before starting Groups 4–7 (components).
> **Checkbox rule:** Mark `[x]` when a task is verified working, not just coded.
> **Mock rule:** While backend is not ready, mock all API calls using `MOCK_CALIBRATION_STATUS_IDLE` and
> `MOCK_CALIBRATION_STATUS_PENDING` from `api-spec.md`. Remove mocks only when backend tasks 5.1–5.4 are `[x]`.

---

## Dependencies

```
Group 1 (models) ──► Group 2 (API service) ──► Group 3 (store)
                                                     │
                  ┌──────────────┬─────────────┬────┴──────────┐
                  ▼              ▼             ▼               ▼
             Group 4        Group 5       Group 6         Group 7
         (node controls)  (viewer page) (list page)   (history page)
```

Backend tasks that unblock frontend integration:
- **Backend 5.1** (new `/status` endpoint) → unblocks Group 3 mock removal
- **Backend 4.1–4.2** (rollback `record_id`) → unblocks Group 7 rollback wiring
- **Backend 5.2** (reject response schema fix) → unblocks Group 5 reject action wiring

---

## Group 1: Update TypeScript Models

**File:** `web/src/app/core/models/calibration.model.ts`

### Task 1.1 — Add `PendingCalibrationResult` and `CalibrationNodeStatusResponse` interfaces

- [x] Open `calibration.model.ts` and read the existing interfaces
- [x] Add `Pose` helper type if not already present: `{ x: number; y: number; z: number; roll: number; pitch: number; yaw: number }`
- [x] Add `PendingCalibrationResult` interface:
  ```typescript
  export interface PendingCalibrationResult {
    fitness: number;
    rmse: number;                          // meters (ICP output)
    quality: 'excellent' | 'good' | 'poor';
    quality_good: boolean;
    source_sensor_id?: string;
    processing_chain: string[];
    pose_before: Pose;                     // x/y/z in mm, angles in degrees
    pose_after: Pose;                      // x/y/z in mm, angles in degrees
    transformation_matrix: number[][];    // 4×4; translation col in meters
  }
  ```
- [x] Add `CalibrationNodeStatusResponse` interface:
  ```typescript
  export interface CalibrationNodeStatusResponse {
    node_id: string;
    node_name: string;
    enabled: boolean;
    calibration_state: 'idle' | 'pending';
    quality_good: boolean | null;
    reference_sensor_id: string | null;
    source_sensor_ids: string[];
    buffered_frames: Record<string, number>;
    last_calibration_time: string | null;
    pending_results: Record<string, PendingCalibrationResult>;
  }
  ```
- [x] **Verify:** No TypeScript compilation errors (`ng build --dry-run` or `tsc --noEmit`)

### Task 1.2 — Add `PoseDelta` interface and update `CalibrationRollbackRequest`

- [x] Add `PoseDelta` interface:
  ```typescript
  export interface PoseDelta {
    dx: number;    // mm (pose_after.x - pose_before.x)
    dy: number;    // mm
    dz: number;    // mm
    droll: number;   // degrees
    dpitch: number;  // degrees
    dyaw: number;    // degrees
  }
  ```
- [x] Find existing `CalibrationRollbackRequest` interface. Change `timestamp: string` → `record_id: string`:
  ```typescript
  export interface CalibrationRollbackRequest {
    record_id: string;   // PK, replaces the old timestamp-based lookup
  }
  ```
- [x] **Verify:** Search for any component or service that constructs `CalibrationRollbackRequest` with `{ timestamp: ... }` — update those call sites to `{ record_id: ... }` as part of this task.

### Task 1.3 — Extend `CalibrationHistoryRecord` with new fields

- [x] Find the existing `CalibrationHistoryRecord` interface
- [x] Add the following new optional fields (backward compatible — all optional):
  ```typescript
  accepted_at?: string;           // ISO-8601 timestamp when accepted
  accepted_by?: string | null;    // Reserved for future auth
  node_id?: string;               // Which calibration DAG node ran this
  rollback_source_id?: string;    // If this is a rollback, original record_id
  registration_method?: { method: string; stages: string[] } | null;
  pose_before: Pose;              // x,y,z in mm; angles in degrees
  pose_after: Pose;               // x,y,z in mm; angles in degrees
  transformation_matrix: number[][];  // 4×4
  ```
- [x] **Note:** `pose_before`, `pose_after`, `transformation_matrix` are non-optional on new records but may be `undefined` on very old legacy DB rows — consider making them `Pose | undefined` if legacy rows are a concern (discuss with backend dev)
- [x] **Verify:** No compilation errors. All existing usages of `CalibrationHistoryRecord` still compile.

---

## Group 2: Update `CalibrationApiService`

**File:** `web/src/app/core/services/api/calibration-api.service.ts`

### Task 2.1 — Add `getNodeStatus()` method

- [x] Open `calibration-api.service.ts` and read the existing methods
- [x] Import `CalibrationNodeStatusResponse` from models
- [x] Add new async method:
  ```typescript
  async getNodeStatus(nodeId: string): Promise<CalibrationNodeStatusResponse> {
    return await firstValueFrom(
      this.http.get<CalibrationNodeStatusResponse>(
        `${environment.apiUrl}/calibration/${nodeId}/status`,
      ),
    );
  }
  ```
- [x] **Mock alternative** (use while backend endpoint is not ready): return `MOCK_CALIBRATION_STATUS_IDLE` from `api-spec.md` mock data instead of the HTTP call; wrap in `Promise.resolve()`
- [x] **Verify:** TypeScript compiles. Call `getNodeStatus('test')` in a test component and confirm it returns `CalibrationNodeStatusResponse` shape.

### Task 2.2 — Fix `rollback()` to use `record_id`

- [x] Find the existing `rollback()` method in `CalibrationApiService`
- [x] Its current request body sends `{ timestamp: string }`. Change to send `{ record_id: string }`:
  ```typescript
  async rollback(
    sensorId: string,
    request: CalibrationRollbackRequest,  // { record_id: string }
  ): Promise<CalibrationRollbackResponse> {
    return await firstValueFrom(
      this.http.post<CalibrationRollbackResponse>(
        `${environment.apiUrl}/calibration/rollback/${sensorId}`,
        request,
      ),
    );
  }
  ```
- [x] Confirm `CalibrationRollbackRequest` is now `{ record_id: string }` (done in Task 1.2)
- [x] **Verify:** No callers of `rollback()` still pass `{ timestamp: ... }`

---

## Group 3: Create `CalibrationStoreService`

**File:** `web/src/app/core/services/stores/calibration-store.service.ts` *(new file)*

> Follow the exact pattern of `RecordingStoreService`. Read that file before starting this group.

### Task 3.1 — Define `CalibrationState` interface and initial state

- [x] Read `web/src/app/core/services/stores/recording-store.service.ts` to understand the `SignalsSimpleStoreService` base class pattern
- [x] Create `web/src/app/core/services/stores/calibration-store.service.ts`
- [x] Define the state interface in the file:
  ```typescript
  export interface CalibrationState {
    nodeStatuses: Record<string, CalibrationNodeStatusResponse>;
    pollingNodeId: string | null;
    historyByNode: Record<string, CalibrationHistoryRecord[]>;
    isLoadingStatus: boolean;
    isLoadingHistory: boolean;
    isTriggering: boolean;
    isAccepting: boolean;
    isRejecting: boolean;
    isRollingBack: boolean;
    error: string | null;
  }
  ```
- [x] Define `INITIAL_STATE: CalibrationState` with all `Record<>` fields as `{}`, booleans as `false`, strings as `null`
- [x] Declare the class extending `SignalsSimpleStoreService<CalibrationState>` with `providedIn: 'root'`
- [x] Call `super(INITIAL_STATE)` in the constructor
- [x] **Verify:** Class instantiates without errors (add a `console.log(this.getState())` temporarily)

### Task 3.2 — Add selectors (computed signals)

- [x] Add all selectors via `this.select(key)`:
  ```typescript
  readonly nodeStatuses = this.select('nodeStatuses');
  readonly pollingNodeId = this.select('pollingNodeId');
  readonly historyByNode = this.select('historyByNode');
  readonly isLoadingStatus = this.select('isLoadingStatus');
  readonly isLoadingHistory = this.select('isLoadingHistory');
  readonly isTriggering = this.select('isTriggering');
  readonly isAccepting = this.select('isAccepting');
  readonly isRejecting = this.select('isRejecting');
  readonly isRollingBack = this.select('isRollingBack');
  readonly error = this.select('error');
  ```
- [x] Add `getNodeStatus` computed factory (returns a function):
  ```typescript
  readonly getNodeStatus = computed(() => {
    const statuses = this.nodeStatuses();
    return (nodeId: string): CalibrationNodeStatusResponse | null =>
      statuses[nodeId] ?? null;
  });
  ```
- [x] Add `getHistoryForNode` computed factory:
  ```typescript
  readonly getHistoryForNode = computed(() => {
    const map = this.historyByNode();
    return (nodeId: string): CalibrationHistoryRecord[] => map[nodeId] ?? [];
  });
  ```
- [x] **Verify:** In a test component, inject the store and bind `store.isTriggering()` to the template — it should render `false`.

### Task 3.3 — Add polling mechanism (`startPolling` / `stopPolling`)

- [x] Declare private poll timer field:
  ```typescript
  private _pollTimer: ReturnType<typeof setInterval> | null = null;
  ```
- [x] Implement `startPolling(nodeId: string): void`:
  ```typescript
  startPolling(nodeId: string): void {
    this.stopPolling();
    this.setState({ pollingNodeId: nodeId });
    void this._fetchStatus(nodeId);  // immediate first fetch
    this._pollTimer = setInterval(() => void this._fetchStatus(nodeId), 2000);
  }
  ```
- [x] Implement `stopPolling(): void`:
  ```typescript
  stopPolling(): void {
    if (this._pollTimer !== null) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    this.setState({ pollingNodeId: null });
  }
  ```
- [x] Implement private `_fetchStatus(nodeId: string): Promise<void>`:
  ```typescript
  private async _fetchStatus(nodeId: string): Promise<void> {
    try {
      const status = await this.calibrationApi.getNodeStatus(nodeId);
      const current = this.nodeStatuses();
      this.setState({ nodeStatuses: { ...current, [nodeId]: status } });
    } catch {
      // Silently ignore poll failures — stale data is better than an error loop
    }
  }
  ```
- [x] Implement `ngOnDestroy()` to call `this.stopPolling()` (implement `OnDestroy`)
- [x] **Verify:** Call `startPolling('test-id')`, confirm `pollingNodeId()` is set. Call `stopPolling()`, confirm `pollingNodeId()` is `null`. Inspect network tab: confirm 2s polling requests fire.

### Task 3.4 — Add action methods (`triggerCalibration`, `acceptCalibration`, `rejectCalibration`, `rollbackHistory`, `loadHistory`)

- [x] Implement `triggerCalibration(nodeId: string, request: CalibrationTriggerRequest): Promise<void>`:
  ```typescript
  async triggerCalibration(nodeId: string, request: CalibrationTriggerRequest): Promise<void> {
    this.setState({ isTriggering: true, error: null });
    try {
      await this.calibrationApi.triggerCalibration(nodeId, request);
    } catch (err) {
      this.setState({ error: this._extractError(err) });
    } finally {
      this.setState({ isTriggering: false });
    }
  }
  ```
- [x] Implement `acceptCalibration(nodeId: string, request: CalibrationAcceptRequest): Promise<void>`:
  - Set `isAccepting: true`
  - Call `calibrationApi.acceptCalibration(nodeId, request)`
  - On success: call `void this._fetchStatus(nodeId)` to refresh immediately
  - On error: set `error`
  - Finally: set `isAccepting: false`
- [x] Implement `rejectCalibration(nodeId: string): Promise<void>`:
  - Set `isRejecting: true`
  - Call `calibrationApi.rejectCalibration(nodeId)`
  - On success: call `void this._fetchStatus(nodeId)` to refresh immediately
  - On error: set `error`
  - Finally: set `isRejecting: false`
- [x] Implement `rollbackHistory(sensorId: string, recordId: string): Promise<void>`:
  - Set `isRollingBack: true`
  - Call `calibrationApi.rollback(sensorId, { record_id: recordId })`
  - On error: set `error`
  - Finally: set `isRollingBack: false`
- [x] Implement `loadHistory(nodeId: string, limit = 50, runId?: string): Promise<void>`:
  - Set `isLoadingHistory: true`
  - Call `calibrationApi.getHistory(nodeId, limit, undefined, runId)`
  - On success: update `historyByNode` signal: `{ ...current, [nodeId]: response.history }`
  - On error: set `error`
  - Finally: set `isLoadingHistory: false`
- [x] Add private helper `_extractError(err: unknown): string`:
  ```typescript
  private _extractError(err: unknown): string {
    if (err instanceof Error) return err.message;
    if (typeof err === 'object' && err !== null && 'error' in err) return String((err as { error: unknown }).error);
    return 'An unexpected error occurred';
  }
  ```
- [x] **Verify:** Mock the API service. Call `triggerCalibration('node-1', {})`. Confirm `isTriggering` goes `true → false`. Confirm `error` is null on success, set on failure.

### Task 3.5 — Export `CalibrationStoreService` from stores index

- [x] Open `web/src/app/core/services/stores/index.ts`
- [x] Add: `export { CalibrationStoreService } from './calibration-store.service';`
- [x] **Verify:** Import `CalibrationStoreService` from `@core/services/stores` in a test component — no module-not-found error.

---

## Group 4: Refactor `NodeCalibrationControls` (DAG Canvas)

**Files:**
- `web/src/app/features/settings/components/flow-canvas/node/node-calibration-controls/node-calibration-controls.ts`
- `web/src/app/features/settings/components/flow-canvas/node/node-calibration-controls/node-calibration-controls.html`

### Task 4.1 — Remove action methods, inject `Router`, add navigation

- [x] Read both files (`*.ts` and `*.html`) in full
- [x] **Remove** the following from the `.ts` file:
  - `triggerCalibration()` method
  - `acceptCalibration()` method
  - `rejectCalibration()` method
  - `CalibrationApiService` injection (`private calibrationApi`)
  - `ToastService` injection (if only used for calibration toasts — keep if used for other things)
  - `isCalibrating` signal (if present)
  - `calibrationError` signal (if present)
  - Any loading state signals related to the above actions
- [x] **Keep:** `hasPendingCalibration` computed signal (used for badge display)
- [x] **Keep:** `node = input<NodeConfig>(...)` input
- [x] **Add:** `private router = inject(Router)` — import `Router` from `@angular/router`
- [x] **Add** navigation method:
  ```typescript
  navigateToCalibration(): void {
    void this.router.navigate(['/calibration', this.node().id]);
  }
  ```
- [x] **Verify:** No unused imports remain. `ng build` passes for this component.

### Task 4.2 — Replace template with minimal status badge + navigation icon

- [x] Replace the entire content of `node-calibration-controls.html` with:
  ```html
  <!-- Calibration Status Badge + Navigation -->
  <div class="flex items-center gap-1">
    @if (hasPendingCalibration()) {
      <syn-badge variant="warning" size="small">Pending</syn-badge>
    } @else {
      <syn-badge variant="neutral" size="small">Idle</syn-badge>
    }
    <syn-icon-button
      (click)="navigateToCalibration(); $event.stopPropagation()"
      label="Go to Calibration Page"
      name="open_in_new"
      size="small"
      title="Go to Calibration"
    ></syn-icon-button>
  </div>
  ```
- [x] Confirm `syn-badge` and `syn-icon-button` are imported in the component's `imports` array (add if missing)
- [x] **Verify:** In the DAG canvas, the node card shows only the status badge and the nav icon button. Clicking the icon opens `/calibration/:id`. No trigger/accept/reject buttons visible.

---

## Group 5: Rebuild `CalibrationViewerComponent` (Detail Page)

**Files:**
- `web/src/app/features/calibration/components/calibration-viewer/calibration-viewer.component.ts`
- `web/src/app/features/calibration/components/calibration-viewer/calibration-viewer.component.html`

### Task 5.1 — Fix broken `calibrationNode` computed and wire `CalibrationStoreService`

- [x] Read the current `.ts` file in full — note the `calibrationNode` computed is `() => null` with TODO comment (around line 59–63)
- [x] Inject `CalibrationStoreService`: `private calibrationStore = inject(CalibrationStoreService)`
- [x] Inject `ActivatedRoute`: `private route = inject(ActivatedRoute)` (likely already injected)
- [x] Add `nodeId = signal<string | null>(null)` — local signal to track current route param
- [x] In the constructor, add a route effect:
  ```typescript
  effect(() => {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.nodeId.set(id);
      this.calibrationStore.startPolling(id);
      void this.calibrationStore.loadHistory(id, 50);
    }
  }, { allowSignalWrites: true });
  ```
- [x] **Replace** the broken `calibrationNode` computed with:
  ```typescript
  calibrationNode = computed<CalibrationNodeStatusResponse | null>(() =>
    this.calibrationStore.getNodeStatus()(this.nodeId() ?? '')
  );
  ```
- [x] Implement `ngOnDestroy()`:
  ```typescript
  ngOnDestroy(): void {
    this.calibrationStore.stopPolling();
  }
  ```
- [x] **Verify:** Navigate to `/calibration/mock-cal-node-001`. With mocked API, `calibrationNode()` is no longer `null`. Template can bind to `calibrationNode()?.node_name`.

### Task 5.2 — Add Δ-pose computation and matrix expand signals

- [x] Add pure helper method `computePoseDelta(result: PendingCalibrationResult): PoseDelta`:
  ```typescript
  computePoseDelta(result: PendingCalibrationResult): PoseDelta {
    return {
      dx: result.pose_after.x - result.pose_before.x,
      dy: result.pose_after.y - result.pose_before.y,
      dz: result.pose_after.z - result.pose_before.z,
      droll: result.pose_after.roll - result.pose_before.roll,
      dpitch: result.pose_after.pitch - result.pose_before.pitch,
      dyaw: result.pose_after.yaw - result.pose_before.yaw,
    };
  }
  ```
- [x] Add `showMatrixFor = signal<Record<string, boolean>>({})` signal
- [x] Add `toggleMatrix(sensorId: string): void`:
  ```typescript
  toggleMatrix(sensorId: string): void {
    const current = this.showMatrixFor();
    this.showMatrixFor.set({ ...current, [sensorId]: !current[sensorId] });
  }
  ```
- [x] Add `pendingResultEntries` computed (to iterate over the record map in template):
  ```typescript
  pendingResultEntries = computed(() => {
    const node = this.calibrationNode();
    if (!node) return [];
    return Object.entries(node.pending_results);
  });
  ```
- [x] **Verify:** Call `computePoseDelta({ pose_before: {x:1500,...}, pose_after: {x:1502.3,...}, ... })` — confirm `dx = 2.3`.

### Task 5.3 — Add workflow action methods and wire to store

- [x] Add `triggerCalibration()` method:
  ```typescript
  async triggerCalibration(): Promise<void> {
    const nodeId = this.nodeId();
    if (!nodeId) return;
    await this.calibrationStore.triggerCalibration(nodeId, {});
  }
  ```
- [x] Add `acceptCalibration()` method (accepts all pending sensors):
  ```typescript
  async acceptCalibration(): Promise<void> {
    const nodeId = this.nodeId();
    if (!nodeId) return;
    await this.calibrationStore.acceptCalibration(nodeId, { sensor_ids: null });
  }
  ```
- [x] Add `rejectCalibration()` method:
  ```typescript
  async rejectCalibration(): Promise<void> {
    const nodeId = this.nodeId();
    if (!nodeId) return;
    await this.calibrationStore.rejectCalibration(nodeId);
  }
  ```
- [x] Add `rollbackToEntry(sensorId: string, record: CalibrationHistoryRecord)`:
  ```typescript
  async rollbackToEntry(sensorId: string, record: CalibrationHistoryRecord): Promise<void> {
    await this.calibrationStore.rollbackHistory(sensorId, record.id);
  }
  ```
- [x] Add a `ToastService` effect: in the constructor, add:
  ```typescript
  effect(() => {
    const error = this.calibrationStore.error();
    if (error) this.toast.error(error);
  });
  ```
- [x] Add store pass-throughs for loading states:
  ```typescript
  isTriggering = this.calibrationStore.isTriggering;
  isAccepting = this.calibrationStore.isAccepting;
  isRejecting = this.calibrationStore.isRejecting;
  isRollingBack = this.calibrationStore.isRollingBack;
  historyForNode = computed(() =>
    this.calibrationStore.getHistoryForNode()(this.nodeId() ?? '')
  );
  ```
- [x] **Verify:** In the template, bind `[disabled]="isTriggering()"` on the Trigger button — button disables while triggering.

### Task 5.4 — Rebuild the component template

- [x] Read the existing `calibration-viewer.component.html` in full
- [x] Rebuild the template with the following structure:

  **Header** (keep existing back-navigation, update to use `calibrationNode()?.node_name`):
  ```html
  <header>
    <syn-button variant="text" (click)="goBack()">← Back</syn-button>
    <h1>{{ calibrationNode()?.node_name ?? 'Calibration' }}</h1>
    <span class="node-id text-sm text-gray-500">{{ nodeId() }}</span>
  </header>
  ```

  **Section 1 — Node Status Card:**
  ```html
  @if (calibrationNode(); as node) {
    <section class="status-card">
      <h2>Status</h2>
      <dl>
        <dt>State</dt>
        <dd>
          @if (node.calibration_state === 'pending') {
            <syn-badge variant="warning">Pending Approval</syn-badge>
          } @else {
            <syn-badge variant="neutral">Idle</syn-badge>
          }
        </dd>
        <dt>Enabled</dt>
        <dd>{{ node.enabled ? 'Yes' : 'No' }}</dd>
        <dt>Last Calibration</dt>
        <dd>{{ node.last_calibration_time ?? '—' }}</dd>
        <dt>Buffered Frames</dt>
        <dd>
          @for (entry of node.buffered_frames | keyvalue; track entry.key) {
            <span>{{ entry.key }}: {{ entry.value }}</span>
          }
        </dd>
      </dl>
      <syn-button (click)="triggerCalibration()" [disabled]="isTriggering()">
        @if (isTriggering()) { Running... } @else { Run Calibration }
      </syn-button>
    </section>
  }
  ```

  **Section 2 — Pending Results Card** (only when `calibration_state === 'pending'`):
  ```html
  @if (calibrationNode()?.calibration_state === 'pending') {
    <section class="pending-results-card">
      <h2>Pending Results</h2>

      @for (entry of pendingResultEntries(); track entry[0]) {
        @let sensorId = entry[0];
        @let result = entry[1];
        @let delta = computePoseDelta(result);

        <div class="sensor-result">
          <h3>Sensor: {{ sensorId }}</h3>
          <div class="quality-metrics">
            <syn-badge [variant]="result.quality_good ? 'success' : 'danger'">
              {{ result.quality }}
            </syn-badge>
            <span>Fitness: {{ (result.fitness * 100).toFixed(1) }}%</span>
            <span>RMSE: {{ result.rmse.toFixed(5) }} m</span>
          </div>

          <!-- Δ-pose table -->
          <table class="delta-table">
            <thead>
              <tr>
                <th>Δx (mm)</th>
                <th>Δy (mm)</th>
                <th>Δz (mm)</th>
                <th>Δroll (°)</th>
                <th>Δpitch (°)</th>
                <th>Δyaw (°)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{{ delta.dx.toFixed(2) }}</td>
                <td>{{ delta.dy.toFixed(2) }}</td>
                <td>{{ delta.dz.toFixed(2) }}</td>
                <td>{{ delta.droll.toFixed(4) }}</td>
                <td>{{ delta.dpitch.toFixed(4) }}</td>
                <td>{{ delta.dyaw.toFixed(4) }}</td>
              </tr>
            </tbody>
          </table>

          <!-- 4×4 matrix (expandable) -->
          <syn-details summary="Show Transformation Matrix (translation in meters)">
            @if (showMatrixFor()[sensorId]) {
              <table class="matrix-table">
                @for (row of result.transformation_matrix; track $index) {
                  <tr>
                    @for (cell of row; track $index) {
                      <td class="font-mono text-xs">{{ cell.toFixed(6) }}</td>
                    }
                  </tr>
                }
              </table>
            }
            <syn-button size="small" variant="text" (click)="toggleMatrix(sensorId)">
              {{ showMatrixFor()[sensorId] ? 'Hide' : 'Show' }} Matrix
            </syn-button>
          </syn-details>
        </div>
      }

      <!-- Accept / Reject actions -->
      <div class="action-bar">
        <syn-button
          variant="filled"
          (click)="acceptCalibration()"
          [disabled]="isAccepting() || isRejecting()"
        >
          @if (isAccepting()) { Accepting... } @else { Accept Calibration }
        </syn-button>
        <syn-button
          variant="outline"
          (click)="rejectCalibration()"
          [disabled]="isAccepting() || isRejecting()"
        >
          @if (isRejecting()) { Rejecting... } @else { Reject }
        </syn-button>
      </div>
    </section>
  }
  ```

  **Section 3 — History accordion** (grouped by `source_sensor_id`):
  ```html
  <section class="history-section">
    <h2>Calibration History</h2>
    @for (record of historyForNode(); track record.id) {
      <syn-details [summary]="record.timestamp + ' — ' + (record.quality ?? 'unknown')">
        <p>Fitness: {{ ((record.fitness ?? 0) * 100).toFixed(1) }}%</p>
        <p>RMSE: {{ (record.rmse ?? 0).toFixed(5) }} m</p>
        @if (record.pose_before && record.pose_after) {
          <!-- Reuse delta display pattern from pending results -->
        }
        @if (record.accepted) {
          <syn-button
            size="small"
            variant="outline"
            (click)="rollbackToEntry(record.sensor_id, record)"
            [disabled]="isRollingBack()"
          >
            <syn-icon name="restore" slot="prefix"></syn-icon>
            @if (isRollingBack()) { Rolling back... } @else { Rollback to This }
          </syn-button>
        }
      </syn-details>
    }
  </section>
  ```

- [x] Ensure `KeyValuePipe` (from `@angular/common`) is in the component's `imports` array if using `| keyvalue`
- [x] **Verify:** Navigate to `/calibration/mock-cal-node-001` with `MOCK_CALIBRATION_STATUS_PENDING`. Confirm: status section renders, pending results section appears with Δ-pose table, Accept/Reject buttons are present and disabled while loading.

---

## Group 6: Refactor `CalibrationComponent` (List Page)

**Files:**
- `web/src/app/features/calibration/calibration.component.ts`
- `web/src/app/features/calibration/calibration.component.html`

### Task 6.1 — Replace WebSocket-derived state with polled data and add Trigger button

- [x] Read the current `.ts` file in full
- [x] Inject `CalibrationStoreService`: `private calibrationStore = inject(CalibrationStoreService)`
- [x] Remove stale WebSocket-only helper methods that are now handled by the store:
  - `hasPendingResults()` (if it reads from WebSocket directly)
  - `getPendingResultsList()`
  - `getBufferedFrameCount()` / `getBufferedFrameEntries()`
  - `formatTime()` (move to a pure function or pipe if needed elsewhere)
  - `getQualityVariant()`
- [x] Add `calibrationNodeConfigs` computed (node configs from `NodeStoreService`, NOT WebSocket):
  ```typescript
  calibrationNodeConfigs = computed(() =>
    this.nodeStore.calibrationNodes()
  );
  ```
- [x] Add `getNodeWsStatus` computed factory (lightweight: `operational_state + calibrating bool`):
  ```typescript
  getNodeWsStatus = computed(() => {
    const map = this.nodeStore.nodeStatusMap();
    return (nodeId: string) => map.get(nodeId) ?? null;
  });
  ```
- [x] Add `getNodePolledStatus` computed factory (rich: pending_results, poses):
  ```typescript
  getNodePolledStatus = computed(() => {
    const statuses = this.calibrationStore.nodeStatuses();
    return (nodeId: string): CalibrationNodeStatusResponse | null => statuses[nodeId] ?? null;
  });
  ```
- [x] In `ngOnInit()` (or via `afterNextRender` effect), start polling for all calibration node configs:
  ```typescript
  ngOnInit(): void {
    // Poll all calibration nodes on list page (usually 1–2 nodes)
    const nodes = this.calibrationNodeConfigs();
    for (const node of nodes) {
      this.calibrationStore.startPolling(node.id);
    }
  }
  ```
  - **Note:** Since `startPolling()` stops the previous poll before starting a new one, polling multiple nodes requires calling it in a loop — confirm whether `CalibrationStoreService` supports per-node polling or if a multi-node refactor is needed. If only one node can be polled at a time, start polling the first node and update on node selection.
- [x] Add `triggerCalibration(nodeId: string)` method:
  ```typescript
  async triggerCalibration(nodeId: string): Promise<void> {
    await this.calibrationStore.triggerCalibration(nodeId, {});
  }
  ```
- [x] Add `ToastService` error effect:
  ```typescript
  effect(() => {
    const error = this.calibrationStore.error();
    if (error) this.toast.error(error);
  });
  ```
- [x] **Verify:** Page loads, calibration nodes render from `calibrationNodeConfigs()`. Network tab shows 2s polling requests.

### Task 6.2 — Update list page template

- [x] Read the current template in full
- [x] For each calibration node card:
  - Replace WebSocket `calibrating` indicator with `application_state` from `getNodeWsStatus(node.id)()`
  - Replace direct WebSocket data reads with `getNodePolledStatus(node.id)()` for pending results
  - Show buffered frames from polled data: `getNodePolledStatus(node.id)()?.buffered_frames`
  - Show `calibration_state` badge from polled data
  - **Add "Run Calibration" button** per node card:
    ```html
    <syn-button
      size="small"
      (click)="triggerCalibration(node.id)"
      [disabled]="calibrationStore.isTriggering()"
    >
      Run Calibration
    </syn-button>
    ```
  - Keep "View Details →" link to `/calibration/:id`
  - Keep "View History →" link to `/calibration/:id/history`
- [x] **Verify:** List page shows node cards with status badges. "Run Calibration" button triggers the calibration API call. Polled data updates every ~2 seconds.

---

## Group 7: Update `CalibrationHistoryDetailComponent` (History Sub-Page)

**Files:**
- `web/src/app/features/calibration/components/calibration-history-detail/calibration-history-detail.component.ts`
- `web/src/app/features/calibration/components/calibration-history-detail/calibration-history-detail.component.html`
- `web/src/app/features/calibration/calibration-history/calibration-history.component.ts` *(parent)*

### Task 7.1 — Add rollback `output` and `isRollingBack` input, add Δ-pose table

- [x] Read the current `calibration-history-detail.component.ts`
- [x] Add `rollback = output<string>()` signal output (emits `record.id`)
- [x] Add `isRollingBack = input<boolean>(false)` signal input
- [x] In the template (`calibration-history-detail.component.html`), add per-entry rollback button:
  ```html
  @if (record().accepted) {
    <syn-button
      variant="outline"
      size="small"
      (click)="rollback.emit(record().id)"
      [disabled]="isRollingBack()"
    >
      <syn-icon name="restore" slot="prefix"></syn-icon>
      @if (isRollingBack()) { Rolling back... } @else { Rollback to This }
    </syn-button>
  }
  ```
- [x] Add Δ-pose table to the history detail view (when `record().pose_before && record().pose_after`):
  ```html
  @if (record().pose_before && record().pose_after) {
    <table class="delta-table text-sm">
      <caption>Pose Change</caption>
      <thead>
        <tr>
          <th>Δx (mm)</th><th>Δy (mm)</th><th>Δz (mm)</th>
          <th>Δroll (°)</th><th>Δpitch (°)</th><th>Δyaw (°)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>{{ (record().pose_after!.x - record().pose_before!.x).toFixed(2) }}</td>
          <td>{{ (record().pose_after!.y - record().pose_before!.y).toFixed(2) }}</td>
          <td>{{ (record().pose_after!.z - record().pose_before!.z).toFixed(2) }}</td>
          <td>{{ (record().pose_after!.roll - record().pose_before!.roll).toFixed(4) }}</td>
          <td>{{ (record().pose_after!.pitch - record().pose_before!.pitch).toFixed(4) }}</td>
          <td>{{ (record().pose_after!.yaw - record().pose_before!.yaw).toFixed(4) }}</td>
        </tr>
      </tbody>
    </table>
  }
  ```
- [x] **Verify:** For accepted records, Rollback button appears. For non-accepted records, button is hidden.

### Task 7.2 — Wire rollback handler in parent `CalibrationHistoryComponent`

- [x] Open `calibration-history.component.ts` (the parent/wrapper page)
- [x] Inject `CalibrationStoreService`
- [x] Add `onRollback(recordId: string, record: CalibrationHistoryRecord): void`:
  ```typescript
  async onRollback(sensorId: string, recordId: string): Promise<void> {
    await this.calibrationStore.rollbackHistory(sensorId, recordId);
  }
  ```
  - **Note:** `sensorId` comes from the record's `source_sensor_id ?? sensor_id` field
- [x] In the parent template, bind the child `rollback` output:
  ```html
  <app-calibration-history-detail
    [record]="record"
    [isRollingBack]="calibrationStore.isRollingBack()"
    (rollback)="onRollback(record.source_sensor_id ?? record.sensor_id, $event)"
  />
  ```
- [x] Add error toast effect (same pattern as other components)
- [x] **Verify:** Clicking "Rollback to This" on a history entry calls `rollbackHistory()` with the correct `sensorId` and `recordId`.

---

## Group 8: Integration, Mocking, and Routing Verification

### Task 8.1 — Create mock data file for frontend development

- [x] Create `web/src/app/core/mocks/calibration-mock.ts`
- [x] Copy mock data from `api-spec.md` section 1 into this file:
  ```typescript
  import { CalibrationNodeStatusResponse } from '@core/models/calibration.model';

  export const MOCK_CALIBRATION_STATUS_IDLE: CalibrationNodeStatusResponse = {
    node_id: 'mock-cal-node-001',
    node_name: 'ICP Calibration',
    enabled: true,
    calibration_state: 'idle',
    quality_good: null,
    reference_sensor_id: 'mock-sensor-ref',
    source_sensor_ids: ['mock-sensor-src'],
    buffered_frames: { 'mock-sensor-ref': 28, 'mock-sensor-src': 25 },
    last_calibration_time: null,
    pending_results: {}
  };

  export const MOCK_CALIBRATION_STATUS_PENDING: CalibrationNodeStatusResponse = {
    node_id: 'mock-cal-node-001',
    node_name: 'ICP Calibration',
    enabled: true,
    calibration_state: 'pending',
    quality_good: true,
    reference_sensor_id: 'mock-sensor-ref',
    source_sensor_ids: ['mock-sensor-src'],
    buffered_frames: { 'mock-sensor-ref': 28, 'mock-sensor-src': 25 },
    last_calibration_time: '2026-03-22T14:30:00.000Z',
    pending_results: {
      'mock-sensor-src': {
        fitness: 0.921,
        rmse: 0.00312,
        quality: 'excellent',
        quality_good: true,
        source_sensor_id: 'mock-sensor-src',
        processing_chain: ['mock-sensor-src', 'mock-cal-node-001'],
        pose_before: { x: 1500.0, y: -200.0, z: 0.0, roll: 0.0, pitch: 0.0, yaw: 45.0 },
        pose_after:  { x: 1502.3, y: -198.7, z: 1.1, roll: 0.12, pitch: -0.08, yaw: 45.31 },
        transformation_matrix: [
          [0.9999, -0.0054,  0.0021, 0.0023],
          [0.0054,  0.9999,  0.0008, 0.0013],
          [-0.0021, -0.0008, 1.0,    0.0000],
          [0.0,     0.0,     0.0,    1.0   ]
        ]
      }
    }
  };
  ```
- [x] In `CalibrationApiService.getNodeStatus()`, temporarily return mock data until backend Task 5.1 is complete:
  ```typescript
  // TODO: Remove mock when backend /status endpoint is live (Backend Task 5.1)
  return Promise.resolve(MOCK_CALIBRATION_STATUS_PENDING);
  ```
- [x] **Verify:** All components render correctly using mock data. Remove mock and restore real HTTP call once Backend Task 5.1 is `[x]`.

### Task 8.2 — Verify routing and lazy-loading

- [x] Open the application routing file (`app.routes.ts` or feature routing module)
- [x] Confirm these routes exist and are correctly configured:
  - `{ path: 'calibration', component: CalibrationComponent }` (list page)
  - `{ path: 'calibration/:id', component: CalibrationViewerComponent }` (detail page)
  - `{ path: 'calibration/:id/history', component: CalibrationHistoryComponent }` (history page)
- [x] Confirm the routes are loaded (lazy or eager — check what pattern the rest of the app uses)
- [x] Manually test navigation:
  1. Open `/calibration` — list page with node cards renders
  2. Click "View Details" link → navigates to `/calibration/mock-cal-node-001`
  3. Click "Back" → returns to `/calibration`
  4. Click "View History" link → navigates to `/calibration/mock-cal-node-001/history`
  5. On DAG canvas, click the nav icon on a calibration node card → navigates to the detail page
- [x] **Verify:** No routing errors in the console. Each page renders without `calibrationNode is null` errors.

---

## Completion Checklist

Before marking all tasks complete, confirm:

- [x] All `- [x]` checkboxes in Groups 1–8 are `[x]`
- [x] `ng build` passes with zero TypeScript errors
- [x] No `eslint` warnings in modified files (`ng lint` or `eslint web/src/...`) — ESLint not configured in this project; `ng build` passes with zero errors
- [ ] Mock API is removed from `CalibrationApiService.getNodeStatus()` once Backend Task 5.1 is `[x]`
- [ ] Mock API is removed from `CalibrationApiService.rollback()` once Backend Task 4.1–4.2 is `[x]`
- [x] `NodeCalibrationControls` has **zero** trigger/accept/reject action methods or buttons
- [x] `CalibrationViewerComponent.calibrationNode` is **never** `null` when navigating to a valid calibration node
- [x] Rollback button only appears on `accepted === true` history records
- [x] Δ-pose table shows mm for position, ° for angles, RMSE in meters, fitness as percent
- [x] 4×4 matrix translation column is labeled "meters" in the UI
