# Frontend Implementation Tasks — ICP Flow Alignment

**Feature:** `icp-flow-alignment`  
**Owner:** @fe-dev

**References:**
- Requirements: `requirements.md`
- Architecture: `technical.md`
- API Contract: `api-spec.md`

**Architecture Context:**
This feature extends the existing `CalibrationNode` to track provenance metadata (`source_sensor_id`, `processing_chain`, `run_id`) in calibration results. **No new alignment node type is added to the DAG palette.** The frontend needs to display the enhanced calibration metadata in trigger responses, history views, and statistics dashboards.

**Dependencies:**
- Backend provenance tracking must be complete before frontend can consume new fields
- API response schemas must be stable before TypeScript model updates begin
- Mock data must include `source_sensor_id`, `processing_chain`, and `run_id` fields

---

## Phase 1 — TypeScript Models and API Adapters

**Goal:** Update frontend type definitions to match the extended calibration API contract.

### Tasks

- [x] **Extend `CalibrationSensorResult` interface** in `web/src/app/models/calibration.model.ts`
  - Add field: `source_sensor_id?: string` — leaf sensor ID (lidar_id)
  - Add field: `processing_chain: string[]` — ordered DAG path from leaf sensor to calibration node
  - Keep all existing fields unchanged (fitness, rmse, quality, pose_before, pose_after, etc.)
  - Mark new fields as optional for backward compatibility

- [x] **Extend `CalibrationTriggerResponse` interface**
  - Add field: `run_id: string` — UUID correlating multi-sensor calibration runs
  - Keep existing `results: { [sensorId: string]: CalibrationSensorResult }` unchanged

- [x] **Extend `CalibrationHistoryRecord` interface**
  - Add fields: `source_sensor_id?: string`, `processing_chain: string[]`, `run_id?: string`
  - Ensure `from_dict()` adapter handles null/undefined gracefully for backward compat

- [ ] **Update mock API responses** in `web/src/app/services/calibration-api.service.spec.ts`
  - Add mock for simple direct connection: `processing_chain = ["sensor-A"]`
  - Add mock for complex DAG: `processing_chain = ["sensor-A", "crop-node", "downsample-node"]`
  - Add mock for multi-sensor run: same `run_id` for multiple sensors

- [x] **Update API adapter service** in `web/src/app/services/calibration-api.service.ts`
  - Ensure `trigger()` method correctly parses `run_id` from response
  - Ensure `getHistory()` method passes through optional `source_sensor_id` and `run_id` query params
  - Handle HTTP 409 Conflict gracefully with user-friendly error message

### Files Modified
- `web/src/app/models/calibration.model.ts` ✓
- `web/src/app/services/calibration-api.service.ts` ✓
- `web/src/app/services/calibration-api.service.spec.ts`

---

## Phase 2 — Calibration Trigger UI Updates

**Goal:** Display enhanced calibration trigger responses with provenance metadata.

### Tasks

- [x] **Update trigger response component** in `web/src/app/components/calibration/calibration-trigger-result.component.ts`
  - Display `run_id` prominently (e.g., "Calibration Run: a3f2b1c4")
  - For each sensor result card, show:
    - Sensor ID (existing)
    - **NEW:** Source Sensor ID badge (if different from sensor ID, indicates processing chain exists)
    - **NEW:** Processing Chain visualization (e.g., "Sensor A → Crop → Downsample")
    - Fitness, RMSE, Quality (existing)
    - Pose Before / Pose After (existing)

- [x] **Add processing chain visualization component**
  - File: `web/src/app/components/calibration/processing-chain.component.ts`
  - Receives `processingChain: string[]` signal input
  - Renders as horizontal flow: `[Sensor A] → [Crop] → [Downsample] → [Calibration]`
  - Use Synergy UI chips/badges with arrow separators
  - Clicking on a node ID optionally highlights it in the DAG canvas (future enhancement)

- [ ] **Update trigger form validation**
  - Ensure `sample_frames` defaults to 5 (increased from 1 for better alignment)
  - Add tooltip explaining that higher `sample_frames` produces denser clouds for ICP

- [ ] **Handle HTTP 409 Conflict gracefully**
  - Display user-friendly message: "Calibration already running. Please wait for current run to complete."
  - Disable trigger button while run is active

