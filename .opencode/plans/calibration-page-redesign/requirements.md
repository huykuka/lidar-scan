# Calibration Page Redesign - Requirements

## Feature Overview

Redesign the ICP calibration workflow to centralize all calibration interactions, controls, and history management on a dedicated calibration page, removing action buttons from the DAG flow-canvas node cards. The DAG diagram will continue to display real-time calibration status via WebSocket (idle, running, pending, accepted, quality indicators) but all operator actions—trigger, accept, reject, rollback—will be moved exclusively to the calibration page.

Calibration history will be persisted in a new dedicated database table to support rollback to any previously accepted calibration. The calibration page will use HTTP polling (2-second interval) to refresh status, history, and detailed metrics, while the DAG diagram continues to receive lightweight WebSocket status updates for real-time visual feedback without requiring user interaction.

This redesign decouples calibration workflow control from the DAG editor, providing a cleaner separation of concerns: the DAG diagram focuses on topology and status visualization, while the calibration page provides comprehensive calibration management, detailed metrics viewing, and historical rollback capabilities.

## User Stories

### US-1: Remove Calibration Controls from DAG Node Cards
**As an operator**, I want calibration action buttons (trigger, accept, reject) removed from the DAG diagram node cards, so that the diagram remains focused on topology and real-time status visualization without cluttering the canvas with workflow controls.

**Acceptance Criteria:**
- The calibration node card on the flow-canvas displays only a status indicator showing: idle (gray), running (blue/animated), pending approval (yellow), or accepted/good quality (green).
- Status updates are received via WebSocket for real-time responsiveness.
- No trigger, accept, or reject buttons appear on the calibration node card.
- Clicking the calibration node card does NOT open calibration controls inline.
- The node card shows a visual quality indicator (color/icon) when a calibration has been accepted and is considered good quality (based on fitness/RMSE thresholds).
- Tooltip or hover state on the node card can show brief summary: "Calibration: Accepted | Fitness: 0.92 | RMSE: 0.003m" but no action buttons.

### US-2: Centralized Calibration Page with Node/Sensor Management
**As an operator**, I want a dedicated calibration page that lists all calibration nodes in the system, expandable to show their connected sensors and individual calibration status, so that I can manage calibration workflows in one centralized location.

**Acceptance Criteria:**
- The calibration page displays a list of all calibration nodes currently defined in the DAG.
- Each calibration node is expandable to reveal:
  - List of connected upstream sensor nodes
  - Current calibration status per sensor (idle, running, pending, accepted)
  - Quality metrics for each sensor's most recent calibration (fitness, RMSE)
  - Before/after pose for each sensor
- If a calibration node has no connected sensors, it shows an informational message: "No sensors connected. Add sensor nodes upstream in the DAG."
- The page refreshes calibration status, sensor list, and quality metrics via HTTP polling at a 2-second interval.
- WebSocket is NOT used on the calibration page; all data comes from polling the backend REST API.

### US-3: Calibration Actions on Dedicated Page
**As an operator**, I want to trigger, accept, reject, and rollback calibrations directly from the calibration page, so that all calibration workflow actions are performed in one place with full context and detailed feedback.

**Acceptance Criteria:**
- **Trigger Calibration:**
  - Each calibration node section has a "Trigger Calibration" button.
  - Clicking trigger initiates an ICP calibration run for all connected sensors.
  - The UI immediately reflects "running" state and polls for progress updates.
  - If no sensors are connected, the button is disabled with a tooltip: "No sensors connected."
- **Accept Pending Results:**
  - When a calibration completes, status changes to "pending approval."
  - An "Accept" button appears next to the calibration node or per-sensor.
  - Clicking accept commits the calibration, updating sensor poses permanently and recording the entry in history.
  - Status changes to "accepted" and quality indicator turns green if thresholds are met.
- **Reject Pending Results:**
  - A "Reject" button appears alongside "Accept" when results are pending.
  - Clicking reject discards the pending calibration without updating sensor poses.
  - Status returns to idle.
- **Rollback to History Entry:**
  - The calibration page includes a "History" section per calibration node or sensor.
  - Each accepted history entry has a "Rollback" action button.
  - Clicking rollback restores the sensor poses from that historical calibration entry.
  - A confirmation modal warns: "Rolling back will overwrite current calibration. Continue?"
  - After rollback, the restored calibration becomes the current accepted state and history records the rollback action.
