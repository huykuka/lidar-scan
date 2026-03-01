# LiDAR Standalone - Architecture & Agent Workflows

## Core Architecture & Technical Context

The `lidar-standalone` project is a high-performance Point Cloud Processing system with integrated performance monitoring.

- **Backend Stack**: Python 3.10+, FastAPI, Open3D, Asyncio.
- **Backend Architecture**: A dynamic Directed Acyclic Graph (DAG) orchestration engine mapping physical data flows entirely through decoupled, pluggable _nodes_ (Modules). Heavy Open3D operations run on threadpools to prevent blocking the async FastAPI event loop.
- **Frontend Stack**: Angular 20 (Signals, Standalone Components exclusively), Tailwind CSS, Synergy UI, Three.js.
- **Frontend Architecture**: Directly manipulates WebGL `BufferGeometry` arrays for 60FPS parsing of 100k+ dense point clouds.
- **Protocols**: Fast binary WebSocket streaming (the `LIDR` protocol) overriding standard HTTP JSON parsing for real-time sensor data.
- **Performance Monitoring**: Low-overhead (<1%) real-time metrics collection covering DAG nodes, Open3D operations, WebSocket performance, and Three.js rendering metrics with Angular dashboard visualization.

CRITICAL: When you need detailed API specifics or rules, use your Read tool on these references:

- Backend Rules: @.opencode/rules/backend.md
- Frontend Rules: @.opencode/rules/frontend.md
- Protocol Specs: @.opencode/rules/protocols.md

## Feature Tracking & Folders

Features are tracked in dedicated subdirectories located in `.opencode/plans/<feature-name>/`.
Each folder contains:

- `requirements.md`: Feature specs and acceptance criteria (BA, PM, Arch).
- `technical.md`: Technical implementation direction, DAG routing, UI logic (Arch, Devs).
- `api-spec.md`: The API contract. Frontend (`@fe-dev`) MUST mock data from this while Backend (`@be-dev`) is working.
- `backend-tasks.md` & `frontend-tasks.md`: Detailed implementation tasks per layer (Devs).
- `qa-tasks.md`: Test plans, TDD checklists, and QA specific tasks (@qa).
- `qa-report.md`: Final test report and coverage results (@qa).
  All Dev and QA agents MUST update checkboxes (`[ ]` to `[x]`) in these files as steps complete.

## Agent Responsibilities & Performance Monitoring

### Core Agent Ownership

- **@be-dev**: Backend metrics collection, DAG node instrumentation, Open3D performance tracking, WebSocket protocol metrics, `/api/metrics` endpoint implementation
- **@fe-dev**: Frontend performance metrics (Three.js FPS, Angular component responsiveness), metrics dashboard UI with Synergy UI components, WebSocket client performance tracking
- **@qa**: Performance dashboard testing, metrics accuracy validation, load testing for <1% overhead requirement, integration testing of monitoring features
- **@architecture**: Performance monitoring system design, metrics data flow architecture, integration points between frontend/backend monitoring
- **@ba & @pm**: Performance requirements definition, acceptance criteria for monitoring features, developer workflow integration

### Performance Monitoring Documentation

Performance monitoring specifications and implementation details are located in:

- `.opencode/plans/performance-monitoring/requirements.md`: Feature requirements and acceptance criteria
- `.opencode/plans/performance-monitoring/technical.md`: Architecture and implementation details
- `.opencode/plans/performance-monitoring/api-spec.md`: Metrics API contracts and data schemas
- `.opencode/plans/performance-monitoring/backend-tasks.md`: Backend implementation tasks and progress
- `.opencode/plans/performance-monitoring/frontend-tasks.md`: Frontend dashboard and metrics tasks

### Performance Monitoring Integration in SDLC

#### Planning Phase

1. **@ba/@pm**: Define performance requirements and acceptance criteria in `requirements.md`
2. **@architecture**: Design monitoring architecture, data collection points, and dashboard integration in `technical.md`
3. **@architecture**: Define metrics API contracts in `api-spec.md`

#### Development Phase

1. **@be-dev**: Implement backend metrics collection following tasks in `backend-tasks.md`
2. **@fe-dev**: Build Angular dashboard and frontend metrics using specifications in `frontend-tasks.md`
3. Both devs MUST mock API data per `api-spec.md` during parallel development

#### QA & Review Phase

1. **@qa**: Validate metrics accuracy, dashboard functionality, and performance overhead requirements
2. **@qa**: Conduct load testing to ensure <1% performance impact
3. **@review**: Code review focusing on monitoring integration and performance impact
4. **@docs**: Update documentation to reflect monitoring capabilities and usage

### Observable Artifacts & Commands

#### Backend Monitoring Endpoints

- `GET /api/metrics` - Real-time system metrics (JSON)
- `GET /api/metrics/dag` - DAG node performance data
- `GET /api/metrics/websocket` - WebSocket protocol performance
- `GET /api/health/performance` - Performance health check

#### Frontend Dashboard Access

- `/dashboard/performance` - Developer performance monitoring dashboard
- Real-time metrics visualization using Angular Signals and Synergy UI
- Three.js rendering performance, WebSocket client metrics, Angular component responsiveness

#### Development Commands

- `npm run dev:monitor` - Start development with performance monitoring enabled
- `python -m app.main --enable-metrics` - Backend with metrics collection
- Performance monitoring logs available in console/dev tools for debugging

## Project Structure

```text
lidar-standalone/
├── .opencode/           # OpenCode Agent workflows, rules, and task tracking
│   ├── agents/          # Agent instructions (e.g., pm, ba, orchestrator)
│   ├── plans/           # Feature planning and subtask breakdown directories
│   └── rules/           # Technology specific rules (frontend, backend, protocols)
├── app/                 # Backend codebase (Python, FastAPI, Open3D)
│   ├── api/             # API routes
│   ├── core/            # Core logic, configurations
│   ├── models/          # DB & domain models
│   ├── services/        # Business logic and DAG modules
│   └── main.py          # Application entrypoint
├── web/                 # Frontend codebase (Angular 20, Three.js, Tailwind CSS)
│   ├── public/          # Static assets
│   ├── src/             # Application source and UI components
│   └── angular.json     # Angular CLI configuration
├── tests/               # Python backend tests
├── scripts/             # Useful build and run scripts
├── requirements.txt     # Python dependencies
└── AGENTS.md            # This file
```
