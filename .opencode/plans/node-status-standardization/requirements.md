# Feature: Node Status Standardization

## Feature Overview

Refactor the entire system to implement a standardized, real-time node status reporting mechanism across all DAG nodes. Each node will broadcast structured status updates via WebSocket, enabling the Angular frontend to visualize operational state, application-specific state, and error messages in a Node-RED-inspired UI style.

This replaces the current mixed-format `get_status()` approach with a unified status schema that supports:
- Real-time operational state tracking (INITIALIZE, RUNNING, STOPPED, ERROR)
- Node-specific application state with custom labels and color indicators
- Error message propagation for debugging
- Minimal performance overhead (<1% like existing monitoring)

## User Stories

### As a system operator:
- I want to see the real-time operational state (INITIALIZE, RUNNING, STOPPED, ERROR) of each DAG node displayed as an icon in the node header, so I can quickly identify which nodes are active or failing
- I want to see node-specific application state (e.g., "connected: true", "recording: active") displayed as a colored badge in the bottom-right corner of each node (Node-RED style), so I understand the runtime condition of each node
- I want error messages to be displayed passively on the node itself without interrupting my workflow, so I can debug issues without losing context

### As a frontend developer:
- I want a standardized WebSocket message format for all node status updates, so I can build a consistent UI rendering pipeline without node-type-specific logic
- I want status updates to be sent only on state changes (not periodic polling), so the WebSocket traffic remains efficient and the UI updates are responsive

### As a backend developer:
- I want a clear status schema that every node must implement, so I can ensure consistency across all module types (sensors, operations, calibration, flow control, fusion)
- I want to reuse the existing WebSocket topic infrastructure (`system_status` topic), so we don't need to refactor the routing layer
- I want minimal performance overhead from status updates (<1%), so the DAG throughput is not impacted

## Acceptance Criteria

### Backend Requirements

#### Status Schema
- [ ] Define a new standardized status schema with the following structure:
  ```typescript
  {
    node_id: string;
    operational_state: "INITIALIZE" | "RUNNING" | "STOPPED" | "ERROR";
    application_state?: {
      label: string;       // e.g., "connected", "recording", "calibrating"
      value: any;          // e.g., true, false, "active", 42
      color?: string;      // Optional color hint: "green", "blue", "orange", "red"
    };
    error_message?: string;  // Present only when operational_state = "ERROR"
    timestamp: number;       // Unix timestamp of status update
  }
  ```

#### ModuleNode Interface
- [ ] Remove or deprecate the current `get_status()` method from `ModuleNode` base class
- [ ] Add a new abstract method `emit_status()` to `ModuleNode` that returns the standardized schema
- [ ] Ensure all nodes call `emit_status()` on state transitions (not on a timer)

#### Status Broadcasting
- [ ] Refactor `status_broadcaster.py` to collect status via the new `emit_status()` method
- [ ] Modify the `system_status` WebSocket topic payload to broadcast the new schema format:
  ```typescript
  {
    nodes: Array<NodeStatusUpdate>  // Array of new-format status objects
  }
  ```
- [ ] Remove the 0.5-second periodic broadcast loop and replace with event-driven status emission triggered by node state changes
- [ ] Implement a status aggregation service that subscribes to node status change events

#### Node Implementations (Breaking Change)
- [ ] Update **all** existing nodes to implement the new `emit_status()` schema:
  - `LidarSensor` (`app/modules/lidar/sensor.py`)
    - Operational state: `INITIALIZE` → `RUNNING` when process starts, `ERROR` on connection issues, `STOPPED` when disabled
    - Application state: `{label: "connection_status", value: "connected"|"disconnected"|"starting", color: "green"|"red"|"orange"}`
  - `CalibrationNode` (`app/modules/calibration/calibration_node.py`)
    - Operational state: `RUNNING` when enabled, `STOPPED` when disabled
    - Application state: `{label: "calibrating", value: true|false, color: "blue"|"gray"}`
  - `IfConditionNode` (`app/modules/flow_control/if_condition/node.py`)
    - Operational state: Always `RUNNING` (no background process)
    - Application state: `{label: "condition", value: "true"|"false", color: "green"|"red"}`
  - Pipeline operation nodes (`app/modules/pipeline/operation_node.py`)
    - Operational state: `RUNNING` when enabled, `STOPPED` when disabled
    - Application state: `{label: "processing", value: true|false, color: "blue"|"gray"}`
  - Fusion nodes (if applicable)
    - Operational state: `RUNNING` when enabled, `STOPPED` when disabled
    - Application state: `{label: "fusing", value: <sensor_count>, color: "blue"}`