- **View Detailed Metrics:**
  - Each calibration result (pending or accepted) has a "View Details" link or expand icon.
  - Expanding shows:
    - Full transformation applied (Δx, Δy, Δz, Δroll, Δpitch, Δyaw in a readable table)
    - Quality metrics: fitness, RMSE, inlier count
    - Registration method metadata: ICP mode (point-to-point/point-to-plane), whether global registration (FPFH+RANSAC) was used
    - Before/after pose for each sensor in tabular format
    - Timestamp of calibration run and acceptance
    - Operator who accepted (if available)

### US-4: Database-Persisted Calibration History
**As an administrator**, I want calibration history stored in a dedicated database table with complete metadata (poses before/after, transformation matrix, quality metrics, timestamps, operator), so that historical calibrations can be audited, compared, and rolled back at any time.

**Acceptance Criteria:**
- A new database table `calibration_history` is created with the following schema:
  - `id` (primary key, auto-increment)
  - `node_id` (foreign key to nodes table, the calibration node)
  - `sensor_id` (foreign key to nodes table, the sensor being calibrated)
  - `pose_before_json` (JSON column storing {x, y, z, roll, pitch, yaw} before calibration)
  - `pose_after_json` (JSON column storing {x, y, z, roll, pitch, yaw} after calibration)
  - `transform_matrix_json` (JSON column storing 4x4 transformation matrix as flat array or nested list)
  - `quality_metrics_json` (JSON column storing {fitness, rmse, inlier_count, correspondence_set_size})
  - `registration_method_json` (JSON column storing {icp_mode: "point_to_point"|"point_to_plane", global_registration_used: bool, voxel_size: float, frames_sampled: int})
  - `status` (enum: pending, accepted, rejected)
  - `triggered_at` (timestamp when calibration was started)
  - `accepted_at` (timestamp when calibration was accepted, null if pending/rejected)
  - `accepted_by` (string, operator username/ID if available, null otherwise)
  - `rollback_source_id` (nullable foreign key to another calibration_history.id if this entry was created by a rollback action)
- History entries are immutable after creation; rollback creates a new history entry copying the old one's pose_after values.
- The backend API exposes endpoints:
  - `GET /api/v1/calibration/history/{node_id}` — returns all history entries for a calibration node, sorted by triggered_at descending
  - `GET /api/v1/calibration/history/sensor/{sensor_id}` — returns history for a specific sensor
  - `POST /api/v1/calibration/rollback/{sensor_id}` — accepts a `history_entry_id` and restores that calibration
- Only accepted calibration entries are eligible for rollback.
- History is retained indefinitely (no automatic deletion) unless explicitly purged by an admin.

### US-5: Transformation Display on Results
**As an operator**, I want to see the transformation applied during calibration displayed as a pose delta (Δx, Δy, Δz, Δroll, Δpitch, Δyaw) in a readable table format, so I can quickly understand how much the sensor pose changed.

**Acceptance Criteria:**
- Calibration results (pending or accepted) display transformation as:
  - **Translation:** Δx, Δy, Δz in meters (or millimeters with unit label)
  - **Rotation:** Δroll, Δpitch, Δyaw in degrees
- Format: A compact table with two columns: "Parameter" and "Change"
  - Example:
    ```
    | Parameter | Change       |
    |-----------|--------------|
    | Δx        | +0.012 m     |
    | Δy        | -0.003 m     |
    | Δz        | +0.007 m     |
    | Δroll     | +1.2°        |
    | Δpitch    | -0.8°        |
    | Δyaw      | +2.5°        |
    ```
- The full 4x4 transformation matrix is stored in the database but not displayed by default on the UI.
- Advanced users can optionally expand a "Show Matrix" section to view the raw 4x4 matrix.
- Pose before and pose after are also displayed in separate sections for reference.

### US-6: DAG Node Status Indicator via WebSocket
**As an operator**, I want the calibration node card on the DAG diagram to show real-time status updates (idle, running, pending, accepted) via WebSocket without requiring page polling, so that I have immediate visual feedback on calibration progress while focusing on the diagram.

**Acceptance Criteria:**
- The backend publishes calibration status updates to a WebSocket topic: `/nodes/{node_id}/status`.
- Status messages include:
  - `calibration_status`: "idle" | "running" | "pending" | "accepted"
  - `quality_good`: boolean (true if fitness/RMSE meet acceptance thresholds)
- The calibration node card on the flow-canvas subscribes to this WebSocket topic.
- Status changes trigger immediate visual updates:
  - **Idle:** Gray border, no special indicator
  - **Running:** Blue border with animated pulse/spinner
  - **Pending:** Yellow/orange border, small "pending approval" badge
  - **Accepted + Good Quality:** Green border, checkmark icon
  - **Accepted + Poor Quality:** Orange border, warning icon
