# Node WebSocket Streaming Flag - Requirements

## Overview

Add a per-node-type capability flag (`websocket_enabled`) that controls whether a node supports WebSocket streaming and related UI controls. This flag is hardcoded per backend plugin, exposed via the `/nodes/definitions` API, and consumed by the Angular frontend to conditionally show/hide visibility toggle, recording controls, and streaming-related UI elements.

## Business Requirements

### Problem Statement

Currently, all nodes display visibility toggle and recording controls in the flow canvas UI, even though not all node types produce streamable point cloud output. This creates confusion for users who see these controls on nodes like:
- **Flow control nodes** (if_condition) - conditional routing logic, no data output
- **Calibration nodes** - only compute transformations, no continuous streaming
- **Operation nodes without outputs** - terminal nodes that don't forward data

Only nodes that actually produce 3D point cloud outputs (sensors, fusion, transform operations) should expose streaming and recording capabilities.

### Acceptance Criteria

**Backend:**
- [x] Each `NodeDefinition` in backend registries specifies `websocket_enabled: bool` (default: `True` for backward compatibility)
- [x] Sensor nodes (`lidar/registry.py`) → `websocket_enabled: True`
- [x] Fusion nodes (`fusion/registry.py`) → `websocket_enabled: True`
- [x] Transform/filter operation nodes (`pipeline/registry.py`) → `websocket_enabled: True`
- [x] Calibration nodes (`calibration/registry.py`) → `websocket_enabled: False`
- [x] Flow control nodes (`flow_control/if_condition/registry.py`) → `websocket_enabled: False`
- [x] The `/api/v1/nodes/definitions` endpoint returns `websocket_enabled` in each definition
- [x] No user-facing API to toggle this flag (it's a static per-type property)

**Frontend:**
- [ ] Angular `NodeDefinition` model includes `websocket_enabled: boolean` field
- [ ] The `flow-canvas-node.component` hides visibility toggle when `websocket_enabled === false`
- [ ] The `flow-canvas-node.component` hides recording controls when `websocket_enabled === false`
- [ ] Nodes with `websocket_enabled: false` still support enable/disable and configuration editing
- [ ] The palette/node listing correctly displays all node types regardless of streaming capability

**QA:**
- [x] Backend unit tests validate `websocket_enabled` field exists in all node definitions
- [ ] Frontend unit tests verify UI elements are hidden/shown based on `websocket_enabled`
- [ ] E2E test: Create calibration node → verify no visibility/recording controls shown
- [ ] E2E test: Create sensor node → verify visibility/recording controls are shown

## Out of Scope

- User-configurable streaming settings (this is a static per-type flag)
- Changing the actual WebSocket streaming behavior (only affects UI visibility)
- Migration logic for existing nodes (the flag defaults to `true`, maintaining current behavior)

## User Workflows

### Current State (Before)
1. User adds a calibration or flow control node to the canvas
2. User sees visibility toggle and recording controls
3. User clicks recording → nothing happens (node has no output stream)
4. User confusion: "Why can't I record from this node?"

### Desired State (After)
1. User adds a calibration or flow control node to the canvas
2. UI shows only enable/disable toggle and settings icon
3. No visibility toggle or recording controls visible
4. User understands node doesn't produce streamable output
5. User adds a sensor node → sees all controls as expected

## Technical Constraints

- Must maintain backward compatibility with existing node configurations
- Default value of `websocket_enabled: True` ensures unknown node types show controls (safe default)
- Field is **read-only** from frontend perspective (no PUT endpoint needed)
- Must not break existing WebSocket subscription logic for streaming nodes

## Success Metrics

- Zero regression in existing streaming behavior for sensor/fusion/operation nodes
- Reduction in support questions about "why can't I record from calibration node?"
- Cleaner, less cluttered UI for non-streaming nodes