### Files Created
- `web/src/app/components/calibration/processing-chain.component.ts` ✓
- `web/src/app/components/calibration/processing-chain.component.html` ✓
- `web/src/app/components/calibration/processing-chain.component.spec.ts` ✓

### Files Modified
- `web/src/app/components/calibration/calibration-trigger-result.component.ts` (updated in calibration-viewer.component.ts)
- `web/src/app/components/calibration/calibration-trigger-result.component.html` (updated in calibration-viewer.component.html)
- `web/src/app/components/calibration/calibration-trigger-form.component.ts`

---

## Phase 3 — Calibration History UI Updates

**Goal:** Display provenance metadata in calibration history tables and detail views.

### Tasks

- [ ] **Add columns to history table** in `web/src/app/components/calibration/calibration-history-table.component.ts`
  - Add column: **Source Sensor ID** (leaf sensor, may differ from sensor_id in complex DAGs)
  - Add column: **Processing Chain** (render as inline chips or badge count, e.g., "3 nodes")
  - Add column: **Run ID** (linkable — clicking filters history by that run)
  - Keep existing columns: Timestamp, Sensor ID, Fitness, RMSE, Quality, Accepted

- [ ] **Add filtering controls**
  - Add dropdown: "Filter by Source Sensor" (populated from unique `source_sensor_id` values)
  - Add input: "Filter by Run ID" (text input, searches for exact match)
  - Use Angular Signals for reactive filtering
  - Update query params when filters change: `?source_sensor_id=X&run_id=Y`

- [ ] **Update history detail view** in `calibration-history-detail.component.ts`
  - Display full processing chain as visual flow diagram (reuse `ProcessingChainComponent`)
  - Display run ID with "View all sensors in this run" link
  - Show source sensor ID prominently

- [ ] **Add "View Calibration Run" feature**
  - When user clicks on a `run_id`, navigate to filtered view showing all sensors from that run
  - Route: `/calibration/history?run_id=a3f2b1c4`
  - Display grouped results: "Calibration Run a3f2b1c4 (2 sensors)"

### Files Modified
- `web/src/app/components/calibration/calibration-history-table.component.ts`
- `web/src/app/components/calibration/calibration-history-table.component.html`
- `web/src/app/components/calibration/calibration-history-detail.component.ts`
- `web/src/app/components/calibration/calibration-history-detail.component.html`

---

## Phase 4 — Calibration Node Status Display

**Goal:** Update real-time node status display to show buffered frame counts per sensor.

### Tasks

- [ ] **Update node status component** in `web/src/app/components/dag/node-status-calibration.component.ts`
  - Change `buffered_frames: string[]` to `buffered_frames: { [sensorId: string]: number }`
  - Display as table:
    ```
    Buffered Frames:
    - Sensor A: 15 / 30
    - Sensor B: 22 / 30
    ```
  - Show visual progress bar for each sensor's buffer fill level
  - Add tooltip explaining ring-buffer behavior (oldest frames evicted when full)

- [ ] **Update pending results display**
  - Show `source_sensor_id` for each pending result
  - Show `processing_chain` as inline badge count or expanded list
  - Keep existing pending result fields (fitness, rmse, quality)

### Files Modified
- `web/src/app/components/dag/node-status-calibration.component.ts`
- `web/src/app/components/dag/node-status-calibration.component.html`

---

## Phase 5 — Accept/Reject Workflow UI

**Goal:** Update accept/reject UI to display and handle provenance metadata.

### Tasks

- [ ] **Update accept confirmation dialog** in `calibration-accept-dialog.component.ts`
  - Display `run_id` in dialog header: "Accept Calibration Run a3f2b1c4?"
  - For each sensor to be accepted, show:
    - Source sensor ID
    - Processing chain (collapsed, expandable)
    - Current pose → New pose (existing)
    - Fitness, RMSE, Quality (existing)
  - Allow selective acceptance (checkboxes per sensor)

- [ ] **Update accept response handling**
  - Parse `run_id` from `AcceptCalibrationResponse`
  - Parse `accepted: string[]` and `remaining_pending: string[]`
  - Display success message: "Accepted 2 sensors from run a3f2b1c4. 1 sensor still pending."