- No action buttons or workflow controls appear on the node card; clicking the node does NOT trigger any calibration action.
- The node card MAY provide a small "View in Calibration Page" link that navigates to the calibration page with the relevant node pre-selected.

### US-7: Rollback to Any Accepted Calibration
**As an operator**, I want to roll back to any previously accepted calibration from the history list, not just the most recent one, so that I can restore the system to a known-good state from any point in the calibration timeline.

**Acceptance Criteria:**
- The calibration history view displays ALL accepted calibration entries for a given sensor or calibration node, sorted newest to oldest.
- Each accepted entry shows:
  - Timestamp of acceptance
  - Quality metrics (fitness, RMSE)
  - Pose after calibration
  - Operator who accepted (if available)
  - "Rollback" button
- Clicking "Rollback" on any entry triggers a confirmation modal:
  - "Are you sure you want to rollback to the calibration from [timestamp]? Current poses will be overwritten."
  - User must confirm or cancel.
- On confirmation, the backend:
  - Restores sensor poses from the selected history entry.
  - Creates a new history entry recording the rollback action (with `rollback_source_id` pointing to the original entry).
  - Updates the node's current status to "accepted" with the restored quality metrics.
- The calibration page immediately reflects the rollback via the next polling cycle (2s).
- Only accepted entries are rollback-eligible; pending or rejected entries do not show a rollback button.

## Data Model: Calibration History Entry

### Database Schema (`calibration_history` table)

| Column                     | Type          | Constraints                     | Description                                                                 |
|----------------------------|---------------|---------------------------------|-----------------------------------------------------------------------------|
| `id`                       | SERIAL        | PRIMARY KEY                     | Unique history entry ID                                                     |
| `node_id`                  | VARCHAR(255)  | FOREIGN KEY (nodes.id)          | ID of the calibration node                                                  |
| `sensor_id`                | VARCHAR(255)  | FOREIGN KEY (nodes.id)          | ID of the sensor node being calibrated                                      |
| `pose_before_json`         | JSONB         | NOT NULL                        | {x, y, z, roll, pitch, yaw} before calibration                              |
| `pose_after_json`          | JSONB         | NOT NULL                        | {x, y, z, roll, pitch, yaw} after calibration                               |
| `transform_matrix_json`    | JSONB         | NOT NULL                        | 4x4 transformation matrix (flat array or nested)                            |
| `quality_metrics_json`     | JSONB         | NOT NULL                        | {fitness, rmse, inlier_count, correspondence_set_size}                      |
| `registration_method_json` | JSONB         | NOT NULL                        | {icp_mode, global_registration_used, voxel_size, frames_sampled}           |
| `status`                   | VARCHAR(20)   | NOT NULL                        | "pending", "accepted", "rejected"                                           |
| `triggered_at`             | TIMESTAMP     | NOT NULL DEFAULT NOW()          | When calibration was initiated                                              |
| `accepted_at`              | TIMESTAMP     | NULL                            | When calibration was accepted (null if pending/rejected)                    |
| `accepted_by`              | VARCHAR(255)  | NULL                            | Operator username or ID (null if not tracked)                               |
| `rollback_source_id`       | INTEGER       | NULL, FOREIGN KEY (id)          | If this entry is from a rollback, ID of the original history entry restored |

### Example History Entry JSON
```json
{
  "id": 123,
  "node_id": "calibration_node_abc123",
  "sensor_id": "sensor_front_lidar",
  "pose_before_json": {
    "x": 1.5, "y": 0.0, "z": 0.8,
    "roll": 0.0, "pitch": 0.0, "yaw": 0.0
  },
  "pose_after_json": {
    "x": 1.512, "y": -0.003, "z": 0.807,
    "roll": 1.2, "pitch": -0.8, "yaw": 2.5
  },
  "transform_matrix_json": [
    [0.9995, -0.0436, 0.0209, 0.012],
    [0.0437, 0.9990, -0.0140, -0.003],
    [-0.0207, 0.0142, 0.9997, 0.007],
    [0.0, 0.0, 0.0, 1.0]
  ],
  "quality_metrics_json": {
    "fitness": 0.92,
    "rmse": 0.003,
    "inlier_count": 45678,
    "correspondence_set_size": 50000
  },
  "registration_method_json": {
    "icp_mode": "point_to_plane",
    "global_registration_used": true,
    "voxel_size": 0.05,
    "frames_sampled": 10
  },
  "status": "accepted",
  "triggered_at": "2026-03-22T10:30:00Z",
  "accepted_at": "2026-03-22T10:32:15Z",
  "accepted_by": "operator_john",
  "rollback_source_id": null
}
```

