# Requirements Specification — WebSocket Topic Cleanup

**Feature:** `websocket-topic-cleanup`  
**Author:** @ba, @pm  
**Date:** 2026-03-08  
**Priority:** High  
**Status:** Approved for Implementation

---

## 1. Business Problem Statement

### Current Issue
When LiDAR system configuration is reloaded (removing sensor nodes), WebSocket clients remain connected to "ghost" topics that no longer have active data producers. This creates poor user experience and potential system instability:

1. **Frontend Impact**: Visualizer workspace shows dead topics in the selector, leading to confusion
2. **Resource Impact**: Server maintains unnecessary WebSocket connections and memory objects
3. **Developer Impact**: Config changes require manual client refresh to see accurate topic list

### Business Impact
- **User Experience**: Developers get confused by stale topics in the workspace UI
- **System Reliability**: Memory growth from unclosed connections affects long-running sessions  
- **Development Velocity**: Manual workarounds slow down sensor configuration workflows

---

## 2. Feature Requirements

### 2.1 Core Functional Requirements

- [ ] **R1**: When a sensor node is removed from configuration, all WebSocket clients connected to that node's topic MUST receive a proper connection close notification
- [ ] **R2**: The `/api/v1/topics` endpoint MUST only return topics that have active producing nodes behind them
- [ ] **R3**: Configuration reload operations MUST clean up any "orphaned" topics from previous failed initialization attempts
- [ ] **R4**: WebSocket close notifications MUST use standard protocol codes so clients can distinguish between network errors and intentional disconnection

### 2.2 Performance Requirements

- [ ] **R5**: Configuration reload operations MUST complete without blocking the main event loop (remain responsive to other requests)
- [ ] **R6**: Memory usage MUST return to baseline levels after reload cycles (no resource leaks)
- [ ] **R7**: WebSocket cleanup for removed topics MUST complete within 5 seconds for up to 100 concurrent connections

### 2.3 Reliability Requirements

- [ ] **R8**: Concurrent configuration reload requests MUST be handled safely without race conditions or data corruption
- [ ] **R9**: If topic removal occurs while a client is waiting for data (capture API), the client MUST receive appropriate error response (503, not timeout)
- [ ] **R10**: System MUST remain stable and functional even if individual WebSocket close operations fail

---

## 3. User Stories

### 3.1 Primary User Stories

**As a** LiDAR system developer  
**I want** removed sensor topics to disappear immediately from the workspace UI  
**So that** I don't accidentally try to visualize data from disconnected sensors

**As a** system administrator  
**I want** configuration changes to clean up all associated resources automatically  
**So that** the system doesn't accumulate memory leaks during development cycles

**As a** frontend application  
**I want** WebSocket connections to close gracefully when topics are removed  
**So that** I can show appropriate "disconnected" status instead of hanging indefinitely

### 3.2 Edge Case Stories

**As a** system under load  
**I want** concurrent configuration requests to be handled safely  
**So that** rapid development iterations don't corrupt system state

**As a** client making capture requests  
**I want** clear error messages when topics disappear during my request  
**So that** I can retry or handle the situation appropriately

---

## 4. Acceptance Criteria

### 4.1 Primary Acceptance Criteria

- [ ] **AC1**: After `POST /nodes/reload` removes a node, `GET /topics` no longer lists that node's topic
- [ ] **AC2**: WebSocket clients connected to a removed topic receive close event with code 1001 ("Going Away")
- [ ] **AC3**: `POST /nodes/reload` responds within 10 seconds even with 50+ active WebSocket connections
- [ ] **AC4**: Configuration import with `merge: false` automatically triggers topic cleanup
- [ ] **AC5**: System performance monitoring shows no memory growth over 10 consecutive reload cycles

### 4.2 Error Handling Acceptance Criteria

- [ ] **AC6**: Concurrent `POST /nodes/reload` requests return 409 Conflict for the second request
- [ ] **AC7**: `GET /topics/capture` returns 503 (not 504) if topic is removed while waiting for data
- [ ] **AC8**: Individual WebSocket close failures don't prevent cleanup of other connections on the same topic

