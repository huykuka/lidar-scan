# Node Reload Improvement - Requirements

## Feature Overview

Optimize the DAG node orchestration reload mechanism to enable fast, granular reloading of individual nodes when configuration changes occur. The current system forces a full DAG teardown and rebuild for any configuration change, causing unacceptable delays and disruption to live data streams. This feature will introduce intelligent change detection and selective node reloading to achieve sub-500ms reload times while preserving WebSocket connections and minimizing downstream impact.

## User Stories

**As a system operator**, I want to modify a node's configuration parameters and see the changes applied immediately (< 500ms), so that I can iterate quickly during system tuning without experiencing long wait times.

**As a data pipeline user**, I want configuration changes to individual nodes to not interrupt my live point cloud visualization or other unaffected nodes, so that I maintain continuity in my workflow.

**As a system integrator**, I want the DAG to automatically detect which nodes need reloading based on configuration changes, so that I don't have to manually manage complex reload dependencies or worry about unintended side effects.

**As a frontend user**, I want visual feedback when a node is reloading, so that I understand when a configuration change is being applied and when it's complete.

## Acceptance Criteria

**Change Detection & Reload Trigger:**
- [ ] User-initiated "Save" action triggers intelligent reload analysis
- [ ] System uses hash-based configuration diffing to detect which nodes changed
- [ ] Only nodes with modified configurations are flagged for reload
- [ ] Unchanged nodes continue operating without interruption

**Reload Performance:**
- [ ] Single node configuration reload completes in < 500ms
- [ ] WebSocket connections to all nodes (changed and unchanged) remain active throughout reload
- [ ] Downstream nodes automatically pause and buffer incoming data during upstream node reload
- [ ] Zero WebSocket reconnections required during reload process

**Concurrent Reload Handling:**
- [ ] If a reload is in progress, subsequent reload requests are rejected with appropriate error message
- [ ] User receives clear feedback when a reload request is rejected due to ongoing operation

**Error Handling & Resilience:**
- [ ] Reload failures are logged with detailed error information for debugging
- [ ] Failed reloads do not crash the DAG or affect unrelated nodes
- [ ] Node state after failed reload is clearly communicated to frontend

**Frontend Integration:**
- [x] Visual indicator shows reload status on affected nodes (e.g., pulsing, dimmed, loading spinner)
- [x] DAG visualization remains stable without full re-render
- [x] Frontend updates only the affected node visuals during reload

**Success Metrics:**
- [ ] Reload time < 500ms for single node configuration change (measured from save trigger to node operational)
- [ ] Zero WebSocket connection drops during reload operation
- [ ] User perceives configuration updates as "instant" compared to current full-DAG reload

## Pain Points Prioritized

1. **PRIMARY: Reload Speed** - Current full-DAG reload takes multiple seconds; target is < 500ms for single node changes
2. **SECONDARY: Connection Disruption** - WebSocket reconnections add overhead and complexity; must preserve all connections
3. **TERTIARY: Downstream Impact** - Cascading effects on connected nodes need intelligent handling (pause & buffer approach)

## Out of Scope

The following are explicitly **NOT** included in this feature:

- **Development hot code reload**: Automatic Python module reloading during development (remains manual)
- **DAG topology changes**: Adding/removing nodes or changing connection routing (separate feature)
- **Node performance optimization**: Improving the internal performance of node processing logic
- **Multi-node simultaneous reload**: Parallel reloading of multiple independent nodes (rejected as too complex for v1)

## Constraints & Expectations

**Technical Constraints:**
- Must maintain compatibility with existing LIDR WebSocket protocol
- Cannot break current DAG node API contracts
- Must work with asyncio event loop without blocking
- Open3D operations must continue running on threadpools

**User Expectations:**
- Sub-500ms perceived latency for configuration changes
- No visible interruption to point cloud rendering in Three.js frontend
- Clear visual feedback during reload process
- Graceful degradation on errors rather than system crashes

**Performance Expectations:**
- Reload overhead < 1% of normal DAG operation CPU time
- Memory footprint should not increase significantly during reload
- No data frame drops during reload for downstream nodes (buffering required)

## Open Questions for Architecture

1. **State Preservation Strategy**: Should node internal state (buffers, caches, intermediate results) be preserved across reload, or should nodes restart with clean state?

2. **Dependency Chain Handling**: If Node A feeds Node B which feeds Node C, and Node A is reloaded, should Node B/C be notified to invalidate cached data from the old Node A instance?

3. **Thread Pool Management**: When reloading nodes that run Open3D operations on threadpools, should we create new threads or reuse existing pool? What's the lifecycle?

4. **WebSocket Topic Management**: With improved WebSocket topic cleanup (existing feature), how do we ensure topic subscriptions survive node reload without duplicate subscriptions?

5. **Config Rollback Mechanism**: While auto-rollback is out of scope for v1 (only logging), should the architecture design allow for future rollback capability?

6. **Batching Strategy**: User requested rejection of concurrent reloads, but should we consider a short debounce window (e.g., 100ms) to batch rapid successive changes into a single reload operation?

## Notes

- This feature builds on existing WebSocket topic cleanup functionality (see `.opencode/plans/websocket-topic-cleanup/`)
- Frontend reload indicators should align with node status standardization efforts (see `.opencode/plans/node-status-standardization/`)
- Architecture team should consider future extensibility for topology changes and parallel reloads in later iterations