## UI Wireframe Description (Text-Based)

### Calibration Page Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│ Calibration Management                                  [Refresh: 2s] │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│ ┌─ ICP Calibration Node #1 ──────────────────────────────────────┐   │
│ │  Status: Idle | Quality: Good (Fitness: 0.92, RMSE: 0.003m)    │   │
│ │  [Trigger Calibration]                                          │   │
│ │                                                                  │   │
│ │  Connected Sensors:                                             │   │
│ │  ┌─ Front LiDAR ──────────────────────────────────────────────┐│   │
│ │  │ Status: Accepted | Last Calibration: 2026-03-22 10:32      ││   │
│ │  │ Pose: x=1.512, y=-0.003, z=0.807, roll=1.2°, pitch=-0.8°   ││   │
│ │  │ [View Details] [History ▼]                                  ││   │
│ │  └─────────────────────────────────────────────────────────────┘│   │
│ │                                                                  │   │
│ │  ┌─ Rear LiDAR ─────────────────────────────────────────────┐  │   │
│ │  │ Status: Pending Approval ⚠                                │  │   │
│ │  │ Fitness: 0.88 | RMSE: 0.005m                              │  │   │
│ │  │ [Accept] [Reject] [View Details]                          │  │   │
│ │  └──────────────────────────────────────────────────────────┘  │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│ ┌─ ICP Calibration Node #2 ──────────────────────────────────────┐   │
│ │  Status: Idle | No sensors connected                            │   │
│ │  [Trigger Calibration] (disabled)                               │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Expanded Details View (Modal or Accordion)

```
┌────────────────────────────────────────────────────────────────────────┐
│ Calibration Details - Front LiDAR                          [Close ✕]  │
├────────────────────────────────────────────────────────────────────────┤
│ Triggered: 2026-03-22 10:30:00                                        │
│ Accepted: 2026-03-22 10:32:15 by operator_john                        │
│                                                                        │
│ ┌─ Transformation Applied ────────────────────────────────────────┐   │
│ │ ┌───────────┬──────────────┐                                    │   │
│ │ │ Parameter │ Change       │                                    │   │
│ │ ├───────────┼──────────────┤                                    │   │
│ │ │ Δx        │ +0.012 m     │                                    │   │
│ │ │ Δy        │ -0.003 m     │                                    │   │
│ │ │ Δz        │ +0.007 m     │                                    │   │
│ │ │ Δroll     │ +1.2°        │                                    │   │
│ │ │ Δpitch    │ -0.8°        │                                    │   │
│ │ │ Δyaw      │ +2.5°        │                                    │   │
│ │ └───────────┴──────────────┘                                    │   │
│ │ [Show 4x4 Matrix ▼]                                             │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│ ┌─ Quality Metrics ───────────────────────────────────────────────┐   │
│ │ Fitness: 0.92 | RMSE: 0.003 m                                   │   │
│ │ Inlier Count: 45,678 / 50,000                                   │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│ ┌─ Registration Method ──────────────────────────────────────────┐   │
│ │ ICP Mode: Point-to-Plane                                        │   │
│ │ Global Registration: FPFH + RANSAC (used)                       │   │
│ │ Voxel Size: 0.05 m | Frames Sampled: 10                        │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│ ┌─ Pose Comparison ──────────────────────────────────────────────┐   │
│ │ Before: x=1.500, y=0.000, z=0.800, roll=0.0°, pitch=0.0°       │   │
│ │ After:  x=1.512, y=-0.003, z=0.807, roll=1.2°, pitch=-0.8°     │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│                                                    [Rollback to This] │
└────────────────────────────────────────────────────────────────────────┘
```

### History View (Collapsible Section per Sensor)