#### WebSocket Infrastructure
- [ ] Confirm the existing `system_status` topic on the `websocket_manager` will be reused (no new topics needed)
- [ ] Ensure status updates are sent **only on state change**, not on a periodic interval
- [ ] Implement rate limiting or debouncing (max 10 updates/second per node) to prevent WebSocket flooding during rapid state transitions

### Frontend Requirements

#### Node Visualization
- [x] Display operational state as an icon in the **left side** of the node header:
  - `INITIALIZE`: ⏳ (hourglass/spinner icon)
  - `RUNNING`: ▶️ (play icon) 
  - `STOPPED`: ⏸️ (pause icon)
  - `ERROR`: ❌ (error icon with red color)
- [x] Display application state badge in the **bottom-right corner outside the node** (Node-RED style):
  - Text label + colored dot/pill indicator
  - Color derived from `application_state.color` field (fallback to gray if not specified)
  - Badge visibility: only show if `application_state` is present in status
- [x] Error messages displayed **passively** within the node body (no modal interruptions):
  - Show `error_message` text in a small red text area at the bottom of the node when `operational_state === "ERROR"`
  - Error text auto-wraps and is limited to 2 lines with ellipsis

#### WebSocket Integration
- [x] Subscribe to the `system_status` WebSocket topic on application load
- [x] Parse the new status schema format and update Angular Signal-based state management
- [x] Map `node_id` to the corresponding visual node component and trigger re-rendering on status updates
- [x] Implement UI debouncing (50ms) to batch rapid status updates and prevent excessive re-renders
- [x] Remove mock mode and connect to real backend WebSocket

#### Status Dashboard (Optional Enhancement)
- [ ] Consider adding a collapsible status panel showing all node statuses in a table/list view for debugging
- [ ] Table columns: Node ID, Name, Operational State, Application State, Last Updated

### Performance Requirements
- [ ] Status update overhead must remain **<1% of total system performance** (measured via existing performance monitoring dashboard)
- [ ] WebSocket `system_status` topic message rate must not exceed 100 messages/second during normal operation
- [ ] No blocking operations on the main event loop when emitting status updates

### Quality Assurance
- [ ] All existing unit tests pass after refactoring
- [ ] Add new unit tests for:
  - Status schema validation (backend)
  - `emit_status()` implementation for each node type
  - WebSocket status broadcasting service
  - Frontend status parsing and UI rendering
- [ ] Add integration tests for:
  - End-to-end status flow: node state change → WebSocket broadcast → UI update
  - Error state propagation and display
  - Multiple simultaneous node status updates
- [ ] Manual testing checklist:
  - Start/stop DAG → verify all nodes transition through correct operational states
  - Disconnect a LiDAR sensor → verify ERROR state + error_message displayed
  - Trigger calibration → verify application_state updates in real-time
  - Load test: Run DAG with 10+ nodes → verify <1% status overhead

### Documentation
- [ ] Update `AGENTS.md` with new status standardization workflow
- [ ] Update `.opencode/rules/backend.md` with the new `emit_status()` contract
- [ ] Update `.opencode/rules/frontend.md` with UI rendering guidelines for node status badges
- [ ] Document the status schema in API specifications
- [ ] Add inline code comments explaining the Node-RED-inspired UI pattern

## Out of Scope

### Not Included in This Feature
- **Historical status logging**: Status updates are ephemeral (real-time only). Historical tracking belongs in a separate logging/monitoring feature
- **Granular progress tracking**: No progress percentage (0-100%) for long-running operations. Operational state is binary (running vs stopped)
- **Performance metrics in status**: Execution time, throughput, memory usage belong in the existing performance monitoring dashboard, not status updates
- **Alerts or notifications**: No push notifications, email alerts, or sound effects on status changes. Only passive UI display
- **User-configurable status thresholds**: No admin panel to customize what triggers an ERROR state. Status logic is hardcoded per node type
- **Status persistence across restarts**: Status is runtime-only. Application restart clears all status (no database storage)
- **Backward compatibility**: This is a **breaking change**. The old `get_status()` format will be removed entirely
- **Gradual migration**: All nodes must be updated in a single release (no dual-format support)

