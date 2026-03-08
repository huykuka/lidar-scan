# Multi-LiDAR Type Support - Requirements

## Feature Overview

Extend the existing single LiDAR node in the lidar-standalone DAG orchestration system to support multiple SICK LiDAR types (TiM, LMS, MRS series) with manual configuration per node. Each LiDAR node will have a dropdown interface to select the specific LiDAR model, with the backend automatically generating appropriate launch arguments based on the selection. This builds upon the SICK scan_xd reference architecture while maintaining backward compatibility with existing single-LiDAR configurations.

## User Stories

### Primary User Stories
- **As a developer**, I want to configure different SICK LiDAR types (TiM, LMS, MRS series) in individual DAG nodes so that I can process multiple sensor types within the same data processing pipeline.
- **As a system operator**, I want to select LiDAR models from a dropdown interface for each node so that I can easily configure mixed sensor setups without manual configuration file editing.
- **As an integrator**, I want existing single-LiDAR configurations to continue working unchanged so that current deployments remain operational during upgrades.

### Secondary User Stories
- **As a performance analyst**, I want point cloud data from different LiDAR types to be standardized through the LIDR protocol so that downstream processing nodes work consistently regardless of sensor type.
- **As a system administrator**, I want the backend to automatically generate correct launch arguments based on UI selections so that configuration errors are minimized.

## Acceptance Criteria

### Core Functionality
- [ ] **Multi-Type Selection**: Each LiDAR node in the DAG must provide a dropdown interface with supported SICK LiDAR models (TiM2xx, TiM5xx, TiM7xx, LMS1xx, LMS5xx, LMS1000, LMS4000, MRS1000, MRS6124, etc.)
- [x] **Backend Configuration**: Backend must automatically generate appropriate launch arguments and configuration parameters based on the selected LiDAR type from the UI
- [ ] **Point Cloud Output**: All supported LiDAR types must output standardized point cloud data via the existing LIDR WebSocket protocol
- [x] **DAG Integration**: Multi-LiDAR nodes must integrate seamlessly with the existing DAG orchestration engine without disrupting other node types

### UI/UX Requirements  
- [ ] **Dropdown Interface**: Angular dashboard must provide an intuitive dropdown selector for each LiDAR node showing available SICK models
- [ ] **Real-time Validation**: UI must validate LiDAR type selection and show connection status for each configured node
- [ ] **Configuration Persistence**: Selected LiDAR types and parameters must be saved and restored across application restarts
- [ ] **Visual Feedback**: Three.js visualization must handle point clouds from different LiDAR types with consistent rendering

### Compatibility & Integration
- [ ] **Backward Compatibility**: Existing single-LiDAR configurations and launch files must continue to work without modification
- [ ] **Standard Protocols**: All LiDAR types must use the existing LIDR binary WebSocket protocol for data streaming
- [ ] **Performance Consistency**: Multi-LiDAR support must maintain <1% performance overhead as defined in the performance monitoring requirements
- [ ] **API Consistency**: FastAPI endpoints must provide consistent interfaces regardless of the LiDAR type configured in individual nodes

### Configuration Management
- [x] **Automatic Parameter Mapping**: Backend must map UI selections to correct device-specific parameters (IP addresses, ports, scan frequencies, etc.)
- [x] **Launch Argument Generation**: System must automatically generate appropriate launch arguments based on SICK scan_xd patterns for each selected LiDAR type
- [ ] **Error Handling**: Clear error messages must be provided when LiDAR types cannot be connected or configured
- [ ] **Device Discovery**: Optional integration with existing SICK device network discovery capabilities for IP address validation

## Out of Scope

### Excluded from Initial Implementation
- **Non-SICK LiDAR Support**: Ouster, Velodyne, Livox, and other non-SICK manufacturers are explicitly out of scope for the first phase
- **Auto-Detection**: Automatic LiDAR type detection and configuration - manual configuration per node is the chosen approach
- **Runtime Switching**: Dynamic switching between LiDAR types without node reconfiguration/restart
- **Advanced Data Types**: IMU data, raw sensor data, or vendor-specific formats beyond standard point clouds
- **Hardware Synchronization**: Multi-device hardware synchronization across different LiDAR types
- **Multi-Vendor Compatibility**: Cross-manufacturer integration or unified configuration interfaces

### Technical Boundaries
- **Protocol Changes**: No modifications to the existing LIDR binary WebSocket protocol structure
- **DAG Architecture Changes**: No fundamental changes to the DAG orchestration engine beyond adding LiDAR type selection
- **Performance Monitoring Changes**: No modifications to existing performance monitoring beyond standard node metrics
- **ROS Integration**: No changes to existing ROS/ROS2 message compatibility (outside core requirements)

### UI/UX Limitations  
- **Advanced Configuration UI**: Complex per-device parameter tuning interfaces (users can manually edit configuration files if needed)
- **Multi-Device Dashboard**: Unified dashboard showing multiple LiDAR devices simultaneously (each node managed independently)
- **Real-time Diagnostics**: Advanced diagnostic interfaces beyond basic connection status

## Dependencies & Constraints

### Technical Dependencies
- Existing SICK scan_xd library and patterns as reference implementation
- Current DAG orchestration engine architecture
- LIDR WebSocket protocol specifications
- Angular 20 Signals and Standalone Components architecture
- FastAPI backend with Open3D integration

### Integration Constraints
- Must maintain existing performance requirements (<1% monitoring overhead)
- Must not disrupt existing single-LiDAR node functionality
- Must work within current Python 3.10+, FastAPI, Open3D tech stack
- Must integrate with existing Angular/Three.js frontend architecture