# Frontend Implementation Tasks — WebSocket Topic Cleanup

**Feature:** `websocket-topic-cleanup`  
**Owner:** @fe-dev  
**References:**
- Requirements: `requirements.md`
- API Contract: `api-spec.md`
- Technical Architecture: `technical.md`

**Note**: This feature is primarily backend-focused. Frontend changes are minimal and mainly involve handling the proper WebSocket close notifications and UI updates.

---

## Phase 1 — WebSocket Client Response (Low Priority)

### MultiWebsocketService Improvements
- [ ] **1.1** — Verify existing `onclose` handler in `MultiWebsocketService` properly handles close code `1001`
  - **File**: `src/app/services/websocket/multi-websocket.service.ts`  
  - **Current behavior**: `socket.onclose = () => { this.connections.delete(topic); subject.complete(); }`
  - **Required**: Ensure this behavior is correct and no reconnection attempts are made for code `1001`
  - **Test**: Mock WebSocket close with code `1001` and verify `subject.complete()` is called

- [ ] **1.2** — Add close code differentiation (optional enhancement)
  - **Enhancement**: Log different close codes at different levels
  - **Implementation**: 
    ```typescript
    socket.onclose = (event) => {
      if (event.code === 1001) {
        console.info(`Topic ${topic} was removed by server`);
      } else {
        console.warn(`Connection to ${topic} closed unexpectedly: ${event.code}`);
      }
      this.connections.delete(topic);
      subject.complete();
    };
    ```

### Error State Handling  
- [ ] **1.3** — Ensure no infinite reconnection loops for intentionally closed topics
  - **Verify**: Reconnection logic (if any exists) checks close code before attempting reconnect
  - **Implementation**: Add guard in reconnection logic: `if (closeEvent.code === 1001) return; // Topic intentionally removed`

---

## Phase 2 — Topic Selector UI Updates (Medium Priority)

### Reactive Topic List
- [ ] **2.1** — Enhance topic list refresh on system status changes
  - **File**: `src/app/services/api/topic-api.service.ts`
  - **Current**: `getTopics()` method exists
  - **Enhancement**: Use Angular `effect()` to automatically refresh topics when node list changes in system status
  - **Implementation**:
    ```typescript
    private readonly systemStatus = inject(SystemStatusService);
    
    constructor() {
      effect(() => {
        const status = this.systemStatus.status();
        if (status?.nodes) {
          // Refresh topics when node list changes
          this.refreshTopics();
        }
      });
    }
    ```

- [ ] **2.2** — Update workspace topic selector to react to topic list changes
  - **File**: Topic selector component (identify specific component)
  - **Current**: Static topic list loaded once
  - **Enhancement**: Subscribe to topic list changes and update available options
  - **Implementation**: Use reactive topic service that updates when backend sends new topic list

### UI State Management
- [ ] **2.3** — Handle "topic disappeared" state in visualizer components
  - **File**: Main visualizer component that subscribes to WebSocket data
  - **Current**: Subscribes to WebSocket observable  
  - **Enhancement**: Show "Stream Disconnected" indicator when observable completes due to topic removal
  - **Implementation**: 
    ```typescript
    ngOnInit() {
      this.websocketService.connect(this.selectedTopic).subscribe({
        next: (data) => this.renderData(data),
        complete: () => this.showDisconnectedState(),
        error: (err) => this.showErrorState(err)
      });
    }
    ```

---

## Phase 3 — UX Improvements (Optional Enhancements)

### User Feedback
- [ ] **3.1** — Add toast notification when active topic disappears
  - **Library**: Use existing notification system (identify which one is used)
  - **Trigger**: When WebSocket observable completes unexpectedly
  - **Message**: "Sensor topic '{topic}' was removed during configuration update"

- [ ] **3.2** — Add visual indicator for "removed topic" state in Three.js scene
  - **File**: Three.js rendering service
  - **Implementation**: Display overlay text or change background color when data stream ends
  - **Styling**: Use consistent design system colors for disconnected state