## Technical Constraints

### Performance
- Status updates must not block the async FastAPI event loop
- WebSocket broadcasts must use fire-and-forget tasks (no awaiting on client send)
- Status emission must be triggered by state changes, not polling loops

### Architecture
- Reuse existing `websocket_manager` and `system_status` topic
- Maintain the DAG orchestrator's decoupled design (nodes don't call WebSocket directly)
- Status emission must be observable by the orchestrator (via callback or event bus)

### Data Integrity
- No sensitive data (credentials, file paths, user PII) in status messages (already confirmed: no security restrictions needed, but follow general best practices)
- Application state values must be JSON-serializable (no numpy arrays or binary data)

### UI/UX
- Node-RED-inspired visual style (header icon + bottom-right badge)
- No modal dialogs or interruptions for errors (passive display only)
- Color-blind friendly color palette for status indicators

## Dependencies

### Existing Systems
- WebSocket Manager (`app/services/websocket/manager.py`) - Already provides `system_status` topic
- Status Broadcaster (`app/services/status_broadcaster.py`) - Needs refactoring for new schema
- ModuleNode base class (`app/services/nodes/base_module.py`) - Needs new abstract method
- Angular DAG Visualization (frontend) - Needs UI updates for status badges

### External Libraries
- No new external dependencies required
- Uses existing FastAPI WebSocket, Angular Signals, Three.js/WebGL

## Success Metrics

### Quantitative
- 100% of DAG nodes implement the new status schema
- WebSocket status message rate < 100 msg/sec under normal load
- Status update overhead < 1% (measured via performance dashboard)
- Zero blocking operations on async event loop during status emission
- All unit/integration tests pass

### Qualitative
- Operators can identify failing nodes at a glance (< 2 seconds to spot ERROR state)
- Frontend developers report that status rendering logic is "simple and consistent"
- Backend developers report that adding status to new node types is "straightforward"
- Visual design is intuitive and matches Node-RED UX expectations

## Open Questions

### Resolved
- ✅ Status types: Operational state + application state + error messages
- ✅ Transport: WebSocket (existing `system_status` topic)
- ✅ Update frequency: On state change only
- ✅ UI display: Node-RED style (header icon + bottom-right badge)
- ✅ Error handling: Passive display (no interruptions)
- ✅ Security: No restrictions (but avoid sensitive data per best practices)
- ✅ Implementation approach: Single-phase breaking change (all nodes updated at once)
- ✅ Schema approach: New schema from scratch (not extending `get_status()`)

### To Be Decided During Implementation
- Exact color palette for operational/application states (defer to @fe-dev + @architecture)
- Icon set for operational states (play/pause/error/hourglass) — use existing Synergy UI icons or custom SVG?
- Rate limiting strategy: Per-node throttling vs global debouncing? (defer to @be-dev + @architecture)
- Status aggregation service architecture: Event bus pattern vs polling? (defer to @architecture)

## References

### Code Locations
- Current status implementation: `app/services/status_broadcaster.py`
- ModuleNode base class: `app/services/nodes/base_module.py`
- Example node implementations:
  - LidarSensor: `app/modules/lidar/sensor.py`
  - CalibrationNode: `app/modules/calibration/calibration_node.py`
  - IfConditionNode: `app/modules/flow_control/if_condition/node.py`
- WebSocket manager: `app/services/websocket/manager.py`
- Frontend DAG visualization: (to be added by @fe-dev in `technical.md`)

### Related Features
- Performance Monitoring: `.opencode/plans/performance-monitoring/` (if exists)
- WebSocket Topic Cleanup: `.opencode/plans/websocket-topic-cleanup/`
- Node Visibility Control: `.opencode/plans/node-visibility-control/`

### Architecture Rules
- Backend: `.opencode/rules/backend.md`
- Frontend: `.opencode/rules/frontend.md`
- Protocols: `.opencode/rules/protocols.md`

---

**Document Status**: ✅ Complete - Ready for @architecture to define technical implementation in `technical.md`

**Next Steps**:
1. @architecture: Review requirements and create `technical.md` with detailed backend/frontend architecture
2. @architecture: Define status schema TypeScript interfaces and Python dataclasses in `api-spec.md`
3. @be-dev + @fe-dev: Implement in parallel using `api-spec.md` as contract (frontend mocks status data initially)
4. @qa: Validate against acceptance criteria and conduct load testing
