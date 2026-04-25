# Snapshot Node - Requirements Specification

## Feature Overview

The **Snapshot Node** is a new flow control module that enables external HTTP-triggered capture and forwarding of point cloud data within the DAG pipeline. Located in `app/modules/flow_control/snapshot/`, this node allows users to programmatically capture the latest upstream point cloud via a POST API endpoint and immediately forward it downstream to connected nodes.

**Key Characteristics:**
- **Trigger-Based**: Only forwards point clouds when triggered via HTTP POST (rising edge behavior)
- **Stateless**: Captures and forwards immediately without persistence
- **Invisible**: No WebSocket streaming topic (flow control role)
- **Standard Output**: Single output port for downstream connections
- **Node-Level Throttling**: Configurable rate limiting per instance

## Business Context

This node addresses the need for external systems (automation scripts, test harnesses, third-party integrations) to programmatically control when specific point cloud snapshots are captured and processed through the DAG pipeline. Unlike continuous streaming nodes, the Snapshot Node gives precise, event-driven control over data flow.

**Use Cases:**
- Manual snapshot capture during system calibration
- Test automation triggering specific capture sequences
- External event-driven data collection (e.g., trigger on sensor alarm)
- Debugging specific pipeline states by capturing known data points

## User Stories

**As a** system integrator,  
**I want** to trigger point cloud snapshots via HTTP API,  
**So that** I can synchronize LiDAR data capture with external events in my automation workflow.

**As a** QA engineer,  
**I want** to programmatically trigger snapshots during automated tests,  
**So that** I can verify pipeline behavior under controlled conditions.

**As a** developer,  
**I want** the snapshot node to respect throttle limits,  
**So that** I can prevent resource exhaustion from rapid trigger requests.

**As an** operator,  
**I want** clear error responses when no data is available,  
**So that** I can detect and handle timing issues in my integration.

**As a** frontend user,  
**I want** to see the Snapshot Node's throttle value and API trigger endpoint in the detail card,  
**So that** I can easily copy the endpoint URL for external system integration without searching through documentation.

## Acceptance Criteria

### Core Functionality
- [x] Node is implemented in `app/modules/flow_control/snapshot/` module
- [x] Node extends `ModuleNode` base class following DAG integration patterns
- [x] Node accepts standard upstream DAG connections
- [x] Node provides single output port for downstream connections
- [x] Node is invisible (no WebSocket streaming topic, `_ws_topic = None`)

### HTTP Trigger API
- [x] Endpoint: `POST /api/v1/nodes/{node_id}/trigger`
- [x] No authentication required (open endpoint)
- [x] Returns HTTP 200 OK on successful trigger
- [x] Response body is simple success confirmation (JSON: `{"status": "ok"}`)
- [x] Returns HTTP 404 Not Found when no upstream data is available yet
- [x] Returns HTTP 400 Bad Request for invalid node_id
- [x] Returns HTTP 409 Conflict if trigger arrives while prior snapshot is processing (drop new trigger)

### Snapshot Behavior
- [x] Captures the **most recent** upstream point cloud at the moment of POST trigger
- [x] Immediately forwards captured snapshot to all connected downstream nodes
- [x] Does **NOT** forward upstream data continuously (only on trigger)
- [x] Does **NOT** persist snapshot to disk or database (pass-through only)
- [x] Snapshot forwarding follows standard DAG pipeline (via `manager.forward_data()`)

### Rate Limiting & Throttling
- [x] Node accepts `throttle_ms` configuration parameter (default: 0 = no limit)
- [x] When `throttle_ms > 0`, enforces minimum interval between successful triggers
- [x] Triggers within throttle window are **dropped** (return HTTP 429 Too Many Requests)
- [x] Throttle state is per-node instance (not global)

### Concurrency Handling
- [x] Maintains processing flag to detect concurrent trigger attempts
- [x] If trigger arrives while previous snapshot is processing, **drop** new trigger (HTTP 409)
- [x] Processing flag is cleared after successful forward or error

### Status & Notifications
- [x] Calls `notify_status_change(self.id)` after each successful snapshot
- [x] Implements `emit_status()` returning `NodeStatusUpdate`
- [x] Operational state mapping:
  - `RUNNING`: Normal operation (whether triggered or idle)
  - `ERROR`: If last trigger resulted in error
- [x] Optional application state showing:
  - Last trigger timestamp
  - Snapshot count
  - Color indicator (blue = recent trigger <5s, gray = idle)

