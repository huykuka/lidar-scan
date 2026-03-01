# LiDAR Standalone - Architecture & Agent Workflows

## Core Architecture & Technical Context

The `lidar-standalone` project is a high-performance Point Cloud Processing system.

- **Backend Stack**: Python 3.10+, FastAPI, Open3D, Asyncio.
- **Backend Architecture**: A dynamic Directed Acyclic Graph (DAG) orchestration engine mapping physical data flows entirely through decoupled, pluggable _nodes_ (Modules). Heavy Open3D operations run on threadpools to prevent blocking the async FastAPI event loop.
- **Frontend Stack**: Angular 20 (Signals, Standalone Components exclusively), Tailwind CSS, Synergy UI, Three.js.
- **Frontend Architecture**: Directly manipulates WebGL `BufferGeometry` arrays for 60FPS parsing of 100k+ dense point clouds.
- **Protocols**: Fast binary WebSocket streaming (the `LIDR` protocol) overriding standard HTTP JSON parsing for real-time sensor data.

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
  All Dev and QA agents MUST update checkboxes (`[ ]` to `[x]`) in these files as steps complete.

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