- [ ] **Update reject confirmation dialog**
  - Display `run_id` in dialog: "Reject Calibration Run a3f2b1c4?"
  - Warn: "This will discard results for X sensors without applying any changes."

### Files Modified
- `web/src/app/components/calibration/calibration-accept-dialog.component.ts`
- `web/src/app/components/calibration/calibration-accept-dialog.component.html`
- `web/src/app/components/calibration/calibration-reject-dialog.component.ts`

---

## Phase 6 — Statistics Dashboard Updates

**Goal:** Display aggregate statistics broken down by provenance metadata.

### Tasks

- [ ] **Add statistics breakdowns** in `calibration-statistics.component.ts`
  - Existing: `by_approval_state` (pending/accepted/rejected)
  - **NEW:** `by_source_sensor` — histogram of calibration attempts per leaf sensor
  - Display as bar chart or table

- [ ] **Add processing chain complexity metric**
  - Calculate average processing chain length: `avg_chain_length = sum(len(chain)) / count`
  - Display as: "Average processing chain length: 2.3 nodes"
  - Useful for understanding DAG complexity

- [ ] **Add run correlation view**
  - Show recent calibration runs with sensor counts: "Run a3f2b1c4: 2 sensors, all accepted"
  - Allow drilling down into a run (links to history filtered by `run_id`)

### Files Modified
- `web/src/app/components/calibration/calibration-statistics.component.ts`
- `web/src/app/components/calibration/calibration-statistics.component.html`

---

## Phase 7 — Backward Compatibility Handling

**Goal:** Ensure frontend gracefully handles legacy calibration records without new fields.

### Tasks

- [ ] **Add null-safety checks** in all components consuming provenance fields
  - Use safe navigation operator: `record.source_sensor_id ?? 'Unknown'`
  - Use default empty array: `record.processing_chain ?? []`
  - Display placeholder badge: "Legacy Record" when `run_id` is null

- [ ] **Update API mock data** to include mix of:
  - Legacy records: `source_sensor_id: null`, `processing_chain: []`, `run_id: null`
  - New records: all fields populated

- [ ] **Test history table rendering** with mixed legacy/new records
  - Legacy rows show "N/A" or "-" in new columns
  - Filtering by `source_sensor_id` excludes legacy records (or includes them as "Unknown")

### Files Modified
- All components from Phases 2-6 (add null-safety)
- `web/src/app/services/calibration-api.service.spec.ts` (add legacy mock data)

---

## Phase 8 — UI Polish and Accessibility

**Goal:** Ensure new UI elements follow Synergy UI design system and accessibility guidelines.

### Tasks

- [ ] **Apply Synergy UI components** consistently
  - Use `<syn-badge>` for sensor IDs, processing chain nodes, run IDs
  - Use `<syn-chip>` for inline processing chain visualization
  - Use `<syn-table>` for history and statistics tables
  - Use `<syn-dialog>` for accept/reject confirmations

- [ ] **Add tooltips and help text**
  - Processing chain: "Ordered list of DAG nodes from sensor to calibration"
  - Source sensor ID: "The original hardware sensor, not intermediate processing nodes"
  - Run ID: "Unique identifier correlating sensors aligned together"

- [ ] **Accessibility checks**
  - All badges have `aria-label` attributes
  - Processing chain flow is keyboard-navigable
  - Color-blind friendly: use icons/shapes, not just colors, to distinguish nodes
  - Screen reader announces: "Processing chain: Sensor A, then Crop, then Downsample"

- [ ] **Responsive design**
  - Processing chain visualization wraps gracefully on mobile
  - History table columns collapse to accordion on small screens
  - Run ID badges remain readable at all viewport sizes

### Files Modified
- All component HTML/SCSS files from Phases 2-6

---

## Phase 9 — Frontend Testing

**Goal:** Comprehensive unit and integration tests for new provenance features.

### Unit Tests

- [ ] **Model adapters** (`calibration.model.spec.ts`)
  - Test `CalibrationSensorResult` with all new fields populated
  - Test `CalibrationSensorResult` with new fields null/undefined (backward compat)
  - Test `CalibrationTriggerResponse` parsing `run_id` correctly

- [ ] **API service** (`calibration-api.service.spec.ts`)
  - Mock `trigger()` response with `run_id` and `processing_chain`
  - Mock `getHistory()` with query params: `?source_sensor_id=X&run_id=Y`
  - Mock HTTP 409 Conflict response during concurrent trigger