### Automatic Recovery
- [ ] **3.3** — Add "Reconnect" button for user-initiated retry after topic removal
  - **Location**: Visualizer component when in disconnected state
  - **Behavior**: Re-fetch topic list and allow user to select new topic
  - **Implementation**: 
    ```typescript
    async reconnect() {
      await this.topicService.refreshTopics();
      this.showTopicSelector = true;
      this.disconnected = false;
    }
    ```

---

## Phase 4 — Testing & Integration

### Unit Tests
- [ ] **4.1** — Test `MultiWebsocketService` close event handling
  - **Test**: WebSocket receives close with code `1001`
  - **Assert**: Connection removed from internal Map
  - **Assert**: Observable completes (calls `subject.complete()`)
  - **Assert**: No reconnection attempt triggered

- [ ] **4.2** — Test topic selector updates on system status change
  - **Mock**: System status service with changing node list
  - **Assert**: Topic API service `getTopics()` called when nodes change
  - **Assert**: UI updates to reflect new topic list

### Integration Tests
- [ ] **4.3** — End-to-end test: Topic removal during active visualization
  - **Setup**: Connect to topic, start Three.js rendering
  - **Action**: Backend removes topic (mock or real API call)
  - **Assert**: WebSocket closes gracefully
  - **Assert**: UI shows disconnected state
  - **Assert**: No console errors or unhandled promise rejections

- [ ] **4.4** — Test topic list refresh after config reload
  - **Setup**: Load workspace with topic selector
  - **Action**: Trigger `POST /nodes/reload` (via API or mock)
  - **Assert**: Topic selector options update within 2 seconds
  - **Assert**: Removed topics no longer appear in dropdown

---

## Phase 5 — Performance & Monitoring Integration

### Dashboard Integration
- [ ] **5.1** — Ensure performance monitoring captures WebSocket cleanup metrics
  - **File**: Performance monitoring dashboard component
  - **Metrics**: WebSocket connection count, topic cleanup duration
  - **Display**: Show real-time connection count and cleanup events in admin dashboard

- [ ] **5.2** — Monitor Three.js rendering performance during topic transitions
  - **Implementation**: Capture frame rate before/after topic removal
  - **Alert**: Log warning if FPS drops significantly during cleanup
  - **Dashboard**: Include connection stability metrics in performance view

---

## Dependencies & Coordination

### Backend Coordination
- [ ] **C1** — Verify backend implements proper `1001` close code (dependency on backend Phase 1)
- [ ] **C2** — Confirm system status broadcasts include updated node list after reload (existing functionality)
- [ ] **C3** — Test frontend changes against backend implementation in development environment

### Testing Dependencies  
- [ ] **C4** — Backend testing environment must be available for integration tests
- [ ] **C5** — Mock WebSocket close events for unit tests (no backend dependency)

---

## Notes & Considerations

### Current Frontend Architecture
The existing `MultiWebsocketService` already handles WebSocket lifecycle correctly. Most requirements are already met by the current implementation.

### Minimal Change Strategy
This feature requires very few frontend changes because:
1. Existing `onclose` handler already calls `subject.complete()`
2. RxJS observables already handle completion gracefully
3. Topic list is already fetched via API calls

### Priority Guidance
- **High Priority**: Phase 1 (verify existing behavior works correctly)
- **Medium Priority**: Phase 2 (topic list updates)  
- **Low Priority**: Phases 3-5 (UX enhancements)

Most of the work is validation and testing rather than new feature development.

---

## Files to Review/Modify

| File | Change Type | Priority |
|---|---|---|
| `src/app/services/websocket/multi-websocket.service.ts` | Verify/enhance close handling | High |
| `src/app/services/api/topic-api.service.ts` | Add reactive refresh | Medium |
| Visualizer component (TBD - identify specific file) | Handle disconnected state | Medium |
| Topic selector component (TBD) | React to topic list changes | Medium |
| Performance dashboard component (TBD) | Show cleanup metrics | Low |

**Note**: Specific component file paths need to be identified based on current Angular project structure.

