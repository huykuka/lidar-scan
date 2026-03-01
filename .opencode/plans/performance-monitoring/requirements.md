# Performance Monitoring & Metrics

## Feature Overview
Implement comprehensive performance monitoring for the LiDAR Standalone application, spanning backend DAG processing and frontend 3D rendering, ensuring minimal overhead and actionable developer insights through Angular dashboards and external endpoints.

## User Stories
- As a Developer, I want to monitor DAG node performance to identify and resolve bottlenecks in point cloud processing.
- As a Developer, I want real-time rendering performance metrics (frame rate, buffer times) in the frontend so I can optimize visualization for large point cloud datasets.
- As a Developer, I want access to metrics via Angular dashboards and API endpoints.
- As a Developer, I want resource usage and WebSocket protocol performance tracked for debugging and optimization.

## Acceptance Criteria

### Backend Monitoring
- [ ] Track DAG node execution time, throughput, queue depth
- [ ] Monitor Open3D operation times, point cloud sizes
- [ ] Monitor WebSocket (LIDR) message rates, payload sizes, connection status
- [ ] Track FastAPI endpoint latency and throughput
- [ ] Monitor system CPU, memory, thread pool usage
- [ ] Metrics endpoint or API for external tools (JSON)
- [ ] Collection must introduce <1% overhead

### Frontend Monitoring
- [ ] Track Three.js FPS, frame/block render times, buffer mutation timings
- [ ] Monitor Angular component/UI responsiveness
- [ ] Display real-time metrics in Angular dashboard (Synergy UI, Signal-based)
- [ ] Frontend WebSocket performance stats (frame RX, parse latency)

### Dashboard & Data Management
- [ ] Built-in Angular metrics dashboard (developer access only)
- [ ] Per-node detail and overview
- [ ] Real-time display; no historical data storage
- [ ] Low-overhead, non-blocking

### Integration & Technical
- [ ] Integrate seamlessly with FastAPI async/DAG architecture and threadpool for Open3D
- [ ] No historical/time-series retention
- [ ] No alerting or analytics beyond developer dashboard view
- [ ] Display-only: not for management or user operations

## Out of Scope
- No support for Prometheus, Grafana, external tools, or enterprise monitoring integration
- No end-user/ops management access
- No alerting, anomaly detection, or SLA compliance
- No metrics retention beyond current session
- No advanced analytics, data export, ML