### Error Handling
- [x] Logs all errors with context (node_id, error type, timestamp)
- [x] Returns appropriate HTTP status codes:
  - 404: No upstream data available
  - 400: Invalid node_id or malformed request
  - 409: Trigger dropped due to concurrent processing
  - 429: Trigger dropped due to throttle limit
  - 500: Internal processing error
- [x] Error responses include JSON body with error details
- [x] Errors increment internal error counter
- [x] Node remains operational after errors (no crash)

### Integration & Standards
- [x] Follows existing flow_control module patterns (IfConditionNode, OutputNode)
- [x] Registered in `app/modules/flow_control/registry.py`
- [x] Compatible with DAG serialization/deserialization
- [x] Works with NodeManager orchestration (routing, forwarding, status)
- [x] Async/await patterns for non-blocking operation
- [x] Uses `app.core.logging.get_logger()` for consistent logging

### Frontend UI (Node Detail Card)
- [ ] Snapshot Node has a dedicated detail card component when selected/clicked
- [ ] Detail card displays throttle value (`throttle_ms`) as an **editable** numeric input field (FormControl)
- [ ] Throttle input accepts numeric values with validation (min: 0, step: 10)
- [ ] Detail card shows the HTTP POST trigger endpoint constructed using `environment.apiUrl` and `nodeId`
- [ ] API endpoint format: `${environment.apiUrl}/nodes/${nodeId}/trigger` (same pattern as IfCondition node)
- [ ] API endpoint is displayed in a readonly input field (consistent with If node UX)
- [ ] Copy button next to the API endpoint for easy clipboard copy
- [ ] Copy action shows success toast notification: "URL copied to clipboard"
- [ ] Detail card is only visible **after** node is saved (has a valid node_id)
- [ ] Before saving, placeholder text shows: "Available after saving the node."
- [ ] Node visibility in pipeline is **always visible** regardless of attachment state
- [ ] No manual trigger button (copy-only functionality)
- [ ] Help text explains throttle: "Minimum interval between snapshot triggers (milliseconds)"

## Out of Scope

The following are **explicitly excluded** from this feature:

- ❌ **Authentication/Authorization**: No API key, JWT, or access control (open endpoint for internal use)
- ❌ **Snapshot Persistence**: No saving to disk, database, or cloud storage
- ❌ **WebSocket Streaming**: No real-time point cloud broadcasting on WebSocket topics
- ❌ **Queue Management**: No retry logic, queuing, or background processing of failed snapshots
- ❌ **Response Metadata**: API returns simple 200 OK, not detailed snapshot metadata (point count, timestamp, etc.)
- ❌ **Dual Output Ports**: Single output only (no conditional routing like IfConditionNode)
- ❌ **Global Rate Limiting**: Throttle is per-node instance only, not system-wide
- ❌ **Async Processing**: Snapshot capture and forward is synchronous (blocking endpoint until complete)
- ❌ **Snapshot History**: No tracking or retrieval of previous snapshots
- ❌ **WebSocket Trigger**: HTTP POST only; no WebSocket command support
- ❌ **Pipeline/Graph Inline Display**: Throttle and API endpoint NOT shown inline in the pipeline graph (detail card only)
- ❌ **Manual Trigger Button**: No "Trigger Now" button in UI (API-only triggering)
- ❌ **Advanced Status Display**: No real-time trigger counts, processing times, or visual indicators (future work)

## Dependencies & Constraints

**Backend Dependencies:**
- FastAPI for HTTP endpoint
- NodeManager for DAG integration
- ModuleNode base class
- Status aggregator service
- Open3D point cloud types (via upstream nodes)

**Performance Constraints:**
- Snapshot operation must not block other DAG nodes (use asyncio properly)
- Heavy point cloud operations should use threadpools if needed
- Target <100ms trigger response time for typical point clouds (<100k points)

**Compatibility:**
- Must work with existing DAG serialization format
- Must integrate with existing node status monitoring
- Must follow LIDR protocol standards for point cloud data format

## Success Metrics

- HTTP trigger endpoint responds successfully within 100ms (95th percentile)
- Zero crashes or deadlocks under concurrent trigger attempts
- Throttle limits prevent >X triggers/second as configured
- Error rate <1% under normal operating conditions
- Node integrates seamlessly with existing DAG pipeline without breaking changes

## Future Considerations

While out of scope for this initial implementation, the following may be considered for future iterations:

- Authentication layer for production deployments
- Snapshot metadata in API response (timestamp, point count, processing time)
- Persistent snapshot storage with retrieval API
- Frontend Angular component for manual triggering and configuration
- WebSocket-based trigger commands
- Snapshot history and replay functionality
- Advanced queuing and retry mechanisms
- Integration with external event systems (webhooks, pub/sub)