- [ ] **ProcessingChainComponent** (`processing-chain.component.spec.ts`)
  - Renders empty chain gracefully
  - Renders single-node chain: `[Sensor A]`
  - Renders multi-node chain with arrows: `[Sensor A] → [Crop] → [Downsample]`

### Integration Tests

- [ ] **Trigger → Review → Accept workflow**
  - Trigger calibration → verify `run_id` displayed in result card
  - Verify processing chain visualization appears
  - Accept → verify success message includes `run_id`
  - Navigate to history → verify new record has `source_sensor_id`, `processing_chain`, `run_id`

- [ ] **History filtering workflow**
  - Load history table
  - Apply "Filter by Source Sensor" → verify filtered results
  - Apply "Filter by Run ID" → verify only records from that run appear
  - Clear filters → verify all records return

- [ ] **Backward compatibility workflow**
  - Load history with mock legacy records (null new fields)
  - Verify table renders without errors
  - Verify "Legacy Record" badge appears
  - Verify filtering excludes legacy records gracefully

### Files Created
- `web/src/app/components/calibration/processing-chain.component.spec.ts`

### Files Modified
- `web/src/app/models/calibration.model.spec.ts`
- `web/src/app/services/calibration-api.service.spec.ts`
- `web/src/app/components/calibration/calibration-trigger-result.component.spec.ts`
- `web/src/app/components/calibration/calibration-history-table.component.spec.ts`

---

## Summary: Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `web/src/app/models/calibration.model.ts` | **Extend** | Add `source_sensor_id`, `processing_chain`, `run_id` to interfaces |
| `web/src/app/services/calibration-api.service.ts` | **Extend** | Pass through query params, handle 409 Conflict |
| `web/src/app/components/calibration/processing-chain.component.ts` | **Create** | New component for visualizing DAG path |
| `web/src/app/components/calibration/calibration-trigger-result.component.ts` | **Extend** | Display `run_id` and processing chain |
| `web/src/app/components/calibration/calibration-history-table.component.ts` | **Extend** | Add columns, filtering by `source_sensor_id` and `run_id` |
| `web/src/app/components/calibration/calibration-history-detail.component.ts` | **Extend** | Show full processing chain, link to run view |
| `web/src/app/components/dag/node-status-calibration.component.ts` | **Extend** | Display buffered frame counts per sensor |
| `web/src/app/components/calibration/calibration-accept-dialog.component.ts` | **Extend** | Show `run_id` in accept dialog |
| `web/src/app/components/calibration/calibration-statistics.component.ts` | **Extend** | Add breakdowns by source sensor and processing chain |

---

## Dependencies on Backend

| Backend Task Group | Frontend Dependency | Frontend Phase |
|--------------------|---------------------|----------------|
| **Group A** (Payload protocol) | Not blocking — frontend doesn't inspect payloads | N/A |
| **Group B** (Data structures) | Not blocking — internal backend concern | N/A |
| **Group C** (CalibrationNode logic) | Required before Phase 1 | Frontend can start with mock data |
| **Group D** (Database/ORM) | Required before Phase 3 (history) | Mock data sufficient for Phase 1-2 |
| **Group E** (API layer) | **BLOCKING** — Phase 1 cannot finalize until schemas stable | Wait for E1-E7 completion |
| **Group F** (Integration tests) | Required before Phase 9 (frontend integration tests) | Mock data sufficient initially |

**Recommendation:** Frontend can start Phase 1 (TypeScript models) with mock data from `api-spec.md` while backend completes Groups A-E. Phase 2-3 can proceed in parallel with backend Group F.

---

## Frontend-Specific Acceptance Criteria

- [ ] Processing chain visualization renders correctly for 1-node, 2-node, and 5+ node chains
- [ ] History table is sortable and filterable by `source_sensor_id` and `run_id`
- [ ] Legacy calibration records (pre-feature) display gracefully without errors
- [ ] HTTP 409 Conflict during concurrent triggers shows user-friendly error message
- [ ] Accept dialog allows selective acceptance of sensors from a multi-sensor run
- [ ] All new UI elements follow Synergy UI design system and accessibility guidelines
- [ ] No regression in existing calibration workflow (trigger → review → accept/reject)