### 4.3 Integration Acceptance Criteria

- [ ] **AC9**: Frontend workspace topic selector updates immediately after reload without manual refresh
- [ ] **AC10**: Performance monitoring dashboard shows cleanup operation metrics
- [ ] **AC11**: All existing functionality (node creation, data streaming, Three.js rendering) remains unaffected

---

## 5. Out of Scope

### 5.1 Explicitly Not Included
- **Automatic reconnection**: Clients must manually resubscribe to topics after reload
- **Topic migration**: Data from old topics is not transferred to new topics during reload  
- **Graceful degradation**: No partial functionality during reload - system stops and restarts
- **Custom close codes**: Uses standard WebSocket close codes only
- **Retroactive cleanup**: Only affects topics after this fix is implemented

### 5.2 Future Considerations
- **Hot reload**: Seamless config updates without stopping data flow
- **Topic versioning**: Maintain client connections across node updates
- **Persistent subscriptions**: Remember client topic preferences across reloads

---

## 6. Dependencies & Assumptions

### 6.1 Technical Dependencies
- Backend must implement proper async/await patterns for WebSocket cleanup
- Frontend `MultiWebsocketService` must handle WebSocket close events correctly
- Database schema supports node deletion operations

### 6.2 Business Assumptions
- Developers are comfortable with occasional connection interruptions during config changes
- 5-second cleanup time is acceptable for development workflows
- System status topic and other "system" topics should never be cleaned up

---

## 7. Success Metrics

### 7.1 Functional Metrics
- **Topic Accuracy**: 100% of listed topics have active producers
- **Cleanup Completeness**: 0 orphaned topics remain after reload
- **Response Time**: Config reload completes in <10 seconds

### 7.2 Quality Metrics  
- **Memory Stability**: No memory growth over 20 reload cycles
- **Error Rate**: <1% WebSocket close operation failures
- **User Experience**: No manual refresh required after config changes

### 7.3 Performance Metrics
- **Event Loop**: No blocking operations >100ms during reload
- **Concurrent Safety**: 0 race conditions in stress testing
- **Resource Usage**: Connection count decreases proportionally with removed topics

---

## 8. Rollout Plan

### 8.1 Implementation Phases
1. **Phase 1**: Backend ConnectionManager async cleanup implementation
2. **Phase 2**: Node lifecycle management async promotion  
3. **Phase 3**: API endpoint updates and error handling
4. **Phase 4**: Integration testing and performance validation
5. **Phase 5**: Frontend integration and UX verification

### 8.2 Testing Strategy
- **Unit Testing**: 95%+ coverage on modified backend components
- **Integration Testing**: Full reload cycle with real WebSocket clients
- **Load Testing**: 100 concurrent connections during cleanup
- **Regression Testing**: All existing functionality preserved

### 8.3 Release Criteria
- [ ] All acceptance criteria verified in test environment
- [ ] Performance metrics meet requirements under load
- [ ] Integration tests pass with real frontend clients
- [ ] Documentation updated for new async patterns
- [ ] Code review approved by architecture team

---

## 9. Risk Assessment

### 9.1 Technical Risks
| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Async conversion breaks existing sync callers | High | Low | Maintain backward compatibility shims |
| WebSocket close failures cascade to other connections | Medium | Medium | Individual error handling per connection |
| Memory leaks from incomplete cleanup | High | Low | Comprehensive testing and monitoring |

### 9.2 Business Risks  
| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Development workflow disruption | Medium | Low | Phased rollout with developer feedback |
| Increased complexity for maintenance | Medium | Medium | Comprehensive documentation and tests |

---

## 10. Approval & Sign-off

- [ ] **Business Analyst**: Requirements complete and testable
- [ ] **Product Manager**: Aligns with development workflow priorities  
- [ ] **Architecture**: Technical approach is sound and scalable
- [ ] **QA**: Acceptance criteria are measurable and comprehensive
- [ ] **DevOps**: Performance and reliability requirements are achievable

**Final Approval**: Ready for backend development to begin

