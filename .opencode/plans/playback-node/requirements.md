# Playback Node - Requirements Specification

## Feature Overview

The **Playback Node** is a new DAG node type that simulates sensor data by reading and replaying previously recorded point cloud data. It feeds recording data into the DAG pipeline as if it were arriving from a live sensor, enabling testing, demonstrations, and development in environments where physical sensors are unavailable or impractical.

The node integrates with the existing recording system that stores point cloud sequences as ZIP-based PCD archives (`.zip` files with sequential `frame_XXXXX.pcd` files and `metadata.json`).

## User Stories

### As a Developer
- I want to test my point cloud processing pipeline without needing physical LiDAR hardware
- I want to replay real sensor data at slower speeds so I can observe processing behavior in detail
- I want to repeatedly test the same scenario (looped playback) for debugging edge cases
- I want to select from available recordings through a simple interface

### As a QA Engineer
- I want to run repeatable test scenarios using recorded sensor data
- I want to verify pipeline behavior with known input data for regression testing
- I want to control playback speed to validate timing-sensitive operations

### As a Product Demo User
- I want to demonstrate the system's capabilities using pre-recorded data when sensors are not available
- I want to show processing results on realistic data without hardware setup

## Acceptance Criteria

### Core Functionality
- [x] Playback Node appears in the node palette/creation menu alongside other source nodes (sensors)
- [x] Users can select any available `.zip` recording file from the `recordings/` directory via dropdown
- [x] Playback starts automatically when the node is configured and the DAG is running
- [x] Point cloud frames are emitted to downstream nodes in the DAG with correct timing
- [x] The node respects the original timestamps from the recording (scaled by playback speed)
- [x] Playback uses best-effort timing (frame intervals approximate the original recording)

### Playback Speed Control
- [x] Playback speed is configurable via node settings (not real-time controls)
- [x] Supported speeds: **1.0x, 0.5x, 0.25x, 0.1x** (fixed presets)
- [x] Default playback speed is **1.0x** (real-time)
- [x] Playback speed changes require node reconfiguration (no hot-swapping during playback)
- [x] Frame timing is calculated as: `original_interval * (1 / playback_speed)`

### Loop Control
- [x] Loop mode is configurable as a boolean setting in the node configuration
- [x] When loop is **enabled**: playback restarts from frame 0 after the last frame
- [x] When loop is **disabled**: playback stops after the last frame and the node becomes idle
- [x] Default behavior is **loop disabled** (play once)

### Recording Selection
- [ ] Node configuration UI displays a dropdown list of available recordings
- [ ] Dropdown shows recording file names from the `recordings/` directory
- [ ] Recordings are discovered from the server's local filesystem at `recordings/`
- [ ] If no recordings exist, the dropdown shows "No recordings available"
- [ ] Changing the selected recording requires stopping the node first (no hot-swap during playback)

### Data Format & Compatibility
- [x] Supports the existing ZIP-based PCD archive format (`.zip` files)
- [x] Reads `metadata.json` from the recording for frame count, timestamps, and field schema
- [x] Unpacks each `frame_XXXXX.pcd` file sequentially using `RecordingReader`
- [x] Emits point cloud data with the same schema/fields as the original recording
- [x] Focus on **LiDAR point cloud recordings** (PCD format) for initial implementation

### DAG Integration
- [x] Playback Node integrates as a standard DAG source node (no upstream dependencies)
- [x] Output follows the standard pipeline payload format (`{"points": np.ndarray, "metadata": dict}`)
- [x] WebSocket streaming is enabled by default (same as sensor nodes)
- [x] Node status indicators show: `idle`, `playing`, `error`
- [x] Node can be stopped/removed like any other node

### User Access
- [ ] Playback Node is available to **all users** (no admin-only restriction)
- [ ] No additional authentication required beyond existing system access

### Error Handling
- [x] If selected recording file is missing or corrupted, show clear error in node status
- [x] If recording contains zero frames, display error and prevent playback
- [x] If PCD frame parsing fails, log error and skip to next frame (continue playback)
- [x] If playback encounters file I/O errors, transition node to error state

