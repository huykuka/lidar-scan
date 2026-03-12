# Requirements Specification — Node Visibility Control

**Feature:** `node-visibility-control`  
**Author:** @ba, @pm  
**Date:** 2026-03-12  
**Priority:** Medium  
**Status:** Approved for Implementation

---

## Feature Overview

Add a `visible` boolean field at the node level to control whether point clouds are displayed in the frontend and streamed via WebSocket. When a node is set to invisible, it stops WebSocket data transmission, unregisters its topic (integrating with the existing topic cleanup system), and removes its point cloud from the Three.js rendering scene. This provides developers with granular control over which sensor data is actively visualized without affecting data recording capabilities.

## User Stories

### Primary User Stories

**As a** LiDAR system developer  
**I want** to hide specific sensor nodes from the visualization  
**So that** I can focus on data from particular sensors without visual clutter

**As a** system operator  
**I want** to temporarily disable data streaming from certain nodes  
**So that** I can reduce network traffic and improve performance for critical sensors

**As a** frontend user  
**I want** invisible nodes to disappear from topic selectors and Three.js scene  
**So that** I only see and interact with actively visualized data streams

**As a** configuration manager  
**I want** node visibility state to persist across system restarts  
**So that** my workspace setup is maintained between sessions

### Edge Case Stories

**As a** system under concurrent operations  
**I want** visibility changes to be applied immediately without blocking other operations  
**So that** I can rapidly toggle multiple nodes for debugging

**As a** system administrator  
**I want** system-critical topics to remain protected from visibility changes  
**So that** essential monitoring and status information is always available

---

## Acceptance Criteria

### Core Functionality

- [ ] **AC1**: New nodes are created with `visible: true` by default
- [ ] **AC2**: Setting `visible: false` on a node stops WebSocket data streaming for that node's topic
- [ ] **AC3**: Setting `visible: false` unregisters the node's WebSocket topic using the existing cleanup system
- [ ] **AC4**: Setting `visible: true` on an invisible node re-registers its WebSocket topic and resumes streaming
- [ ] **AC5**: Invisible nodes are removed from the Three.js rendering scene completely
- [ ] **AC6**: Invisible nodes are hidden from frontend topic selector dropdowns

### API Integration

- [ ] **AC7**: Node creation/update API endpoints accept `visible` field in request body
- [ ] **AC8**: `GET /api/v1/nodes` includes `visible` field in response for each node
- [ ] **AC9**: `PUT /api/v1/nodes/{node_id}` allows updating only the `visible` field without affecting other properties
- [ ] **AC10**: System topics (e.g., `system_status`) cannot have their visibility changed (return 400 Bad Request)

### UI Integration

- [ ] **AC11**: Frontend UI displays eye icon toggle buttons for each node
- [ ] **AC12**: Toggling visibility in UI immediately updates the display and backend state
- [ ] **AC13**: UI visually indicates invisible nodes (grayed out in lists) when visibility controls are shown
- [ ] **AC14**: UI updates complete within 100ms, full system changes within 1 second

### Persistence & Configuration

- [ ] **AC15**: Visibility state is stored in the database and persists across system restarts
- [ ] **AC16**: DAG configuration reloads maintain existing visibility state for unchanged nodes
- [ ] **AC17**: Imported DAG configurations preserve any `visible` field values from the config file
- [ ] **AC18**: Exported DAG configurations include current visibility state for each node

### Integration with Existing Systems

- [ ] **AC19**: Invisible nodes continue to record data if the recording system is active
- [ ] **AC20**: WebSocket topic cleanup system properly handles visibility state changes
- [ ] **AC21**: Performance monitoring tracks visibility toggle operations and their impact
- [ ] **AC22**: All existing functionality (data processing, recording, metrics) remains unaffected for invisible nodes

### Performance & Reliability