```
┌─ Calibration History - Front LiDAR ────────────────────────────────┐
│ ┌─ 2026-03-22 10:32:15 (Current) ──────────────────────────────┐  │
│ │ Status: Accepted | Fitness: 0.92 | RMSE: 0.003m              │  │
│ │ Accepted by: operator_john                                    │  │
│ │ [View Details]                                                │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ┌─ 2026-03-21 14:20:00 ──────────────────────────────────────┐    │
│ │ Status: Accepted | Fitness: 0.89 | RMSE: 0.004m            │    │
│ │ Accepted by: operator_jane                                  │    │
│ │ [View Details] [Rollback to This]                           │    │
│ └────────────────────────────────────────────────────────────┘    │
│                                                                    │
│ ┌─ 2026-03-20 09:15:00 ──────────────────────────────────────┐    │
│ │ Status: Accepted | Fitness: 0.91 | RMSE: 0.003m            │    │
│ │ Accepted by: operator_john                                  │    │
│ │ [View Details] [Rollback to This]                           │    │
│ └────────────────────────────────────────────────────────────┘    │
│                                                                    │
│ [Load More...]                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### DAG Node Card (Flow-Canvas)

```
┌──────────────────────────────────┐
│   ICP Calibration Node           │
│                                  │
│   Status: ● Accepted (Good) ✓   │  ← Green status indicator
│   Fitness: 0.92 | RMSE: 0.003m   │
│                                  │
│   [View in Calibration Page →]   │  ← Optional navigation link
└──────────────────────────────────┘
```

## Open Questions

### Q1: Operator Authentication & Tracking
- **Question:** Should the system track which operator accepted/rejected calibrations? If yes, is there an existing authentication/user system to integrate with?
- **Impact:** Affects database schema (`accepted_by` column) and API design.
- **Proposed Default:** Store a generic "operator" string or leave null if no user system exists. Add full user tracking later if authentication is implemented.

### Q2: Concurrent Calibration Runs
- **Question:** Can multiple calibration nodes run simultaneously, or should the system enforce one calibration at a time?
- **Impact:** Backend concurrency model, UI blocking behavior.
- **Proposed Default:** Allow concurrent calibration runs (one per calibration node) since they operate on independent sensor sets.

### Q3: Notification on Calibration Completion
- **Question:** Should the system provide a notification (toast, sound, email) when a calibration run completes and requires operator approval?
- **Impact:** Frontend notification system design.
- **Proposed Default:** Show a browser toast notification when the calibration page detects a status change from "running" to "pending" via polling.

### Q4: Calibration Presets/Templates
- **Question:** Should operators be able to save and load calibration presets (voxel size, ICP mode, correspondence thresholds, etc.)?
- **Impact:** Additional UI and backend storage for preset configurations.
- **Proposed Default:** Out of scope for initial implementation; operators manually configure parameters each time.

### Q5: Point Cloud Visualization on Calibration Page
- **Question:** Should the calibration page include a Three.js point cloud viewer showing before/after alignment, similar to the main point cloud view?
- **Impact:** Significant frontend complexity, requires streaming point cloud data to calibration page.
- **Proposed Default:** Out of scope for initial implementation; operators can reference the main DAG visualization for point cloud inspection.

### Q6: History Retention Policy
- **Question:** Should calibration history be purged after a certain time (e.g., 90 days) or number of entries (e.g., keep only last 100 per sensor)?
- **Impact:** Database growth, history page pagination.
- **Proposed Default:** Retain all history indefinitely. Add pagination if history lists become large (e.g., 50 entries per page).

### Q7: Rejection Reason Capture
- **Question:** Should the system allow operators to enter a reason when rejecting a calibration (e.g., "Poor point cloud overlap", "Sensor moved during scan")?
- **Impact:** Database schema (`rejection_reason` column), UI modal for rejection.
- **Proposed Default:** Out of scope for initial implementation; operators can log reasons manually in external systems.

### Q8: Real-Time Progress During Calibration
- **Question:** Should the calibration page show granular progress (e.g., "Downsampling... 30%", "Running ICP... 60%") during a calibration run?
- **Impact:** Backend must emit progress updates, frontend must poll or subscribe to progress events.
- **Proposed Default:** Show only high-level status ("Running...") initially. Add granular progress in a future enhancement.

## Out of Scope

- **Point Cloud Visualization on Calibration Page:** No embedded Three.js viewer on the calibration page. Operators use the main DAG point cloud view for visual inspection.
- **Automatic Approval:** Calibrations always require explicit operator approval; no automatic acceptance based on quality thresholds.
- **Multi-Sensor Simultaneous Trigger:** Initial implementation triggers all sensors under a calibration node together. Per-sensor selective triggering is out of scope.
- **Export/Import Calibration Profiles:** No preset saving, loading, or sharing in initial version.
- **Email/SMS Notifications:** No external alerting; only in-app UI feedback and optional browser toast notifications.
- **Calibration Comparison Tool:** No side-by-side comparison of two calibrations in initial version.
- **Audit Log for All Actions:** History records accepted calibrations and rollbacks but does not log every button click or page view.
- **Multi-User Collaboration:** No real-time collaboration features (e.g., "Operator X is currently reviewing this calibration").
- **Advanced Filtering/Search in History:** No filtering by date range, quality metrics, or operator in initial version. History is displayed chronologically with pagination.