### UI/UX Requirements
- [ ] Node configuration panel includes:
  - Recording selector (dropdown)
  - Playback speed selector (dropdown: 1.0x, 0.5x, 0.25x, 0.1x)
  - Loop toggle (checkbox)
- [ ] Node displays current playback status: frame number, total frames, elapsed time
- [ ] Node icon/badge indicates it is a playback source (distinct from live sensors)

## Out of Scope

### Explicitly NOT Included
- ❌ Real-time playback controls (pause, stop, resume buttons during playback)
- ❌ Seek/scrubbing to specific frame positions
- ❌ Playback faster than real-time (>1.0x speed)
- ❌ Support for non-PCD recording formats (e.g., raw binary, CSV)
- ❌ Recording preview or thumbnail display in selection UI
- ❌ Multi-sensor synchronized playback (playing multiple recordings in sync)
- ❌ Remote or cloud-based recording storage (only local filesystem)
- ❌ Recording upload functionality
- ❌ Playback from external URLs or network streams
- ❌ Frame-by-frame manual stepping
- ❌ Recording editing or trimming within the playback node
- ❌ Support for non-LiDAR sensor recordings (cameras, IMU, etc.) in initial version

### Future Considerations (Not in V1)
- Support for other sensor types (camera images, IMU data) when recording format expands
- Advanced playback controls (pause, resume, seek)
- Multi-recording synchronized playback for sensor fusion testing
- Recording library UI with search, filtering, and preview thumbnails

## Open Questions for PM/Architecture Review

1. **Recording Metadata Display**: Should the node configuration UI show recording metadata (duration, frame count, recording date) before selection, or only after selection?

2. **Playback State Persistence**: If a user saves the DAG configuration with a Playback Node, should the selected recording and settings be persisted? What happens if the recording file is later deleted?

3. **Frame Rate Variability**: Real recordings may have variable frame intervals. Should we:
   - Use actual timestamps from `metadata.json` (scaled by playback speed)?
   - Calculate average FPS and use fixed intervals?

4. **End-of-Playback Behavior**: When loop is disabled and playback finishes, should the node:
   - Remain in the DAG but idle (current assumption)?
   - Automatically remove itself from the DAG?
   - Emit a completion event for downstream automation?

5. **Recording Discovery**: Should the system scan the `recordings/` directory on-demand when opening the dropdown, or cache the list and refresh periodically?

6. **Playback Priority**: Should playback timing use best-effort async delays or should it run on a dedicated thread/process for more precise timing control?

7. **WebSocket Streaming**: Should the Playback Node always stream via WebSocket (like sensors), or should this be configurable to reduce overhead during batch testing?

8. **Node Naming**: Should the node be called "Playback Node", "Recording Player", "Sensor Simulator", or something else?

## Technical Constraints

- Must reuse existing `RecordingReader` from `app/services/shared/recording.py`
- Must conform to standard DAG node interface and lifecycle
- Must integrate with existing WebSocket streaming infrastructure
- File I/O operations should run on threadpools to prevent async event loop blocking
- Recordings stored locally at `recordings/` directory (configurable via app settings)

## Dependencies

- Existing Recording System (`RecordingWriter`, `RecordingReader`, `RecordingService`)
- DAG Node Framework and Routing Service
- WebSocket Topic Management
- Node Configuration UI Components (Angular)

## Success Metrics

- Developers can test pipelines without hardware in <5 minutes
- Playback timing accuracy is within ±10% of specified speed
- System can handle playback of 100k+ point recordings at 10 FPS without frame drops
- Zero crashes or memory leaks during extended loop playback (>1 hour)

---

**Document Status**: Draft for PM/Architecture Review  
**Created**: 2026-04-19  
**Last Updated**: 2026-04-19  
**Author**: Business Analyst  
**Next Steps**: Review by @pm and @architecture, then proceed to technical design