- [ ] **AC23**: Visibility changes complete within 1 second for up to 50 concurrent nodes
- [ ] **AC24**: Multiple rapid visibility toggles on the same node are handled gracefully
- [ ] **AC25**: System remains responsive during batch visibility operations
- [ ] **AC26**: Memory usage returns to baseline after visibility state changes (no leaks)

---

## Out of Scope

### Explicitly Not Included

- **Granular visibility states**: Only boolean visible/invisible, no partial visibility or opacity controls
- **Layer-based visibility**: No grouping of nodes into visibility layers or categories
- **Conditional visibility**: No automatic visibility based on data quality, performance, or other metrics
- **Historical visibility**: No tracking of visibility change history or audit logs
- **Multi-user visibility**: Visibility state is global, not per-user or per-session
- **Visibility-based access control**: No security implications, purely a display feature
- **Data processing impact**: Invisible nodes continue all backend processing operations

### Future Considerations

- **Visibility groups**: Allow grouping nodes for batch visibility control
- **Conditional visibility**: Auto-hide nodes based on data quality or error states
- **User-specific visibility**: Per-user workspace configurations
- **Advanced rendering states**: Support for wireframe, point size, or color modifications
- **Visibility presets**: Save/load visibility configurations for different workflows

---

## Dependencies & Assumptions

### Technical Dependencies

- Existing WebSocket topic cleanup system must be functional
- Database schema supports adding boolean columns to node records
- Frontend Three.js rendering system supports dynamic scene object management
- Backend DAG orchestrator supports conditional topic registration

### Business Assumptions

- Developers are comfortable with immediate visibility changes without confirmation dialogs
- Recording operations should continue regardless of visibility (data integrity priority)
- System topics require protection to maintain monitoring capabilities
- 1-second response time is acceptable for complete visibility state changes

### Integration Assumptions

- WebSocket `ConnectionManager` can handle dynamic topic registration/unregistration
- Frontend `MultiWebsocketService` correctly handles topic removal notifications
- Three.js scene management supports efficient object addition/removal
- Database supports atomic visibility updates without affecting other node properties

---

## Success Metrics

### Functional Metrics

- **State Consistency**: 100% of visibility state changes reflected correctly in UI, database, and WebSocket topics
- **Performance Impact**: <5% increase in toggle response time compared to baseline UI operations
- **Reliability**: 0 cases of invisible nodes still streaming data or visible nodes missing data

### User Experience Metrics

- **UI Responsiveness**: Visibility toggles complete visual update within 100ms
- **System Responsiveness**: Complete visibility change (backend + frontend + WebSocket) within 1 second
- **Error Rate**: <1% failed visibility change operations under normal load

### Integration Metrics

- **Topic Cleanup**: 100% of invisible node topics properly unregistered from WebSocket system
- **Data Integrity**: 100% of invisible nodes continue recording when recording system is active
- **Configuration Persistence**: 100% of visibility state maintained across system restarts and reloads

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| WebSocket topic cleanup integration failure | High | Low | Comprehensive testing with existing cleanup system |
| Database visibility updates cause node corruption | High | Low | Atomic updates with rollback capability |
| Three.js scene removal causes memory leaks | Medium | Medium | Proper cleanup testing and monitoring |
| Performance degradation during batch visibility changes | Medium | Low | Async processing and batching optimization |

### Business Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| User confusion about invisible vs deleted nodes | Medium | Medium | Clear UI indicators and documentation |
| Accidental hiding of critical system monitoring | High | Low | System topic protection and warnings |
| Increased complexity for new developers | Low | High | Comprehensive documentation and examples |

---

## Acceptance & Sign-off

- [ ] **Business Analyst**: Requirements complete and testable
- [ ] **Product Manager**: Aligns with developer workflow priorities  
- [ ] **Architecture**: Technical approach integrates cleanly with existing systems
- [ ] **QA**: Acceptance criteria are measurable and comprehensive
- [ ] **DevOps**: Performance requirements are achievable

**Final Approval**: Ready for technical specification and implementation planning